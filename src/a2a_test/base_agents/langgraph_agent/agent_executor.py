from typing import Any, AsyncIterable

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.tasks import TaskUpdater
from a2a.server.events import EventQueue
from a2a.types import (
    TaskState,
    Part,
    TextPart,
    InvalidParamsError,
    UnsupportedOperationError,
)
from a2a.utils import new_task, new_agent_text_message
from a2a.utils.errors import ServerError

from agent import HelloAgent


class HelloAgentExecutor(AgentExecutor):
    """A2A AgentExecutor for HelloAgent."""

    def __init__(self) -> None:
        self.agent = HelloAgent()

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        """Execute the agent with the given context."""
        if not context.get_user_input():
            raise ServerError(error=InvalidParamsError())

        task = context.current_task
        if not task:
            task = new_task(context.message)
            await event_queue.enqueue_event(task)

        updater = TaskUpdater(
            event_queue=event_queue,
            task_id=task.id,
            context_id=task.context_id,
        )

        try:
            # Invoke the agent
            result = self.agent.invoke(
                context.get_user_input(),
                context_id=task.context_id,
            )

            # Determine status
            status = (
                TaskState.completed
                if result.get("status") == "completed"
                else TaskState.error
            )

            # Create response parts
            parts = [TextPart(content=result.get("result", "No response"))]

            # Update task status
            await updater.update_status(status, parts, final=True)

        except Exception as exc:
            await updater.update_status(
                TaskState.error,
                [TextPart(content=f"Error: {str(exc)}")],
                final=True,
            )

    async def cancel(self, context: RequestContext) -> None:
        """Cancel the current task."""
        raise ServerError(
            error=UnsupportedOperationError("Cancellation not supported")
        )