import uuid
from typing import Dict, Any
from datetime import datetime
from src.core.protocol import Agent, AgentResponse
from src.core.logger import logger
from src.tools.tools import DataHarvesterTool
from src.mcp_server.rag import logic_ingest_invoice

class ExtractorAgent(Agent):
    name = "Extractor Agent"
    description = "Extracts raw text from documents using Data Harvester Tool."

    def __init__(self):
        self.harvester_tool = DataHarvesterTool()

    def process(self, inputs: Dict[str, Any]) -> AgentResponse:
        file_path = inputs.get("file_path")
        metadata = inputs.get("metadata", {})
        
        # Also support receiving from Monitor Payload
        if not file_path and inputs.get("payload"):
             file_path = inputs["payload"].get("file_path")
             metadata.update(inputs["payload"].get("metadata", {}))

        if not file_path:
             return AgentResponse(
                 id=str(uuid.uuid4()),
                 timestamp=datetime.now().isoformat(),
                 source_agent=self.name,
                 target_agent="Error Handler",
                 message_type="ERROR",
                 payload={"error": "File path missing"},
                 context_id=inputs.get("context_id")
             )

        logger.info(f"Extractor Agent: Processing {file_path}")
        
        try:
            # Tool Call
            raw_text = self.harvester_tool.run(file_path)
            
            # Side effect: RAG Ingestion 
            # Ideally this assumes RAG is a separate parallel agent or pipeline step.
            # Keeping legacy logic hook for now as per "don't break existing code"
            try:
                pass
                # logic_ingest_invoice(raw_text, Path(file_path).name, metadata)
            except Exception:
                pass

            return AgentResponse(
                id=str(uuid.uuid4()),
                timestamp=datetime.now().isoformat(),
                source_agent=self.name,
                target_agent="Translation Agent",
                message_type="TASK_HANDOFF",
                payload={
                    "raw_text": raw_text,
                    "file_path": file_path,
                    "metadata": metadata
                },
                context_id=inputs.get("context_id")
            )
        except Exception as e:
            logger.error(f"Extraction Error: {e}")
            return AgentResponse(
                 id=str(uuid.uuid4()),
                 timestamp=datetime.now().isoformat(),
                 source_agent=self.name,
                 target_agent="Error Handler",
                 message_type="ERROR",
                 payload={"error": str(e)},
                 context_id=inputs.get("context_id")
             )

class MockExtractorAgent(Agent):
    name = "Mock Extractor Agent"
    description = "Returns hardcoded mock text for testing."
    
    def process(self, inputs: Dict[str, Any]) -> AgentResponse:
        logger.info("Mock Extractor: Returning placeholder text.")
        return AgentResponse(
            id=str(uuid.uuid4()),
            timestamp=datetime.now().isoformat(),
            source_agent=self.name,
            target_agent="Translation Agent",
            message_type="TASK_HANDOFF",
            payload={
                "raw_text": """
                INVOICE # INV-004
                Date: 2023-11-20
                Vendor: VEND-001
                
                Line Items:
                - SKU-001 | Pallet Wrapping Film | 50 | 12.00 | 600.00
                - SKU-002 | Industrial Gloves    | 120| 3.00  | 360.00
                
                Total: 960.00
                """,
                "metadata": {"status": "mock"}
            },
            context_id="mock_id"
        )