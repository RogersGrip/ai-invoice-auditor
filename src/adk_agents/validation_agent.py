import uuid
from typing import Dict, Any
from datetime import datetime, timezone

from src.frameworks.google_adk import ADKAgent
from src.core.protocol import AgentResponse
from src.core.logger import logger
from src.tools.tools import DataCompletenessCheckerTool

class DataValidationAgent(ADKAgent):
    def __init__(self):
        super().__init__(name="Data Validation Agent", model=None, instruction="Validate invoice data completeness.")
        self.checker_tool = DataCompletenessCheckerTool()

    def process(self, inputs: Dict[str, Any]) -> AgentResponse:
        # self.start_as_current_observation(inputs) # ADKAgent handles logging usually, but keeping flow
        
        data = inputs.get("extracted_data") or inputs.get("payload", {}).get("extracted_data")
        
        if not data:
            return AgentResponse(
                id=str(uuid.uuid4()),
                timestamp=datetime.now(timezone.utc).isoformat(),
                source_agent=self.name,
                target_agent="Error",
                message_type="ERROR",
                payload={"error": "No data to validate"}
            )
            
        logger.info(f"[{self.name}] Validating completeness...")
        try:
            # FIX: Pass dictionary args
            result = self.checker_tool.run({"invoice_data": data})
            
            return AgentResponse(
                id=str(uuid.uuid4()),
                timestamp=datetime.now(timezone.utc).isoformat(),
                source_agent=self.name,
                target_agent="Business Validation Agent",
                message_type="TASK_HANDOFF",
                payload={
                    "extracted_data": data,
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