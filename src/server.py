import uvicorn
import uuid
import os
import json
import asyncio
import nest_asyncio
from fastapi import FastAPI, HTTPException, BackgroundTasks, Body
from contextlib import asynccontextmanager
from pathlib import Path
from datetime import datetime
from typing import Dict, Set
from pydantic import BaseModel

from src.core.logger import logger, setup_logger
from src.core.state import InvoiceState, ProcessingStatus, ApprovalInfo
from src.workflows.graph import create_invoice_graph
from src.workflows.rag_graph import create_rag_graph
from src.core.config import settings
from src.adk_agents.monitor_agent import InvoiceMonitorAgent

nest_asyncio.apply()
setup_logger()

graph_app = None
rag_app = None
monitor_agent = InvoiceMonitorAgent()

# Track active threads
processing_threads: Dict[str, str] = {}
processing_files: Set[str] = set()

# --- Simple Pydantic Models for UI Interaction ---
class ChatRequest(BaseModel):
    query: str

class FileUploadRequest(BaseModel):
    file_path: str
    file_type: str = "application/pdf"

@asynccontextmanager
async def lifespan(app: FastAPI):
    global graph_app, rag_app
    logger.info(">>> Initializing AI Invoice Auditor Orchestrator...")
    graph_app = create_invoice_graph()
    rag_app = create_rag_graph()
    
    # Start the monitor loop in the background
    monitor_task = asyncio.create_task(monitor_loop())
    yield
    monitor_task.cancel()
    logger.info(">>> Shutting down Orchestrator...")

app = FastAPI(title="AI Invoice Auditor", version="1.0.0", lifespan=lifespan)

async def monitor_loop():
    logger.info("Monitoring Watch Folder...")
    while True:
        try:
            jobs = monitor_agent.scan()
            for job in jobs:
                fpath = job.get("file_path")
                fname = os.path.basename(fpath)
                
                # Simple check to avoid re-processing same file in this runtime
                if fname in processing_files:
                    continue
                
                logger.info(f"Detected new file: {fname}")
                processing_files.add(fname)
                asyncio.create_task(process_file(fname, fpath))
            
            await asyncio.sleep(5)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Monitor Loop Error: {e}")
            await asyncio.sleep(5)

async def process_file(file_name: str, file_path: str):
    thread_id = f"thread_{uuid.uuid4()}"
    processing_threads[file_name] = thread_id
    config = {"configurable": {"thread_id": thread_id}}
    
    state = InvoiceState(
        file_path=file_path,
        file_name=file_name,
        metadata={"source": "monitor", "ingest_timestamp": datetime.now().isoformat()}
    )
    
    logger.info(f"Starting Workflow [Thread: {thread_id}] for {file_name}")
    try:
        async for event in graph_app.astream(state, config=config):
            pass
            
        snapshot = await graph_app.aget_state(config)
        final_state = snapshot.values
        
        status = final_state.status if hasattr(final_state, 'status') else "UNKNOWN"
        logger.info(f"Workflow Paused/Finished | Status: {status}")
        
        if status in [ProcessingStatus.COMPLETED, ProcessingStatus.REJECTED]:
            if file_name in processing_threads: del processing_threads[file_name]
            if file_name in processing_files: processing_files.remove(file_name)
            
    except Exception as e:
        logger.error(f"Workflow Critical Fail [{file_name}]: {e}")
        if file_name in processing_threads: del processing_threads[file_name]
        if file_name in processing_files: processing_files.remove(file_name)

# --- DEDICATED CHAT ENDPOINT (Clean RAG Invocation) ---
@app.post("/v1/chat")
async def chat_endpoint(request: ChatRequest):
    """
    Simple endpoint to invoke the RAG graph directly.
    """
    logger.info(f"💬 Chat Query Received: {request.query}")
    
    if not rag_app:
        raise HTTPException(status_code=500, detail="RAG Service not initialized.")
        
    try:
        # Invoke RAG Subgraph
        response = await rag_app.ainvoke({"query": request.query})
        
        # Extract answer safely
        answer = response.get("answer", "No answer generated.")
        context = response.get("context", "")
        
        return {
            "answer": answer,
            "context_preview": context[:200] if context else None
        }
    except Exception as e:
        logger.error(f"RAG Invocation Error: {e}")
        return {"answer": f"I encountered an error processing your request: {str(e)}"}

