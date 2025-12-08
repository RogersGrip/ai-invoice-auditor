from typing import Dict, Any
import uuid
from datetime import datetime, timezone
from src.core.protocol import Agent, AgentResponse
from src.core.logger import logger
from src.tools.tools import DataCompletenessCheckerTool

class DataValidationAgent(Agent):
    name = "Data Validation Agent"
    description = "Checks for missing mandatory fields."

    def __init__(self):
        self.checker_tool = DataCompletenessCheckerTool()

    def process(self, inputs: Dict[str, Any]) -> AgentResponse:
        self.start_as_current_observation(inputs)
        
        data = inputs.get("extracted_data") or inputs.get("payload", {}).get("extracted_data")
        
        if not data:
            return AgentResponse(
                id=str(uuid.uuid4()),
                timestamp=datetime.now(timezone.utc).isoformat(),
                source_agent=self.name,
                target_agent="Error",
                message_type="ERROR",
                payload={"error": "No data"}
            )

        logger.info(f"[{self.name}] Validating completeness...")
        try:
            result = self.checker_tool.run(data)
            return AgentResponse(
                id=str(uuid.uuid4()),
                timestamp=datetime.now(timezone.utc).isoformat(),
                source_agent=self.name,
                target_agent="Business Validation Agent",
                message_type="TASK_HANDOFF",
                payload={
                    "validated_data": data,
                    "validation_status": result.get("validation_status"),
                    "missing_fields": result.get("missing_fields", [])
                },
                context_id=inputs.get("context_id")
            )
        except Exception as e:
            logger.error(f"Validation Error: {e}")
            return AgentResponse(
                id=str(uuid.uuid4()),
                timestamp=datetime.now(timezone.utc).isoformat(),
                source_agent=self.name,
                target_agent="Error",
                message_type="ERROR",
                payload={"error": str(e)}
            )