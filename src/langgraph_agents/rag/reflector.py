from typing import Dict, Any
import uuid
from datetime import datetime
from src.core.protocol import Agent, AgentResponse
from src.core.config import settings
from src.core.logger import logger
from src.tools.tools import RAGEvaluatorTool
import json

class ReflectionAgent(Agent):
    name = "Reflection Agent"
    description = "Evaluates the generated response for Hallucination and Relevance."

    def __init__(self):
        self.evaluator_tool = RAGEvaluatorTool()

    def process(self, inputs: Dict[str, Any]) -> AgentResponse:
        self.start_as_current_observation(inputs)
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

        logger.info("Reflection Agent: Evaluating Response Quality (All Metrics)")
        try:
            content_str = self.evaluator_tool.run(question, answer, context)
            try:
                metrics = json.loads(content_str)
            except:
                metrics = {"error": "JSON Parse Error"}

            # Check for failure or zero scores
            is_zero_score = False
            try:
                if isinstance(metrics, dict):
                    vals = [v for k, v in metrics.items() if isinstance(v, (int, float))]
                    if vals and all(v == 0.0 for v in vals):
                        is_zero_score = True
            except: pass

            if "error" in metrics or is_zero_score:
                logger.warning(f"Ragas evaluation failed or returned zeros. Metrics: {metrics}")
                metrics["status"] = "Evaluation Failed"
            else:
                metrics["status"] = "Evaluation Successful"

            logger.info(f"Reflection Metrics: {metrics}")

            return AgentResponse(
                id=str(uuid.uuid4()),
                source_agent=self.name,
                timestamp=datetime.now().isoformat(),
                target_agent="End",
                message_type="RESPONSE",
                payload={"answer": answer, "evaluation": json.dumps(metrics)},
                context_id=inputs.get("context_id")
            )

        except Exception as e:
            logger.warning(f"Reflection critical failure: {e}")
            dummy = {
                "faithfulness": 0.0, 
                "answer_relevancy": 0.0,
                "reasoning": f"Eval Failed: {e}"
            }
            return AgentResponse(
                id=str(uuid.uuid4()),
                source_agent=self.name,
                timestamp=datetime.now().isoformat(),
                target_agent="End",
                message_type="RESPONSE",
                payload={"answer": answer, "evaluation": json.dumps(dummy)},
                context_id=inputs.get("context_id")
            )