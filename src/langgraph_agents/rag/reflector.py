from typing import Dict, Any
import uuid
from datetime import datetime
from src.core.protocol import Agent, AgentResponse
from src.core.config import settings
from src.core.logger import logger
from src.tools.tools import RAGEvaluatorTool

class ReflectionAgent(Agent):
    name = "Reflection Agent"
    description = "Evaluates the generated response for Hallucination and Relevance."

    def __init__(self):
        self.evaluator_tool = RAGEvaluatorTool()

    def process(self, inputs: Dict[str, Any]) -> AgentResponse:
        """
        Evaluates: Answer Relevance, Context Relevance, Groundedness.
        """
        payload = inputs.get("payload", {})
        question = inputs.get("query") or payload.get("query")
        answer = inputs.get("answer") or payload.get("answer")
        context = inputs.get("context") or payload.get("context")
        
        if not all([question, answer, context]):
             return AgentResponse(
                 id=str(uuid.uuid4()),
                 source_agent=self.name,
                 timestamp=datetime.now().isoformat(),
                 target_agent="Error Handler",
                 message_type="ERROR",
                 payload={"error": "Missing inputs for reflection"},
                 context_id=inputs.get("context_id")
             )

        logger.info("Reflection Agent: Evaluating Response Quality (5 Metrics)")

        try:
            content = self.evaluator_tool.run(question, answer, context)
                
            return AgentResponse(
                id=str(uuid.uuid4()),
                source_agent=self.name,
                timestamp=datetime.now().isoformat(),
                target_agent="End",
                message_type="RESPONSE",
                payload={"answer": answer, "evaluation": content},
                context_id=inputs.get("context_id")
            )
            
        except Exception as e:
            logger.warning(f"Reflection failed: {e}")
            # Return dummy metrics on failure so UI doesn't break
            dummy = {
                "context_precision": 0.0, "context_recall": 0.0, 
                "faithfulness": 0.0, "answer_relevance": 0.0, 
                "context_entity_recall": 0.0, "reasoning": f"Eval Failed: {e}"
            }
            return AgentResponse(
                 id=str(uuid.uuid4()),
                 source_agent=self.name,
                 timestamp=datetime.now().isoformat(),
                 target_agent="End",
                 message_type="RESPONSE",
                 payload={"answer": answer, "evaluation": str(dummy)},
                 context_id=inputs.get("context_id")
             )
