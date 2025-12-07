from typing import Dict, Any, List
import uuid
from datetime import datetime
from src.core.protocol import Agent, AgentResponse
from src.core.logger import logger
from src.tools.tools import SemanticRetrieverTool

class RetrievalAgent(Agent):
    name = "Retrieval Agent"
    description = "Retrieves semantic context from the Vector DB."

    def __init__(self):
        self.retriever_tool = SemanticRetrieverTool()

    def process(self, inputs: Dict[str, Any]) -> AgentResponse:
        query = inputs.get("query")
        filename = inputs.get("filename") # Optional filtering
        
        if not query:
             return AgentResponse(
                 id=str(uuid.uuid4()),
                 source_agent=self.name,
                 timestamp=datetime.now().isoformat(),
                 target_agent="Error Handler",
                 message_type="ERROR",
                 payload={"error": "No query provided"},
                 context_id=inputs.get("context_id")
             )

        logger.info(f"Retrieval Agent: Searching for '{query}' (Filter: {filename})")
        
        try:
            results = self.retriever_tool.run(query, limit=15, filename=filename)
        except Exception as e:
            logger.error(f"Retrieval Error: {e}")
            results = []
            
        logger.info(f"Retrieval Agent: Found {len(results)} matches.")
             
        return AgentResponse(
            id=str(uuid.uuid4()),
            source_agent=self.name,
            timestamp=datetime.now().isoformat(),
            target_agent="Augmentation Agent",
            message_type="TASK_HANDOFF",
            payload={"retrieved_docs": results, "query": query},
            context_id=inputs.get("context_id")
        )
