# validation_agent.py

import uuid
from typing import Dict, Any
from datetime import datetime, timezone

from agent_adk import AgentADK
from src.core.protocol import AgentResponse
from src.core.logger import logger
from src.tools.tools import DataCompletenessCheckerTool


class DataValidationAgent(AgentADK):
    
    def __init__(self, model: str = None):
        instruction = """You are a Data Validation Agent responsible for checking invoice data completeness.

Your task is to validate that all required invoice fields are present and properly formatted.
Check for missing mandatory fields and ensure data quality."""
        
        super().__init__(
            name="Data_Validation_Agent",
            instruction=instruction,
            model=model or "bedrock/amazon.nova-lite-v1:0",
            tools=None,
            verbose=False
        )
        
        self.checker_tool = DataCompletenessCheckerTool()
    
    async def process_async(self, inputs: Dict[str, Any]) -> AgentResponse:
        data = inputs.get("extracted_data") or inputs.get("payload", {}).get("extracted_data")
        context_id = inputs.get("context_id", str(uuid.uuid4()))
        
        if not data:
            return AgentResponse(
                id=str(uuid.uuid4()),
                timestamp=datetime.now(timezone.utc).isoformat(),
                source_agent="Data Validation Agent",
                target_agent="Error",
                message_type="ERROR",
                payload={"error": "No data to validate"},
                context_id=context_id
            )
        
        logger.info(f"[Data Validation Agent] Validating completeness...")
        
        try:
            result = self.checker_tool.run({"invoice_data": data})
            
            return AgentResponse(
                id=str(uuid.uuid4()),
                timestamp=datetime.now(timezone.utc).isoformat(),
                source_agent="Data Validation Agent",
                target_agent="Business Validation Agent",
                message_type="TASK_HANDOFF",
                payload={
                    "extracted_data": data,
                    "validation_status": result.get("validation_status"),
                    "missing_fields": result.get("missing_fields", []),
                    "validation_results": result
                },
                context_id=context_id
            )
            
        except Exception as e:
            logger.error(f"Validation Error: {e}")
            return AgentResponse(
                id=str(uuid.uuid4()),
                timestamp=datetime.now(timezone.utc).isoformat(),
                source_agent="Data Validation Agent",
                target_agent="Error",
                message_type="ERROR",
                payload={"error": str(e)},
                context_id=context_id
            )
    
    def process(self, inputs: Dict[str, Any]) -> AgentResponse:
        import asyncio
        return asyncio.run(self.process_async(inputs))


