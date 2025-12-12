# ===== FILE: src/adk_agents/business_validator_agent.py =====
import json
import uuid
from typing import Dict, Any
from datetime import datetime, timezone

from src.adk_agents.base_agent import AgentADK
from google.adk.tools import BaseTool
from google.genai.types import FunctionDeclaration, Schema, Type
from src.core.protocol import AgentResponse
from src.mcp_server.erp import logic_validate_line_item

class ValidateLineItemTool(BaseTool):
    def __init__(self):
        super().__init__(name="validate_line_item", description="Validates line item against ERP.")

    def _get_declaration(self):
        return FunctionDeclaration(
            name=self.name,
            description="Checks if an invoice line item matches the ERP records. Returns match/mismatch status.",
            parameters=Schema(
                type=Type.OBJECT, 
                properties={
                    "item_code": Schema(type=Type.STRING, description="Product SKU or Item Code"),
                    "unit_price": Schema(type=Type.NUMBER, description="Unit price from invoice"),
                    "currency": Schema(type=Type.STRING, description="Currency code (e.g. USD)")
                },
                required=["item_code", "unit_price"]
            )
        )
    
    def run(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return logic_validate_line_item(
            item_code=args.get("item_code"),
            unit_price=float(args.get("unit_price", 0)),
            currency=args.get("currency", "USD")
        )

class BusinessValidationAgent(AgentADK):
    def __init__(self):
        super().__init__(
            name="business_validation_agent",
            instruction=(
                "You are an ERP Validation Machine. "
                "You CANNOT verify prices yourself. You MUST use the 'validate_line_item' tool for EVERY item. "
                "1. Loop through the provided items. "
                "2. Call 'validate_line_item' for each one. "
                "3. Report only the final status (match/mismatch)."
            ),
            tools=[ValidateLineItemTool()]
        )

    def process(self, inputs: Dict[str, Any]) -> AgentResponse:
        import asyncio
        return asyncio.run(self.process_async(inputs))

    async def process_async(self, inputs: Dict[str, Any]) -> AgentResponse:
        data = inputs.get("validated_data") or inputs.get("extracted_data", {})
        line_items = data.get("line_items", [])
        context_id = inputs.get("context_id", str(uuid.uuid4()))

        if not line_items:
             return self._create_response("match", [], data, context_id)

        # Force tool use in prompt
        task_prompt = f"Validate these {len(line_items)} items now:\n{json.dumps(line_items, indent=2)}"
        result_text = await self.run(task_prompt)
        
        status = "match"
        discrepancies = []
        lower = result_text.lower()
        if "mismatch" in lower or "discrepancy" in lower or "failed" in lower:
            status = "mismatch"
            discrepancies.append(result_text)

        return self._create_response(status, discrepancies, data, context_id)

    def _create_response(self, status, discrepancies, data, context_id):
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
            context_id=context_id
        )