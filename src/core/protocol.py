from a2a.types import (
    Task, 
    TaskStatus, 
    TaskState, 
    Role, 
    Message, 
    Part, 
    FilePart, 
    DataPart,
    Artifact, 
    AgentCard, 
    AgentProvider, 
    AgentCapabilities, 
    AgentSkill,
    AgentInterface,
    AgentResponse
)
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from abc import ABC, abstractmethod

class MCPTool(BaseModel):
    name: str
    description: str
    input_schema: Dict[str, Any]

class MCPResource(BaseModel):
    uri: str
    name: str
    mime_type: Optional[str] = None

class MCPClient(ABC):
    @abstractmethod
    def list_tools(self) -> List[MCPTool]: pass
    @abstractmethod
    def call_tool(self, name: str, arguments: Dict[str, Any]) -> Any: pass

class Agent(ABC):
    @property
    @abstractmethod
    def name(self) -> str: pass
    
    @property
    @abstractmethod
    def description(self) -> str: pass
    
    @abstractmethod
    def process(self, inputs: Dict[str, Any]) -> AgentResponse: pass
    
    def start_as_current_observation(self, inputs: Dict[str, Any]):
        from src.core.logger import logger
        logger.info(f"[{self.name}] STARTING OBSERVATION | Keys: {list(inputs.keys())}")