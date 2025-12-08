import re
from typing import Dict, Any, List
import uuid
from datetime import datetime, timezone

from src.core.protocol import Agent, AgentResponse
from src.core.logger import logger
from src.core.mcp_client import LocalMCPClient
from src.mcp_server.erp import mcp as erp_server

class BusinessValidationAgent(Agent):
    name = "Business Validation Agent"
    description = "Validates invoice line items against ERP records using MCP."

    def __init__(self):
        self.mcp_client = LocalMCPClient(erp_server)

    def _parse_price(self, price_input: Any) -> float:
        """
        Robustly parses price strings like '4,00 €', '$5.00', '1.200,50' into floats.
        """
        if price_input is None:
            return 0.0
        if isinstance(price_input, (int, float)):
            return float(price_input)
        
        # Convert to string and strip symbols (keep digits, comma, dot, minus)
        clean_str = re.sub(r'[^\d.,-]', '', str(price_input)).strip()
        
        if not clean_str:
            return 0.0
            
        try:
            # Handle European format: 1.000,00 -> 1000.00
            # If comma is present and appears AFTER the last dot (or no dot), assume it's decimal
            if ',' in clean_str:
                if '.' in clean_str:
                    # Mixed case (e.g. 1.200,50) - complex, simplistic fallback:
                    # Remove all dots, replace comma with dot
                    if clean_str.rfind(',') > clean_str.rfind('.'):
                        clean_str = clean_str.replace('.', '').replace(',', '.')
                    else:
                        clean_str = clean_str.replace(',', '') # 1,200.50 -> 1200.50
                else:
                    # Just comma (4,00) -> replace with dot
                    clean_str = clean_str.replace(',', '.')
            
            return float(clean_str)
        except ValueError:
            logger.warning(f"Could not parse price: {price_input}")
            return 0.0

    def process(self, inputs: Dict[str, Any]) -> AgentResponse:
        self.start_as_current_observation(inputs)
        
        data = inputs.get("validated_data") or inputs.get("extracted_data", {})
        if hasattr(data, "model_dump"):
            data = data.model_dump()
            
        logger.info("Business Validator: Auditing Lines against ERP via MCP")
        
        discrepancies = []
        line_items = data.get("line_items", [])
        
        for item in line_items:
            try:
                item_code = str(item.get("item_code", "UNKNOWN"))
                
                # Fix: Use robust parser
                unit_price = self._parse_price(item.get("unit_price"))
                
                currency = str(item.get("currency", "USD")) or "USD"
                
                result = self.mcp_client.call_tool(
                    name="validate_line_item",
                    arguments={
                        "item_code": item_code,
                        "unit_price": unit_price,
                        "currency": currency
                    }
                )
                
                if result.get("status") != "match":
                    discrepancies.append(f"{item_code}: {result.get('reason')}")
                    
            except Exception as e:
                logger.error(f"MCP Call Failed for item {item.get('item_code', 'Unknown')}: {e}")
                discrepancies.append(f"Validation Error for {item.get('item_code', 'Unknown')}")

        status = "match" if not discrepancies else "mismatch"
        
        return AgentResponse(
            id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc).isoformat(),
            source_agent=self.name,
            target_agent="Reporting Agent",
            message_type="TASK_HANDOFF",
            payload={
                "business_validation_status": status,
                "discrepancies": discrepancies,
                "validated_data": data
            },
            context_id=inputs.get("context_id")
        )