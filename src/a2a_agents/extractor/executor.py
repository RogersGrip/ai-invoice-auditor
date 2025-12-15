from a2a.server.agent_execution import AgentExecutor
from a2a.server.agent_execution.context import RequestContext
from a2a.server.events.event_queue import EventQueue
from a2a.utils import new_agent_text_message, new_agent_data_message
from src.langgraph_agents.extractor_agent import ExtractorAgent

class ExtractorAgentExecutor(AgentExecutor):
    def __init__(self):
        self.agent = ExtractorAgent()

    async def execute(self, context: RequestContext, event_queue: EventQueue):
        try:
            # Parse Input
            inputs = {}
            if context.message and context.message.parts:
                for part in context.message.parts:
                    if part.root.text:
                        inputs["raw_text"] = part.root.text # Usually not passed to extractor, but just in case
                    if part.root.data and part.root.data.data:
                        inputs.update(part.root.data.data)
                    # Handle File Input (Protocol allows file parts)
                    # But often file path is passed in data or text for local tools
                    
            # ExtractorAgent expects "file_path"
            if "file_path" not in inputs:
                # Fallback: Check if file object is in parts (if A2A supports file ref)
                # For now assuming file_path string is passed in data
                pass

            # Execute
            response = self.agent.process(inputs)

            if response.message_type == "ERROR":
                await event_queue.enqueue_event(new_agent_text_message(f"Error: {response.payload.get('error')}"))
                return

            # Return Result
            # Extractor returns "raw_text"
            payload = response.payload
            
            # Send as Data Message
            await event_queue.enqueue_event(new_agent_data_message(payload))
            
        except Exception as e:
            await event_queue.enqueue_event(new_agent_text_message(f"Execution Error: {str(e)}"))

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        await event_queue.enqueue_event(new_agent_text_message("Cancelled"))
