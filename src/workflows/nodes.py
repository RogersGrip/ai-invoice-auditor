import httpx
from loguru import logger
from src.core.state import InvoiceState, ProcessingStatus
from src.tools.ocr_engine import OCREngine
from src.mcp_server.erp import logic_validate_line_item
from src.mcp_server.rag import logic_ingest_invoice

# Initialize Tool
ocr_tool = OCREngine()

def extractor_node(state: InvoiceState) -> InvoiceState:
    logger.info(f"Step: Extraction | File: {state['file_name']}")
    try:
        # 1. Optical Character Recognition
        raw_text = ocr_tool.extract(state['file_path'])
        state['raw_text'] = raw_text
        
        # 2. RAG Indexing (Memory)
        logic_ingest_invoice(raw_text, state['file_name'])
        
        state['current_step'] = "extractor"
        state['status'] = ProcessingStatus.EXTRACTED
    except Exception as e:
        logger.error(f"Extraction Error: {e}")
        state['error'] = str(e)
        state['status'] = ProcessingStatus.FAILED
    return state

def translator_node(state: InvoiceState) -> InvoiceState:
    logger.info(f"Step: Translation (A2A) | File: {state['file_name']}")
    
    # Call the External Agent
    url = "http://localhost:8001/translate"
    
    payload = {
        "raw_text": state['raw_text'],
        "metadata": state['metadata'],
        "target_language": "English"
    }
    
    try:
        with httpx.Client(timeout=60) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            
            # Map external agent response to internal state
            state['extracted_data'] = data['structured_data']
            state['standardized_invoice'] = data['structured_data']
            
            # Check for explicit errors in JSON response
            if data.get('structured_data', {}).get('error'):
                 raise ValueError(data['structured_data']['error'])

            state['current_step'] = "translator"
            state['status'] = ProcessingStatus.TRANSLATED
            
    except Exception as e:
        logger.error(f"Translation Agent Failed: {e}")
        state['error'] = f"Translation Agent Error: {e}"
        state['status'] = ProcessingStatus.FAILED
        
    return state

def validator_node(state: InvoiceState) -> InvoiceState:
    logger.info(f"Step: Validation | File: {state['file_name']}")
    
    invoice = state.get('extracted_data', {})
    
    # Guard clause for empty data
    if not invoice or 'line_items' not in invoice:
        state['validation_report'] = {"valid": False, "error": "No line items extraction found."}
        # We don't mark FAILED here because the validator 'ran' successfully, 
        # it just found invalid data. We let the reporter handle the verdict.
        state['status'] = ProcessingStatus.VALIDATED 
        return state

    discrepancies = []
    
    # Business Logic Check
    for item in invoice.get('line_items', []):
        code = item.get('item_code') or "UNKNOWN"
        price = item.get('unit_price') or 0.0
        currency = item.get('currency') or "USD"

        res = logic_validate_line_item(item_code=code, unit_price=price, currency=currency)
        
        if res['status'] == 'discrepancy':
            discrepancies.append(f"Item {code}: {res['reason']}")
        elif res['status'] == 'mismatch':
            discrepancies.append(f"Item {code}: SKU not found in ERP.")

    report = {
        "is_valid": len(discrepancies) == 0,
        "discrepancies": discrepancies,
        "line_items_checked": len(invoice['line_items'])
    }
    
    state['validation_report'] = report
    state['current_step'] = "validator"
    state['status'] = ProcessingStatus.VALIDATED
    
    return state

def reporter_node(state: InvoiceState) -> InvoiceState:
    logger.info(f"Step: Reporting | File: {state['file_name']}")
    
    # 1. Handle Critical System Failures (Early Exit)
    if state['status'] == ProcessingStatus.FAILED:
        logger.error(f"❌ FINAL VERDICT: SYSTEM FAILURE | {state['file_name']}")
        logger.error(f"   Reason: {state['error']}")
        return state

    # 2. Handle Validation Results
    report = state.get('validation_report', {})
    valid = report.get('is_valid', False)
    issues = report.get('discrepancies', [])
    error = report.get('error')

    if valid:
        logger.success(f"✅ FINAL VERDICT: APPROVED | {state['file_name']}")
    else:
        logger.warning(f"❌ FINAL VERDICT: NEEDS REVIEW | {state['file_name']}")
        if error:
            logger.warning(f"   - Validation Error: {error}")
        for issue in issues:
            logger.warning(f"   - {issue}")
            
    state['status'] = ProcessingStatus.COMPLETED
    return state