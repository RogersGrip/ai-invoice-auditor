import sys
import os
sys.path.append(os.getcwd())
from src.mcp_server.erp import mcp

tm = getattr(mcp, "_tool_manager", None)
if tm:
    print(f"ToolManager Dir: {dir(tm)}")
    # Try common names
    try:
        print(f"tm._tools keys: {list(tm._tools.keys())}")
    except:
        pass
else:
    print("No _tool_manager")
