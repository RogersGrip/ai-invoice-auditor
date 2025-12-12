# ===== FILE: src/core/llm_wrapper.py =====
import os
from typing import Any, List, Optional
from langchain_aws import ChatBedrockConverse
from langchain_core.language_models.chat_models import BaseChatModel
from src.core.config import settings
from src.core.logger import logger

class BedrockLLMService:
    def __init__(self, model_id: str = None, temperature: Optional[float] = None):
        # 1. Resolve Model ID
        raw_model = model_id or settings.VALIDATION_MODEL
        self.model_id = raw_model.replace("bedrock/", "").replace("bedrock_converse/", "")
        
        # 2. Set Parameters (Matching your working temp.py)
        self.temperature = temperature if temperature is not None else 0.7
        self.region_name = "us-east-1"
        self.max_tokens = 4096

        # 3. Initialize
        self._llm = ChatBedrockConverse(
            model=self.model_id,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            region_name=self.region_name
        )

    def get_llm(self) -> BaseChatModel:
        return self._llm

    def invoke(self, prompt: str) -> str:
        try:
            # Simple wrapper for text generation
            response = self._llm.invoke(prompt)
            return str(response.content)
        except Exception as e:
            logger.error(f"Bedrock Invoke Failed ({self.model_id}): {e}")
            raise e

    def bind_tools(self, tools: List[Any]):
        return self._llm.bind_tools(tools)