import uuid
from typing import Dict, Any
from datetime import datetime, timezone

from src.frameworks.google_adk import ADKAgent
from src.core.protocol import AgentResponse
from src.core.logger import logger
from src.tools.tools import InsightReporterTool

class ReportingAgent(ADKAgent):
    def __init__(self):
        super().__init__(name="Reporting Agent", model=None, instruction="Generate final reports.")
        self.reporter_tool = InsightReporterTool()

    def process(self, inputs: Dict[str, Any]) -> AgentResponse:
        file_name = inputs.get("file_name", "report")
        
        try:
            # FIX: Pass dictionary args
            output_paths = self.reporter_tool.run({
                "file_name": file_name,
                "extracted_data": inputs.get("extracted_data", {}),
                "validation_report": inputs.get("validation_results", {}),
                "safety_report": inputs.get("safety_report", {}),
                "metadata": inputs.get("metadata", {})
            })
            
            return AgentResponse(
                id=str(uuid.uuid4()),
                source_agent=self.name,
                target_agent="Ingestion",
                timestamp=datetime.now(timezone.utc).isoformat(),
                message_type="RESPONSE",
                payload=output_paths,
                context_id=inputs.get("context_id")
            )
        except Exception as e:
            logger.error(f"Reporting Error: {e}")
            return AgentResponse(
                id=str(uuid.uuid4()),
                timestamp=datetime.now(timezone.utc).isoformat(),
                source_agent=self.name,
                target_agent="Error",
                message_type="ERROR",
                payload={"error": str(e)}
            )