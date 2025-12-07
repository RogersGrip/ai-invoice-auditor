from typing import Dict, Any
from litellm import completion
from src.core.protocol import Agent, AgentResponse
from src.core.config import settings
from src.core.logger import logger

class ReflectionAgent(Agent):
    name = "Reflection Agent"
    description = "Evaluates the generated response for Hallucination and Relevance."

    def process(self, inputs: Dict[str, Any]) -> AgentResponse:
        """
        Evaluates: Answer Relevance, Context Relevance, Groundedness.
        """
        question = inputs.get("query")
        answer = inputs.get("answer")
        context = inputs.get("context")
        
        if not all([question, answer, context]):
            return AgentResponse(content="{'error': 'Missing Inputs'}", metadata={"score": 0.0})

        logger.info("Reflection Agent: Evaluating Response Quality (5 Metrics)")

        # Full Ragas-style Metrics Prompt
        prompt = f"""
        You are an expert RAG Evaluator. Rate the following interaction on a scale of 0.0 to 1.0.
        
        CONTEXT: {context[:2000]}
        
        USER QUESTION: {question}
        AI ANSWER: {answer}
        
        Calculate the following 5 metrics:
        1. Context Precision: (Are the retrieved chunks relevant to the query?)
        2. Context Recall: (Did we retrieve all necessary info?)
        3. Faithfulness: (Is the answer derived purely from context?)
        4. Answer Relevance: (Does it directly answer the user?)
        5. Context Entity Recall: (Did we capture specific entities like IDs/Dates?)
        
        Return ONLY a JSON object with keys: 
        "context_precision", "context_recall", "faithfulness", "answer_relevance", "context_entity_recall", "reasoning".
        """
        
        try:
            model = settings.VALIDATION_MODEL
            if settings.MODEL_PROVIDER == "ollama":
                model = f"ollama/{settings.OLLAMA_MODEL}"

            response = completion(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                format="json" # Force JSON if supported by provider
            )
            
            content = response.choices[0].message.content
            
            # Clean up markdown
            if "```" in content:
                content = content.replace("```json", "").replace("```", "").strip()
                
            return AgentResponse(
                content=content,
                metadata={"evaluation_model": model}
            )
            
        except Exception as e:
            logger.warning(f"Reflection failed: {e}")
            # Return dummy metrics on failure so UI doesn't break
            dummy = {
                "context_precision": 0.0, "context_recall": 0.0, 
                "faithfulness": 0.0, "answer_relevance": 0.0, 
                "context_entity_recall": 0.0, "reasoning": f"Eval Failed: {e}"
            }
            return AgentResponse(content=str(dummy), metadata={"error": str(e)})
