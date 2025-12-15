from typing import Dict, Any, Optional
from pydantic import BaseModel
from a2a.types import (
    Task,
    TaskStatus,
    TaskState,
    Message,
    Role,
    Part,
    DataPart,
    FilePart,
    Artifact,
    AgentCard,
    AgentCapabilities,
    AgentSkill,
    AgentProvider,
    SendMessageRequest,
    SendMessageResponse
)
from a2a.client import A2AClient as BaseA2AClient
from abc import ABC, abstractmethod

class AgentResponse(BaseModel):
    id: str
    timestamp: str
    source_agent: str
    target_agent: str
    message_type: str
    payload: Dict[str, Any]
    context_id: Optional[str] = None

class Agent(ABC):
    @property
    @abstractmethod
    def name(self) -> str: pass
    
    @abstractmethod
    def process(self, inputs: Dict[str, Any]) -> AgentResponse: pass

    def start_as_current_observation(self, inputs: Dict[str, Any]):
        from src.core.logger import logger
        logger.info(f"[{self.name}] STARTING OBSERVATION inputs keys: {list(inputs.keys())}")