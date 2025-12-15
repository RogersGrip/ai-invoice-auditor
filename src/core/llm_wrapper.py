# ===== FILE: src/core/llm_wrapper.py =====
import os
from typing import Any, List, Optional
from langchain_aws import ChatBedrockConverse
from langchain_community.chat_models import ChatOllama
from langchain_core.language_models.chat_models import BaseChatModel
from src.core.config import settings
from src.core.logger import logger

class BedrockLLMService:
    def __init__(self, model_id: str = None, temperature: Optional[float] = None):
        # 1. Resolve Model ID
        raw_model = model_id or settings.VALIDATION_MODEL
        self.model_id = raw_model.replace("bedrock/", "").replace("bedrock_converse/", "")
        
        # 2. Set Parameters
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
            response = self._llm.invoke(prompt)
            return str(response.content)
        except Exception as e:
            logger.error(f"Bedrock Invoke Failed ({self.model_id}): {e}")
            raise e

    def bind_tools(self, tools: List[Any]):
        return self._llm.bind_tools(tools)

class OllamaLLMService:
    def __init__(self, model_id: str = None, temperature: Optional[float] = None):
        # 1. Resolve Model ID
        self.model_id = model_id or settings.OLLAMA_MODEL
        self.base_url = settings.OLLAMA_BASE_URL
        self.temperature = temperature if temperature is not None else 0.7

        # 2. Initialize
        self._llm = ChatOllama(
            model=self.model_id,
            base_url=self.base_url,
            temperature=self.temperature
        )

    def get_llm(self) -> BaseChatModel:
        return self._llm

    def invoke(self, prompt: str) -> str:
        try:
            response = self._llm.invoke(prompt)
            return str(response.content)
        except Exception as e:
            logger.error(f"Ollama Invoke Failed ({self.model_id}): {e}")
            raise e

    def bind_tools(self, tools: List[Any]):
        return self._llm.bind_tools(tools)

class LLMService:
    def __init__(self, model_id: str = None, temperature: Optional[float] = None):
        self.provider = settings.MODEL_PROVIDER
        
        if self.provider == "ollama":
            self.service = OllamaLLMService(model_id, temperature)
        else:
            self.service = BedrockLLMService(model_id, temperature)
            
    def get_llm(self) -> BaseChatModel:
        return self.service.get_llm()
        
    def invoke(self, prompt: str) -> str:
        return self.service.invoke(prompt)
        
    def bind_tools(self, tools: List[Any]):
        return self.service.bind_tools(tools)