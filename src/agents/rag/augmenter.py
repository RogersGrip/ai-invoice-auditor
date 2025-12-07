from typing import Dict, Any, List
from src.core.protocol import Agent, AgentResponse
from src.core.logger import logger

class AugmentationAgent(Agent):
    name = "Augmentation Agent"
    description = "Re-ranks chunks to improve context quality."

    def process(self, inputs: Dict[str, Any]) -> AgentResponse:
        """
        Expects: 'docs' or 'retrieved_docs' (list of dicts)
        """
        docs = inputs.get("docs") or inputs.get("retrieved_docs", [])
        if not docs:
             return AgentResponse(content=[], metadata={"status": "empty"})

        logger.info(f"Augmentation Agent: Reranking {len(docs)} docs")
        
        # Simple Logic: Filter by similarity score threshold (e.g. 0.7)
        # In production this would call a Cross-Encoder
        ranked_docs = sorted(docs, key=lambda x: x.get('score', 0), reverse=True)
        
        # Reranked Context String Construction
        context_str = "\n---\n".join([
            f"[Source: {d['metadata'].get('filename')} (Score: {d.get('score'):.2f})]\n{d.get('text')}"
            for d in ranked_docs
        ])
        
        return AgentResponse(
            content=context_str,
            metadata={
                "top_score": ranked_docs[0].get('score') if ranked_docs else 0,
                "used_docs": len(ranked_docs)
            }
        )
