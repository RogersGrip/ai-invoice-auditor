from typing import Dict, Any, List
from src.core.protocol import Agent, AgentResponse
from src.database.qdrant_db import vector_store
from src.core.logger import logger

class RetrievalAgent(Agent):
    name = "Retrieval Agent"
    description = "Retrieves semantic context from the Vector DB."

    def process(self, inputs: Dict[str, Any]) -> AgentResponse:
        query = inputs.get("query")
        filename = inputs.get("filename") # Optional filtering
        
        if not query:
             return AgentResponse(content=[], metadata={"error": "No query provided"})

        logger.info(f"Retrieval Agent: Searching for '{query}' (Filter: {filename})")
        
        # Initial Retrieval (Top-K)
        try:
            results = vector_store.search(query, limit=5, filename=filename)
        except Exception as e:
            logger.error(f"Retrieval Error: {e}")
            results = []
            
        logger.info(f"Retrieval Agent: Found {len(results)} matches.")
        for i, r in enumerate(results):
             logger.info(f"Hit {i+1}: {r.get('metadata', {}).get('filename')} (Score: {r.get('score', 0):.4f})")
             
        return AgentResponse(
            content=results,
            metadata={"count": len(results)}
        )
