from typing import Dict, Any
import uuid
import os
from datetime import datetime
from src.core.protocol import Agent, AgentResponse
from src.core.logger import logger
from src.tools.tools import InsightReporterTool

class ReportingAgent(Agent):
    name = "Reporting Agent"
    description = "Aggregates all findings and generates a final report."

    @property
    def inputs_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "validated_data": {"type": "object"},
                "discrepancies": {"type": "array"}
            }
        }

    @property
    def outputs_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "report_paths": {"type": "object"}
            }
        }

    def __init__(self):
        self.reporter_tool = InsightReporterTool()

    def process(self, inputs: Dict[str, Any]) -> AgentResponse:
        self.start_as_current_observation(inputs)
        
        payload = inputs.get("payload", {})
        
        extracted_data = payload.get("validated_data") or inputs.get("extracted_data", {})
        validation_report = {
            "business_status": payload.get("business_validation_status"),
            "discrepancies": payload.get("discrepancies", []),
            "is_valid": payload.get("business_validation_status") == "match"
        }
        
        if not extracted_data:
             extracted_data = inputs.get("extracted_data", {})
             
        file_path = inputs.get("file_path") or payload.get("file_path", "unknown_report")
        file_name = os.path.basename(file_path)
        metadata = inputs.get("metadata", {})
        
        logger.info(f"[{self.name}] Calling Insight Reporter Tool...")
        
        try:
            output_paths = self.reporter_tool.run(
                file_name=file_name,
                extracted_data=extracted_data,
                validation_report=validation_report,
                metadata=metadata
            )
            
            return AgentResponse(
                id=str(uuid.uuid4()),
                source_agent=self.name,
                target_agent="End",
                timestamp=datetime.now().isoformat(),
                message_type="RESPONSE",
                payload={
                    "json_report": output_paths.get("json"),
                    "pdf_report": output_paths.get("pdf"),
                    "summary": "Reports generated successfully."
                },
                context_id=inputs.get("context_id")
            )
            
        except Exception as e:
            logger.error(f"Reporting Failed: {e}")
            return AgentResponse(
                 id=str(uuid.uuid4()),
                 source_agent=self.name,
                 timestamp=datetime.now().isoformat(),
                 target_agent="Error Handler",
                 message_type="ERROR",
                 payload={"error": str(e)},
                 context_id=inputs.get("context_id")
            )
