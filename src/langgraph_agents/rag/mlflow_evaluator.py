import json
import re
from typing import Dict, Any
from src.core.llm_wrapper import LLMService
from src.core.config import settings
from src.core.logger import logger

class MLflowEvaluator:
    """
    Fallback evaluator using LLM-as-a-Judge when Ragas is unavailable or fails.
    Simulates MLflow's GenAI evaluation metrics.
    """
    def __init__(self):
        # Replaced BedrockCommandRPlus with LLMService
        self.llm_service = LLMService(
            model_id=settings.VALIDATION_MODEL,
            temperature=0.0
        )

    def evaluate(self, query: str, answer: str, context: str) -> Dict[str, Any]:
        logger.info("Starting MLflow Fallback Evaluation...")
        
        faithfulness_prompt = f"""
        You are an expert evaluator.
        Rate the faithfulness of the answer to the context on a scale of 0.0 to 1.0.
        
        Context: {context}
        Answer: {answer}
        
        Output ONLY a JSON object with keys "score" and "reason".
        Example: {{"score": 0.8, "reason": "Matches context mostly."}}
        
        JSON:
        """
        
        relevance_prompt = f"""
        You are an expert evaluator.
        Rate the relevance of the answer to the query on a scale of 0.0 to 1.0.
        
        Query: {query}
        Answer: {answer}
        
        Output ONLY a JSON object with keys "score" and "reason".
        Example: {{"score": 0.9, "reason": "Directly answers the question."}}
        
        JSON:
        """
        
        scores = {}
        try:
            # Use invoke method
            resp_f = self.llm_service.invoke(faithfulness_prompt)
            data_f = self._parse_json(resp_f)
            scores["faithfulness"] = data_f.get("score", 0.0)

            resp_r = self.llm_service.invoke(relevance_prompt)
            data_r = self._parse_json(resp_r)
            scores["answer_relevancy"] = data_r.get("score", 0.0)
            
            # Placeholders for metrics harder to calculate with simple prompting
            scores["context_precision"] = 0.0
            scores["context_recall"] = 0.0
            scores["status"] = "MLflow Fallback"
            
            return scores
        except Exception as e:
            logger.error(f"MLflow Evaluator Failed: {e}")
            return {
                "faithfulness": 0.0,
                "answer_relevancy": 0.0,
                "error": f"Fallback Failed: {e}"
            }

    def _parse_json(self, text: str) -> Dict:
        try:
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                return json.loads(match.group(0))
        except:
            pass
        return {"score": 0.0}