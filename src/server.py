import uvicorn
import uuid
import os
import json
import asyncio
import shutil
import nest_asyncio
from fastapi import FastAPI, HTTPException, BackgroundTasks, Body
from contextlib import asynccontextmanager
from typing import Set, List
from pathlib import Path
from datetime import datetime, timezone

# --- STRICT A2A IMPORTS ---
from a2a.types import (
    SendMessageRequest,
    SendMessageResponse,
    Task,
    AgentCard,
    Message,
    TaskStatus,
    TaskState,
    Part,
    TextPart,
    FilePart,
    Role
)

from src.core.logger import logger, setup_logger
from src.core.state import InvoiceState, ProcessingStatus
from src.workflows.graph import create_invoice_graph
from src.core.config import settings
from src.adk_agents.monitor_agent import InvoiceMonitorAgent

nest_asyncio.apply()
setup_logger()

graph_app = None
monitor_agent = InvoiceMonitorAgent()
processing_files: Set[str] = set()
monitor_task = None

FAILED_DIR = settings.DATA_DIR / "failed"
FAILED_DIR.mkdir(exist_ok=True)

async def run_workflow_async(task_id: str, file_path: str):
    """
    Runs the LangGraph workflow in the background.
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
    except Exception:
        pass

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
            timeout=120.0
        )
        logger.info(f"🏁 Workflow Finished | {fname} | Status: {final_state.get('status')}")

    except asyncio.TimeoutError:
        logger.error(f"⏱️ Workflow Timed Out (120s) | {fname}")
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
                # Generate a unique task ID for this file
                task_id = str(uuid.uuid4())
                asyncio.create_task(run_workflow_async(task_id, fpath))
            
            await asyncio.sleep(5)
        except asyncio.CancelledError:
            break
        except Exception:
            await asyncio.sleep(5)

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
    msg = request.params.message
    context_id = msg.context_id or str(uuid.uuid4())
    
    tasks_created = []

    # 1. Check for File Parts (Upload Triggers)
    for part in msg.parts:
        # A2A 'part' has a 'root' attribute which holds the actual content (TextPart, FilePart, etc.)
        content = part.root 

        if isinstance(content, FilePart):
            task_id = content.name
            fname = content.name
            
            if fname.endswith(".meta.json"): continue

            input_file = str(settings.INVOICE_WATCH_DIR / fname)
            
            # Handle URI logic if provided
            if content.file_with_uri and content.file_with_uri.startswith("file://"):
                input_file = content.file_with_uri.replace("file://", "")
            
            if not os.path.exists(input_file):
                await asyncio.sleep(1) # Slight buffer for FS sync

            if fname in processing_files:
                tasks_created.append(task_id)
                continue
            
            processing_files.add(fname)
            background_tasks.add_task(run_workflow_async, task_id, input_file)
            tasks_created.append(task_id)

    # If we created async tasks (file uploads), return immediate acknowledgment
    if tasks_created:
        return SendMessageResponse(
            task=Task(
                id=tasks_created[0],
                context_id=context_id,
                status=TaskStatus(state=TaskState.submitted, timestamp=datetime.now(timezone.utc).isoformat())
            )
        )

    # 2. Check for Text Parts (Chat/RAG Triggers)
    input_text = next((p.root.text for p in msg.parts if isinstance(p.root, TextPart)), None)
    
    if input_text:
        try:
            from src.workflows.rag_graph import create_rag_graph
            rag = create_rag_graph()
            
            # Run RAG Sync (or await if async supported in graph)
            res = await rag.ainvoke({"query": input_text})
            
            answer = res.get("answer") or "I could not generate an answer based on the retrieved documents."
            eval_metrics = res.get("evaluation") or {}
            
            full_text = f"{answer}\n\nMetrics: {eval_metrics}"
            
            return SendMessageResponse(
                message=Message(
                    id=str(uuid.uuid4()),
                    role=Role.agent,
                    context_id=context_id,
                    parts=[Part(root=TextPart(text=full_text))]
                )
            )
        except Exception as e:
            logger.error(f"RAG Error: {e}")
            return SendMessageResponse(
                message=Message(
                    id=str(uuid.uuid4()),
                    role=Role.agent,
                    context_id=context_id,
                    parts=[Part(root=TextPart(text=f"System Error: {str(e)}"))]
                )
            )

    # Default fallback
    return SendMessageResponse(
        message=Message(
            id=str(uuid.uuid4()), 
            role=Role.agent, 
            parts=[Part(root=TextPart(text="Request received."))]
        )
    )

@app.post("/v1/approve")
async def approve_invoice(payload: dict = Body(...)):
    """
    Human-in-the-Loop Endpoint.
    """
    file_name = payload.get("file_name")
    comment = payload.get("comment", "Manual Approval")

    if not file_name: raise HTTPException(400, "file_name required")

    base = Path(file_name).stem
    report_path = settings.OUTPUT_DIR / f"{base}_report.json"

    if not report_path.exists():
        # Fuzzy search for report
        candidates = list(settings.OUTPUT_DIR.glob(f"*{base}*_report.json"))
        if candidates: report_path = candidates[0]
        else: raise HTTPException(404, "Report not found")

    try:
        with open(report_path, 'r') as f:
            data = json.load(f)
        
        # HITL Update Logic
        data['meta']['status'] = "APPROVED"
        data['meta']['approval_comment'] = comment
        data['meta']['approval_timestamp'] = datetime.now().isoformat()
        
        with open(report_path, 'w') as f:
            json.dump(data, f, indent=2)

        logger.info(f"✅ Manually Approved: {file_name}")
        return {"status": "success", "message": f"Approved {file_name}"}

    except Exception as e:
        raise HTTPException(500, str(e))

@app.get("/health")
def health():
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run("src.server:app", host="0.0.0.0", port=8000, reload=False)