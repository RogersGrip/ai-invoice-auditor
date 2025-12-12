# business_validator_agent.py

import json
import uuid
import os
from typing import Dict, Any
from datetime import datetime, timezone

from agent_adk import AgentADK
from src.core.protocol import AgentResponse
from src.mcp_server.erp import logic_validate_line_item


class BusinessValidationAgent(AgentADK):
    """BusinessValidationAgent using ADK framework without tools (Cohere doesn't support function calling)"""
    
    def __init__(self, model: str = "bedrock/amazon.nova-lite-v1:0"):
        """
        Initialize BusinessValidationAgent
        
        Args:
            model: LLM model identifier (use Nova Lite for tool support, not Cohere)
        """
        instruction = """You are an expert ERP Auditor. Your task is to validate invoice line items against ERP business rules.

When given a list of invoice line items in JSON format, you should:

1. Review each line item carefully
2. Check for the following validation criteria:
   - Item code should be valid (alphanumeric, typically 6-12 characters)
   - Unit price should be reasonable (positive number, typically between 0.01 and 10000.00)
   - Currency should be a valid 3-letter code (USD, EUR, GBP, etc.)
   - Quantity should be a positive integer

3. Provide a summary with:
   - Total items validated
   - Status: MATCH (all items valid) or MISMATCH (one or more issues found)
   - List any specific discrepancies found

Be thorough but concise in your analysis."""
        
        # Use Nova Lite which supports better reasoning, or remove tools for Cohere
        super().__init__(
            name="Business_Validation_Agent",
            instruction=instruction,
            model=model,
            tools=None,  # Cohere doesn't support function calling on Bedrock
            verbose=True
        )
        
        # Store reference to validation function for direct use
        self.validate_func = logic_validate_line_item
    
    async def process_async(self, inputs: Dict[str, Any]) -> AgentResponse:
        """
        Asynchronous processing that validates invoice line items.
        
        Args:
            inputs: Dictionary containing validated_data or extracted_data with line_items
        
        Returns:
            AgentResponse with validation results
        """
        # Extract data
        data = inputs.get("validated_data") or inputs.get("extracted_data", {})
        line_items = data.get("line_items", [])
        context_id = inputs.get("context_id", str(uuid.uuid4()))
        
        # Handle empty line items
        if not line_items:
            return self._create_response("match", [], data, context_id, "No line items to validate")
        
        # Perform validation directly since tools aren't supported
        validation_results = []
        all_valid = True
        
        for item in line_items:
            try:
                result = self.validate_func(
                    item_code=item.get("item_code", ""),
                    unit_price=float(item.get("unit_price", 0)),
                    currency=item.get("currency", "USD")
                )
                validation_results.append({
                    "item": item,
                    "validation": result
                })
                
                if result.get("status") != "valid":
                    all_valid = False
                    
            except Exception as e:
                validation_results.append({
                    "item": item,
                    "validation": {"status": "error", "message": str(e)}
                })
                all_valid = False
        
        # Create validation summary for LLM review
        validation_summary = {
            "total_items": len(line_items),
            "validation_results": validation_results,
            "all_valid": all_valid
        }
        
        # Create prompt for LLM to analyze results
        task_prompt = f"""Please analyze the following invoice line item validation results:

{json.dumps(validation_summary, indent=2)}

Provide a brief summary indicating:
1. How many items were validated
2. Overall status (MATCH if all valid, MISMATCH if any issues)
3. List any specific discrepancies or issues found

Keep your response concise and professional."""
        
        # Setup session and process
        await self.setup_session()
        result_text = await self.process_message(task_prompt)
        await self.cleanup()
        
        # Determine final status based on validation
        status = "match" if all_valid else "mismatch"
        discrepancies = self._extract_discrepancies(validation_results) if not all_valid else []
        
        return self._create_response(status, discrepancies, data, context_id, result_text)
    
    def process(self, inputs: Dict[str, Any]) -> AgentResponse:
        """
        Synchronous wrapper for compatibility with existing pipeline.
        
        Args:
            inputs: Dictionary containing validated_data or extracted_data
        
        Returns:
            AgentResponse with validation results
        """
        import asyncio
        return asyncio.run(self.process_async(inputs))
    
    def _extract_discrepancies(self, validation_results: list) -> list:
        """
        Extract discrepancy details from validation results.
        
        Args:
            validation_results: List of validation result dictionaries
        
        Returns:
            List of discrepancy descriptions
        """
        discrepancies = []
        
        for result in validation_results:
            validation = result.get("validation", {})
            if validation.get("status") != "valid":
                item = result.get("item", {})
                item_code = item.get("item_code", "Unknown")
                message = validation.get("message", "Validation failed")
                discrepancies.append(f"Item {item_code}: {message}")
        
        return discrepancies
    
    def _create_response(
        self, 
        status: str, 
        discrepancies: list, 
        data: dict, 
        context_id: str,
        validation_summary: str = ""
    ) -> AgentResponse:
        """
        Create standardized AgentResponse object.
        
        Args:
            status: Validation status (match/mismatch)
            discrepancies: List of discrepancy descriptions
            data: Original validated data
            context_id: Context ID for tracking
            validation_summary: Full validation summary from agent
        
        Returns:
            AgentResponse object
        """
        return AgentResponse(
            id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc).isoformat(),
            source_agent="BusinessValidationAgent",
            target_agent="Reporting Agent",
            message_type="TASK_HANDOFF",
            payload={
                "business_validation_status": status,
                "discrepancies": discrepancies,
                "validated_data": data,
                "validation_summary": validation_summary
            },
            context_id=context_id
        )


# Example usage
if __name__ == "__main__":
    import asyncio
    
    async def test_agent():
        # Use Nova Lite instead of Cohere for better compatibility
        agent = BusinessValidationAgent(model="bedrock/amazon.nova-lite-v1:0")
        
        # Display agent info
        agent.print_info()
        
        # Test data
        test_inputs = {
            "context_id": "test-123",
            "extracted_data": {
                "line_items": [
                    {
                        "item_code": "ITEM001",
                        "unit_price": 100.0,
                        "currency": "USD",
                        "quantity": 5
                    },
                    {
                        "item_code": "ITEM002",
                        "unit_price": 250.0,
                        "currency": "USD",
                        "quantity": 2
                    },
                    {
                        "item_code": "INVALID",
                        "unit_price": -50.0,  # Invalid price
                        "currency": "USD",
                        "quantity": 1
                    }
                ]
            }
        }
        
        print("\n" + "="*60)
        print("Testing BusinessValidationAgent")
        print("="*60 + "\n")
        
        response = await agent.process_async(test_inputs)
        
        print("\n" + "="*60)
        print("VALIDATION RESULTS")
        print("="*60)
        print(f"Status: {response.payload['business_validation_status']}")
        print(f"\nDiscrepancies: {len(response.payload['discrepancies'])}")
        for disc in response.payload['discrepancies']:
            print(f"  - {disc}")
        print(f"\nSummary:\n{response.payload.get('validation_summary', 'N/A')}")
        print("="*60 + "\n")
    
    asyncio.run(test_agent())