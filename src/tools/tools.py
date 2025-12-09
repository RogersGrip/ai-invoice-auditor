import json
import re
import os
from typing import Dict, Any, List, Optional
from pathlib import Path
from datetime import datetime, timezone
from fpdf import FPDF
import instructor
from pydantic import BaseModel, Field

from src.core.protocol import MCPTool
from src.core.config import settings
from src.core.logger import logger
from src.database.qdrant_db import vector_store
from src.tools.ocr_engine import OCREngine
from src.core.state import InvoiceData

from langchain_aws import ChatBedrockConverse, BedrockEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from litellm import completion

try:
    if settings.LANGFUSE_PUBLIC_KEY:
        from langfuse import observe
    else:
        raise ImportError
except ImportError:
    def observe(*args, **kwargs):
        def decorator(func): return func
        return decorator

class BaseTool(MCPTool):
    pass

class InvoiceWatcherTool(BaseTool):
    name: str = "Invoice-Watcher Tool"
    description: str = "Monitors a designated mailbox or file system."
    input_schema: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to watch"}
        }
    }

class DataHarvesterTool(BaseTool):
    name: str = "Data Harvester Tool"
    description: str = "Extracts data from documents using OCR."
    input_schema: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "file_path": {"type": "string"}
        },
        "required": ["file_path"]
    }

    @observe(name="DataHarvesterTool.run")
    def run(self, file_path: str) -> str:
        engine = OCREngine()
        return engine.extract(file_path)

class LangBridgeTool(BaseTool):
    name: str = "Lang-Bridge Tool"
    description: str = "Standardizes invoice content to English JSON using LLM Structured Outputs."
    input_schema: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "target_language": {"type": "string", "default": "en"}
        },
        "required": ["text"]
    }

    @observe(name="LangBridgeTool.run")
    def run(self, text: str, target_language: str = "en") -> Dict[str, Any]:
        """
        Uses Instructor with JSON Mode to extract structured data.
        This avoids 'Invalid parameter' errors on Bedrock/Cohere native tool calling.
        """
        model_name = settings.TRANSLATION_MODEL
        
        # Use MD_JSON mode which is robust for Cohere/Command models
        client = instructor.from_litellm(completion, mode=instructor.Mode.MD_JSON)

        logger.info(f"LangBridge: Extracting structured data using {model_name}")
        
        try:
            # We explicitly ask the model to act as a tool caller to fill InvoiceData
            invoice_data = client.chat.completions.create(
                model=model_name,
                response_model=InvoiceData,
                messages=[
                    {
                        "role": "system", 
                        "content": "You are an expert Invoice Auditor. Extract data from the invoice below into the required JSON structure. Translate non-English descriptions to English. Normalize currencies to ISO codes (USD, EUR, INR, GBP)."
                    },
                    {"role": "user", "content": f"Invoice Content:\n{text}"}
                ],
                max_tokens=4000,
                temperature=0.0
            )
            return {"extracted_data": invoice_data.model_dump(), "model": model_name}
        except Exception as e:
            logger.error(f"LangBridge Tool Call Error: {e}")
            # Return a valid empty structure to prevent workflow crash
            return {
                "extracted_data": InvoiceData().model_dump(), 
                "error": str(e)
            }

class DataCompletenessCheckerTool(BaseTool):
    name: str = "DataCompletenessChecker Tool"
    description: str = "Checks for missing mandatory fields."
    input_schema: Dict[str, Any] = {
        "type": "object", 
        "properties": {"invoice_data": {"type": "object"}},
        "required": ["invoice_data"]
    }

    @observe(name="DataCompletenessCheckerTool.run")
    def run(self, invoice_data: Dict[str, Any]) -> Dict[str, Any]:
        missing = []
        required_headers = ["invoice_no", "invoice_date", "total_amount", "vendor_id"]
        
        # Handle case where invoice_data might be None due to upstream failure
        if not invoice_data:
            return {"validation_status": "invalid", "missing_fields": ["CRITICAL_DATA_MISSING"]}

        for field in required_headers:
            val = invoice_data.get(field)
            if not val or val == "None":
                missing.append(field)
        
        items = invoice_data.get("line_items", [])
        if not items:
            missing.append("line_items")
        else:
            for i, item in enumerate(items):
                if not item.get("item_code"):
                    missing.append(f"line_item[{i}].item_code")
                # Relaxed check: either total OR unit_price is needed
                if item.get("total") is None and item.get("unit_price") is None:
                    missing.append(f"line_item[{i}].price_info")

        is_valid = len(missing) == 0
        return {
            "validation_status": "valid" if is_valid else "invalid",
            "missing_fields": missing
        }

