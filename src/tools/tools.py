import json
import uuid
from typing import Dict, Any, List
from pathlib import Path
from datetime import datetime, timezone
from fpdf import FPDF
from google.adk.tools import BaseTool
from google.genai.types import FunctionDeclaration, Schema, Type
from src.core.config import settings
from src.core.logger import logger
from src.database.qdrant_db import vector_store
from src.tools.ocr_engine import OCREngine
from src.core.state import InvoiceData
from src.core.llm_wrapper import LLMService
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_aws import ChatBedrockConverse, BedrockEmbeddings
from ragas import evaluate
from ragas.metrics import faithfulness, answer_relevancy, context_precision, context_recall, answer_correctness
from ragas.llms import LangchainLLMWrapper
from ragas.embeddings import LangchainEmbeddingsWrapper
from datasets import Dataset

class InsightReporterTool(BaseTool):
    def __init__(self):
        super().__init__(name="insight_reporter_tool", description="Generates detailed audit reports.")

    def _get_declaration(self):
        return FunctionDeclaration(
            name=self.name, description=self.description,
            parameters=Schema(type=Type.OBJECT, properties={"file_name": Schema(type=Type.STRING)}, required=["file_name"])
        )

    def _sanitize(self, text: Any) -> str:
        if text is None: return "N/A"
        return str(text).encode('latin-1', 'replace').decode('latin-1')

    def run(self, args: Dict[str, Any]) -> Dict[str, str]:
        file_name = args.get("file_name", "unknown")
        data = args.get("extracted_data", {})
        val = args.get("validation_report", {})
        safety = args.get("safety_report", {})
        metadata = args.get("metadata", {})
        
        base_name = Path(file_name).stem
        json_path = settings.OUTPUT_DIR / f"{base_name}_report.json"
        pdf_path = settings.OUTPUT_DIR / f"{base_name}_report.pdf"

        # Determine Global Status
        status = "COMPLETED"
        if safety and not safety.get("is_safe"): status = "FLAGGED_SAFETY"
        elif val and not val.get("is_valid"): status = "DATA_INVALID"
        elif val.get("business_status") == "mismatch": status = "ERP_MISMATCH"

        report_payload = {
            "meta": {"file_name": file_name, "status": status, "timestamp": datetime.now(timezone.utc).isoformat(), "metadata": metadata},
            "data": data,
            "validation": val,
            "safety": safety
        }
        
        with open(json_path, "w") as f:
            json.dump(report_payload, f, indent=2)

        # Generate Professional PDF
        try:
            pdf = FPDF()
            pdf.add_page()
            
            # Header
            pdf.set_fill_color(30, 64, 175)  # Dark Blue
            pdf.set_text_color(255, 255, 255)
            pdf.set_font("Arial", 'B', 20)
            pdf.cell(0, 20, " Invoice Audit Report", ln=1, align='L', fill=True)
            
            # Meta Info
            pdf.set_text_color(0, 0, 0)
            pdf.ln(10)
            pdf.set_font("Arial", 'B', 10)
            pdf.cell(40, 6, "File Reference:", 0, 0)
            pdf.set_font("Arial", '', 10)
            pdf.cell(0, 6, self._sanitize(file_name), 0, 1)
            
            pdf.set_font("Arial", 'B', 10)
            pdf.cell(40, 6, "Audit Date:", 0, 0)
            pdf.set_font("Arial", '', 10)
            pdf.cell(0, 6, datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC"), 0, 1)
            
            pdf.set_font("Arial", 'B', 10)
            pdf.cell(40, 6, "Overall Status:", 0, 0)
            
            # Status Color
            if status == "COMPLETED": pdf.set_text_color(0, 128, 0)
            else: pdf.set_text_color(220, 20, 60)
            
            pdf.set_font("Arial", 'B', 12)
            pdf.cell(0, 6, status.replace("_", " "), 0, 1)
            pdf.set_text_color(0, 0, 0)
            
            # Safety Section
            pdf.ln(8)
            pdf.set_fill_color(240, 240, 240)
            pdf.set_font("Arial", 'B', 12)
            pdf.cell(0, 8, " RAI Safety & Guardrails", 1, 1, 'L', True)
            pdf.set_font("Arial", '', 10)
            pdf.ln(2)
            
            is_safe = safety.get("is_safe", True)
            pdf.cell(50, 6, "Content Safety:", 1)
            pdf.cell(0, 6, "SAFE" if is_safe else "UNSAFE", 1, 1)
            
            if safety.get("pii_detected"):
                pdf.cell(50, 6, "PII Redacted:", 1)
                pdf.cell(0, 6, self._sanitize(", ".join(safety.get("pii_detected"))), 1, 1)

            # Invoice Data Table
            pdf.ln(8)
            pdf.set_font("Arial", 'B', 12)
            pdf.cell(0, 8, " Extracted Data", 1, 1, 'L', True)
            pdf.set_font("Arial", '', 10)
            pdf.ln(2)
            
            fields = [
                ("Invoice No", data.get("invoice_no")),
                ("Date", data.get("invoice_date")),
                ("Vendor", data.get("vendor_id")),
                ("Total", f"{data.get('total_amount', 0)} {data.get('currency', '')}")
            ]
            
            for label, value in fields:
                pdf.set_font("Arial", 'B', 10)
                pdf.cell(40, 6, label, 1)
                pdf.set_font("Arial", '', 10)
                pdf.cell(0, 6, self._sanitize(value), 1, 1)
                
            # Line Items
            items = data.get("line_items", [])
            if items:
                pdf.ln(5)
                pdf.set_font("Arial", 'B', 10)
                pdf.cell(0, 6, f"Line Items ({len(items)})", 0, 1)
                pdf.set_fill_color(220, 220, 220)
                
                # Table Header
                pdf.cell(80, 7, "Description", 1, 0, 'C', True)
                pdf.cell(25, 7, "Qty", 1, 0, 'C', True)
                pdf.cell(30, 7, "Price", 1, 0, 'C', True)
                pdf.cell(30, 7, "Total", 1, 1, 'C', True)
                
                pdf.set_font("Arial", '', 9)
                for item in items:
                    pdf.cell(80, 6, self._sanitize(item.get("description", "N/A")[:45]), 1)
                    pdf.cell(25, 6, str(item.get("qty", 0)), 1, 0, 'C')
                    pdf.cell(30, 6, str(item.get("unit_price", 0)), 1, 0, 'R')
                    pdf.cell(30, 6, str(item.get("total", 0)), 1, 1, 'R')

            # Validation Results
            pdf.ln(8)
            pdf.set_font("Arial", 'B', 12)
            pdf.cell(0, 8, " Audit Findings", 1, 1, 'L', True)
            pdf.ln(2)
            
            discrepancies = val.get("discrepancies", [])
            missing = val.get("missing_fields", [])
            
            if not discrepancies and not missing and val.get("is_valid"):
                pdf.set_text_color(0, 128, 0)
                pdf.cell(0, 8, "No discrepancies found. Invoice Valid.", 0, 1)
            else:
                pdf.set_text_color(200, 0, 0)
                pdf.set_font("Arial", 'B', 10)
                for m in missing:
                    pdf.cell(0, 6, f"[MISSING] {m}", 0, 1)
                for d in discrepancies:
                    pdf.multi_cell(0, 6, f"[MISMATCH] {self._sanitize(d)}")
            
            pdf.output(str(pdf_path))
            logger.info(f"PDF Generated: {pdf_path}")
            
        except Exception as e:
            logger.error(f"PDF Generation Error: {e}")
            
        return {"json_path": str(json_path), "pdf_path": str(pdf_path)}