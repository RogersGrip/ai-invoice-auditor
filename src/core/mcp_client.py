import inspect
from typing import List, Dict, Any, Callable
from fastmcp import FastMCP
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import CallToolResult, ListToolsResult
from src.core.protocol import MCPTool, MCPClient as BaseMCPClient
from src.core.logger import logger

class LocalMCPClient(BaseMCPClient):
    def __init__(self, mcp_server: FastMCP):
        self.server = mcp_server
        self._tools_map: Dict[str, Callable] = {}
        self._resources_map: Dict[str, Callable] = {}
        self._load_registry()

    def _load_registry(self):
        try:
            if hasattr(self.server, "_tool_manager"):
                for name, tool_obj in self.server._tool_manager._tools.items():
                    self._tools_map[name] = tool_obj.fn
            
            if hasattr(self.server, "_resource_manager"):
                for uri, res_obj in self.server._resource_manager._resources.items():
                    self._resources_map[uri] = res_obj.fn
            
            logger.info(f"MCP Client loaded {len(self._tools_map)} tools from {self.server.name}")
        except Exception as e:
            logger.error(f"Failed to load MCP registry: {e}")

    def list_tools(self) -> List[MCPTool]:
        tools = []
        for name, fn in self._tools_map.items():
            sig = inspect.signature(fn)
            schema = {
                "type": "object",
                "properties": {
                    k: {"type": "string"} 
                    for k in sig.parameters.keys()
                }
            }
            tools.append(MCPTool(
                name=name,
                description=fn.__doc__ or "No description",
                input_schema=schema
            ))
        return tools

    def call_tool(self, name: str, arguments: Dict[str, Any], sampling: bool = False) -> Any:
        logger.debug(f"MCP Call: {name} | Sampling: {sampling}")
        
        if name not in self._tools_map:
            raise ValueError(f"Tool {name} not found in MCP server.")
            
        fn = self._tools_map[name]
        try:
            # Simulate LLM Sampling if requested within the MCP Context
            if sampling:
                logger.info("Sampling enabled for tool execution (Capability Check)")
            
            return fn(**arguments)
        except TypeError as e:
            logger.error(f"MCP Argument Mismatch for {name}: {e}")
            raise e
        except Exception as e:
            logger.error(f"MCP Tool Execution Error: {e}")
            raise e

    def get_resource(self, uri: str) -> Any:
        if uri not in self._resources_map:
            raise ValueError(f"Resource {uri} not found.")
        return self._resources_map[uri]()