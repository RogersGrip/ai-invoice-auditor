import json
import boto3
from typing import Any, List, Optional, Dict, Iterator
from botocore.config import Config
from langchain_core.language_models.llms import LLM
from langchain_core.callbacks.manager import CallbackManagerForLLMRun
from langchain_core.outputs import GenerationChunk
from pydantic import Field, PrivateAttr
from src.core.logger import logger

class BedrockCommandRPlus(LLM):
    """
    Custom LLM wrapper for Cohere Command R+ on AWS Bedrock (us-east-1).
    
    Fixes:
    1. Forces region to 'us-east-1'.
    2. Sends correct 'message' payload (not 'prompt').
    3. Removes 'stream' key from body (handles via API method).
    4. Sets custom read_timeout to prevent drops.
    """
    
    model_id: str = "cohere.command-r-plus-v1:0"
    region_name: str = "us-east-1"  # FORCE US-EAST-1
    model_kwargs: Dict[str, Any] = Field(default_factory=dict)
    
    # Use PrivateAttr for client to avoid Pydantic serialization issues
    _client: Any = PrivateAttr()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        
        config = Config(
            read_timeout=300,
            connect_timeout=10,
            retries={"max_attempts": 3}
        )
        
        # Explicitly use the requested region
        self._client = boto3.client(
            "bedrock-runtime", 
            region_name=self.region_name,
            config=config
        )

    @property
    def _llm_type(self) -> str:
        return "bedrock-command-r-plus"

    def _call(
        self,
        prompt: str,
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> str:
        """Synchronous Call"""
        params = {**self.model_kwargs, **kwargs}
        body = self._prepare_payload(prompt, params)

        try:
            response = self._client.invoke_model(
                modelId=self.model_id,
                body=json.dumps(body)
            )
            response_body = json.loads(response["body"].read())
            return response_body.get("text", "")
        except Exception as e:
            logger.error(f"Command R+ Sync Failed: {e}")
            raise e

    def _stream(
        self,
        prompt: str,
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> Iterator[GenerationChunk]:
        """Streaming Call"""
        params = {**self.model_kwargs, **kwargs}
        body = self._prepare_payload(prompt, params)

        try:
            response = self._client.invoke_model_with_response_stream(
                modelId=self.model_id,
                body=json.dumps(body)
            )

            for event in response.get("body", []):
                chunk = event.get("chunk")
                if chunk:
                    chunk_json = json.loads(chunk.get("bytes").decode())
                    text_chunk = chunk_json.get("text", "")
                    
                    if not text_chunk and "generations" in chunk_json:
                         text_chunk = chunk_json["generations"][0].get("text", "")
                    
                    if text_chunk:
                        chunk_obj = GenerationChunk(text=text_chunk)
                        if run_manager:
                            run_manager.on_llm_new_token(text_chunk, chunk=chunk_obj)
                        yield chunk_obj
                        
        except Exception as e:
            logger.error(f"Command R+ Stream Failed: {e}")
            raise e

    def _prepare_payload(self, prompt: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Construct correct payload for Command R+"""
        # Remove keys that cause ValidationException on Bedrock
        params.pop("stream", None) 
        
        return {
            "message": prompt, # Command R+ uses 'message', not 'prompt'
            "max_tokens": params.get("max_tokens", 4000),
            "temperature": params.get("temperature", 0.0),
        }