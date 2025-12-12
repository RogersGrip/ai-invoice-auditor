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
    
    if fname in processing_files: 
        return
        
    processing_files.add(fname)
    logger.info(f"🚀 Starting Workflow for: {fname} (ID: {task_id})")
    
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

    try:
        if not graph_app:
            logger.error("Graph not initialized!")
            return

        final_state = await asyncio.wait_for(
            graph_app.ainvoke(initial_state, config=config),
            timeout=60.0
        )
        logger.info(f"🏁 Workflow Finished | {fname} | Status: {final_state.get('status')}")
        
    except asyncio.TimeoutError:
        logger.error(f"⏱️ Workflow Timed Out (60s) | {fname}")
        try:
            shutil.move(file_path, str(FAILED_DIR / fname))
        except: pass

    except Exception as e:
        logger.error(f"❌ Workflow Critical Failure | {fname} | Error: {e}")
        try:
            shutil.move(file_path, str(FAILED_DIR / fname))
        except: pass
            
    finally:
        if fname in processing_files:
            processing_files.remove(fname)


async def monitor_loop():
    logger.info("📂 Invoice Monitor Started (Async)...")
    while True:
        try:
            jobs = monitor_agent.scan()
            for job in jobs:
                fpath = job.get("file_path")
                fname = os.path.basename(fpath)
                
                if not os.path.exists(fpath): continue
                if fname in processing_files: continue
                
                logger.info(f"♻️  Found new file: {fname}")
                asyncio.create_task(run_workflow_async(fname, fpath))
            
            await asyncio.sleep(5)
        except asyncio.CancelledError: break
        except Exception: await asyncio.sleep(5)

@asynccontextmanager
async def lifespan(app: FastAPI):
    global graph_app, monitor_task
    graph_app = create_invoice_graph()
    logger.info("✅ Orchestrator Graph Initialized")
    monitor_task = asyncio.create_task(monitor_loop())
    yield
    logger.info("Shutting down...")
    if monitor_task: monitor_task.cancel()

app = FastAPI(title="AI Invoice Auditor A2A Server", version="1.0.0", lifespan=lifespan)

@app.post("/v1/message:send", response_model=SendMessageResponse)
async def send_message(request: SendMessageRequest, background_tasks: BackgroundTasks):
    msg = request.message
    context_id = msg.contextId or str(uuid.uuid4())
    
    # 1. File Trigger
    tasks_created = []
    for part in msg.parts:
        if part.file:
            task_id = part.file.name
            fname = part.file.name
            if fname.endswith(".meta.json"): continue
            
            input_file = str(settings.INVOICE_WATCH_DIR / fname)
            if part.file.fileWithUri and part.file.fileWithUri.startswith("file://"):
                input_file = part.file.fileWithUri.replace("file://", "")
                
            if not os.path.exists(input_file): await asyncio.sleep(1) 
            
            if fname in processing_files:
                tasks_created.append(task_id)
                continue
                
            processing_files.add(fname)
            background_tasks.add_task(run_workflow_async, task_id, input_file)
            tasks_created.append(task_id)

    if tasks_created:
        return SendMessageResponse(task=Task(id=tasks_created[0], contextId=context_id, status=TaskStatus(state=TaskState.SUBMITTED)))

    # 2. RAG
    input_text = next((p.text for p in msg.parts if p.text), None)
    if input_text:
        try:
            from src.workflows.rag_graph import create_rag_graph
            rag = create_rag_graph()
            res = await rag.ainvoke({"query": input_text})
            
            # FIXED: Safe access to response fields to prevent 500 Error
            answer = res.get("answer") or "I could not generate an answer based on the retrieved documents."
            eval_metrics = res.get("evaluation") or {}
            
            full_text = f"{answer}\n\nMetrics: {eval_metrics}"
            
            return SendMessageResponse(message=Message(
                messageId=str(uuid.uuid4()),
                role=Role.AGENT,
                contextId=context_id,
                parts=[Part(text=full_text)]
            ))
        except Exception as e:
            logger.error(f"RAG Error: {e}")
            # Return error as message instead of crashing
            return SendMessageResponse(message=Message(
                messageId=str(uuid.uuid4()),
                role=Role.AGENT,
                contextId=context_id,
                parts=[Part(text=f"System Error: {str(e)}")]
            ))

    return SendMessageResponse(message=Message(messageId=str(uuid.uuid4()), role=Role.AGENT, parts=[Part(text="Request received.")]))

@app.post("/v1/approve")
async def approve_invoice(payload: dict = Body(...)):
    file_name = payload.get("file_name")
    comment = payload.get("comment", "Manual Approval")
    if not file_name: raise HTTPException(400, "file_name required")
    base = Path(file_name).stem
    report_path = settings.OUTPUT_DIR / f"{base}_report.json"
    
    if not report_path.exists():
        candidates = list(settings.OUTPUT_DIR.glob(f"*{base}*_report.json"))
        if candidates: report_path = candidates[0]
        else: raise HTTPException(404, "Report not found")
        
    try:
        with open(report_path, 'r') as f: data = json.load(f)
        data['meta']['status'] = "APPROVED"
        data['meta']['approval_comment'] = comment
        data['meta']['approval_timestamp'] = datetime.now().isoformat()
        with open(report_path, 'w') as f: json.dump(data, f, indent=2)
        logger.info(f"✅ Manually Approved: {file_name}")
        return {"status": "success", "message": f"Approved {file_name}"}
    except Exception as e:
        raise HTTPException(500, str(e))

@app.get("/health")
def health(): return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run("src.server:app", host="0.0.0.0", port=8000, reload=False)