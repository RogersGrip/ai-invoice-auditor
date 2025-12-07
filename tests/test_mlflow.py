import sys
import os
from loguru import logger

# Add project root to sys.path
sys.path.append(os.getcwd())

from src.core.config import settings
from src.langgraph_agents.rag.mlflow_evaluator import MLflowEvaluator

def test_mlflow_flow():
    logger.info(">>> Testing MLflow GenAI Evaluation <<<")
    
    # Ensure provider is ollama
    settings.MODEL_PROVIDER = "ollama"
    settings.OLLAMA_MODEL = "llama3:8b" 
    
    # Mock Data
    query = "What is the invoice number?"
    answer = "The invoice number is INV-2023-001."
    context = "Invoice Number: INV-2023-001\nDate: 2023-01-01"
    
    logger.info(f"Query: {query}")
    
    try:
        evaluator = MLflowEvaluator()
        metrics = evaluator.evaluate(query, answer, context)
        
        logger.info("--- Evaluation Results ---")
        print(f"DEBUG METRICS: {metrics}")
        
        # Check for ANY key being present AND value > 0
        has_score = False
        for k, v in metrics.items():
            if isinstance(v, (int, float)) and v > 0:
                has_score = True
                break
        
        if has_score:
             logger.success("✔ MLflow Evaluation PASSED (With Non-Zero Scores)")
        else:
             logger.error("✘ MLflow Evaluation FAILED (All Scores are 0.0 or Missing)")
            
    except Exception as e:
        logger.error(f"MLflow Test Crash: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_mlflow_flow()
