# ===== FILE: src/frameworks/google_adk/runners.py =====
from typing import Any, AsyncGenerator
from src.frameworks.google_adk.agents import Agent
from src.frameworks.google_adk.types import Content, Part
from src.core.logger import logger

class Runner:
    def __init__(
        self,
        agent: Agent,
        session_service: Any = None,
        artifact_service: Any = None,
        memory_service: Any = None,
        app_name: str = "ADK_App"
    ):
        self.agent = agent
        self.session_service = session_service
        self.app_name = app_name

    async def run_async(
        self,
        user_id: str,
        session_id: str,
        new_message: Content
    ) -> AsyncGenerator[Content, None]:
        
        logger.info(f"Runner started for user {user_id} session {session_id}")
        
        # Extract text from input
        input_text = ""
        if new_message.parts:
            input_text = new_message.parts[0].text or ""

        # Delegate to Agent (In a real scenario, this handles state/history)
        try:
            response_text = await self.agent.process(input_text)
            
            # Yield response
            yield Content(
                role="model",
                parts=[Part(text=response_text)]
            )
        except Exception as e:
            logger.error(f"Runner Execution Error: {e}")
            yield Content(
                role="model",
                parts=[Part(text=f"Error: {str(e)}")]
            )