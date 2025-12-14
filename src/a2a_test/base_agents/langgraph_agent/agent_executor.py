from datetime import datetime
from typing import AsyncIterable
from langchain_core.messages import HumanMessage
from typing import Any, Dict
# A2A imports (adjust paths as needed)
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.tasks import TaskUpdater
from a2a.server.events import EventQueue
from a2a.utils.errors import ServerError
from a2a.types import (
    InternalError,
    InvalidParamsError,
    Part,
    TaskState,
    TextPart,
    UnsupportedOperationError
)
from a2a.utils import (
    new_agent_text_message,
    new_task
)
from agent import HelloAgent

class HelloAgentExecutor(AgentExecutor):
    """A2A AgentExecutor for HelloAgent."""

    def __init__(self) -> None:
        self.agent = HelloAgent()

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Execute the agent task following A2A protocol."""
        error = self._validate_request(context)
        if error:
            raise ServerError(error=InvalidParamsError())
        
        query = context.get_user_input()
        task = context.current_task

        if not task:
            task = new_task(context.message)
            await event_queue.enqueue_event(task)

        updater = TaskUpdater(
            event_queue=event_queue, 
            task_id=task.id, 
            context_id=task.context_id
        )

        try:
            # Invoke agent synchronously and convert to async stream
            config = {"configurable": {"thread_id": task.context_id}}
            result = self.agent.invoke(query, config)
            
            # Determine final status
            status = TaskState.completed if result['status'] == 'completed' else TaskState.working
            
            # Create response parts
            parts = new_agent_text_message(result['result'], task.context_id, task.id)
            
            # Update task with final result
            await updater.update_status(status, parts, final=True)
            
        except Exception as e:
            await updater.update_status(
                TaskState.error,
                [TextPart(content=f"Error: {str(e)}")],
                final=True
            )

    def _validate_request(self, context: RequestContext) -> str | None:
        """Validate the incoming request."""
        if not context.get_user_input():
            return "No user input provided"
        return None
    
    async def cancel(self, context: RequestContext) -> None:
        """Handle task cancellation."""
        task = context.current_task
        if task:
            # Note: This assumes Task has a cancel method
            try:
                await task.cancel()
            except AttributeError:
                pass  # Task might not support cancellation
        
        raise ServerError(error=UnsupportedOperationError("Cancellation not fully implemented"))

    async def on_message_send(self, request: Any, event_queue: EventQueue, task: Any) -> AsyncIterable[Part]:
        """Handle incoming A2A messages (if required by protocol)."""
        # Forward to agent for processing
        config = {"configurable": {"thread_id": task.context_id}}
        result = self.agent.invoke(request.content, config)
        
        status = TaskState.completed if result['status'] == 'completed' else TaskState.working
        parts = new_agent_text_message(result['result'], task.context_id, task.id)
        
        yield parts

# Usage example
if __name__ == "__main__":
    executor = HelloAgentExecutor()
    # executor.execute(...) would be called by A2A server
    result = executor.agent.invoke("Hello, can you add 5 and 7?")
    print(result)
