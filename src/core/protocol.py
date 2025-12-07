from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

# --- A2A Protocol ---

class AgentTool(BaseModel):
    name: str
    description: str
    args_schema: Optional[Dict[str, Any]] = None

class AgentResponse(BaseModel):
    """
    Standardized A2A Message Schema.
    Follows:
    {
       "id": "uuid-v4",
       "timestamp": "iso-8601",
       "source_agent": "agent_name",
       "target_agent": "agent_name",
       "message_type": "TASK_HANDOFF | QUERY | RESPONSE | ERROR",
       "payload": { ... },
       "context_id": "trace_id_for_observability"
    }
    """
    id: str = Field(..., description="UUID v4 for the message")
    timestamp: str = Field(..., description="ISO 8601 timestamp")
    source_agent: str
    target_agent: str
    message_type: str = Field(..., pattern="^(TASK_HANDOFF|QUERY|RESPONSE|ERROR)$")
    payload: Dict[str, Any]
    context_id: Optional[str] = None

class Agent(ABC):
    """Abstract Base Class for all Agents adhering to A2A Protocol."""
    
    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        pass

    @property
    @abstractmethod
    def inputs_schema(self) -> Dict[str, Any]:
        """JSON Schema for expected inputs."""
        pass

    @property
    @abstractmethod
    def outputs_schema(self) -> Dict[str, Any]:
        """JSON Schema for expected outputs."""
        pass

    @abstractmethod
    def process(self, inputs: Dict[str, Any]) -> AgentResponse:
        """Main execution entry point."""
        pass

    def start_as_current_observation(self, inputs: Dict[str, Any]):
        """
        Standard logging/trace method for observability.
        """
        from loguru import logger
        logger.info(f"[{self.name}] STARTING OBSERVATION with inputs: {list(inputs.keys())}")

# --- MCP Protocol Interfaces ---

class MCPTool(BaseModel):
    name: str
    description: str
    input_schema: Dict[str, Any]
    output_schema: Optional[Dict[str, Any]] = None

class MCPResource(BaseModel):
    uri: str
    name: str
    mime_type: Optional[str] = None

class MCPClient(ABC):
    """Interface for connecting to MCP Servers."""
    
    @abstractmethod
    def list_tools(self) -> List[MCPTool]:
        pass
        
    @abstractmethod
    def call_tool(self, name: str, arguments: Dict[str, Any]) -> Any:
        pass

class MCPServer(ABC):
    """Interface for MCP Servers."""
    
    @abstractmethod
    def register_tool(self, tool: MCPTool, fn: Any):
        pass
        
    @abstractmethod
    def register_resource(self, resource: MCPResource, fn: Any):
        pass