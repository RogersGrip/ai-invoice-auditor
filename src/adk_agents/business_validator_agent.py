# ===== FILE: src/adk_agents/business_validator_agent.py =====
import json
import uuid
import os
from typing import Dict, Any
from datetime import datetime, timezone

# --- ADK Framework Imports ---
from src.frameworks.google_adk.agents import Agent as ADKAgent
from src.frameworks.google_adk.models import LiteLlm
from src.frameworks.google_adk.tools import BaseTool

# --- Project Imports ---
from src.core.protocol import AgentResponse
from src.mcp_server.erp import logic_validate_line_item

# 1. Define the specific Tool for this Agent
class ValidateLineItemTool(BaseTool):
    def __init__(self):
        super().__init__(
            name="validate_line_item",
            description="Validates a single invoice line item against ERP records. Arguments: item_code (str), unit_price (float), currency (str)."
        )
    
    def run(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return logic_validate_line_item(
            item_code=args.get("item_code"),
            unit_price=float(args.get("unit_price", 0)),
            currency=args.get("currency", "USD")
        )

# 2. The Business Validator Agent Wrapper
class BusinessValidationAgent:
    def __init__(self):
        # Configure the ADK Model
        self.model = LiteLlm(
            model="bedrock/cohere.command-r-plus-v1:0",
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
            aws_region_name=os.getenv("AWS_DEFAULT_REGION", "us-east-1")
        )
        
        # Instantiate the ADK Agent
        self.adk_agent = ADKAgent(
            name="Business Validation Agent",
            model=self.model,
            instruction=(
                "You are an expert ERP Auditor. Your task is to validate invoice line items using the 'validate_line_item' tool. "
                "For every line item provided in the input list, you MUST call the validation tool. "
                "After validating all items, summarize the results. If any item fails validation, mark the status as mismatch."
            ),
            tools=[ValidateLineItemTool()]
        )

    async def process_async(self, inputs: Dict[str, Any]) -> AgentResponse:
        """
        Asynchronous processing that delegates to the ADK agent.
        """
        data = inputs.get("validated_data") or inputs.get("extracted_data", {})
        line_items = data.get("line_items", [])
        context_id = inputs.get("context_id", str(uuid.uuid4()))

        if not line_items:
             return self._create_response("match", [], data, context_id)

        # Create the prompt for the ADK Agent
        task_prompt = f"""
        Here is the list of invoice line items to audit:
        {json.dumps(line_items, indent=2)}
        
        Please validate every single item against the ERP system.
        """
        
        # Execute the ADK Agent
        # The agent will use its LLM + Tools to process the request
        result_text = await self.adk_agent.process(task_prompt)
        
        # Parse the Agent's natural language response to determine structured status
        status = "match"
        discrepancies = []
        
        lower_result = result_text.lower()
        if "mismatch" in lower_result or "discrepancy" in lower_result or "failed" in lower_result:
            status = "mismatch"
            discrepancies.append(result_text) # Use the agent's summary as the discrepancy detail

        return self._create_response(status, discrepancies, data, context_id)

    def process(self, inputs: Dict[str, Any]) -> AgentResponse:
        """
        Synchronous wrapper for compatibility with the existing graph pipeline.
        """
        import asyncio
        return asyncio.run(self.process_async(inputs))

    def _create_response(self, status, discrepancies, data, context_id):
        return AgentResponse(
            id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc).isoformat(),
            source_agent="Business Validation Agent",
            target_agent="Reporting Agent",
            message_type="TASK_HANDOFF",
            payload={
                "business_validation_status": status,
                "discrepancies": discrepancies,
                "validated_data": data
            },
            context_id=context_id
        )