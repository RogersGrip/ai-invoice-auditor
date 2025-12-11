from typing import Dict, Any, List
import uuid
from datetime import datetime
from src.core.protocol import Agent, AgentResponse
from src.core.logger import logger
from src.tools.tools import ChunkRankerTool

class AugmentationAgent(Agent):
    name = "Augmentation Agent"
    description = "Re-ranks chunks to improve context quality."

    def __init__(self):
        self.ranker_tool = ChunkRankerTool()

    def process(self, inputs: Dict[str, Any]) -> AgentResponse:
        self.start_as_current_observation(inputs)
        
        docs = inputs.get("docs") or inputs.get("retrieved_docs") or inputs.get("payload", {}).get("retrieved_docs", [])
        
        if not docs:
            return AgentResponse(
                id=str(uuid.uuid4()),
                source_agent=self.name,
                timestamp=datetime.now().isoformat(),
                target_agent="Error Handler",
                message_type="ERROR",
                payload={"error": "No docs to rank"},
                context_id=inputs.get("context_id")
            )

        logger.info(f"Augmentation Agent: Reranking {len(docs)} docs")
        # FIX: Pass dictionary args
        context_str = self.ranker_tool.run({"docs": docs})
        
        return AgentResponse(
            id=str(uuid.uuid4()),
            source_agent=self.name,
            timestamp=datetime.now().isoformat(),
            target_agent="Generation Agent",
            message_type="TASK_HANDOFF",
            payload={
                "context": context_str,
                "query": inputs.get("query") or inputs.get("payload", {}).get("query")
            },
            context_id=inputs.get("context_id")
        )