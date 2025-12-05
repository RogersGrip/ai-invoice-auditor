from src.core.state import InvoiceState, ProcessingStatus
from src.tools.ocr_engine import OCREngine
from loguru import logger

ocr_tool = OCREngine()

def extractor_node(state: InvoiceState) -> InvoiceState:
    '''Extract text from invoice using OCR 

    Args:
        state (InvoiceState): Current state of the invoice processing
    
    Returns:
        InvoiceState: Updated state with extracted text or error info
    '''

    logger.info(f"Extractor Node: Processing {state['file_name']}")
    
    try:
        raw_text = ocr_tool.extract(state['file_path'])
        
        # Update state with extracted text
        state['raw_text'] = raw_text
        state['status'] = ProcessingStatus.EXTRACTED
        state['current_step'] = "extractor"
        
        logger.debug(f"Extraction successful. Length: {len(raw_text)} chars")
        
    except Exception as e:
        logger.error(f"Extraction failed: {e}")
        state['error'] = str(e)
        state['status'] = ProcessingStatus.FAILED
        
    return state