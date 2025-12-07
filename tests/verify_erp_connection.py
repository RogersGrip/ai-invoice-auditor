import sys
import os

# Add project root to path
sys.path.append(os.getcwd())

from src.core.mcp_client import LocalMCPClient
from src.mcp_server.erp import mcp as erp_server

def test_erp_mcp_connection():
    print(">>> Initializing LocalMCPClient with ERP Server...")
    
    # Simulate the binding logic used in BusinessValidationAgent
    # FastMCP stores tools in _tool_manager._tools (internal API)
    try:
        tool_fn = erp_server._tool_manager._tools["validate_line_item"].fn
        tool_map = {
             "validate_line_item": tool_fn
        }
    except AttributeError:
        print("!!! Failed to access FastMCP internal tool registry. Implementation might have changed.")
        return False
        
    client = LocalMCPClient(tool_map)
    
    print(">>> Testing 'validate_line_item'...")
    
    # 1. Test Valid SKU (Mock Data)
    # Mock DB usually has SKU-001 at 12.00
    result_match = client.call_tool("validate_line_item", {
        "item_code": "SKU-001",
        "unit_price": 12.00,
        "currency": "USD"
    })
    
    print(f"Result (Match): {result_match}")
    assert result_match["status"] == "match", "Expected match for SKU-001"
    
    # 2. Test Mismatch
    result_mismatch = client.call_tool("validate_line_item", {
        "item_code": "SKU-001",
        "unit_price": 1000.00,
        "currency": "USD"
    })
    
    print(f"Result (Mismatch): {result_mismatch}")
    assert result_mismatch["status"] == "discrepancy", "Expected discrepancy for high price"
    
    print(">>> MCP ERP Verification PASSED ✅")
    return True

if __name__ == "__main__":
    try:
        success = test_erp_mcp_connection()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"!!! Validation Failed: {e}")
        sys.exit(1)
