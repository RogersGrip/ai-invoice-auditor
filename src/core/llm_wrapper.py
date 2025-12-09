import json
from typing import Any, List, Optional, Dict
from langchain_aws import BedrockLLM
from langchain_core.callbacks.manager import CallbackManagerForLLMRun
from src.core.logger import logger

class BedrockCommandRPlus(BedrockLLM):
    """
    Specialized wrapper for Cohere Command R+ on Bedrock.
    Inherits auth/client from BedrockLLM but fixes the payload structure
    to use 'message' instead of 'prompt', resolving ValidationException.
    """
    
    def _call(
        self,
        prompt: str,
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> str:
        # Prepare parameters
        params = {**self.model_kwargs, **kwargs}
        temperature = params.get("temperature", 0.0)
        max_tokens = params.get("max_tokens", 4000)

        # Construct the CORRECT payload for Command R+
        # It expects "message" key, NOT "prompt"
        body = json.dumps({
            "message": prompt,
            "max_tokens": max_tokens,
            "temperature": temperature,
            # stream=False is default
        })

        try:
            # Reuse the client that BedrockLLM already instantiated (with correct credentials)
            response = self.client.invoke_model(
                modelId=self.model_id,
                body=body
            )
            response_body = json.loads(response["body"].read())
            
            # Cohere R+ returns 'text' in the response
            return response_body.get("text", "")
            
        except Exception as e:
            logger.error(f"BedrockCommandRPlus Invocation Failed: {e}")
            raise e