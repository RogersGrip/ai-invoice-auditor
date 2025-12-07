from typing import Dict, Any
import uuid
from datetime import datetime
from src.core.protocol import Agent, AgentResponse
from src.core.logger import logger
from src.tools.tools import DataCompletenessCheckerTool

class DataValidationAgent(Agent):
    name = "Data Validation Agent"
    description = "Checks for missing mandatory fields and data types."

    @property
    def inputs_schema(self) -> Dict[str, Any]:
        return {
             "type": "object",
             "properties": {
                 "extracted_data": {"type": "object"}
             }
        }

    @property
    def outputs_schema(self) -> Dict[str, Any]:
        return {
             "type": "object",
             "properties": {
                 "validation_status": {"type": "string"},
                 "missing_fields": {"type": "array"}
             }
        }

    def __init__(self):
        self.checker_tool = DataCompletenessCheckerTool()

    def process(self, inputs: Dict[str, Any]) -> AgentResponse:
        self.start_as_current_observation(inputs)
        
        data = inputs.get("extracted_data")
        if not data and inputs.get("payload"):
             data = inputs["payload"].get("extracted_data")
             
        # Normalize
        if hasattr(data, "model_dump"):
            data = data.model_dump()

        if not data:
             return AgentResponse(
                 id=str(uuid.uuid4()),
                 source_agent=self.name,
                 timestamp=datetime.now().isoformat(),
                 target_agent="Error Handler",
                 message_type="ERROR",
                 payload={"error": "No data to validate"},
                 context_id=inputs.get("context_id")
             )
             
        logger.info(f"[{self.name}] Calling DataCompletenessChecker Tool...")
        
        try:
            result = self.checker_tool.run(data)
            
            is_valid = result["is_valid"]
            missing = result["missing_fields"]
            
            if not is_valid:
                logger.warning(f"Validation Issues: {missing}")
                
            return AgentResponse(
                id=str(uuid.uuid4()),
                timestamp=datetime.now().isoformat(),
                source_agent=self.name,
                target_agent="Business Validation Agent",
                message_type="TASK_HANDOFF",
                payload={
                    "extracted_data": data,
                    "validation_status": "valid" if is_valid else "invalid", 
                    "missing_fields": missing,
                    "errors": missing
                },
                context_id=inputs.get("context_id")
            )
        except Exception as e:
            logger.error(f"Validation Failed: {e}")
            return AgentResponse(
                 id=str(uuid.uuid4()),
                 source_agent=self.name,
                 timestamp=datetime.now().isoformat(),
                 target_agent="Error Handler",
                 message_type="ERROR",
                 payload={"error": str(e)},
                 context_id=inputs.get("context_id")
            )
