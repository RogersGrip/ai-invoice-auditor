import sys
import os
sys.path.append(os.getcwd())
try:
    from src.mcp_server.erp import mcp
    print("MCP Dict Keys:", list(mcp.__dict__.keys()))
    # Check if there's a list_tools in a different attribute
    # print("Dir:", dir(mcp))
except Exception as e:
    print(e)
