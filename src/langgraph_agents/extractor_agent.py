import uuid
from typing import Dict, Any
from datetime import datetime, timezone
from src.core.protocol import Agent, AgentResponse
from src.core.logger import logger
from src.tools.tools import DataHarvesterTool

class ExtractorAgent(Agent):
    name = "Extractor Agent"
    description = "Extracts raw text from documents using Data Harvester Tool."

    def __init__(self):
        self.harvester_tool = DataHarvesterTool()

    def process(self, inputs: Dict[str, Any]) -> AgentResponse:
        self.start_as_current_observation(inputs)
        
        file_path = inputs.get("file_path")
        metadata = inputs.get("metadata", {})
        
        if not file_path:
            return AgentResponse(
                id=str(uuid.uuid4()),
                timestamp=datetime.now(timezone.utc).isoformat(),
                source_agent=self.name,
                target_agent="Error Handler",
                message_type="ERROR",
                payload={"error": "File path missing"},
                context_id=inputs.get("context_id")
            )

        logger.info(f"Extractor Agent: Processing {file_path}")

        try:
            # 1. Run Extraction
            raw_text = self.harvester_tool.run(file_path)
            
            # 2. Return Result
            return AgentResponse(
                id=str(uuid.uuid4()),
                timestamp=datetime.now(timezone.utc).isoformat(),
                source_agent=self.name,
                target_agent="Safety Agent", # Hand off to Safety next
                message_type="TASK_HANDOFF",
                payload={
                    "raw_text": raw_text,
                    "file_path": file_path,
                    "metadata": metadata
                },
                context_id=inputs.get("context_id")
            )

        except Exception as e:
            logger.error(f"Extraction Error: {e}")
            return AgentResponse(
                id=str(uuid.uuid4()),
                timestamp=datetime.now(timezone.utc).isoformat(),
                source_agent=self.name,
                target_agent="Error Handler",
                message_type="ERROR",
                payload={"error": str(e)},
                context_id=inputs.get("context_id")
            )