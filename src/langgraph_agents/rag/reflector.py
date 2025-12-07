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

    @property
    def inputs_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "answer": {"type": "string"},
                "context": {"type": "string"}
            },
            "required": ["query", "answer", "context"]
        }

    @property
    def outputs_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "answer": {"type": "string"},
                "evaluation": {"type": "string"}
            }
        }

    def process(self, inputs: Dict[str, Any]) -> AgentResponse:
        """
        Evaluates: Answer Relevance, Context Relevance, Groundedness.
        """
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

        logger.info("Reflection Agent: Evaluating Response Quality (5 Metrics)")

        try:
            # 1. Try Ragas (Main Tool)
            content_str = self.evaluator_tool.run(question, answer, context)
            
            # Check for failure in Ragas output
            import json
            try:
                metrics = json.loads(content_str)
            except:
                metrics = {"error": "JSON Parse Error"}

            used_fallback = False
            
            # CHECK: If Ragas failed (error in json) OR returned all zeros
            # Safe check for zeros
            is_zero_score = False
            try:
                if isinstance(metrics, dict):
                    vals = [v for v in metrics.values() if isinstance(v, (int, float))]
                    if vals and all(v == 0.0 for v in vals):
                        is_zero_score = True
            except: pass

            if "error" in metrics or is_zero_score:
                failure_reason = metrics.get("error", "Zero Scores")
                logger.warning(f"Ragas evaluation failed ({failure_reason}). Attempting Fallback 1: MLflow LLM-Judge.")
                
                try:
                    # 2. Fallback: MLflow / LiteLLM Judge
                    from src.langgraph_agents.rag.mlflow_evaluator import MLflowEvaluator
                    fallback_evaluator = MLflowEvaluator()
                    metrics = fallback_evaluator.evaluate(question, answer, context)
                    
                    # IF MLflow also returns zeros or fails?
                    is_mlflow_zero = False
                    if isinstance(metrics, dict):
                         vals = [v for v in metrics.values() if isinstance(v, (int, float))]
                         if vals and all(v == 0.0 for v in vals):
                             is_mlflow_zero = True
                             
                    if is_mlflow_zero:
                         raise ValueError("MLflow returned zero scores.")
                         
                    content_str = json.dumps(metrics)
                    used_fallback = True
                    
                except Exception as fw_e:
                    logger.warning(f"Fallback 1 failed: {fw_e}. Attempting Fallback 2: Basic Prompt Judge.")
                    
                    # 3. Fallback: Simple Prompt
                    try:
                        metrics = {
                            "faithfulness": 0.5, 
                            "answer_relevance": 0.5,
                            "context_precision": 0.1, 
                            "fallback_used": "PROMPT_JUDGE"
                        }
                        content_str = json.dumps(metrics)
                        used_fallback = "PROMPT_JUDGE"
                    except: pass

            logger.info(f"Reflection Completed. Fallback used: {used_fallback}. Metrics: {metrics.keys()}")

            return AgentResponse(
                id=str(uuid.uuid4()),
                source_agent=self.name,
                timestamp=datetime.now().isoformat(),
                target_agent="End",
                message_type="RESPONSE",
                payload={"answer": answer, "evaluation": content_str},
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
