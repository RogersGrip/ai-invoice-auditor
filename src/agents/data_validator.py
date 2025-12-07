from typing import Dict, Any, List
from src.core.protocol import Agent, AgentResponse
from src.core.logger import logger
from src.core.config import settings

class DataValidationAgent(Agent):
    name = "Data Validation Agent"
    description = "Checks for data completeness and missing mandatory fields."

    def process(self, inputs: Dict[str, Any]) -> AgentResponse:
        """
        Inputs: 'extracted_data' (dict or InvoiceData)
        """
        data = inputs.get("extracted_data")
        if not data:
             return AgentResponse(content=None, metadata={"status": "skipped"})
             
        # Normalize dict
        if hasattr(data, "model_dump"):
            data = data.model_dump()
            
        logger.info("Data Validator: Checking for missing fields...")
        
        missing = []
        # Check Header Fields
        required_headers = ["invoice_no", "invoice_date", "total_amount", "vendor_id"]
        for field in required_headers:
            if not data.get(field):
                missing.append(field)
                
        # Check Line Items
        items = data.get("line_items", [])
        if not items:
            missing.append("line_items")
        else:
            for i, item in enumerate(items):
                if not item.get("item_code"):
                    missing.append(f"line_item[{i}].item_code")
                if not item.get("total") and not item.get("unit_price"):
                     missing.append(f"line_item[{i}].price_info")

        is_valid = len(missing) == 0
        if not is_valid:
            logger.warning(f"Data Validation Failed. Missing: {missing}")
            
        return AgentResponse(
            content={"is_valid": is_valid, "missing_fields": missing},
            metadata={"checked_fields": len(required_headers) + len(items)}
        )
