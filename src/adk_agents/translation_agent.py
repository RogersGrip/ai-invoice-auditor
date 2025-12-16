import uuid
from typing import Dict, Any
from datetime import datetime, timezone
from src.adk_agents.base_agent import AgentADK
from src.core.protocol import AgentResponse
from src.tools.tools import LangBridgeTool

class TranslationAgent(AgentADK):
    def __init__(self):
        super().__init__(
            name="translation_agent",
            instruction="Translate text.", 
            tools=[LangBridgeTool()]
        )
        self.bridge_tool = LangBridgeTool()

    async def process_async(self, inputs: Dict[str, Any]) -> AgentResponse:
        raw_text = inputs.get("raw_text") or inputs.get("payload", {}).get("raw_text")
        if not raw_text: 
            return AgentResponse(id=str(uuid.uuid4()), timestamp=datetime.now(timezone.utc).isoformat(), source_agent=self.name, target_agent="Error", message_type="ERROR", payload={"error": "No text"})
        
        try:
            res = self.bridge_tool.run({"text": raw_text})
            return AgentResponse(
                id=str(uuid.uuid4()), timestamp=datetime.now(timezone.utc).isoformat(), 
                source_agent=self.name, target_agent="Data Validation Agent", 
                message_type="TASK_HANDOFF", payload=res, context_id=inputs.get("context_id")
            )
        except Exception as e:
            return AgentResponse(id=str(uuid.uuid4()), timestamp=datetime.now(timezone.utc).isoformat(), source_agent=self.name, target_agent="Error", message_type="ERROR", payload={"error": str(e)})

    def process(self, inputs: Dict[str, Any]) -> AgentResponse:
        import asyncio
        return asyncio.run(self.process_async(inputs))