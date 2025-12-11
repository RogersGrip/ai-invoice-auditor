import os
from typing import Any, List
from langchain_aws import ChatBedrockConverse
from langchain_core.language_models.chat_models import BaseChatModel
from src.core.config import settings
from src.core.logger import logger

class BedrockLLMService:
    def __init__(self, model_id: str = None, temperature: float = 0.0):
        self.model_id = model_id or settings.VALIDATION_MODEL
        self.temperature = temperature
        self._llm = ChatBedrockConverse(
            model=self.model_id,
            temperature=self.temperature,
            max_tokens=4096,
            region_name=os.getenv("AWS_DEFAULT_REGION", "us-east-1")
        )

    def get_llm(self) -> BaseChatModel:
        return self._llm

    def invoke(self, prompt: str) -> str:
        try:
            response = self._llm.invoke(prompt)
            return response.content
        except Exception as e:
            logger.error(f"Bedrock Invoke Failed: {e}")
            raise e

    def bind_tools(self, tools: List[Any]):
        return self._llm.bind_tools(tools)