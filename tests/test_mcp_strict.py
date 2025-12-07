import sys
import os
from loguru import logger

sys.path.append(os.getcwd())

from src.core.mcp_client import LocalMCPClient
from src.mcp_server.erp import mcp as erp_server

def test_local_mcp_client():
    logger.info(">>> Testing Strict MCP Protocol <<<")
    
    # 1. Establish "Connection" (Map tool names to functions)
    tool_map = {
         "validate_line_item": erp_server._tool_manager._tools["validate_line_item"].fn
    }
    client = LocalMCPClient(tool_map)
    
    # 2. List Tools
    tools = client.list_tools()
    logger.info(f"Available Tools: {[t.name for t in tools]}")
    assert "validate_line_item" in [t.name for t in tools]
    
    # 3. Call Tool (Valid)
    # Using 'SKU-001' from PO-1001 (price 12.00)
    res = client.call_tool("validate_line_item", {"item_code": "SKU-001", "unit_price": 12.00, "currency": "USD"})
    logger.info(f"Tool Result (Valid): {res}")
    assert res["status"] == "match"
    
    # 4. Call Tool (Invalid)
    res_invalid = client.call_tool("validate_line_item", {"item_code": "INVALID-SKU", "unit_price": 100.0, "currency": "USD"})
    logger.info(f"Tool Result (Invalid): {res_invalid}")
    assert res_invalid["status"] == "mismatch"
    
    logger.success("✔ strict MCP Client Implementation Verified")

if __name__ == "__main__":
    test_local_mcp_client()