class BusinessValidationTool(BaseTool):
    name: str = "Business Validation Tool"
    description: str = "Cross-verifies extracted invoice data against enterprise systems."
    input_schema: Dict[str, Any] = {"type": "object", "properties": {"item_code": {"type": "string"}}}

class InsightReporterTool(BaseTool):
    name: str = "Insight Reporter Tool"
    description: str = "Generates high-fidelity PDF and JSON audit reports."
    input_schema: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "file_name": {"type": "string"},
            "extracted_data": {"type": "object"},
            "validation_report": {"type": "object"},
            "safety_report": {"type": "object"}
        }
    }

    def _sanitize(self, text: Any) -> str:
        if text is None: return ""
        text = str(text)
        replacements = {
            "EUR": "EUR", "€": "EUR",
            "'": "'", "‘": "'", "“": '"', "”": '"',
            "-": "-", "—": "-", "…": "...",
            "£": "GBP", "¥": "JPY", "₹": "INR",
            "©": "(c)", "®": "(r)"
        }
        for char, repl in replacements.items():
            text = text.replace(char, repl)
        return text.encode('latin-1', 'replace').decode('latin-1')

    @observe(name="InsightReporterTool.run")
    def run(self, file_name: str, extracted_data: Dict, validation_report: Dict, safety_report: Optional[Dict] = None, metadata: Dict = {}) -> Dict[str, str]:
        base_name = Path(file_name).stem
        json_path = settings.OUTPUT_DIR / f"{base_name}_report.json"
        pdf_path = settings.OUTPUT_DIR / f"{base_name}_report.pdf"
        html_path = settings.OUTPUT_DIR / f"{base_name}_report.html"

        status = "COMPLETED"
        if safety_report and not safety_report.get("is_safe"): status = "FLAGGED"
        elif validation_report and not validation_report.get("is_valid"): status = "DATA_INVALID"
        elif validation_report.get("business_status") == "mismatch": status = "BUSINESS_MISMATCH"

        report_data = {
            "meta": {
                "file_name": file_name,
                "status": status,
                "ts": datetime.now(timezone.utc).isoformat(),
                "metadata": metadata
            },
            "data": extracted_data,
            "validation": validation_report,
            "safety": safety_report
        }

        with open(json_path, 'w') as f:
            json.dump(report_data, f, indent=2)

        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", 'B', 16)
        pdf.set_fill_color(240, 248, 255)
        pdf.cell(0, 15, "AI Invoice Auditor Report", ln=1, align='C', fill=True, border=1)
        pdf.ln(5)

        pdf.set_font("Arial", 'B', 10)
        pdf.cell(30, 8, "File Name:", border=0)
        pdf.set_font("Arial", '', 10)
        pdf.cell(0, 8, self._sanitize(file_name), border=0, ln=1)

        pdf.set_font("Arial", 'B', 10)
        pdf.cell(30, 8, "Status:", border=0)
        if status == "COMPLETED":
            pdf.set_text_color(34, 139, 34)
        elif status == "FLAGGED":
            pdf.set_text_color(220, 20, 60)
        else:
            pdf.set_text_color(255, 140, 0)
        pdf.cell(0, 8, status, border=0, ln=1)
        pdf.set_text_color(0, 0, 0)
        pdf.ln(5)

        # Safety Section
        if safety_report:
            pdf.set_fill_color(255, 240, 245) if not safety_report.get("is_safe") else pdf.set_fill_color(240, 255, 240)
            pdf.set_font("Arial", 'B', 12)
            pdf.cell(0, 8, " Safety & Compliance", ln=1, fill=True, border=1)
            pdf.set_font("Arial", size=10)
            pdf.cell(40, 8, "Toxicity Score:", border=1)
            pdf.cell(0, 8, f"{safety_report.get('toxicity_score', 0.0):.2f}", border=1, ln=1)
            pii = ", ".join(safety_report.get("pii_detected", [])) or "None"
            pdf.cell(40, 8, "PII Detected:", border=1)
            pdf.cell(0, 8, self._sanitize(pii), border=1, ln=1)
            pdf.ln(5)

        # Data Section
        pdf.set_fill_color(230, 230, 250)
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(0, 8, " Extracted Invoice Data", ln=1, fill=True, border=1)
        pdf.set_font("Arial", size=10)
        
        inv_no = self._sanitize(extracted_data.get('invoice_no', 'N/A'))
        inv_date = self._sanitize(extracted_data.get('invoice_date', 'N/A'))
        vendor = self._sanitize(extracted_data.get('vendor_id', 'N/A'))
        total_str = f"{extracted_data.get('total_amount')} {extracted_data.get('currency')}"
        
        pdf.cell(40, 8, "Invoice #", border=1, fill=True)
        pdf.cell(55, 8, inv_no, border=1)
        pdf.cell(40, 8, "Date", border=1, fill=True)
        pdf.cell(55, 8, inv_date, border=1, ln=1)
        pdf.cell(40, 8, "Vendor", border=1, fill=True)
        pdf.cell(55, 8, vendor, border=1)
        pdf.cell(40, 8, "Total", border=1, fill=True)
        pdf.cell(55, 8, self._sanitize(total_str), border=1, ln=1)
        pdf.ln(5)

        items = extracted_data.get("line_items", [])
        if items:
            pdf.set_font("Arial", 'B', 10)
            pdf.set_fill_color(220, 220, 220)
            pdf.cell(30, 8, "Code", border=1, fill=True, align='C')
            pdf.cell(90, 8, "Description", border=1, fill=True, align='C')
            pdf.cell(20, 8, "Qty", border=1, fill=True, align='C')
            pdf.cell(25, 8, "Price", border=1, fill=True, align='C')
            pdf.cell(25, 8, "Total", border=1, fill=True, align='C', ln=1)
            
            pdf.set_font("Arial", size=9)
            for item in items:
                code = self._sanitize(item.get("item_code", ""))
                desc = self._sanitize(item.get("description", ""))[:50]
                qty = self._sanitize(item.get("qty", ""))
                price = self._sanitize(item.get("unit_price", ""))
                total = self._sanitize(item.get("total", ""))
                
                pdf.cell(30, 8, code, border=1)
                pdf.cell(90, 8, desc, border=1)
                pdf.cell(20, 8, qty, border=1, align='R')
                pdf.cell(25, 8, price, border=1, align='R')
                pdf.cell(25, 8, total, border=1, align='R', ln=1)
        pdf.ln(5)

        # Validation Section
        pdf.set_font("Arial", 'B', 12)
        pdf.set_fill_color(255, 250, 205)
        pdf.cell(0, 8, " Validation Results", ln=1, fill=True, border=1)
        pdf.set_font("Arial", size=10)
        
        discrepancies = validation_report.get("discrepancies", [])
        if not discrepancies:
            pdf.set_text_color(0, 100, 0)
            pdf.cell(0, 8, " [PASS] All business rules validated.", ln=1)
        else:
            pdf.set_text_color(200, 0, 0)
            for d in discrepancies:
                pdf.cell(0, 6, f" [FAIL] {self._sanitize(d)}", ln=1)

        pdf.output(str(pdf_path))
        return {"json": str(json_path), "pdf": str(pdf_path), "html": str(html_path)}

