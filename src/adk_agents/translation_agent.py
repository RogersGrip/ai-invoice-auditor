from typing import Dict, Any
import uuid
from datetime import datetime, timezone
from src.core.protocol import Agent, AgentResponse
from src.core.logger import logger
from src.tools.tools import LangBridgeTool

class TranslationAgent(Agent):
    name = "Translation Agent"
    description = "Standardizes invoice content to English JSON."

    def __init__(self):
        self.bridge_tool = LangBridgeTool()

    def process(self, inputs: Dict[str, Any]) -> AgentResponse:
        self.start_as_current_observation(inputs)
        
        raw_text = inputs.get("raw_text") or inputs.get("payload", {}).get("raw_text")
        
        if not raw_text:
            return AgentResponse(
                id=str(uuid.uuid4()),
                timestamp=datetime.now(timezone.utc).isoformat(),
                source_agent=self.name,
                target_agent="Error Handler",
                message_type="ERROR",
                payload={"error": "No text to translate"}
            )

        logger.info(f"[{self.name}] Translating text...")
        try:
            result = self.bridge_tool.run(raw_text)
            return AgentResponse(
                id=str(uuid.uuid4()),
                timestamp=datetime.now(timezone.utc).isoformat(),
                source_agent=self.name,
                target_agent="Data Validation Agent",
                message_type="TASK_HANDOFF",
                payload=result,
                context_id=inputs.get("context_id")
            )
        except Exception as e:
            logger.error(f"Translation Error: {e}")
            return AgentResponse(
                id=str(uuid.uuid4()),
                timestamp=datetime.now(timezone.utc).isoformat(),
                source_agent=self.name,
                target_agent="Error Handler",
                message_type="ERROR",
                payload={"error": str(e)}
            )