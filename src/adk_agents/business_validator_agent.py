from typing import Dict, Any, List
import uuid
from datetime import datetime
from src.core.protocol import Agent, AgentResponse, AgentTool
from src.core.logger import logger
from src.core.mcp_client import LocalMCPClient
from src.mcp_server.erp import mcp as erp_server
from src.tools.tools import BusinessValidationTool

class BusinessValidationAgent(Agent):
    name = "Business Validation Agent"
    description = "Validates invoice line items against ERP records using MCP."

    def __init__(self):
        # Initialize MCP Client connected to the ERP Server's tool registry
        tool_map = {
             "validate_line_item": erp_server._tool_manager._tools["validate_line_item"].fn
        }
        self.mcp_client = LocalMCPClient(tool_map)
        self.validator_tool = BusinessValidationTool()

    @property
    def inputs_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "extracted_data": {"type": "object"}
            }
        }

    @property
    def outputs_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "business_validation_status": {"type": "string"},
                "discrepancies": {"type": "array"},
                "validated_data": {"type": "object"}
            }
        }

    def process(self, inputs: Dict[str, Any]) -> AgentResponse:
        self.start_as_current_observation(inputs)
        data = inputs.get("extracted_data", {})
        
        # If passed from DataValidator, it might be in 'content' or mixed.
        # We expect the full invoice data here.
        if hasattr(data, "model_dump"):
            data = data.model_dump()
            
        logger.info("Business Validator: Auditing Lines against ERP via MCP")
        
        discrepancies = []
        line_items = data.get("line_items", [])
        
        for item in line_items:
            # MCP Tool Call
            try:
                # In a pure internal MCP setup, tool.run() might call the client.
                # Here we use the client directly as per design, but could wrap in validator_tool.
                result = self.mcp_client.call_tool(
                    "validate_line_item",
                    arguments={
                        "item_code": item.get("item_code", "UNKNOWN"),
                        "unit_price": item.get("unit_price", 0.0),
                        "currency": item.get("currency", "USD")
                    }
                )
                
                if result["status"] != "match":
                    discrepancies.append(f"{item.get('item_code')}: {result.get('reason')}")
                    
            except Exception as e:
                logger.error(f"MCP Call Failed: {e}")
                discrepancies.append(f"Validation Error: {str(e)}")

        status = "match" if not discrepancies else "mismatch"

        return AgentResponse(
            id=str(uuid.uuid4()),
            timestamp=datetime.now().isoformat(),
            source_agent=self.name,
            target_agent="Reporting Agent",
            message_type="TASK_HANDOFF",
            payload={
                "business_validation_status": status,
                "discrepancies": discrepancies,
                "validated_data": data # Pass full data along
            },
            context_id=inputs.get("context_id")
        )
