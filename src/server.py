# ===== FILE: src/server.py =====
import uvicorn
import uuid
import os
import json
import asyncio
import shutil
import nest_asyncio
from fastapi import FastAPI, HTTPException, BackgroundTasks, Body
from contextlib import asynccontextmanager
from typing import Set
from pathlib import Path
from datetime import datetime

from src.core.protocol import (
    SendMessageRequest, SendMessageResponse, Task, AgentCard,
    Message, Role, TaskState, TaskStatus, Part
)
from src.core.logger import logger, setup_logger
from src.core.state import InvoiceState, ProcessingStatus
from src.workflows.graph import create_invoice_graph
from src.core.config import settings
from src.adk_agents.monitor_agent import InvoiceMonitorAgent

# Apply Asyncio Patch
nest_asyncio.apply()
setup_logger()

# Global State
graph_app = None
monitor_agent = InvoiceMonitorAgent()
processing_files: Set[str] = set()
monitor_task = None

# Ensure Failed Dir exists
FAILED_DIR = settings.DATA_DIR / "failed"
FAILED_DIR.mkdir(exist_ok=True)

async def run_workflow_async(task_id: str, file_path: str):
    """
    Core processing logic for a single file.
    """
    fname = os.path.basename(file_path)
    
    # 1. Deduplication check (In-memory only)
    if fname in processing_files: 
        return
        
    processing_files.add(fname)
    logger.info(f"🚀 Starting Workflow for: {fname} (ID: {task_id})")
    
    # 2. Setup State
    config = {"configurable": {"thread_id": task_id}}
    metadata = {"source": "monitor"}
    try:
        meta_path = Path(file_path).with_suffix(".meta.json")
        if meta_path.exists():
            with open(meta_path, "r") as f:
                metadata.update(json.load(f))
    except Exception: pass

    initial_state = InvoiceState(
        file_path=str(file_path),
        file_name=fname,
        metadata=metadata,
        current_step="start",
        status=ProcessingStatus.PENDING
    )

    # 3. Run Graph
    try:
        if not graph_app:
            logger.error("Graph not initialized!")
            return

        # Execute Async
        final_state = await graph_app.ainvoke(initial_state, config=config)
        logger.info(f"🏁 Workflow Finished | {fname} | Status: {final_state.get('status')}")
        
    except Exception as e:
        logger.error(f"❌ Workflow Critical Failure | {fname} | Error: {e}")
        # Move to failed to prevent infinite loop
        try:
            shutil.move(file_path, str(FAILED_DIR / fname))
            logger.warning(f"Moved {fname} to failed folder.")
        except Exception as mv_err:
            logger.error(f"Failed to move poison file: {mv_err}")
            
    finally:
        if fname in processing_files:
            processing_files.remove(fname)


async def monitor_loop():
    """
    Async Monitor Loop running on the main event loop.
    """
    logger.info("📂 Invoice Monitor Started (Async)...")
    logger.info(f"Watching: {monitor_agent.watch_dir.resolve()}")
    
    while True:
        try:
            # 1. Scan for new files
            jobs = monitor_agent.scan()
            
            if jobs:
                # Debug logging for internal state
                if processing_files:
                    logger.info(f"⏳ Currently processing: {list(processing_files)}")
            
            for job in jobs:
                fpath = job.get("file_path")
                fname = os.path.basename(fpath)
                
                # Check existence
                if not os.path.exists(fpath): 
                    continue
                
                # Check In-Progress
                if fname in processing_files:
                    continue
                
                logger.info(f"♻️  Processing found file: {fname}")
                asyncio.create_task(run_workflow_async(fname, fpath))
            
            await asyncio.sleep(5)
            
        except asyncio.CancelledError:
            logger.info("Monitor loop cancelled.")
            break
        except Exception as e:
            logger.error(f"Monitor Loop Error: {e}")
            await asyncio.sleep(5)

