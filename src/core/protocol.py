from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

# --- A2A Protocol ---

class AgentTool(BaseModel):
    name: str
    description: str
    args_schema: Optional[Dict[str, Any]] = None

class AgentResponse(BaseModel):
    content: Any
    metadata: Dict[str, Any] = Field(default_factory=dict)

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

    @abstractmethod
    def process(self, inputs: Dict[str, Any]) -> AgentResponse:
        """Main execution entry point."""
        pass

# --- MCP Protocol Interfaces ---

class MCPTool(BaseModel):
    name: str
    description: str
    input_schema: Dict[str, Any]

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