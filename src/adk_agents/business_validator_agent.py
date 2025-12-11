import uuid
import json
from typing import Dict, Any
from datetime import datetime, timezone
from langchain_core.tools import tool
from src.adk_agents.base_adk import ADKAgent
from src.core.protocol import AgentResponse
from src.mcp_server.erp import logic_validate_line_item

@tool
def validate_line_item_tool(item_code: str, unit_price: float, currency: str = "USD") -> str:
    """Validates a single line item against the ERP system. Returns JSON status."""
    res = logic_validate_line_item(item_code, unit_price, currency)
    return json.dumps(res)

class BusinessValidationAgent(ADKAgent):
    def __init__(self):
        super().__init__(
            name="Business Validation Agent",
            description="ERP Auditor. Validate invoice line items against ERP records using the validate_line_item_tool.",
            model_id="cohere.command-r-plus-v1:0"
        )
        self.register_tools([validate_line_item_tool])

    def process(self, inputs: Dict[str, Any]) -> AgentResponse:
        self.start_as_current_observation(inputs)
        
        data = inputs.get("validated_data") or inputs.get("extracted_data", {})
        if hasattr(data, "model_dump"):
            data = data.model_dump()
            
        line_items = data.get("line_items", [])
        if not line_items:
             return self._create_response("match", [], data, inputs.get("context_id"))

        task_prompt = f"""
        Audit these Invoice Line Items against the ERP:
        {json.dumps(line_items, indent=2)}
        
        1. Call validate_line_item_tool for EVERY item.
        2. If any return 'mismatch' or 'discrepancy', report it.
        3. Summarize findings.
        """

        result = self.run_loop(task_prompt)
        
        final_text = result["output"].lower()
        discrepancies = []
        status = "match"
        
        if "mismatch" in final_text or "discrepancy" in final_text or "fail" in final_text:
            status = "mismatch"
            discrepancies.append(result["output"])

        return self._create_response(status, discrepancies, data, inputs.get("context_id"))

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