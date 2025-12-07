from typing import Dict, Any
import uuid
from datetime import datetime
from src.core.protocol import Agent, AgentResponse
from src.core.logger import logger
from src.tools.tools import LangBridgeTool

class TranslationAgent(Agent):
    name = "Translation Agent"
    description = "Detects language and translates content to English if necessary."

    @property
    def inputs_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "raw_text": {"type": "string"}
            },
            "required": ["raw_text"]
        }

    @property
    def outputs_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "english_text": {"type": "string"},
                "extracted_data": {"type": "object"},
                "model": {"type": "string"}
            }
        }

    def __init__(self):
        self.bridge_tool = LangBridgeTool()

    def process(self, inputs: Dict[str, Any]) -> AgentResponse:
        self.start_as_current_observation(inputs)
        
        # Resolve Input
        raw_text = inputs.get("raw_text")
        if not raw_text and inputs.get("payload"):
            raw_text = inputs["payload"].get("raw_text")

        if not raw_text:
            return AgentResponse(
                 id=str(uuid.uuid4()),
                 source_agent=self.name,
                 timestamp=datetime.now().isoformat(),
                 target_agent="Error Handler",
                 message_type="ERROR",
                 payload={"error": "No text to translate"},
                 context_id=inputs.get("context_id")
            )

        logger.info(f"[{self.name}] Calling Lang-Bridge Tool...")
        
        try:
            # Strict Tool Call
            result = self.bridge_tool.run(raw_text)
            
            return AgentResponse(
                id=str(uuid.uuid4()),
                timestamp=datetime.now().isoformat(),
                source_agent=self.name,
                target_agent="Data Validation Agent",
                message_type="TASK_HANDOFF",
                payload=result, # Contains extracted_data, english_text, model
                context_id=inputs.get("context_id")
            )
            
        except Exception as e:
            logger.error(f"Translation Failed: {e}")
            return AgentResponse(
                 id=str(uuid.uuid4()),
                 source_agent=self.name,
                 timestamp=datetime.now().isoformat(),
                 target_agent="Error Handler",
                 message_type="ERROR",
                 payload={"error": str(e)},
                 context_id=inputs.get("context_id")
            )