if __name__ == "__main__":
    import asyncio
    
    async def test_agent():
        agent = DataValidationAgent()
        agent.print_info()
        
        print("\n" + "="*70)
        print("DATA VALIDATION AGENT TEST")
        print("="*70 + "\n")
        
        complete_invoice = {
            "invoice_no": "INV-2024-001",
            "invoice_date": "2024-12-12",
            "vendor_id": "VENDOR-123",
            "total_amount": 1500.00,
            "currency": "USD",
            "line_items": [
                {
                    "item_code": "ITEM001",
                    "description": "Product A",
                    "quantity": 10,
                    "unit_price": 100.00,
                    "total": 1000.00
                },
                {
                    "item_code": "ITEM002",
                    "description": "Product B",
                    "quantity": 5,
                    "unit_price": 100.00,
                    "total": 500.00
                }
            ]
        }
        
        incomplete_invoice = {
            "invoice_no": "INV-2024-002",
            "invoice_date": "2024-12-12",
            "total_amount": 2500.00,
            "line_items": []
        }
        
        missing_critical_fields = {
            "invoice_no": "INV-2024-003",
            "currency": "USD",
            "line_items": [
                {
                    "description": "Product C",
                    "quantity": 5,
                    "unit_price": 50.00
                }
            ]
        }
        
        print("="*70)
        print("TEST 1: Validate Complete Invoice")
        print("="*70)
        
        test_inputs_1 = {
            "context_id": "test-validation-001",
            "extracted_data": complete_invoice
        }
        
        response1 = await agent.process_async(test_inputs_1)
        
        print(f"Message Type: {response1.message_type}")
        print(f"Source Agent: {response1.source_agent}")
        print(f"Target Agent: {response1.target_agent}")
        print(f"Validation Status: {response1.payload.get('validation_status')}")
        print(f"Missing Fields: {response1.payload.get('missing_fields')}")
        
        if response1.payload.get('validation_status') == 'valid':
            print("Result: PASS - All required fields present")
        else:
            print("Result: FAIL - Missing fields detected")
        
        print()
        
        print("="*70)
        print("TEST 2: Validate Incomplete Invoice (Missing Vendor & Empty Line Items)")
        print("="*70)
        
        test_inputs_2 = {
            "context_id": "test-validation-002",
            "extracted_data": incomplete_invoice
        }
        
        response2 = await agent.process_async(test_inputs_2)
        
        print(f"Message Type: {response2.message_type}")
        print(f"Validation Status: {response2.payload.get('validation_status')}")
        print(f"Missing Fields: {response2.payload.get('missing_fields')}")
        
        if response2.payload.get('missing_fields'):
            print(f"\nIssues Found:")
            for field in response2.payload.get('missing_fields', []):
                print(f"  - {field}")
        
        print()
        
        print("="*70)
        print("TEST 3: Validate Invoice with Critical Fields Missing")
        print("="*70)
        
        test_inputs_3 = {
            "context_id": "test-validation-003",
            "extracted_data": missing_critical_fields
        }
        
        response3 = await agent.process_async(test_inputs_3)
        
        print(f"Message Type: {response3.message_type}")
        print(f"Validation Status: {response3.payload.get('validation_status')}")
        print(f"Missing Fields: {response3.payload.get('missing_fields')}")
        
        critical_missing = [f for f in response3.payload.get('missing_fields', []) 
                          if any(x in f for x in ['invoice_date', 'total_amount', 'vendor_id'])]
        
        if critical_missing:
            print(f"\nCritical Fields Missing:")
            for field in critical_missing:
                print(f"  - {field}")
        
        print()
        
        print("="*70)
        print("TEST 4: Handle No Data Scenario")
        print("="*70)
        
        test_inputs_4 = {
            "context_id": "test-validation-004"
        }
        
        response4 = await agent.process_async(test_inputs_4)
        
        print(f"Message Type: {response4.message_type}")
        print(f"Target Agent: {response4.target_agent}")
        print(f"Error: {response4.payload.get('error')}")
        
        print()
        
        print("="*70)
        print("TEST 5: Validate Line Items with Missing Item Codes")
        print("="*70)
        
        line_items_missing_codes = {
            "invoice_no": "INV-2024-005",
            "invoice_date": "2024-12-12",
            "vendor_id": "VENDOR-789",
            "total_amount": 500.00,
            "currency": "USD",
            "line_items": [
                {
                    "description": "Product without code",
                    "quantity": 10,
                    "unit_price": 50.00
                }
            ]
        }
        
        test_inputs_5 = {
            "context_id": "test-validation-005",
            "extracted_data": line_items_missing_codes
        }
        
        response5 = await agent.process_async(test_inputs_5)
        
        print(f"Validation Status: {response5.payload.get('validation_status')}")
        print(f"Missing Fields: {response5.payload.get('missing_fields')}")
        
        item_code_issues = [f for f in response5.payload.get('missing_fields', []) 
                           if 'item_code' in f]
        
        if item_code_issues:
            print(f"\nLine Item Issues:")
            for issue in item_code_issues:
                print(f"  - {issue}")
        
        print("\n" + "="*70)
        print("ALL TESTS COMPLETED")
        print("="*70)
        
        print("\nValidation Summary:")
        test_results = [
            ("Complete Invoice", response1.payload.get('validation_status') == 'valid'),
            ("Incomplete Invoice", response2.payload.get('validation_status') == 'invalid'),
            ("Missing Critical Fields", response3.payload.get('validation_status') == 'invalid'),
            ("No Data Error", response4.message_type == 'ERROR'),
            ("Missing Item Codes", response5.payload.get('validation_status') == 'invalid')
        ]
        
        for test_name, passed in test_results:
            status = "PASS" if passed else "FAIL"
            print(f"  {test_name}: {status}")
    
    try:
        asyncio.run(test_agent())
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
    except Exception as e:
        print(f"\n\nError during testing: {e}")
        import traceback
        traceback.print_exc()