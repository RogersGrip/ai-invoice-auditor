from typing import Dict, Any, List
import uuid
from datetime import datetime
from src.core.protocol import Agent, AgentResponse
from src.core.logger import logger
from src.core.config import settings
from src.tools.tools import DataCompletenessCheckerTool

class DataValidationAgent(Agent):
    name = "Data Validation Agent"
    description = "Checks for data completeness and missing mandatory fields."

    def __init__(self):
        self.checker_tool = DataCompletenessCheckerTool()

    def process(self, inputs: Dict[str, Any]) -> AgentResponse:
        """
        Inputs: 'extracted_data' (dict or InvoiceData)
        """
        # Resolve Input
        data = inputs.get("extracted_data")
        if not data and inputs.get("payload"):
             data = inputs["payload"].get("extracted_data")

        if not data:
             return AgentResponse(
                 id=str(uuid.uuid4()),
                 source_agent=self.name,
                 timestamp=datetime.now().isoformat(),
                 target_agent="Error Handler",
                 message_type="ERROR",
                 payload={"error": "No data to validate"},
                 context_id=inputs.get("context_id")
             )
             
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
            id=str(uuid.uuid4()),
            timestamp=datetime.now().isoformat(),
            source_agent=self.name,
            target_agent="Business Validation Agent",
            message_type="TASK_HANDOFF",
            payload={
                "extracted_data": data,
                "validation_status": "valid" if is_valid else "invalid", 
                "missing_fields": missing,
                "errors": missing # map missing to errors list
            },
            context_id=inputs.get("context_id")
        )
