from enum import Enum
from typing import Dict, Any, List, Optional, Protocol
from pydantic import BaseModel

class MCPToolType(str, Enum):
    ACTION = "action"
    RETRIEVAL = "retrieval"
    SYSTEM = "system"

class MCPToolDefinition(BaseModel):
    name: str
    description: str
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]
    tool_type: MCPToolType = MCPToolType.ACTION

class MCPRequest(BaseModel):
    tool_name: str
    arguments: Dict[str, Any]
    context_id: str | None = None

class MCPResponse(BaseModel):
    content: Any
    is_error: bool = False
    metadata: Dict[str, Any] = {}

class AgentStatus(str, Enum):
    IDLE = "idle"
    BUSY = "busy"
    OFFLINE = "offline"
    ERROR = "error"

class AgentManifest(BaseModel):
    agent_id: str
    name: str
    version: str
    capabilities: List[str]
    tools: List[MCPToolDefinition]
    endpoint: str

class AgentMessage(BaseModel):
    sender_id: str
    target_id: str
    interaction_id: str
    payload: Dict[str, Any]
    timestamp: float

class BaseAgent(Protocol):
    def get_manifest(self) -> AgentManifest:
        ...
        
    async def process_task(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        ...