import uvicorn
import uuid
import os
import warnings
from fastapi import FastAPI, HTTPException, Header, BackgroundTasks, Path, Body
from contextlib import asynccontextmanager
from typing import List, Optional

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

setup_logger()

graph_app = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global graph_app
    logger.info("Initializing Orchestrator Graph...")
    graph_app = create_invoice_graph()
    yield
    logger.info("Shutting down...")

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
        logger.info(f"STARTING WORKFLOW | ID: {thread_id} | File: {abs_path}")
        graph_app.invoke(initial_state, config=config)
    except Exception as e:
        logger.error(f"WORKFLOW FAILED | ID: {thread_id} | Error: {e}")

@app.get("/.well-known/agent-card.json", response_model=AgentCard)
async def get_default_agent_card():
    card = AgentDiscovery.get_card("AI Invoice Auditor Orchestrator")
    if not card:
        return AgentDiscovery.get_all_cards().get(list(AgentDiscovery.get_all_cards().keys())[0])
    return card

@app.get("/v1/agents/{agent_name}/agent-card.json", response_model=AgentCard)
async def get_specific_agent_card(agent_name: str = Path(...)):
    card = AgentDiscovery.get_card(agent_name)
    if not card:
        raise HTTPException(status_code=404, detail=f"Agent card for '{agent_name}' not found")
    return card

@app.post("/v1/message:send", response_model=SendMessageResponse)
async def send_message(
    request: SendMessageRequest,
    background_tasks: BackgroundTasks,
    a2a_version: str = Header(default="0.3.0", alias="A2A-Version")
):
    msg = request.message
    context_id = msg.contextId or str(uuid.uuid4())
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

            background_tasks.add_task(run_background_task, task_id, input_file)
            tasks_created.append(task_id)

    if tasks_created:
        return SendMessageResponse(
            task=Task(
                id=tasks_created[0],
                contextId=context_id,
                status=TaskStatus(state=TaskState.SUBMITTED)
            )
        )

    # Chat Handling
    input_text = next((p.text for p in msg.parts if p.text), None)
    if input_text:
        from src.workflows.rag_graph import create_rag_graph
        rag = create_rag_graph()
        result = rag.invoke({"query": input_text})
        
        response_msg = Message(
            messageId=str(uuid.uuid4()),
            role=Role.AGENT,
            contextId=context_id,
            parts=[Part(text=result.get("answer", "No answer found."))]
        )
        return SendMessageResponse(message=response_msg)

    raise HTTPException(status_code=400, detail="No valid input.")

@app.get("/v1/tasks/{id}", response_model=Task)
async def get_task(id: str):
    config = {"configurable": {"thread_id": id}}
    try:
        snapshot = graph_app.get_state(config)
        if not snapshot.values:
             raise HTTPException(status_code=404, detail="Task not found or not started.")
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
        if not snapshot.values:
             logger.error(f"Resume Failed: No state found for {id}")
             raise HTTPException(status_code=404, detail=f"Task {id} not found to resume.")
        
        if not snapshot.next:
            return {"status": "Task is not paused or already completed."}
        
        logger.info(f"Resuming task {id} with comment: {comment}")
        graph_app.invoke(None, config=config)
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