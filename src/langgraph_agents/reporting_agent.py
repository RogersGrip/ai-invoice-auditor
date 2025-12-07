import os
import json
import uuid
from fpdf import FPDF
from typing import Dict, Any
from datetime import datetime
from src.core.protocol import Agent, AgentResponse
from src.core.logger import logger
from src.core.config import settings
from src.tools.tools import InsightReporterTool

class ReporterAgent(Agent):
    name = "Reporting Agent"
    description = "Generates comprehensive PDF, JSON, and HTML audit reports."
    
    def __init__(self):
        self.reporter_tool = InsightReporterTool()

    def process(self, inputs: Dict[str, Any]) -> AgentResponse:
        # Resolve Inputs from Payload
        payload = inputs.get("payload", {})
        
        # We expect a merged context or specific keys
        # The payload might come from Business Validation Agent which has { "validated_data": ..., "business_validation_status": ... }
        # Ideally, we need the earlier validation results (missing fields) too.
        # Implied: Context handling or aggregation.
        # For this step, let's assume 'inputs' contains everything needed or we extract what we can.
        
        extracted_data = payload.get("validated_data") or inputs.get("extracted_data", {})
        validation_report = {
            "business_status": payload.get("business_validation_status"),
            "discrepancies": payload.get("discrepancies", []),
            "is_valid": payload.get("business_validation_status") == "match" # Simplified logic
        }
        
        # Fallback if direct input
        if not extracted_data:
             extracted_data = inputs.get("extracted_data", {})
             
        # Metadata
        file_path = inputs.get("file_path") or payload.get("file_path", "unknown_report")
        file_name = os.path.basename(file_path)
        
        metadata = inputs.get("metadata", {})
        overall_status = "COMPLETED"
        
        # Ensure output dir
        os.makedirs(settings.OUTPUT_DIR, exist_ok=True)
        base_name = os.path.splitext(file_name)[0]
        
        logger.info(f"Reporter Agent: Generating detailed reports for {base_name}")
        
        # 1. JSON Report (Complete Dump)
        json_dump = {
            "meta": {
                "file_name": file_name,
                "status": overall_status,
                "timestamp": datetime.now().isoformat(),
                "metadata": metadata
            },
            "extraction": extracted_data,
            "validation": validation_report
        }
        json_path = f"{settings.OUTPUT_DIR}/{base_name}_report.json"
        with open(json_path, 'w') as f:
            json.dump(json_dump, f, indent=2)

        # 2. PDF Report
        pdf_path = f"{settings.OUTPUT_DIR}/{base_name}_report.pdf"
        try:
            self._generate_pdf(base_name, json_dump, pdf_path)
        except Exception as e:
            logger.error(f"PDF Generation Error: {e}")

        # 3. HTML Snippet
        html_path = f"{settings.OUTPUT_DIR}/{base_name}_report.html"
        self._generate_html(base_name, json_dump, html_path)
        
        return AgentResponse(
            id=str(uuid.uuid4()),
            source_agent=self.name,
            target_agent="End",
            timestamp=datetime.now().isoformat(),
            message_type="RESPONSE",
            payload={
                "json_report": json_path,
                "pdf_report": pdf_path,
                "html_report": html_path,
                "summary": "Reports generated successfully."
            },
            context_id=inputs.get("context_id")
        )

    def _sanitize_text(self, text: str) -> str:
        """
        Sanitize text for FPDF (Latin-1).
        Replaces common unicode characters with ASCII equivalents.
        """
        replacements = {
            "\u20ac": "EUR",  # Euro
            "\u2013": "-",    # En dash
            "\u2014": "--",   # Em dash
            "\u2018": "'",    # Left single quote
            "\u2019": "'",    # Right single quote
            "\u201c": '"',    # Left double quote
            "\u201d": '"',    # Right double quote
            "\u2022": "-",    # Bullet
            "…": "..."        # Ellipsis
        }
        for char, repl in replacements.items():
            text = text.replace(char, repl)
        
        # Final fallback: encode to latin-1, replacing unencodable chars with '?'
        return text.encode('latin-1', 'replace').decode('latin-1')

    def _generate_pdf(self, title: str, data: Dict, path: str):
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", 'B', 16)
        
        # Header
        pdf.cell(0, 10, "AI Invoice Auditor - Audit Report", ln=1, align='C')
        pdf.line(10, 20, 200, 20)
        pdf.ln(10)

        # File Info
        pdf.set_font("Arial", size=10)
        status = data["meta"]["status"]
        status_color = (0, 128, 0) if "COMPLETED" in status and data["validation"].get("is_valid") else (200, 0, 0)
        
        pdf.cell(0, 8, f"File: {self._sanitize_text(data['meta']['file_name'])}", ln=1)
        pdf.set_text_color(*status_color)
        pdf.set_font("Arial", 'B', 10)
        pdf.cell(0, 8, f"Processing Status: {status}", ln=1)
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("Arial", size=10)
        
        # Extracted Invoice Details
        ext = data.get("extraction", {})
        if ext:
            pdf.ln(5)
            pdf.set_font("Arial", 'B', 12)
            pdf.set_fill_color(230, 230, 230)
            pdf.cell(0, 8, "Invoice Summary", ln=1, fill=True)
            pdf.set_font("Arial", size=10)
            
            pdf.cell(50, 8, f"Invoice #: {self._sanitize_text(str(ext.get('invoice_no', 'N/A')))}", border=1)
            pdf.cell(50, 8, f"Date: {self._sanitize_text(str(ext.get('invoice_date', 'N/A')))}", border=1)
            pdf.cell(50, 8, f"Vendor: {self._sanitize_text(str(ext.get('vendor_id', 'N/A')))}", border=1)
            pdf.ln(8)
            pdf.cell(95, 8, f"Total Amount: {ext.get('total_amount', 0)} {self._sanitize_text(str(ext.get('currency', 'USD')))}", border=1)
            pdf.ln(12)
            
            # Line Items Table
            items = ext.get("line_items", [])
            if items:
                pdf.set_font("Arial", 'B', 10)
                pdf.cell(30, 8, "Code", border=1, fill=True)
                pdf.cell(80, 8, "Description", border=1, fill=True)
                pdf.cell(20, 8, "Qty", border=1, fill=True)
                pdf.cell(30, 8, "Price", border=1, fill=True)
                pdf.cell(30, 8, "Total", border=1, fill=True)
                pdf.ln(8)
                
                pdf.set_font("Arial", size=9)
                for item in items:
                    pdf.cell(30, 8, self._sanitize_text(str(item.get("item_code", ""))), border=1)
                    pdf.cell(80, 8, self._sanitize_text(str(item.get("description", "")))[:40], border=1)
                    pdf.cell(20, 8, str(item.get("qty", 0)), border=1)
                    pdf.cell(30, 8, str(item.get("unit_price", 0)), border=1)
                    pdf.cell(30, 8, str(item.get("total", 0)), border=1)
                    pdf.ln(8)

        # Validation Results
        val = data.get("validation", {})
        pdf.ln(10)
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(0, 8, "Validation & Audit Results", ln=1, fill=True)
        pdf.set_font("Arial", size=10)
        
        is_valid = val.get("is_valid", False)
        verdict = "APPROVED" if is_valid else "ISSUES DETECTED"
        pdf.set_text_color(0, 128, 0) if is_valid else pdf.set_text_color(200, 0, 0)
        pdf.cell(0, 8, f"Verdict: {verdict}", ln=1)
        pdf.set_text_color(0, 0, 0)
        
        discrepancies = val.get("discrepancies", [])
        if discrepancies:
            pdf.set_text_color(200, 0, 0)
            for d in discrepancies:
                pdf.cell(0, 6, f"- {self._sanitize_text(d)}", ln=1)
            pdf.set_text_color(0, 0, 0)
        else:
            pdf.cell(0, 6, "- No logic discrepancies found against ERP rules.", ln=1)

        pdf.output(path)

    def _generate_html(self, title: str, data: Dict, path: str):
        ext = data.get("extraction", {})
        val = data.get("validation", {})
        meta = data.get("meta", {})
        
        status_class = "success" if val.get("is_valid") else "error"
        status_text = "APPROVED" if val.get("is_valid") else "ADJUSTMENT REQUIRED"
        
        rows = ""
        for item in ext.get("line_items", []):
            rows += f"""
            <tr>
                <td>{item.get("item_code")}</td>
                <td>{item.get("description")}</td>
                <td>{item.get("qty")}</td>
                <td>{item.get("unit_price")}</td>
                <td>{item.get("total")}</td>
            </tr>
            """
            
        discrepancies_html = ""
        if val.get("discrepancies"):
            for d in val.get("discrepancies"):
                discrepancies_html += f"<li class='error-text'>{d}</li>"
        else:
            discrepancies_html = "<li class='success-text'>All checks passed successfully.</li>"
            
        html_content = f"""
        <html>
        <head>
            <title>Audit Report: {title}</title>
            <style>
                body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f4f6f9; padding: 20px; }}
                .container {{ max_width: 800px; margin: 0 auto; background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
                h1 {{ color: #2c3e50; border-bottom: 2px solid #ecf0f1; padding-bottom: 10px; }}
                .badge {{ padding: 5px 10px; border-radius: 4px; font-weight: bold; color: white; display: inline-block; }}
                .badge.success {{ background-color: #27ae60; }}
                .badge.error {{ background-color: #c0392b; }}
                .section {{ margin-top: 25px; }}
                table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
                th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
                th {{ background-color: #f8f9fa; color: #666; }}
                .error-text {{ color: #c0392b; font-weight: 500; }}
                .success-text {{ color: #27ae60; font-weight: 500; }}
                .meta {{ font-size: 0.9em; color: #7f8c8d; margin-bottom: 20px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>🧾 Invoice Audit Report</h1>
                <div class="meta">
                    Filename: <strong>{meta.get('file_name')}</strong> | 
                    Status: <span class="badge {status_class}">{status_text}</span> |
                    System Status: {meta.get('status')}
                </div>
                
                <div class="section">
                    <h3>🔍 Extracted Details</h3>
                    <div style="display: flex; justify-content: space-between; background: #f8f9fa; padding: 15px; border-radius: 5px;">
                        <div>
                            <strong>Invoice #:</strong> {ext.get('invoice_no', 'N/A')}<br>
                            <strong>Date:</strong> {ext.get('invoice_date', 'N/A')}
                        </div>
                        <div>
                            <strong>Vendor:</strong> {ext.get('vendor_id', 'N/A')}<br>
                            <strong>Total:</strong> {ext.get('total_amount')} {ext.get('currency')}
                        </div>
                    </div>
                </div>

                <div class="section">
                    <h3>📦 Line Items</h3>
                    <table>
                        <tr>
                            <th>Code</th><th>Description</th><th>Qty</th><th>Price</th><th>Total</th>
                        </tr>
                        {rows}
                    </table>
                </div>

                <div class="section">
                    <h3>🛡️ Compliance Check</h3>
                    <ul>
                        {discrepancies_html}
                    </ul>
                </div>
                
                <div class="section">
                    <p><em>Generated by AI Invoice Auditor</em></p>
                </div>
            </div>
        </body>
        </html>
        """
        with open(path, 'w', encoding="utf-8") as f:
            f.write(html_content)
