from typing import Dict, Any, List
from src.core.protocol import Agent, AgentResponse
from src.core.logger import logger
from src.core.state import ValidationResult
from src.mcp_server.erp import logic_validate_line_item

class ValidatorAgent(Agent):
    name = "Validation Agent"
    description = "Validates invoice data against business rules and ERP records."

    def process(self, inputs: Dict[str, Any]) -> AgentResponse:
        """
        Expects 'extracted_data' (dict or InvoiceData dump).
        """
        data = inputs.get("extracted_data", {})
        if not data:
             return AgentResponse(content=None, metadata={"status": "skipped"})

        logger.info("Validator Agent: Validating Line Items")

        discrepancies = []
        line_items = data.get("line_items", [])
        
        for item in line_items:
            code = item.get("item_code") or "UNKNOWN"
            price = item.get("unit_price") or 0.0
            currency = item.get("currency") or "USD"
            
            # Call ERP Logic (Simulating MCP Tool Call)
            res = logic_validate_line_item(item_code=code, unit_price=price, currency=currency)
            
            if res["status"] != "match":
                reason = res.get("reason", "Unknown mismatch")
                discrepancies.append(f"Item {code}: {reason}")

        is_valid = len(discrepancies) == 0
        
        result = ValidationResult(
            is_valid=is_valid,
            discrepancies=discrepancies,
            total_lines=len(line_items)
        )
        
        return AgentResponse(
            content=result.model_dump(),
            metadata={"valid": is_valid, "discrepancies": len(discrepancies)}
        )
