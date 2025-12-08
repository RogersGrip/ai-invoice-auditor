import json
from typing import Dict, Any, List
from fastmcp import FastMCP
from pydantic import BaseModel, Field
from src.core.mock_data_loader import mock_db
from src.core.logger import logger

# Initialize FastMCP Server
mcp = FastMCP("Mock ERP Agent", dependencies=["pydantic"])

class ValidationResult(BaseModel):
    status: str = Field(..., description="'match', 'mismatch', or 'warning'")
    reason: str
    erp_value: float | None = None
    discrepancy_percent: float | None = None

@mcp.resource("erp://po_records")
def get_po_records() -> str:
    """Returns the list of all Mock PO Records."""
    return json.dumps(mock_db.load_po_records(), indent=2)

@mcp.resource("erp://sku_master")
def get_sku_master() -> str:
    """Returns the SKU Master database."""
    return json.dumps(mock_db.load_sku_master(), indent=2)

@mcp.tool()
def validate_line_item(item_code: str, unit_price: float, currency: str = "USD") -> Dict[str, Any]:
    """
    Validates a single line item against the ERP Mock Database.
    Checks SKU existence and price tolerance (±5%).
    """
    logger.debug(f"ERP Logic Check: {item_code} @ {unit_price} {currency}")
    
    skus = mock_db.load_sku_master()
    sku_data = next((item for item in skus if item["item_code"] == item_code), None)
    
    if not sku_data:
        logger.warning(f"ERP Mismatch: SKU {item_code} not found in master.")
        return ValidationResult(
            status="mismatch",
            reason=f"SKU {item_code} not found in ERP Master."
        ).model_dump()

    pos = mock_db.load_po_records()
    found_price = None
    
    # Simple logic: Find the first occurrence of this SKU in any PO to get 'Standard Price'
    for po in pos:
        for line in po.get("line_items", []):
            if line.get("item_code") == item_code:
                found_price = float(line.get("unit_price", 0.0))
                break
        if found_price is not None:
            break
            
    if found_price is None:
        return ValidationResult(
            status="warning",
            reason=f"SKU {item_code} found, but no historical PO price data."
        ).model_dump()

    # Tolerance Check
    difference = abs(unit_price - found_price)
    percent_diff = (difference / found_price) * 100 if found_price > 0 else 100.0

    if percent_diff > 5.0:
        logger.info(f"ERP Discrepancy: {item_code} | Inv: {unit_price} vs ERP: {found_price} ({percent_diff:.2f}%)")
        return ValidationResult(
            status="discrepancy",
            reason=f"Price mismatch > 5%. Invoice: {unit_price}, ERP: {found_price}",
            erp_value=found_price,
            discrepancy_percent=round(percent_diff, 2)
        ).model_dump()

    return ValidationResult(
        status="match",
        reason="Price and SKU validated successfully.",
        erp_value=found_price
    ).model_dump()

if __name__ == "__main__":
    mcp.run()