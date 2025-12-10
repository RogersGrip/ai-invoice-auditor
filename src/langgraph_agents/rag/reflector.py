from typing import Dict, Any
import uuid
import json
from datetime import datetime
from src.core.protocol import Agent, AgentResponse
from src.core.config import settings
from src.core.logger import logger
from src.tools.tools import RAGEvaluatorTool
from src.langgraph_agents.rag.mlflow_evaluator import MLflowEvaluator

class ReflectionAgent(Agent):
    name = "Reflection Agent"
    description = "Evaluates response quality using Ragas, falling back to MLflow and LLM Judge."

    def __init__(self):
        self.ragas_tool = RAGEvaluatorTool()
        self.mlflow_eval = MLflowEvaluator()

    def process(self, inputs: Dict[str, Any]) -> AgentResponse:
        self.start_as_current_observation(inputs)
        payload = inputs.get("payload", {})
        query = inputs.get("query") or payload.get("query")
        answer = inputs.get("answer") or payload.get("answer")
        context = inputs.get("context") or payload.get("context")

        if not all([query, answer, context]):
            return AgentResponse(
                id=str(uuid.uuid4()),
                source_agent=self.name,
                timestamp=datetime.now().isoformat(),
                target_agent="Error Handler",
                message_type="ERROR",
                payload={"error": "Missing inputs"},
                context_id=inputs.get("context_id")
            )

        logger.info("Reflection Agent: Evaluating Response Quality...")
        metrics = {}

        # 1. Try Ragas
        try:
            logger.info("Attempt 1: Ragas Evaluation")
            content = self.ragas_tool.run(query, answer, context)
            metrics = json.loads(content)
            
            # Check for error or zero scores indicating failure
            if "error" in metrics or all(v == 0.0 for v in metrics.values() if isinstance(v, (int, float))):
                raise ValueError("Ragas returned zeros or error.")
            
            metrics["source"] = "Ragas"
            
        except Exception as e:
            logger.warning(f"Ragas failed ({e}). Trying MLflow Fallback...")
            
            # 2. Try MLflow Fallback
            try:
                metrics = self.mlflow_eval.evaluate(query, answer, context)
                metrics["source"] = "MLflow Fallback"
            except Exception as e2:
                logger.warning(f"MLflow failed ({e2}). Using hard fallback.")
                metrics = {
                    "faithfulness": 0.5,
                    "answer_relevancy": 0.5,
                    "source": "Hard Fallback",
                    "reason": "All evaluators failed."
                }

        logger.info(f"Final Metrics: {metrics}")
        
        return AgentResponse(
            id=str(uuid.uuid4()),
            source_agent=self.name,
            timestamp=datetime.now().isoformat(),
            target_agent="End",
            message_type="RESPONSE",
            payload={"answer": answer, "evaluation": json.dumps(metrics)},
            context_id=inputs.get("context_id")
        )