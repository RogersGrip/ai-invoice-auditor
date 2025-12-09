import uvicorn
import uuid
import os
import threading
import time
import warnings
from fastapi import FastAPI, HTTPException, Header, BackgroundTasks, Path, Body
from fastapi.concurrency import run_in_threadpool
from contextlib import asynccontextmanager
from typing import List, Optional, Set

warnings.filterwarnings("ignore", category=DeprecationWarning)

from src.core.protocol import (
    SendMessageRequest, SendMessageResponse, Task, AgentCard,
    Message, Role, TaskState, TaskStatus, Part
)
from src.core.logger import logger, setup_logger
from src.core.mappers import map_state_to_task
from src.core.state import InvoiceState, ProcessingStatus
from src.core.discovery import AgentDiscovery
from src.workflows.graph import create_invoice_graph
from src.core.config import settings
from src.adk_agents.monitor_agent import InvoiceMonitorAgent

setup_logger()

graph_app = None
monitor_agent = InvoiceMonitorAgent()
stop_monitor = False
# Track files currently in the pipeline to prevent looping
processing_files: Set[str] = set()

def monitor_loop():
    logger.info("📂 Invoice Monitor Started...")
    while not stop_monitor:
        try:
            jobs = monitor_agent.scan()
            for job in jobs:
                file_path = job.get("file_path")
                if not file_path: continue
                fname = os.path.basename(file_path)
                
                # SKIP if already processed or currently processing
                if (settings.PROCESSED_DIR / fname).exists():
                    continue
                if fname in processing_files:
                    continue

                logger.info(f"👀 Auto-processing: {fname}")
                processing_files.add(fname)
                run_background_task(fname, file_path)
                time.sleep(2)
        except Exception as e:
            logger.error(f"Monitor Loop Error: {e}")
        time.sleep(5)

@asynccontextmanager
async def lifespan(app: FastAPI):
    global graph_app, stop_monitor
    logger.info("Initializing Orchestrator Graph...")
    graph_app = create_invoice_graph()
    
    t = threading.Thread(target=monitor_loop, daemon=True)
    t.start()
    
    yield
    
    logger.info("Shutting down...")
    stop_monitor = True
    t.join(timeout=2)

app = FastAPI(title="AI Invoice Auditor A2A Server", version="1.0.0", lifespan=lifespan)

def run_background_task(thread_id: str, file_path: str):
    if not graph_app: return
    config = {"configurable": {"thread_id": thread_id}}
    abs_path = os.path.abspath(file_path)
    
    initial_state = InvoiceState(
        file_path=abs_path,
        file_name=os.path.basename(abs_path),
        metadata={"source": "api"},
        current_step="start",
        status=ProcessingStatus.PENDING
    )
    
    try:
        logger.info(f"STARTING WORKFLOW | ID: {thread_id}")
        graph_app.invoke(initial_state, config=config)
    except Exception as e:
        logger.error(f"WORKFLOW FAILED | ID: {thread_id} | Error: {e}")
        fname = os.path.basename(file_path)
        if fname in processing_files:
            processing_files.remove(fname)

@app.get("/.well-known/agent-card.json", response_model=AgentCard)
async def get_default_agent_card():
    card = AgentDiscovery.get_card("AI Invoice Auditor Orchestrator")
    if not card: 
        cards = AgentDiscovery.get_all_cards()
        if cards:
            return cards.get(list(cards.keys())[0])
        raise HTTPException(500, "No cards loaded")
    return card

@app.get("/v1/agents/{agent_name}/agent-card.json", response_model=AgentCard)
async def get_specific_agent_card(agent_name: str = Path(...)):
    card = AgentDiscovery.get_card(agent_name)
    if not card: raise HTTPException(status_code=404, detail=f"Agent card for '{agent_name}' not found")
    return card

@app.post("/v1/message:send", response_model=SendMessageResponse)
async def send_message(request: SendMessageRequest, background_tasks: BackgroundTasks, a2a_version: str = Header(default="0.3.0", alias="A2A-Version")):
    msg = request.message
    context_id = msg.contextId or str(uuid.uuid4())
    
    # Handle File Processing Tasks
    tasks_created = []
    for part in msg.parts:
        if part.file:
            task_id = part.file.name
            fname = part.file.name
            if part.file.fileWithUri and part.file.fileWithUri.startswith("file://"):
                input_file = part.file.fileWithUri.replace("file://", "")
            else:
                input_file = str(settings.INVOICE_WATCH_DIR / fname)
            
            if not os.path.exists(input_file):
                raise HTTPException(status_code=400, detail=f"File not found on server: {input_file}")
            
            if fname not in processing_files:
                processing_files.add(fname)
                background_tasks.add_task(run_background_task, task_id, input_file)
                tasks_created.append(task_id)
            
    if tasks_created:
        return SendMessageResponse(task=Task(id=tasks_created[0], contextId=context_id, status=TaskStatus(state=TaskState.SUBMITTED)))

    # Handle Chat / RAG
    input_text = next((p.text for p in msg.parts if p.text), None)
    if input_text:
        # Run RAG in threadpool to avoid blocking main loop
        def run_rag_sync(text):
            from src.workflows.rag_graph import create_rag_graph
            rag = create_rag_graph()
            return rag.invoke({"query": text})

        try:
            result = await run_in_threadpool(run_rag_sync, input_text)
            response_msg = Message(
                messageId=str(uuid.uuid4()), 
                role=Role.AGENT, 
                contextId=context_id, 
                parts=[Part(text=result.get("answer", "No answer found."))]
            )
            return SendMessageResponse(message=response_msg)
        except Exception as e:
            logger.error(f"RAG Error: {e}")
            raise HTTPException(status_code=500, detail=f"RAG Error: {e}")

    raise HTTPException(status_code=400, detail="No valid input found (text or file).")

@app.get("/v1/tasks/{id}", response_model=Task)
async def get_task(id: str):
    config = {"configurable": {"thread_id": id}}
    try:
        snapshot = graph_app.get_state(config)
        if not snapshot.values: raise HTTPException(status_code=404, detail="Task not found")
        current_invoice_state = InvoiceState(**snapshot.values)
        return map_state_to_task(current_invoice_state, context_id="default-ctx")
    except HTTPException: raise
    except Exception as e:
        logger.error(f"Error fetching task {id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/v1/tasks/{id}/resume")
async def resume_task(id: str, comment: Optional[str] = Body(None, embed=True)):
    config = {"configurable": {"thread_id": id}}
    try:
        logger.info(f"Received RESUME request for Task ID: {id}")
        snapshot = graph_app.get_state(config)
        if not snapshot.values: raise HTTPException(status_code=404, detail=f"Task {id} not found")
        
        # Check if actually paused
        if not snapshot.next: 
            return {"status": "Task is not paused (Completed or Failed)"}
            
        logger.info(f"Resuming task {id} with comment: {comment}")
        # Passing None input resumes from the interruption point
        graph_app.invoke(None, config=config)
        
        # Cleanup from processing list once resumed and finished
        if id in processing_files:
            processing_files.remove(id)
            
        return {"status": "Resumed successfully"}
    except HTTPException: raise
    except Exception as e:
        logger.error(f"Failed to resume task {id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
def health():
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run("src.server:app", host="0.0.0.0", port=8000, reload=True)