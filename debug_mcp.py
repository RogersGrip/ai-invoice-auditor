import sys
import os
sys.path.append(os.getcwd())
from src.mcp_server.erp import mcp

print(f"MCP Object Dir: {dir(mcp)}")
try:
    print(f"Tools via list_tools: {mcp.list_tools()}")
except Exception as e:
    print(f"list_tools failed: {e}")
