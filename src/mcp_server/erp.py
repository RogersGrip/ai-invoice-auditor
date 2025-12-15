import json
from typing import Dict, Any, Optional
from fastmcp import FastMCP
from src.core.mock_data_loader import mock_db
from src.core.logger import logger

# Initialize FastMCP with Sampling Capability
mcp = FastMCP(
    "Mock ERP Agent", 
    capabilities={
        "sampling": {},  # Enable LLM Sampling support
        "tools": {},
        "resources": {}
    }
)

@mcp.tool()
def validate_line_item(item_code: str, unit_price: float, currency: str = "USD") -> Dict[str, Any]:
    """
    Validates a single line item against the ERP Mock Database.
    """
    logger.debug(f"ERP Check: {item_code} @ {unit_price} {currency}")
    
    # Logic implementation ...
    skus = mock_db.load_sku_master()
    if not any(item["item_code"] == item_code for item in skus):
        return {"status": "mismatch", "reason": f"SKU {item_code} not found."}

    pos = mock_db.load_po_records()
    found_price = None
    for po in pos:
        for line in po.get("line_items", []):
            if line.get("item_code") == item_code:
                found_price = float(line.get("unit_price", 0.0))
                break
        if found_price is not None: break

    if found_price is None:
        return {"status": "warning", "reason": "No PO price history."}

    diff = abs(unit_price - found_price)
    pct = (diff / found_price) * 100 if found_price > 0 else 100.0

    if pct > 5.0:
        return {
            "status": "mismatch",
            "reason": f"Price mismatch {pct:.2f}% (Inv: {unit_price}, ERP: {found_price})",
            "erp_value": found_price
        }

    return {"status": "match", "reason": "Valid", "erp_value": found_price}

@mcp.resource("erp://po_records")
def get_po_records() -> str:
    """Returns all Purchase Order records from the mock DB."""
    return json.dumps(mock_db.load_po_records(), indent=2)

if __name__ == "__main__":
    mcp.run()