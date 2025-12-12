# reporting_agent.py

import uuid
from typing import Dict, Any
from datetime import datetime, timezone

from agent_adk import AgentADK
from src.core.protocol import AgentResponse
from src.core.logger import logger
from src.tools.tools import InsightReporterTool


class ReportingAgent(AgentADK):
    
    def __init__(self, model: str = None):
        instruction = """You are a Report Generator responsible for creating comprehensive audit reports.

Your task is to analyze invoice processing results and generate detailed reports including:
- Extracted invoice data
- Validation results
- Safety check outcomes
- Overall processing status

Provide a brief summary of the report generation process."""
        
        super().__init__(
            name="Reporting_Agent",
            instruction=instruction,
            model=model or "bedrock/amazon.nova-lite-v1:0",
            tools=None,
            verbose=False
        )
        
        self.reporter_tool = InsightReporterTool()
    
    async def process_async(self, inputs: Dict[str, Any]) -> AgentResponse:
        file_name = inputs.get("file_name", "report")
        context_id = inputs.get("context_id", str(uuid.uuid4()))
        
        try:
            output_paths = self.reporter_tool.run({
                "file_name": file_name,
                "extracted_data": inputs.get("extracted_data", {}),
                "validation_report": inputs.get("validation_results", {}),
                "safety_report": inputs.get("safety_report", {}),
                "metadata": inputs.get("metadata", {})
            })
            
            return AgentResponse(
                id=str(uuid.uuid4()),
                timestamp=datetime.now(timezone.utc).isoformat(),
                source_agent="Reporting Agent",
                target_agent="Ingestion",
                message_type="RESPONSE",
                payload=output_paths,
                context_id=context_id
            )
            
        except Exception as e:
            logger.error(f"Reporting Error: {e}")
            return AgentResponse(
                id=str(uuid.uuid4()),
                timestamp=datetime.now(timezone.utc).isoformat(),
                source_agent="Reporting Agent",
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
    from pathlib import Path
    from src.core.config import settings
    
    async def test_agent():
        settings.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        
        agent = ReportingAgent()
        agent.print_info()
        
        print("\n" + "="*70)
        print("REPORTING AGENT TEST")
        print("="*70 + "\n")
        
        test_inputs = {
            "context_id": "test-report-001",
            "file_name": "test_invoice_001.pdf",
            "extracted_data": {
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
            },
            "validation_results": {
                "validation_status": "valid",
                "is_valid": True,
                "business_status": "match",
                "missing_fields": [],
                "discrepancies": []
            },
            "safety_report": {
                "is_safe": True,
                "confidence": 0.95,
                "issues": []
            },
            "metadata": {
                "processed_at": datetime.now().isoformat(),
                "pipeline_version": "1.0.0"
            }
        }
        
        print("="*70)
        print("TEST 1: Valid Invoice Report Generation")
        print("="*70)
        response = await agent.process_async(test_inputs)
        print(f"Message Type: {response.message_type}")
        print(f"Source Agent: {response.source_agent}")
        print(f"JSON Report: {response.payload.get('json')}")
        print(f"PDF Report: {response.payload.get('pdf')}")
        print()
        
        test_inputs_invalid = {
            "context_id": "test-report-002",
            "file_name": "test_invoice_002.pdf",
            "extracted_data": {
                "invoice_no": "INV-2024-002",
                "invoice_date": "2024-12-12",
                "vendor_id": "VENDOR-456",
                "total_amount": 2500.00,
                "currency": "USD"
            },
            "validation_results": {
                "validation_status": "invalid",
                "is_valid": False,
                "business_status": "mismatch",
                "missing_fields": ["line_items"],
                "discrepancies": ["Price mismatch for ITEM003"]
            },
            "safety_report": {
                "is_safe": False,
                "confidence": 0.45,
                "issues": ["Suspicious vendor pattern detected"]
            },
            "metadata": {
                "processed_at": datetime.now().isoformat(),
                "pipeline_version": "1.0.0"
            }
        }
        
        print("="*70)
        print("TEST 2: Invalid Invoice Report Generation")
        print("="*70)
        response2 = await agent.process_async(test_inputs_invalid)
        print(f"Message Type: {response2.message_type}")
        print(f"JSON Report: {response2.payload.get('json')}")
        print(f"PDF Report: {response2.payload.get('pdf')}")
        print()
        
        print("="*70)
        print("TEST 3: Verify Generated Files")
        print("="*70)
        json_file = Path(response.payload.get('json'))
        pdf_file = Path(response.payload.get('pdf'))
        
        print(f"JSON exists: {json_file.exists()}")
        print(f"PDF exists: {pdf_file.exists()}")
        
        if json_file.exists():
            import json
            with open(json_file) as f:
                report_data = json.load(f)
            print(f"JSON Report Status: {report_data['meta']['status']}")
            print(f"JSON Report Timestamp: {report_data['meta']['timestamp']}")
        
        print("\n" + "="*70)
        print("ALL TESTS COMPLETED")
        print("="*70)
        print(f"Generated reports in: {settings.OUTPUT_DIR.absolute()}")
    
    try:
        asyncio.run(test_agent())
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
    except Exception as e:
        print(f"\n\nError during testing: {e}")
        import traceback
        traceback.print_exc()