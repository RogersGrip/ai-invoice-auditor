import uuid
import json
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
        raw_text_input = inputs.get("raw_text") # Support direct text input

        logger.info(f"Extractor Agent: Processing {file_path}")

        try:
            if raw_text_input:
                # If we already have text (e.g. from a JSON file loaded previously or passed directly)
                raw_text = raw_text_input
            elif file_path:
                # Use Tool to extract
                raw_text = self.harvester_tool.run({"file_path": file_path})
            else:
                 raise ValueError("No file_path or raw_text provided.")

            return AgentResponse(
                id=str(uuid.uuid4()),
                timestamp=datetime.now(timezone.utc).isoformat(),
                source_agent=self.name,
                target_agent="Safety Agent",
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