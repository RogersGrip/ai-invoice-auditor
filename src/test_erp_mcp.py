import json
import sys
from pathlib import Path
from src.core.logger import find_project_root

# Add project root to path for imports
PROJECT_ROOT = find_project_root(Path(__file__).resolve())
sys.path.append(str(PROJECT_ROOT))

# Import pure logic functions
from src.mcp_server.erp import logic_get_po_records, logic_validate_line_item

def test_erp_logic():
    print("=========================================")
    print("   TESTING BUSINESS VALIDATION AGENT     ")
    print("=========================================")
    
    # 1. Test Resource
    print("\n[1] Testing Resource: erp://po_records")
    try:
        json_str = logic_get_po_records()
        data = json.loads(json_str)
        print(f"Success. Loaded {len(data)} PO records.")
        print(f"Preview: PO-{data[0]['po_number']} (Vendor: {data[0]['vendor_id']})")
    except Exception as e:
        print(f"Failed: {e}")

    # 2. Test Tool (Happy Path)
    print("\n[2] Testing Tool: validate_line_item (Happy Path)")
    try:
        # SKU-001 is $12.00 in PO-1001
        result = logic_validate_line_item("SKU-001", 12.00, "USD")
        print(f"Input: SKU-001 @ $12.00")
        print(f"Result: {result['status'].upper()} - {result['reason']}")
    except Exception as e:
        print(f"Error: {e}")

    # 3. Test Tool (Discrepancy)
    print("\n[3] Testing Tool: validate_line_item (Discrepancy)")
    try:
        # Price is $50.00 (Expected $12.00)
        result = logic_validate_line_item("SKU-001", 50.00, "USD")
        print(f"Input: SKU-001 @ $50.00")
        print(f"Result: {result['status'].upper()} - {result['reason']}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_erp_logic()