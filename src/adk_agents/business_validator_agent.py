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
            description=self.description,
            parameters=Schema(
                type=Type.OBJECT, 
                properties={
                    "item_code": Schema(type=Type.STRING),
                    "unit_price": Schema(type=Type.NUMBER),
                    "currency": Schema(type=Type.STRING)
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
            instruction="You are an ERP Auditor. Validate invoice line items using the 'validate_line_item' tool.",
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

        task_prompt = f"Audit these items against ERP:\n{json.dumps(line_items, indent=2)}"
        result_text = await self.run(task_prompt)
        
        status = "match"
        discrepancies = []
        if "mismatch" in result_text.lower() or "discrepancy" in result_text.lower():
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