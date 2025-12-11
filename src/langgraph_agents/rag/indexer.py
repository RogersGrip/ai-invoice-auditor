from typing import Dict, Any
import uuid
from datetime import datetime
from src.core.protocol import Agent, AgentResponse
from src.core.logger import logger
from src.tools.tools import VectorIndexerTool

class IndexingAgent(Agent):
    name = "Indexing Agent"
    description = "Parses and indexes invoice documents into the Vector DB."

    def __init__(self):
        self.indexer_tool = VectorIndexerTool()

    def process(self, inputs: Dict[str, Any]) -> AgentResponse:
        self.start_as_current_observation(inputs)
        
        text = inputs.get("text", "")
        filename = inputs.get("filename", "unknown")
        meta = inputs.get("metadata", {})
        
        if not text:
             return AgentResponse(
                id=str(uuid.uuid4()),
                source_agent=self.name,
                timestamp=datetime.now().isoformat(),
                target_agent="Error Handler",
                message_type="ERROR",
                payload={"error": "No text to index"},
                context_id=inputs.get("context_id")
            )

        logger.info(f"Indexing Agent: Processing {filename}")
        try:
            # FIX: Pass dictionary args
            indexed_count = self.indexer_tool.run({
                "text": text, 
                "metadata": {"filename": filename, **meta}
            })
            
            logger.success(f"Indexed {indexed_count} chunks for {filename}")
            return AgentResponse(
                id=str(uuid.uuid4()),
                source_agent=self.name,
                timestamp=datetime.now().isoformat(),
                target_agent="End",
                message_type="RESPONSE",
                payload={"chunks_indexed": indexed_count, "filename": filename},
                context_id=inputs.get("context_id")
            )
        except Exception as e:
            logger.error(f"Indexing Error: {e}")
            return AgentResponse(
                id=str(uuid.uuid4()),
                source_agent=self.name,
                timestamp=datetime.now().isoformat(),
                target_agent="Error Handler",
                message_type="ERROR",
                payload={"error": str(e)},
                context_id=inputs.get("context_id")
            )