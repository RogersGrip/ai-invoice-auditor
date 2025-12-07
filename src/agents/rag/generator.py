import os
from typing import Dict, Any
from litellm import completion
from src.core.protocol import Agent, AgentResponse
from src.core.config import settings
from src.core.logger import logger
from langfuse import observe

class GenerationAgent(Agent):
    name = "Generation Agent"
    description = "Generates natural language answers using retrieved context."

    @observe(name="GenerationAgent.process")
    def process(self, inputs: Dict[str, Any]) -> AgentResponse:
        query = inputs.get("query")
        context = inputs.get("context", "")
        
        if not query:
             return AgentResponse(content="No query provided.")
        
        system_prompt = """You are an expert AI Invoice Auditor Assistant.
        Answer the user's question using ONLY the provided context.
        If the answer is not in the context, say "I don't have enough information in the provided documents."
        Include citations to filenames if possible.
        """
        
        user_prompt = f"""
        CONTEXT:
        {context}
        
        QUESTION: {query}
        
        ANSWER:
        """
        
        try:
            model = settings.REPORTING_MODEL
            if settings.MODEL_PROVIDER == "ollama":
                model = f"ollama/{settings.OLLAMA_MODEL}"
            
            logger.info(f"Generation Agent: Synthesizing answer using {model}")
            
            response = completion(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ]
            )
            
            output = response.choices[0].message.content
            
            return AgentResponse(
                content=output,
                metadata={"model": model}
            )
            
        except Exception as e:
            logger.error(f"Generation failed: {e}")
            return AgentResponse(content=f"Error processing request: {e}", metadata={"error": str(e)})
