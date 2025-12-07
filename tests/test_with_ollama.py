import os
import sys
from loguru import logger

# Add project root to sys.path
import asyncio
try:
    asyncio.get_event_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

sys.path.append(os.getcwd())

from src.core.config import settings
from src.core.state import InvoiceState, ProcessingStatus
from src.workflows.graph import create_invoice_graph

def run_ollama_test():
    logger.info(">>> starting OLLAMA Integration Test <<<")
    
    import asyncio
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    # 1. Override Settings
    settings.MODEL_PROVIDER = "ollama"
    settings.OLLAMA_MODEL = "llama3" # Ensure you have this pulled: ollama pull llama3
    
    logger.info(f"Configuration: Provider={settings.MODEL_PROVIDER}, Model={settings.OLLAMA_MODEL}")
    
    # 2. Setup Mock Data
    sample_text = """
    INVOICE
    Invoice No: INV-2024-001
    Date: 2024-05-20
    Vendor: VEND-001
    
    Item Code   Description     Qty    Unit Price   Total
    SKU-001     Widget A        10     50.00        500.00
    SKU-002     Widget B        5      20.00        100.00
    
    Total Amount: 600.00 USD
    """
    
    # 3. Create Graph
    app = create_invoice_graph()
    
    # 4. Initialize State with Pre-Extracted Text (Skipping OCR for this test)
    state = InvoiceState(
        file_path="test_invoice.txt",
        file_name="test_invoice.txt",
        raw_text=sample_text,
        current_step="extractor", # Start after extraction
        status=ProcessingStatus.EXTRACTED # Pretend we just extracted
    )
    
    # 5. Run Workflow
    logger.info("Invoking Workflow...")
    try:
        final_state_output = app.invoke(state)
        
        # Handle dict output from graph
        final_state = final_state_output
        if not isinstance(final_state, dict):
            final_state = final_state_output.model_dump()
            
        logger.info(f"Final Status: {final_state.get('status')}")
        logger.info(f"Validation Report: {final_state.get('validation_report')}")
        
        if final_state.get('status') == ProcessingStatus.COMPLETED:
            logger.success("✔ Ollama Test PASSED")
        else:
            logger.error("✘ Ollama Test FAILED status check")
            
    except Exception as e:
        logger.error(f"Test Failed with Exception: {e}")

if __name__ == "__main__":
    run_ollama_test()
