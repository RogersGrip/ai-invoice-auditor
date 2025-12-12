# ===== FILE: src/adk_agents/validation_agent.py =====
import uuid
from typing import Dict, Any
from datetime import datetime, timezone
from src.adk_agents.base_agent import AgentADK
from src.core.protocol import AgentResponse
from src.tools.tools import DataCompletenessCheckerTool

class DataValidationAgent(AgentADK):
    def __init__(self):
        super().__init__(
            name="data_validation_agent", 
            instruction="Validate data.", 
            tools=[DataCompletenessCheckerTool()]
        )
        self.checker_tool = DataCompletenessCheckerTool()

    async def process_async(self, inputs: Dict[str, Any]) -> AgentResponse:
        data = inputs.get("extracted_data")
        if not data: return AgentResponse(id=str(uuid.uuid4()), timestamp=datetime.now(timezone.utc).isoformat(), source_agent=self.name, target_agent="Error", message_type="ERROR", payload={"error": "No data"})
        
        try:
            res = self.checker_tool.run({"invoice_data": data})
            return AgentResponse(
                id=str(uuid.uuid4()), timestamp=datetime.now(timezone.utc).isoformat(),
                source_agent=self.name, target_agent="Business Validation Agent", 
                message_type="TASK_HANDOFF",
                payload={"extracted_data": data, "validation_status": res.get("validation_status"), "missing_fields": res.get("missing_fields", [])},
                context_id=inputs.get("context_id")
            )
        except Exception as e:
            return AgentResponse(id=str(uuid.uuid4()), timestamp=datetime.now(timezone.utc).isoformat(), source_agent=self.name, target_agent="Error", message_type="ERROR", payload={"error": str(e)})

    def process(self, inputs: Dict[str, Any]) -> AgentResponse:
        import asyncio
        return asyncio.run(self.process_async(inputs))