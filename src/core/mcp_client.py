from typing import List, Dict, Any, Callable
from src.core.protocol import MCPClient, MCPTool
from src.core.logger import logger

class LocalMCPClient(MCPClient):
    """
    A local implementation of MCP Client that connects to 
    in-process MCP Servers (functions registered in memory).
    """
    def __init__(self, server_tools: Dict[str, Callable]):
        self.server_tools = server_tools
        self.tools_metadata = [] 
        # In a real scenario, we'd fetch metadata from server. 
        # Here we assume tool names match keys.

    def list_tools(self) -> List[MCPTool]:
        # For this mock local client, we just return names wrapped in tools
        return [
            MCPTool(name=name, description="Local Tool", input_schema={}) 
            for name in self.server_tools.keys()
        ]

    def call_tool(self, name: str, arguments: Dict[str, Any]) -> Any:
        logger.debug(f"MCP Client: Calling tool '{name}'")
        
        if name not in self.server_tools:
            logger.error(f"MCP Error: Tool '{name}' not found.")
            raise ValueError(f"Tool {name} not found on server.")
            
        tool_fn = self.server_tools[name]
        try:
            return tool_fn(**arguments)
        except Exception as e:
            logger.error(f"MCP Tool Execution Failed: {e}")
            raise e
