import uvicorn
import uuid
import os
from fastapi import FastAPI, HTTPException, Header, BackgroundTasks, Path
from contextlib import asynccontextmanager

from src.core.protocol import (
    SendMessageRequest, SendMessageResponse, Task, AgentCard,
    Message, Role, TaskState, TaskStatus, Part
)
from src.core.logger import logger, setup_logger
from src.core.mappers import map_state_to_task
from src.core.state import InvoiceState, ProcessingStatus
from src.core.discovery import AgentDiscovery
from src.workflows.graph import create_invoice_graph

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
    config = {"configurable": {"thread_id": thread_id}}
    initial_state = InvoiceState(
        file_path=file_path,
        file_name=os.path.basename(file_path),
        metadata={"source": "api"},
        current_step="start",
        status=ProcessingStatus.PENDING
    )
    try:
        logger.info(f"Starting background processing for {thread_id}")
        graph_app.invoke(initial_state, config=config)
    except Exception as e:
        logger.error(f"Background task failed for {thread_id}: {e}")

@app.get("/.well-known/agent-card.json", response_model=AgentCard)
async def get_default_agent_card():
    card = AgentDiscovery.get_card("AI Invoice Auditor Orchestrator")
    if not card:
        raise HTTPException(status_code=404, detail="Default agent card not found")
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
    task_id = msg.taskId or str(uuid.uuid4())
    
    input_file = None
    input_text = None
    
    for part in msg.parts:
        if part.file:
            if part.file.fileWithUri and part.file.fileWithUri.startswith("file://"):
                input_file = part.file.fileWithUri.replace("file://", "")
            else:
                 input_file = f"data/invoices/{part.file.name}"
        if part.text:
            input_text = part.text

    if input_file:
        if not os.path.exists(input_file):
            raise HTTPException(status_code=400, detail=f"File not found: {input_file}")

        background_tasks.add_task(run_background_task, task_id, input_file)

        return SendMessageResponse(
            task=Task(
                id=task_id,
                contextId=context_id,
                status=TaskStatus(state=TaskState.SUBMITTED)
            )
        )

    elif input_text:
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

    else:
        raise HTTPException(status_code=400, detail="No supported input found (file or text).")

@app.get("/v1/tasks/{id}", response_model=Task)
async def get_task(id: str):
    config = {"configurable": {"thread_id": id}}
    try:
        snapshot = graph_app.get_state(config)
        if not snapshot.values:
             raise HTTPException(status_code=404, detail="Task not found or not started.")
        
        current_invoice_state = InvoiceState(**snapshot.values)
        return map_state_to_task(current_invoice_state, context_id="default-ctx")
        
    except Exception as e:
        logger.error(f"Error fetching task {id}: {e}")
        raise HTTPException(status_code=404, detail=f"Task {id} not found.")

@app.get("/health")
def health():
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run("src.server:app", host="0.0.0.0", port=8000, reload=True)