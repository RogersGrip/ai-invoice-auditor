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
            return AgentResponse(content="Skipped Validation", metadata={"score": 0.0})

        logger.info("Reflection Agent: Evaluating Response Quality")

        # Simple Self-Reflection Prompt (Lightweight "Ragas")
        # In a real heavy setup, we would run the actual Ragas library here.
        prompt = f"""
        You are a Quality Assurance AI. Rate the quality of the following RAG interaction.
        
        CONTEXT: {context[:500]}... (truncated)
        QUESTION: {question}
        ANSWER: {answer}
        
        Evaluate on:
        1. Groundedness (Is the answer supported by context?)
        2. Relevance (Does it answer the question?)
        
        Return ONLY a JSON object: {{"groundedness": 0-1, "relevance": 0-1, "reason": "brief explanation"}}
        """
        
        try:
            model = settings.VALIDATION_MODEL
            if settings.MODEL_PROVIDER == "ollama":
                model = f"ollama/{settings.OLLAMA_MODEL}"

            response = completion(
                model=model,
                messages=[{"role": "user", "content": prompt}]
            )
            
            # Note: response_format='json_object' depends on model support. 
            # If fail, we might get text. For this prototype assuming simple string return.
            content = response.choices[0].message.content
            
            # Clean up markdown
            if "```" in content:
                content = content.replace("```json", "").replace("```", "").strip()
            return AgentResponse(
                content=content,
                metadata={"evaluation": "metrics"}
            )
            
        except Exception as e:
            logger.warning(f"Reflection failed: {e}")
            return AgentResponse(content="Reflection Error", metadata={"error": str(e)})