class SystemStatsTool(BaseTool):
    name: str = "System-Stats Tool"
    description: str = "Aggregates current system statistics."
    input_schema: Dict[str, Any] = {"type": "object", "properties": {}}

    @observe(name="SystemStatsTool.run")
    def run(self) -> str:
        try:
            processed = list(settings.PROCESSED_DIR.glob("*.*"))
            reports = list(settings.OUTPUT_DIR.glob("*.pdf"))
            return f"Processed: {len(processed)}, Reports: {len(reports)}"
        except Exception as e:
            return f"Error: {e}"

class VectorIndexerTool(BaseTool):
    name: str = "Vector-Indexer Tool"
    description: str = "Indexes documents into Qdrant."
    input_schema: Dict[str, Any] = {
        "type": "object",
        "properties": {"text": {"type": "string"}, "metadata": {"type": "object"}},
        "required": ["text"]
    }
    _text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)

    @observe(name="VectorIndexerTool.run")
    def run(self, text: str, metadata: Dict[str, Any] = {}) -> int:
        chunks = self._text_splitter.create_documents([text])
        for i, chunk in enumerate(chunks):
            vector_store.add_document(chunk.page_content, {**metadata, "chunk_id": i})
        return len(chunks)

class SemanticRetrieverTool(BaseTool):
    name: str = "Semantic-Retriever Tool"
    description: str = "Performs semantic search."
    input_schema: Dict[str, Any] = {
        "type": "object",
        "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}, "filename": {"type": "string"}},
        "required": ["query"]
    }

    @observe(name="SemanticRetrieverTool.run")
    def run(self, query: str, limit: int = 5, filename: Optional[str] = None) -> List[Dict]:
        return vector_store.search(query, limit=limit, filename=filename)

