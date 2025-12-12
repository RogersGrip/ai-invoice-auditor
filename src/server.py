# ===== FILE: src/server.py =====
import uvicorn
import uuid
import os
import json
import threading
import time
import warnings
import asyncio
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
processing_files: Set[str] = set()

# Monitor runs in a separate thread to not block FastAPI
def monitor_loop():
    logger.info("📂 Invoice Monitor Started...")
    while not stop_monitor:
        try:
            if not graph_app:
                time.sleep(1)
                continue
                
            jobs = monitor_agent.scan()
            for job in jobs:
                file_path = job.get("file_path")
                if not file_path: continue
                
                fname = os.path.basename(file_path)
                
                # Skip processed files
                if (settings.PROCESSED_DIR / fname).exists():
                    continue
                    
                if fname in processing_files:
                    continue
                
                logger.info(f"👀 Auto-processing: {fname}")
                processing_files.add(fname)
                
                # Trigger processing via API logic (using run_coroutine_threadsafe if needed, 
                # but here we rely on the background task mechanism being triggered externally or via loop)
                # Since we are in a thread, we can't await. We should use a request to self or task queue.
                # For simplicity in this local setup, we start a new loop for the graph execution.
                
                asyncio.run(run_workflow_async(fname, file_path))
                
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

async def run_workflow_async(thread_id: str, file_path: str):
    if not graph_app: return
    
    config = {"configurable": {"thread_id": thread_id}}
    abs_path = os.path.abspath(file_path)
    
    # Load Metadata
    metadata = {"source": "api"}
    try:
        meta_path = Path(abs_path).with_suffix(".meta.json")
        if meta_path.exists():
            with open(meta_path, "r") as f:
                metadata.update(json.load(f))
    except Exception: pass

    initial_state = InvoiceState(
        file_path=abs_path,
        file_name=os.path.basename(abs_path),
        metadata=metadata,
        current_step="start",
        status=ProcessingStatus.PENDING
    )

    try:
        logger.info(f"STARTING WORKFLOW | ID: {thread_id}")
        # Use AINVOKE for async graph
        await graph_app.ainvoke(initial_state, config=config)
        logger.info(f"WORKFLOW COMPLETED | ID: {thread_id}")
    except Exception as e:
        logger.error(f"WORKFLOW FAILED | ID: {thread_id} | Error: {e}")
    finally:
        fname = os.path.basename(file_path)
        if fname in processing_files:
            processing_files.remove(fname)

@app.get("/.well-known/agent-card.json", response_model=AgentCard)
async def get_default_agent_card():
    card = AgentDiscovery.get_card("AI Invoice Auditor Orchestrator")
    if not card:
        cards = AgentDiscovery.get_all_cards()
        if cards: return cards.get(list(cards.keys())[0])
    return card or AgentCard(name="Default", description="Fallback", capabilities={}, defaultInputModes=[], defaultOutputModes=[], skills=[])

@app.post("/v1/message:send", response_model=SendMessageResponse)
async def send_message(request: SendMessageRequest, background_tasks: BackgroundTasks):
    msg = request.message
    context_id = msg.contextId or str(uuid.uuid4())
    
    tasks_created = []
    
    # 1. Handle File Uploads / Triggers
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
                # Check if it was just uploaded via Streamlit
                time.sleep(1) 
            
            if fname in processing_files:
                tasks_created.append(task_id)
                continue
                
            processing_files.add(fname)
            # Add async task
            background_tasks.add_task(run_workflow_async, task_id, input_file)
            tasks_created.append(task_id)

    if tasks_created:
        return SendMessageResponse(task=Task(id=tasks_created[0], contextId=context_id, status=TaskStatus(state=TaskState.SUBMITTED)))

    # 2. Handle Text Query (RAG)
    input_text = next((p.text for p in msg.parts if p.text), None)
    if input_text:
        try:
            # Lazy import to avoid circular dependency
            from src.workflows.rag_graph import create_rag_graph
            rag = create_rag_graph()
            # Use async invoke
            result = await rag.ainvoke({"query": input_text})
            
            response_msg = Message(
                messageId=str(uuid.uuid4()),
                role=Role.AGENT,
                contextId=context_id,
                parts=[Part(text=result.get("answer", "No answer found.") + "\n\n" + str(result.get("evaluation", "")))]
            )
            return SendMessageResponse(message=response_msg)
        except Exception as e:
            logger.error(f"RAG Error: {e}")
            raise HTTPException(status_code=500, detail=f"RAG Error: {e}")

    raise HTTPException(status_code=400, detail="No valid input found.")

@app.get("/health")
def health():
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run("src.server:app", host="0.0.0.0", port=8000, reload=True)