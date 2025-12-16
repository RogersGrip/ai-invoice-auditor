from a2a.server.agent_execution import AgentExecutor
from a2a.server.agent_execution.context import RequestContext
from a2a.server.events.event_queue import EventQueue
from a2a.utils import new_agent_text_message, new_agent_parts_message
from a2a.types import Part, DataPart
from src.adk_agents.translation_agent import TranslationAgent
import asyncio

class TranslatorAgentExecutor(AgentExecutor):
    def __init__(self):
        self.agent = TranslationAgent()

    async def execute(self, context: RequestContext, event_queue: EventQueue):
        try:
            inputs = {}
            if context.message and context.message.parts:
                for part in context.message.parts:
                    if part.root.text:
                        inputs["raw_text"] = part.root.text
                    if part.root.data and part.root.data.data:
                        inputs.update(part.root.data.data)

            response = await self.agent.process_async(inputs)

            if response.message_type == "ERROR":
                await event_queue.enqueue_event(new_agent_text_message(f"Error: {response.payload.get('error')}"))
                return

            payload = response.payload
            
            # Fix: Use new_agent_parts_message with explicit DataPart
            data_part = DataPart(data=payload)
            part = Part(data=data_part)
            await event_queue.enqueue_event(new_agent_parts_message(parts=[part]))

        except Exception as e:
            await event_queue.enqueue_event(new_agent_text_message(f"Execution Error: {str(e)}"))

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        await event_queue.enqueue_event(new_agent_text_message("Cancelled"))