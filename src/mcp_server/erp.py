import json
from fastmcp import FastMCP
from typing import Any
from src.core.mock_data_loader import mock_db
from loguru import logger

# Initialize Server
mcp = FastMCP("Mock ERP Agent")

# ==========================================
# CORE LOGIC (Pure Python - Testable)
# ==========================================

def logic_get_po_records() -> str:
    """Internal logic to fetch PO records."""
    data = mock_db.load_po_records()
    return json.dumps(data, indent=2)

def logic_get_sku_master() -> str:
    """Internal logic to fetch SKU master."""
    data = mock_db.load_sku_master()
    return json.dumps(data, indent=2)

def logic_validate_line_item(item_code: str, unit_price: float, currency: str) -> dict[str, Any]:
    """Internal logic to validate a single line item."""
    logger.info(f"Validating {item_code} @ {unit_price} {currency}")
    
    # 1. Load Master Data
    skus = mock_db.load_sku_master()
    sku_data = next((item for item in skus if item["item_code"] == item_code), None)
    
    if not sku_data:
        return {
            "status": "mismatch",
            "reason": f"SKU {item_code} not found in ERP Master.",
            "erp_price": None
        }

    # 2. Find Expected Price from PO History
    pos = mock_db.load_po_records()
    found_price = None
    
    for po in pos:
        for line in po["line_items"]:
            if line["item_code"] == item_code:
                found_price = line["unit_price"]
                break
        if found_price:
            break
            
    if found_price is None:
         return {
            "status": "warning",
            "reason": f"SKU {item_code} found, but no PO history to compare price.",
            "erp_price": None
        }

    # 3. Check Tolerance (5%)
    difference = abs(unit_price - found_price)
    percent_diff = (difference / found_price) * 100
    
    if percent_diff > 5.0:
        return {
            "status": "discrepancy",
            "reason": f"Price mismatch > 5%. Invoice: {unit_price}, ERP: {found_price}",
            "erp_price": found_price,
            "diff_percent": round(percent_diff, 2)
        }
        
    return {
        "status": "match",
        "reason": "Price and SKU validated successfully.",
        "erp_price": found_price
    }

# ==========================================
# MCP INTERFACE (Decorators)
# ==========================================

@mcp.resource("erp://po_records")
def get_po_records() -> str:
    return logic_get_po_records()

@mcp.resource("erp://sku_master")
def get_sku_master() -> str:
    return logic_get_sku_master()

@mcp.tool()
def validate_line_item(item_code: str, unit_price: float, currency: str) -> dict[str, Any]:
    """
    Validates a single invoice line item against the ERP SKU Master.
    Checks for price discrepancies greater than 5%.
    """
    return logic_validate_line_item(item_code, unit_price, currency)

if __name__ == "__main__":
    mcp.run()