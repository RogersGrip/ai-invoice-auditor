# ===== FILE: src/adk_agents/translation_agent.py =====
import uuid
import os
from typing import Dict, Any
from datetime import datetime, timezone

# Use the ADK base if you want consistency, or just implement the protocol
from src.frameworks.google_adk import ADKAgent
from src.core.protocol import AgentResponse
from src.tools.tools import LangBridgeTool
from src.core.logger import logger

class TranslationAgent(ADKAgent):
    def __init__(self):
        # We don't strictly need the full ADK loop for Translation (it's a direct tool call usually),
        # but we inherit to keep the type signature if needed.
        # If we don't pass a model, we can just act as a wrapper around the tool.
        super().__init__(name="Translation Agent", model=None, instruction="Translate invoice text.")
        self.bridge_tool = LangBridgeTool()

    def process(self, inputs: Dict[str, Any]) -> AgentResponse:
        # Direct execution without the LLM loop for speed/reliability on this specific task
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
            # Direct tool run
            result = self.bridge_tool.run({"text": raw_text})
            
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