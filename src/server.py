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

# Imports for A2A Protocol
from a2a.types import (
    SendMessageRequest,
    SendMessageResponse,
    Task,
    TaskStatus,
    TaskState,
    Message,
    Role,
    Part
)

# Core Imports
from src.core.logger import logger, setup_logger
from src.core.state import InvoiceState, ProcessingStatus, ApprovalInfo
from src.workflows.graph import create_invoice_graph
# [Fix] Import the RAG graph factory
from src.workflows.rag_graph import create_rag_graph 
from src.core.config import settings
from src.adk_agents.monitor_agent import InvoiceMonitorAgent

nest_asyncio.apply()
setup_logger()

# Global State
graph_app = None
rag_app = None  # [Fix] Variable to hold the RAG workflow
monitor_agent = InvoiceMonitorAgent()
processing_threads: Dict[str, str] = {}
processing_files: Set[str] = set()

@asynccontextmanager
async def lifespan(app: FastAPI):
    global graph_app, rag_app
    logger.info(">>> Initializing AI Invoice Auditor Orchestrator...")
    
    # Initialize both workflows
    graph_app = create_invoice_graph()
    rag_app = create_rag_graph() # [Fix] Initialize RAG Graph
    
    # Start the folder watcher
    monitor_task = asyncio.create_task(monitor_loop())
    yield
    monitor_task.cancel()
    logger.info(">>> Shutting down Orchestrator...")

app = FastAPI(title="AI Invoice Auditor", version="1.0.0", lifespan=lifespan)

async def monitor_loop():
    """Background task to watch the invoices folder."""
    logger.info("📂 Monitoring Watch Folder...")
    while True:
        try:
            jobs = monitor_agent.scan()
            for job in jobs:
                fpath = job.get("file_path")
                fname = os.path.basename(fpath)
                
                # Prevent duplicate processing of the same file session
                if fname in processing_files:
                    continue
                
                logger.info(f"♻️  Detected new file: {fname}")
                processing_files.add(fname)
                asyncio.create_task(process_file(fname, fpath))
                
            await asyncio.sleep(5)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Monitor Loop Error: {e}")
            await asyncio.sleep(5)

async def process_file(file_name: str, file_path: str):
    """Runs the Main Invoice Processing Graph."""
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
        
        # Cleanup if completed
        if status == ProcessingStatus.COMPLETED:
            if file_name in processing_threads: del processing_threads[file_name]
            if file_name in processing_files: processing_files.remove(file_name)
            
    except Exception as e:
        logger.error(f"❌ Workflow Critical Fail [{file_name}]: {e}")
        if file_name in processing_threads: del processing_threads[file_name]
        if file_name in processing_files: processing_files.remove(file_name)

@app.post("/v1/message:send", response_model=SendMessageResponse)
async def send_message(request: SendMessageRequest, background_tasks: BackgroundTasks):
    """
    Handles Chat messages. 
    1. If file attached: Triggers Invoice Processing Graph.
    2. If text query: Triggers RAG Graph (Q&A).
    """
    msg = request.message
    context_id = msg.contextId or str(uuid.uuid4())

    # --- 1. Handle File Uploads ---
    for part in msg.parts:
        if part.file:
            fname = part.file.name
            if fname not in processing_files:
                fpath = str(settings.INVOICE_WATCH_DIR / fname)
                if os.path.exists(fpath):
                    processing_files.add(fname)
                    background_tasks.add_task(process_file, fname, fpath)
            
            return SendMessageResponse(
                task=Task(
                    id=fname,
                    contextId=context_id,
                    status=TaskStatus(state=TaskState.SUBMITTED)
                )
            )

    # --- 2. Handle RAG / Chat Queries ---
    text_query = next((p.text for p in msg.parts if p.text), None)
    
    if text_query:
        logger.info(f"💬 Processing RAG Query: {text_query}")
        try:
            # [Fix] Invoke the RAG Graph
            response = await rag_app.ainvoke({"query": text_query})
            answer = response.get("answer", "I'm sorry, I couldn't generate an answer.")
            
            return SendMessageResponse(
                message=Message(
                    messageId=str(uuid.uuid4()),
                    role=Role.AGENT,
                    contextId=context_id,
                    parts=[Part(text=answer)]
                )
            )
        except Exception as e:
            logger.error(f"RAG Error: {e}")
            return SendMessageResponse(
                message=Message(
                    messageId=str(uuid.uuid4()),
                    role=Role.AGENT,
                    contextId=context_id,
                    parts=[Part(text=f"Error processing query: {str(e)}")]
                )
            )

    return SendMessageResponse(message=Message(messageId=str(uuid.uuid4()), role=Role.AGENT, parts=[Part(text="Ack")]))

@app.post("/v1/approve")
async def approve_invoice(payload: dict = Body(...)):
    """API Endpoint for Human-in-the-Loop Approval."""
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

        logger.info(f"👤 Human Approval for {file_name}: {reason}")
        
        approval_info = ApprovalInfo(
            approved_by=approved_by,
            reason=reason,
            timestamp=datetime.now().isoformat()
        )
        
        # Update state with approval info
        await graph_app.aupdate_state(config, {"approval_info": approval_info})
        # Resume workflow
        asyncio.create_task(resume_workflow(file_name, config))
        
        return {"status": "success", "message": f"Approved {file_name}. Resuming workflow."}
        
    except Exception as e:
        logger.error(f"Approval failed: {e}")
        raise HTTPException(500, f"Approval failed: {str(e)}")

async def resume_workflow(file_name: str, config: dict):
    try:
        async for event in graph_app.astream(None, config=config):
            pass
            
        snapshot = await graph_app.aget_state(config)
        if snapshot.values.status == ProcessingStatus.COMPLETED:
            if file_name in processing_threads: del processing_threads[file_name]
            if file_name in processing_files: processing_files.remove(file_name)
            logger.info(f"✅ Workflow {file_name} completed after approval.")
            
    except Exception as e:
        logger.error(f"Error resuming {file_name}: {e}")

@app.get("/health")
def health():
    return {"status": "ok", "threads": len(processing_threads)}

if __name__ == "__main__":
    uvicorn.run("src.server:app", host="0.0.0.0", port=8000, reload=False)