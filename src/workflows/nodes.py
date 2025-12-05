import httpx
import json
from loguru import logger
from src.core.state import InvoiceState, ProcessingStatus
from src.tools.ocr_engine import OCREngine
from src.mcp_server.erp import logic_validate_line_item
from src.mcp_server.rag import logic_ingest_invoice

ocr_tool = OCREngine()

def extractor_node(state: InvoiceState) -> InvoiceState:
    logger.info(f"► NODE: Extractor | File: {state['file_name']}")
    try:
        raw_text = ocr_tool.extract(state['file_path'])
        state['raw_text'] = raw_text
        
        # Log snippet for debugging
        logger.debug(f"OCR Content (First 200 chars):\n{raw_text[:200]}...")
        
        logic_ingest_invoice(raw_text, state['file_name'])
        
        state['current_step'] = "extractor"
        state['status'] = ProcessingStatus.EXTRACTED
    except Exception as e:
        logger.error(f"Extraction Failed: {e}")
        state['error'] = str(e)
        state['status'] = ProcessingStatus.FAILED
    return state

def translator_node(state: InvoiceState) -> InvoiceState:
    logger.info(f"► NODE: Translator | File: {state['file_name']}")
    
    url = "http://localhost:8001/translate"
    payload = {
        "raw_text": state['raw_text'],
        "metadata": state['metadata'],
        "target_language": "English"
    }
    
    try:
        with httpx.Client(timeout=60) as client:
            logger.debug(f"A2A Request to {url}")
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            
            # VERBOSE LOGGING: Raw Structure
            logger.debug(f"▼ A2A RESPONSE DATA ▼\n{json.dumps(data['structured_data'], indent=2)}")

            if data.get('structured_data', {}).get('error'):
                 raise ValueError(data['structured_data']['error'])

            state['extracted_data'] = data['structured_data']
            state['standardized_invoice'] = data['structured_data']
            state['current_step'] = "translator"
            state['status'] = ProcessingStatus.TRANSLATED
            
    except Exception as e:
        logger.error(f"Translation Failed: {e}")
        state['error'] = str(e)
        state['status'] = ProcessingStatus.FAILED
        
    return state

def validator_node(state: InvoiceState) -> InvoiceState:
    logger.info(f"► NODE: Validator | File: {state['file_name']}")
    
    invoice = state.get('extracted_data', {})
    if not invoice or 'line_items' not in invoice:
        logger.error("Validation Halt: No line_items found in extraction.")
        state['validation_report'] = {"valid": False, "error": "Missing line items"}
        state['status'] = ProcessingStatus.VALIDATED 
        return state

    discrepancies = []
    
    for item in invoice.get('line_items', []):
        code = item.get('item_code') or "UNKNOWN"
        price = item.get('unit_price') or 0.0
        currency = item.get('currency') or "USD"

        # Logic Check
        res = logic_validate_line_item(item_code=code, unit_price=price, currency=currency)
        
        if res['status'] != 'match':
            logger.warning(f"  ⚠ Validation Issue [{code}]: {res['reason']}")
            if res['status'] == 'discrepancy':
                discrepancies.append(f"Item {code}: {res['reason']}")
            elif res['status'] == 'mismatch':
                discrepancies.append(f"Item {code}: SKU not found in ERP.")

    report = {
        "is_valid": len(discrepancies) == 0,
        "discrepancies": discrepancies,
        "line_items_checked": len(invoice['line_items'])
    }
    
    # Audit Log Entry
    audit_msg = f"AUDIT: {state['file_name']} | Valid: {report['is_valid']} | Issues: {len(discrepancies)}"
    logger.bind(AUDIT=True).info(audit_msg)
    
    state['validation_report'] = report
    state['current_step'] = "validator"
    state['status'] = ProcessingStatus.VALIDATED
    
    return state

def reporter_node(state: InvoiceState) -> InvoiceState:
    logger.info(f"► NODE: Reporter | File: {state['file_name']}")
    
    if state['status'] == ProcessingStatus.FAILED:
        logger.error(f"❌ STOP: Workflow Failed - {state['error']}")
        return state

    report = state.get('validation_report', {})
    if report.get('is_valid'):
        logger.success(f"✅ APPROVED: {state['file_name']}")
    else:
        logger.warning(f"❌ REVIEW REQUIRED: {state['file_name']}")
            
    state['status'] = ProcessingStatus.COMPLETED
    return state