@asynccontextmanager
async def lifespan(app: FastAPI):
    global graph_app, monitor_task
    
    # Initialize Graph
    graph_app = create_invoice_graph()
    logger.info("✅ Orchestrator Graph Initialized")
    
    # Start Monitor
    monitor_task = asyncio.create_task(monitor_loop())
    
    yield
    
    # Shutdown
    logger.info("Shutting down...")
    if monitor_task:
        monitor_task.cancel()
        try:
            await monitor_task
        except asyncio.CancelledError:
            pass

app = FastAPI(title="AI Invoice Auditor A2A Server", version="1.0.0", lifespan=lifespan)

@app.post("/v1/message:send", response_model=SendMessageResponse)
async def send_message(request: SendMessageRequest, background_tasks: BackgroundTasks):
    msg = request.message
    context_id = msg.contextId or str(uuid.uuid4())
    
    # 1. Handle File Trigger
    tasks_created = []
    for part in msg.parts:
        if part.file:
            task_id = part.file.name
            fname = part.file.name
            if fname.endswith(".meta.json"): continue
            
            if part.file.fileWithUri and part.file.fileWithUri.startswith("file://"):
                input_file = part.file.fileWithUri.replace("file://", "")
            else:
                input_file = str(settings.INVOICE_WATCH_DIR / fname)
            
            if not os.path.exists(input_file):
                await asyncio.sleep(1) 
            
            if fname in processing_files:
                tasks_created.append(task_id)
                continue
                
            processing_files.add(fname)
            background_tasks.add_task(run_workflow_async, task_id, input_file)
            tasks_created.append(task_id)

    if tasks_created:
        return SendMessageResponse(task=Task(id=tasks_created[0], contextId=context_id, status=TaskStatus(state=TaskState.SUBMITTED)))

    # 2. Handle RAG
    input_text = next((p.text for p in msg.parts if p.text), None)
    if input_text:
        try:
            from src.workflows.rag_graph import create_rag_graph
            rag = create_rag_graph()
            res = await rag.ainvoke({"query": input_text})
            
            return SendMessageResponse(message=Message(
                messageId=str(uuid.uuid4()),
                role=Role.AGENT,
                contextId=context_id,
                parts=[Part(text=res.get("answer", "No answer.") + "\n\n" + str(res.get("evaluation", "")))]
            ))
        except Exception as e:
            logger.error(f"RAG Error: {e}")
            raise HTTPException(status_code=500, detail=f"RAG Error: {e}")

    return SendMessageResponse(message=Message(
        messageId=str(uuid.uuid4()),
        role=Role.AGENT,
        parts=[Part(text="Request received.")]
    ))

# --- HITL Approval Endpoint ---
@app.post("/v1/approve")
async def approve_invoice(payload: dict = Body(...)):
    """
    Manually approves an invoice report.
    Payload: {"file_name": "...", "comment": "..."}
    """
    file_name = payload.get("file_name")
    comment = payload.get("comment", "Manual Approval")
    
    if not file_name: raise HTTPException(400, "file_name required")
    
    # Try finding the report (might be simple name or timestamped name)
    # We look for any report ending with this stem
    base = Path(file_name).stem
    report_path = settings.OUTPUT_DIR / f"{base}_report.json"
    
    if not report_path.exists():
        # Fallback: search for partial match
        candidates = list(settings.OUTPUT_DIR.glob(f"*{base}*_report.json"))
        if candidates:
            report_path = candidates[0]
        else:
            raise HTTPException(404, "Report not found")
        
    try:
        with open(report_path, 'r') as f:
            data = json.load(f)
        
        # Update Status
        data['meta']['status'] = "APPROVED"
        data['meta']['approval_comment'] = comment
        data['meta']['approval_timestamp'] = datetime.now().isoformat()
        
        with open(report_path, 'w') as f:
            json.dump(data, f, indent=2)
            
        logger.info(f"✅ Manually Approved: {file_name}")
        return {"status": "success", "message": f"Approved {file_name}"}
    except Exception as e:
        logger.error(f"Approval Failed: {e}")
        raise HTTPException(500, str(e))

@app.get("/health")
def health():
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run("src.server:app", host="0.0.0.0", port=8000, reload=True)