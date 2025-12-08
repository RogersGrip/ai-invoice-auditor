from __future__ import annotations
from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime, timezone
from abc import ABC, abstractmethod

# --- A2A Enums ---

class TaskState(str, Enum):
    UNSPECIFIED = "unspecified"
    SUBMITTED = "submitted"
    WORKING = "working"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INPUT_REQUIRED = "input-required"
    REJECTED = "rejected"
    AUTH_REQUIRED = "auth-required"

class Role(str, Enum):
    UNSPECIFIED = "unspecified"
    USER = "user"
    AGENT = "agent"

# --- Core A2A Objects ---

class FilePart(BaseModel):
    mediaType: str = Field(..., description="MIME type of the file")
    name: str = Field(..., description="Name of the file")
    fileWithUri: Optional[str] = None
    fileWithBytes: Optional[str] = None

class DataPart(BaseModel):
    data: Dict[str, Any]

class Part(BaseModel):
    text: Optional[str] = None
    file: Optional[FilePart] = None
    data: Optional[DataPart] = None
    metadata: Optional[Dict[str, Any]] = None

class Message(BaseModel):
    messageId: str = Field(..., description="Unique UUID for the message")
    role: Role
    parts: List[Part]
    contextId: Optional[str] = None
    taskId: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    referenceTaskIds: Optional[List[str]] = None

class Artifact(BaseModel):
    artifactId: str
    name: Optional[str] = None
    description: Optional[str] = None
    parts: List[Part]
    metadata: Optional[Dict[str, Any]] = None

class TaskStatus(BaseModel):
    state: TaskState
    message: Optional[Message] = None
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class Task(BaseModel):
    id: str
    contextId: str
    status: TaskStatus
    artifacts: Optional[List[Artifact]] = None
    history: Optional[List[Message]] = None
    metadata: Optional[Dict[str, Any]] = None

# --- Operations Objects ---

class SendMessageConfiguration(BaseModel):
    acceptedOutputModes: Optional[List[str]] = None
    blocking: bool = False

class SendMessageRequest(BaseModel):
    tenant: Optional[str] = None
    message: Message
    configuration: Optional[SendMessageConfiguration] = None
    metadata: Optional[Dict[str, Any]] = None

class SendMessageResponse(BaseModel):
    task: Optional[Task] = None
    message: Optional[Message] = None

# --- Agent Discovery (Agent Card) ---

class AgentProvider(BaseModel):
    organization: str
    url: str

class AgentCapabilities(BaseModel):
    streaming: bool = False
    pushNotifications: bool = False
    stateTransitionHistory: bool = False

class AgentSkill(BaseModel):
    id: str
    name: str
    description: str
    tags: List[str]
    inputModes: Optional[List[str]] = None
    outputModes: Optional[List[str]] = None

class AgentInterface(BaseModel):
    url: str
    protocolBinding: str
    tenant: Optional[str] = None

class AgentCard(BaseModel):
    protocolVersion: str = "0.3.0"
    name: str
    description: str
    version: str
    provider: Optional[AgentProvider] = None
    capabilities: AgentCapabilities
    defaultInputModes: List[str]
    defaultOutputModes: List[str]
    skills: List[AgentSkill]
    supportedInterfaces: Optional[List[AgentInterface]] = None
    documentationUrl: Optional[str] = None
    
    model_config = ConfigDict(populate_by_name=True)

# --- MCP Protocol Basics ---

class MCPTool(BaseModel):
    name: str
    description: str
    input_schema: Dict[str, Any]

class MCPResource(BaseModel):
    uri: str
    name: str
    mime_type: Optional[str] = None

class MCPClient(ABC):
    """Abstract Base Class for MCP Clients"""
    @abstractmethod
    def list_tools(self) -> List[MCPTool]: pass
    
    @abstractmethod
    def call_tool(self, name: str, arguments: Dict[str, Any]) -> Any: pass

# --- Abstract Agent ---

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
    @property
    @abstractmethod
    def description(self) -> str: pass
    @abstractmethod
    def process(self, inputs: Dict[str, Any]) -> AgentResponse: pass
    
    def start_as_current_observation(self, inputs: Dict[str, Any]):
        from src.core.logger import logger
        logger.info(f"[{self.name}] STARTING OBSERVATION inputs keys: {list(inputs.keys())}")