# --- DEDICATED UPLOAD ENDPOINT (Clean Ingest Trigger) ---
@app.post("/v1/upload")
async def upload_trigger_endpoint(request: FileUploadRequest, background_tasks: BackgroundTasks):
    """
    Simple endpoint to trigger processing for a file uploaded via UI.
    """
    fpath = request.file_path
    fname = os.path.basename(fpath)
    
    if not os.path.exists(fpath):
        raise HTTPException(status_code=404, detail="File not found on server disk.")
        
    logger.info(f"📥 Manual Upload Triggered: {fname}")
    
    if fname not in processing_files:
        processing_files.add(fname)
        background_tasks.add_task(process_file, fname, fpath)
        return {"status": "submitted", "task_id": fname}
    else:
        return {"status": "ignored", "message": "File already processing"}

# --- APPROVAL ENDPOINTS ---
@app.post("/v1/approve")
async def approve_invoice(payload: dict = Body(...)):
    file_name = payload.get("file_name")
    reason = payload.get("reason", "Manual Override via UI")
    approved_by = payload.get("approved_by", "human_admin")
    
    if not file_name:
        raise HTTPException(400, "file_name is required")
        
    thread_id = processing_threads.get(file_name)
    if not thread_id:
        raise HTTPException(404, f"No active workflow found for {file_name}")
        
    config = {"configurable": {"thread_id": thread_id}}
    
    try:
        current_snapshot = await graph_app.aget_state(config)
        if not current_snapshot.next:
             raise HTTPException(400, "Workflow is not in a pausable state or has already finished.")
             
        logger.info(f"Human Approval for {file_name}: {reason}")
        
        approval_info = ApprovalInfo(
            approved_by=approved_by,
            reason=reason,
            timestamp=datetime.now().isoformat()
        )
        
        await graph_app.aupdate_state(config, {"approval_info": approval_info})
        asyncio.create_task(resume_workflow(file_name, config))
        
        return {"status": "success", "message": f"Approved {file_name}. Resuming workflow."}
    except Exception as e:
        logger.error(f"Approval failed: {e}")
        raise HTTPException(500, f"Approval failed: {str(e)}")

@app.post("/v1/reject")
async def reject_invoice(payload: dict = Body(...)):
    file_name = payload.get("file_name")
    reason = payload.get("reason", "Rejected via UI")
    rejected_by = payload.get("rejected_by", "human_admin")
    
    if not file_name:
        raise HTTPException(400, "file_name is required")
        
    thread_id = processing_threads.get(file_name)
    if not thread_id:
        raise HTTPException(404, f"No active workflow found for {file_name}")
        
    config = {"configurable": {"thread_id": thread_id}}
    
    try:
        current_snapshot = await graph_app.aget_state(config)
        if not current_snapshot.next:
             raise HTTPException(400, "Workflow is not in a pausable state.")

        logger.info(f"Human Rejection for {file_name}: {reason}")
        
        approval_info = ApprovalInfo(
            approved_by=rejected_by,
            reason=f"REJECTED: {reason}",
            timestamp=datetime.now().isoformat()
        )
        
        await graph_app.aupdate_state(config, {
            "approval_info": approval_info,
            "status": ProcessingStatus.REJECTED
        })
        
        asyncio.create_task(resume_workflow(file_name, config))
        return {"status": "success", "message": f"Rejected {file_name}."}
        
    except Exception as e:
        logger.error(f"Rejection failed: {e}")
        raise HTTPException(500, f"Rejection failed: {str(e)}")

async def resume_workflow(file_name: str, config: dict):
    try:
        async for event in graph_app.astream(None, config=config):
            pass
            
        snapshot = await graph_app.aget_state(config)
        status = snapshot.values.status
        
        if status in [ProcessingStatus.COMPLETED, ProcessingStatus.REJECTED]:
            if file_name in processing_threads: del processing_threads[file_name]
            if file_name in processing_files: processing_files.remove(file_name)
            logger.info(f"Workflow {file_name} finished after human review (Status: {status}).")
            
    except Exception as e:
        logger.error(f"Error resuming {file_name}: {e}")

@app.get("/health")
def health():
    return {"status": "ok", "threads": len(processing_threads)}

if __name__ == "__main__":
    uvicorn.run("src.server:app", host="0.0.0.0", port=8000, reload=False)