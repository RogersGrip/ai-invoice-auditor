from typing import Dict, Any
from src.core.protocol import Agent, AgentResponse
from src.tools.ocr_engine import OCREngine
from src.core.logger import logger
from src.mcp_server.rag import logic_ingest_invoice # Legacy hook, maybe move to RAG Agent later

class ExtractorAgent(Agent):
    name = "Extractor Agent"
    description = "Extracts raw text from documents using OCR."

    def __init__(self):
        self.ocr = OCREngine()

    def process(self, inputs: Dict[str, Any]) -> AgentResponse:
        file_path = inputs.get("file_path")
        file_name = inputs.get("file_name")
        metadata = inputs.get("metadata", {})
        
        if not file_path:
             return AgentResponse(content=None, metadata={"error": "File path missing"})

        logger.info(f"Extractor Agent: Processing {file_name}")
        
        try:
            raw_text = self.ocr.extract(file_path)
            
            # Side effect: RAG Ingestion (Optional: Could be separate step in graph)
            # For now keeping it here as per original flow, but using silent ingestion
            try:
                # We should use IndexingAgent here properly via A2A, but for now direct call or legacy
                # logic_ingest_invoice(raw_text, file_name, metadata)
                pass
            except Exception:
                pass

            return AgentResponse(
                content=raw_text, 
                metadata={"status": "success", "length": len(raw_text)}
            )
        except Exception as e:
            logger.error(f"Extraction Error: {e}")
            return AgentResponse(content=None, metadata={"error": str(e)})

class MockExtractorAgent(Agent):
    name = "Mock Extractor Agent"
    description = "Returns hardcoded mock text for testing."
    
    def process(self, inputs: Dict[str, Any]) -> AgentResponse:
        logger.info("Mock Extractor: Returning placeholder text.")
        return AgentResponse(
            content="""
            INVOICE # INV-004
            Date: 2023-11-20
            Vendor: VEND-001
            
            Line Items:
            - SKU-001 | Pallet Wrapping Film | 50 | 12.00 | 600.00
            - SKU-002 | Industrial Gloves    | 120| 3.00  | 360.00
            
            Total: 960.00
            """,
            metadata={"status": "mock"}
        )