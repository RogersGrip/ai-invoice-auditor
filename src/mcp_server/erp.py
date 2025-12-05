import json
from fastmcp import FastMCP
from typing import Any, Dict
from src.core.mock_data_loader import mock_db
from loguru import logger

mcp = FastMCP("Mock ERP Agent")


def logic_validate_line_item(item_code: str, unit_price: float, currency: str) -> Dict[str, Any]:
    logger.debug(f"ERP Logic Check: {item_code} @ {unit_price} {currency}")
    
    skus = mock_db.load_sku_master()
    sku_data = next((item for item in skus if item["item_code"] == item_code), None)
    
    if not sku_data:
        logger.warning(f"ERP Mismatch: SKU {item_code} not found in master.")
        return {
            "status": "mismatch",
            "reason": f"SKU {item_code} not found in ERP Master.",
            "erp_price": None
        }

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
         logger.warning(f"ERP Warning: SKU {item_code} exists but no PO price history.")
         return {
            "status": "warning",
            "reason": f"SKU {item_code} found, but no PO history.",
            "erp_price": None
        }

    difference = abs(unit_price - found_price)
    percent_diff = (difference / found_price) * 100
    
    if percent_diff > 5.0:
        logger.info(f"ERP Discrepancy: {item_code} | Inv: {unit_price} vs ERP: {found_price} ({percent_diff:.2f}%)")
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

# --- MCP Tools ---

@mcp.resource("erp://po_records")
def get_po_records() -> str:
    return json.dumps(mock_db.load_po_records(), indent=2)

@mcp.resource("erp://sku_master")
def get_sku_master() -> str:
    return json.dumps(mock_db.load_sku_master(), indent=2)

@mcp.tool()
def validate_line_item(item_code: str, unit_price: float, currency: str) -> Dict[str, Any]:
    """Validates invoice line item against ERP records."""
    return logic_validate_line_item(item_code, unit_price, currency)

if __name__ == "__main__":
    mcp.run()