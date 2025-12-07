import os
import mlflow
import pandas as pd
from typing import Dict, Any, List
from src.core.config import settings
from src.core.logger import logger
from mlflow.metrics.genai import (
    answer_relevance,
    faithfulness,
    relevance,
    make_genai_metric
)

class MLflowEvaluator:
    """
    Evaluates RAG performance using MLflow's LLM-as-a-Judge capabilities.
    """
    
    def __init__(self):
        self.experiment_name = "RAG_Evaluation_Ollama"
        mlflow.set_experiment(self.experiment_name)
        
        # Configure the judge model connection string
        # mlflow.genai.evaluate uses OpenAI-compatible strings usually
        # For Ollama, we might need to point it to a proxy or use 'openai:/...' with base_url
        self.model_name = settings.VALIDATION_MODEL
        if settings.MODEL_PROVIDER == "ollama":
             # Fix: Remove extra 'ollama/' prefix. The model name in Ollama is just 'llama3:8b' etc.
             # The 'openai:/' prefix is for MLflow to know which flavor to use.
             self.model_conf = f"openai:/{settings.OLLAMA_MODEL}"
        else:
            self.model_conf = "openai:/gpt-4o"

    
    def evaluate(self, query: str, answer: str, context: str) -> Dict[str, Any]:
        """
        Runs the evaluation suite manually using LiteLLM to ensure robustness.
        """
        logger.info("Starting MLflow GenAI Evaluation (Manual Mode)...")
        from litellm import completion
        import re

        scores = {}
        
        # Helper to run a metric
        def run_metric(name, prompt_template):
            try:
                # Format Prompt
                prompt = prompt_template.format(query=query, answer=answer, context=context)
                
                # Call LLM
                model = settings.VALIDATION_MODEL
                if settings.MODEL_PROVIDER == "ollama":
                    model = f"ollama/{settings.OLLAMA_MODEL}"

                response = completion(
                     model=model,
                     messages=[{"role": "user", "content": prompt}]
                )
                content = response.choices[0].message.content
                
                # Parse Score (Look for simple number 1-5)
                # We ask for JSON or specific format, but regex finding the last digit is robust enough usually
                # or finding "Score: X"
                match = re.search(r"Score:\s*(\d)", content)
                if match:
                    score = int(match.group(1))
                else:
                    # Fallback: look for just a digit
                    match = re.search(r"\b([1-5])\b", content)
                    score = int(match.group(1)) if match else 0
                
                return max(0, min(5, score)) # Clamp 0-5
            except Exception as e:
                logger.warning(f"Metric {name} failed: {e}")
                return 0

        # Define Prompts
        faithfulness_prompt = (
            "You are an impartial judge. Evaluate the 'Faithfulness' of the answer based on the context.\n"
            "Faithfulness definition: The answer must be derived ONLY from the context. No outside info.\n"
            "Context: {context}\n"
            "Answer: {answer}\n"
            "Provide a score from 1 to 5, where 1 is Hallucinated/Contradictory and 5 is Fully Supported.\n"
            "Format your response as: 'Reasoning: ... Score: <number>'"
        )
        
        relevance_prompt = (
            "You are an impartial judge. Evaluate the 'Answer Relevance' of the answer to the query.\n"
            "Query: {query}\n"
            "Answer: {answer}\n"
            "Provide a score from 1 to 5, where 1 is Irrelevant and 5 is Highly Relevant.\n"
            "Format your response as: 'Reasoning: ... Score: <number>'"
        )

        try:
            with mlflow.start_run(run_name=f"eval_{query[:10]}"):
                # Compute Scores
                f_score = run_metric("faithfulness", faithfulness_prompt)
                r_score = run_metric("answer_relevance", relevance_prompt)
                
                # Log to MLflow
                mlflow.log_metric("faithfulness", f_score)
                mlflow.log_metric("answer_relevance", r_score)
                
                # Log Inputs/Outputs
                mlflow.log_text(f"Query: {query}\nAnswer: {answer}\nContext: {context}", "eval_data.txt")
                
                scores = {
                    "faithfulness": float(f_score), # Normalize to float for tools.py
                    "answer_relevance": float(r_score),
                    # Normalize for Ragas compatibility (divide by 5 for 0-1 scale? Ragas usually is 0-1)
                    # Tools.py uses them as is, but Ragas usually outputs 0.0-1.0. 
                    # Let's normalize here to 0.0-1.0 to match Ragas expectations if UI expects that.
                    "faithfulness_normalized": f_score / 5.0,
                    "answer_relevance_normalized": r_score / 5.0
                }
                
            logger.success(f"MLflow Evaluation Complete (Manual). Scores: {scores}")
            
            # Return normalized keys matching tools.py expectation (or map them there)
            # tools.py looks for "faithfulness", let's give it the 0-1 normalized value if that's what Ragas does.
            # Ragas faithfulness is 0-1.
            return {
                "faithfulness": scores["faithfulness_normalized"],
                "answer_relevance": scores["answer_relevance_normalized"],
                "context_precision": 0.0,
                "context_recall": 0.0
            }
            
        except Exception as e:
            logger.error(f"MLflow Manual Evaluation Failed: {e}")
            return {"error": str(e), "faithfulness": 0.0}