class ChunkRankerTool(BaseTool):
    name: str = "Chunk-Ranker Tool"
    description: str = "Re-ranks retrieved chunks."
    input_schema: Dict[str, Any] = {"type": "object", "properties": {"docs": {"type": "array"}}}

    @observe(name="ChunkRankerTool.run")
    def run(self, docs: List[Dict]) -> str:
        if not docs: return ""
        # Mock re-ranking based on score for now, but infrastructure is here
        ranked = sorted(docs, key=lambda d: d.get('score', 0), reverse=True)
        return "\n---\n".join([f"Source: {d.get('metadata',{}).get('filename')}\n{d.get('text')}" for d in ranked])

class ResponseSynthesizerTool(BaseTool):
    name: str = "Response-Synthesizer Tool"
    description: str = "Generates answers using LLM."
    input_schema: Dict[str, Any] = {
        "type": "object",
        "properties": {"query": {"type": "string"}, "context": {"type": "string"}},
        "required": ["query", "context"]
    }

    @observe(name="ResponseSynthesizerTool.run")
    def run(self, query: str, context: str) -> str:
        try:
            return completion(
                model=settings.REPORTING_MODEL,
                messages=[{"role": "user", "content": f"Context:\n{context}\n\nQuestion: {query}"}],
                temperature=0.0
            ).choices[0].message.content
        except Exception as e:
            return f"Error: {e}"

class RAGEvaluatorTool(BaseTool):
    name: str = "RAG-Evaluator Tool"
    description: str = "Evaluates RAG performance using Ragas metrics."
    input_schema: Dict[str, Any] = {
        "type": "object",
        "properties": {"query": {"type": "string"}, "answer": {"type": "string"}, "context": {"type": "string"}},
        "required": ["query", "answer", "context"]
    }

    @observe(name="RAGEvaluatorTool.run")
    def run(self, query: str, answer: str, context: str) -> str:
        try:
            from ragas import evaluate
            from ragas.metrics import (
                faithfulness, 
                answer_relevancy, 
                context_precision, 
                context_recall
            )
            from ragas.llms import LangchainLLMWrapper
            from ragas.embeddings import LangchainEmbeddingsWrapper
            from datasets import Dataset

            bedrock_llm = ChatBedrockConverse(model=settings.VALIDATION_MODEL, temperature=0)
            bedrock_emb = BedrockEmbeddings(model_id=settings.EMBEDDING_MODEL)

            data = {
                "question": [query],
                "answer": [answer],
                "contexts": [[context]], 
                "ground_truth": [answer] # Self-consistency check since we don't have human ground truth here
            }
            dataset = Dataset.from_dict(data)
            
            # Using ALL metrics as requested
            results = evaluate(
                dataset=dataset,
                metrics=[faithfulness, answer_relevancy, context_precision, context_recall],
                llm=LangchainLLMWrapper(bedrock_llm),
                embeddings=LangchainEmbeddingsWrapper(bedrock_emb)
            )
            return json.dumps(dict(results))
        except Exception as e:
            logger.error(f"RAGAS Eval Failed: {e}")
            return json.dumps({
                "error": str(e), 
                "faithfulness": 0.0, 
                "answer_relevancy": 0.0, 
                "context_precision": 0.0, 
                "context_recall": 0.0
            })