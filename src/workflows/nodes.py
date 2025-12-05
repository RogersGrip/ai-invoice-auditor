import httpx
import json
import os
from fpdf import FPDF
from loguru import logger
from langfuse import observe
from src.core.state import InvoiceState, ProcessingStatus
from src.tools.ocr_engine import OCREngine
from src.mcp_server.erp import logic_validate_line_item
from src.mcp_server.rag import logic_ingest_invoice
from src.core.utils import print_hitl_analysis

ocr_tool = OCREngine()

@observe(name="extractor_node", as_type="chain")
def extractor_node(state: InvoiceState) -> InvoiceState:
    logger.info(f"► NODE: Extractor | File: {state['file_name']}")
    try:
        raw_text = ocr_tool.extract(state['file_path'])
        state['raw_text'] = raw_text
        
        # Ingest with Full Metadata
        logic_ingest_invoice(raw_text, state['file_name'], state['metadata'])
        
        state['current_step'] = "extractor"
        state['status'] = ProcessingStatus.EXTRACTED
    except Exception as e:
        logger.error(f"Extraction Failed: {e}")
        state['error'] = str(e)
        state['status'] = ProcessingStatus.FAILED
    return state

@observe(name="translator_node", as_type="chain")
def translator_node(state: InvoiceState) -> InvoiceState:
    logger.info(f"► NODE: Standardizer | File: {state['file_name']}")
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
            
            if data.get('structured_data', {}).get('error'):
                 raise ValueError(data['structured_data']['error'])

            state['extracted_data'] = data['structured_data']
            state['standardized_invoice'] = data['structured_data']
            state['current_step'] = "translator"
            state['status'] = ProcessingStatus.TRANSLATED
            
            # HITL Simulation
            print_hitl_analysis("Standardization", data['structured_data'], ["Translation/Extraction Complete"])

    except Exception as e:
        logger.error(f"Standardization Failed: {e}")
        state['error'] = str(e)
        state['status'] = ProcessingStatus.FAILED
    return state

@observe(name="validator_node", as_type="chain")
def validator_node(state: InvoiceState) -> InvoiceState:
    logger.info(f"► NODE: Validator | File: {state['file_name']}")
    invoice = state.get('extracted_data', {})
    
    if not invoice or 'line_items' not in invoice:
        state['validation_report'] = {"valid": False, "error": "Missing line items"}
        state['status'] = ProcessingStatus.VALIDATED
        return state

    discrepancies = []
    for item in invoice.get('line_items', []):
        code = item.get('item_code') or "UNKNOWN"
        price = item.get('unit_price') or 0.0
        currency = item.get('currency') or "USD"
        
        res = logic_validate_line_item(item_code=code, unit_price=price, currency=currency)
        
        if res['status'] != 'match':
            if res['status'] == 'discrepancy':
                discrepancies.append(f"Item {code}: {res['reason']}")
            elif res['status'] == 'mismatch':
                discrepancies.append(f"Item {code}: SKU not found in ERP.")

    report = {
        "is_valid": len(discrepancies) == 0,
        "discrepancies": discrepancies,
        "total_lines": len(invoice['line_items'])
    }
    
    state['validation_report'] = report
    state['current_step'] = "validator"
    state['status'] = ProcessingStatus.VALIDATED
    
    print_hitl_analysis("Validation", report, discrepancies)
    
    return state

def _generate_pdf_report(state: InvoiceState, output_path: str):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt=f"Invoice Audit Report: {state['file_name']}", ln=1, align='C')
    pdf.ln(10)
    
    report = state.get('validation_report', {})
    status = "APPROVED" if report.get('is_valid') else "REVIEW REQUIRED"
    pdf.set_text_color(0, 128, 0) if status == "APPROVED" else pdf.set_text_color(255, 0, 0)
    pdf.cell(200, 10, txt=f"Status: {status}", ln=1)
    pdf.set_text_color(0, 0, 0)
    
    pdf.cell(200, 10, txt=f"Total Lines: {report.get('total_lines')}", ln=1)
    pdf.ln(5)
    
    if report.get('discrepancies'):
        pdf.cell(200, 10, txt="Discrepancies Found:", ln=1)
        pdf.set_font("Arial", size=10)
        for disc in report['discrepancies']:
            pdf.cell(200, 10, txt=f"- {disc}", ln=1)
            
    pdf.output(output_path)

@observe(name="reporter_node", as_type="chain")
def reporter_node(state: InvoiceState) -> InvoiceState:
    logger.info(f"► NODE: Reporter | File: {state['file_name']}")
    if state['status'] == ProcessingStatus.FAILED:
        return state

    output_dir = "./outputs/reports"
    os.makedirs(output_dir, exist_ok=True)
    base_name = os.path.splitext(state['file_name'])[0]
    
    # JSON Report
    json_path = f"{output_dir}/{base_name}_report.json"
    with open(json_path, 'w') as f:
        json.dump(state['validation_report'], f, indent=2)
        
    # PDF Report
    pdf_path = f"{output_dir}/{base_name}_report.pdf"
    try:
        _generate_pdf_report(state, pdf_path)
    except Exception as e:
        logger.error(f"PDF Generation failed: {e}")

    # HTML Snippet (Simple)
    html_path = f"{output_dir}/{base_name}_report.html"
    status_color = "green" if state['validation_report']['is_valid'] else "red"
    html_content = f"""
    <html><body>
    <h1>Audit Report: {state['file_name']}</h1>
    <h2 style='color:{status_color}'>Status: {'APPROVED' if state['validation_report']['is_valid'] else 'REVIEW REQUIRED'}</h2>
    <ul>
    {''.join([f'<li>{d}</li>' for d in state['validation_report']['discrepancies']])}
    </ul>
    </body></html>
    """
    with open(html_path, 'w') as f:
        f.write(html_content)

    logger.success(f"Reports generated in {output_dir}")
    state['status'] = ProcessingStatus.COMPLETED
    return state