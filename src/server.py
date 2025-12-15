# ===== FILE: src/server.py =====
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

# --- Official A2A SDK Imports ---
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

# --- Core Imports ---
from src.core.logger import logger, setup_logger
from src.core.state import InvoiceState, ProcessingStatus, ApprovalInfo
from src.workflows.graph import create_invoice_graph
from src.core.config import settings
from src.adk_agents.monitor_agent import InvoiceMonitorAgent

# Apply fixes
nest_asyncio.apply()
setup_logger()

# Globals
graph_app = None
monitor_agent = InvoiceMonitorAgent()
processing_threads: Dict[str, str] = {}  # Map file_name -> thread_id
processing_files: Set[str] = set()

@asynccontextmanager
async def lifespan(app: FastAPI):
    global graph_app
    logger.info(">>> Initializing AI Invoice Auditor Orchestrator...")
    graph_app = create_invoice_graph()
    
    # Start background monitor
    monitor_task = asyncio.create_task(monitor_loop())
    yield
    # Cleanup
    monitor_task.cancel()
    logger.info(">>> Shutting down Orchestrator...")

app = FastAPI(title="AI Invoice Auditor", version="1.0.0", lifespan=lifespan)

# ==============================================================================
# MONITORING LOOP
# ==============================================================================
async def monitor_loop():
    logger.info("📂 Monitoring Watch Folder...")
    while True:
        try:
            # Use the tool logic from the monitor agent
            jobs = monitor_agent.scan()
            
            for job in jobs:
                fpath = job.get("file_path")
                fname = os.path.basename(fpath)
                
                if fname in processing_files:
                    continue
                
                logger.info(f"♻️  Detected new file: {fname}")
                processing_files.add(fname)
                
                # Spawn workflow
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
    
    logger.info(f"🚀 Starting Workflow [Thread: {thread_id}] for {file_name}")
    
    try:
        # Initial run
        async for event in graph_app.astream(state, config=config):
            pass # We rely on 'observe' decorators for logging, but streaming keeps it async friendly
            
        # Check final status
        snapshot = await graph_app.aget_state(config)
        final_state = snapshot.values
        status = final_state.status if hasattr(final_state, 'status') else "UNKNOWN"
        
        logger.info(f"🏁 Workflow Paused/Finished | Status: {status}")
        
        # If completed, clean up. If paused (HITL), keep in memory.
        if status == ProcessingStatus.COMPLETED:
            if file_name in processing_threads: del processing_threads[file_name]
            if file_name in processing_files: processing_files.remove(file_name)

    except Exception as e:
        logger.error(f"❌ Workflow Critical Fail [{file_name}]: {e}")
        if file_name in processing_threads: del processing_threads[file_name]
        if file_name in processing_files: processing_files.remove(file_name)

# ==============================================================================
# API ENDPOINTS
# ==============================================================================

@app.post("/v1/message:send", response_model=SendMessageResponse)
async def send_message(request: SendMessageRequest, background_tasks: BackgroundTasks):
    """
    A2A Protocol Endpoint: Accepts messages/files from other agents or UI.
    """
    msg = request.message
    context_id = msg.contextId or str(uuid.uuid4())
    
    # Handle File Inputs
    for part in msg.parts:
        if part.file:
            fname = part.file.name
            # Simplified: Assume file is already in watch dir or handle URI logic here
            # For this demo, we assume the file was placed in the folder and this message triggers awareness
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

    # Handle Text Queries (RAG)
    text_query = next((p.text for p in msg.parts if p.text), None)
    if text_query:
        # Use MCP RAG Tooling
        from src.mcp_server.rag import retrieve_context
        # Context object would be needed for FastMCP, here we emulate or call direct logic
        # For simplicity in this A2A wrapper, we assume a direct call or use the graph if RAG was a graph
        # Let's use the RAG graph if it exists, or just the MCP tool
        try:
            # We can use the graph defined in src/workflows/rag_graph.py if integrated
            # For now, let's just return a simple response
            return SendMessageResponse(
                message=Message(
                    messageId=str(uuid.uuid4()),
                    role=Role.AGENT,
                    contextId=context_id,
                    parts=[Part(text=f"Received query: {text_query}. (RAG integration pending full graph setup)")]
                )
            )
        except Exception as e:
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
    """
    HITL Endpoint: Manually approves a paused/flagged invoice.
    Updates the state with ApprovalInfo and resumes the graph.
    """
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
        # 1. Verify we are paused
        current_snapshot = await graph_app.aget_state(config)
        if not current_snapshot.next:
             # It might be finished or failed terminally
             raise HTTPException(400, "Workflow is not in a pausable state or has already finished.")

        logger.info(f"👤 Human Approval for {file_name}: {reason}")

        # 2. Inject Approval Info into State
        approval_info = ApprovalInfo(
            approved_by=approved_by,
            reason=reason,
            timestamp=datetime.now().isoformat()
        )
        
        # Update the state. We strictly type the update dict.
        await graph_app.aupdate_state(config, {"approval_info": approval_info})

        # 3. Resume Workflow
        # invoking with None resumes from the interruption point (human_review)
        # The human_review node will now see approval_info and pass to ingestion
        asyncio.create_task(resume_workflow(file_name, config))

        return {"status": "success", "message": f"Approved {file_name}. Resuming workflow."}

    except Exception as e:
        logger.error(f"Approval failed: {e}")
        raise HTTPException(500, f"Approval failed: {str(e)}")

async def resume_workflow(file_name: str, config: dict):
    try:
        async for event in graph_app.astream(None, config=config):
            pass
        
        # Cleanup after finish
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