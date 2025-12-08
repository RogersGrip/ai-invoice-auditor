from typing import Dict, Any, List
import uuid
from datetime import datetime

from src.core.protocol import Agent, AgentResponse
from src.core.logger import logger
from src.core.mcp_client import LocalMCPClient
from src.mcp_server.erp import mcp as erp_server

class BusinessValidationAgent(Agent):
    name = "Business Validation Agent"
    description = "Validates invoice line items against ERP records using MCP."

    def __init__(self):
        # Initialize MCP Client with the ERP FastMCP instance
        self.mcp_client = LocalMCPClient(erp_server)

    def process(self, inputs: Dict[str, Any]) -> AgentResponse:
        self.start_as_current_observation(inputs)
        
        data = inputs.get("extracted_data", {})
        # Handle Pydantic model input
        if hasattr(data, "model_dump"):
            data = data.model_dump()
            
        logger.info("Business Validator: Auditing Lines against ERP via MCP")
        
        discrepancies = []
        line_items = data.get("line_items", [])
        
        for item in line_items:
            try:
                # 1. Prepare Arguments
                item_code = item.get("item_code", "UNKNOWN")
                unit_price = float(item.get("unit_price", 0.0))
                currency = item.get("currency", "USD")
                
                # 2. Call MCP Tool
                result = self.mcp_client.call_tool(
                    name="validate_line_item",
                    arguments={
                        "item_code": item_code,
                        "unit_price": unit_price,
                        "currency": currency
                    }
                )
                
                # 3. Analyze Result
                if result.get("status") != "match":
                    reason = result.get("reason", "Unknown mismatch")
                    discrepancies.append(f"{item_code}: {reason}")
                    
            except Exception as e:
                logger.error(f"MCP Call Failed for item {item.get('item_code')}: {e}")
                discrepancies.append(f"Validation Error for {item.get('item_code')}: {str(e)}")

        status = "match" if not discrepancies else "mismatch"
        
        return AgentResponse(
            id=str(uuid.uuid4()),
            timestamp=datetime.utcnow().isoformat(),
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