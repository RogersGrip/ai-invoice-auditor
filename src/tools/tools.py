import json
import re
import os
from typing import Dict, Any, List, Optional
from pathlib import Path
from datetime import datetime, timezone
from fpdf import FPDF

# Core & Protocol
from src.core.protocol import MCPTool
from src.core.config import settings
from src.core.logger import logger
from src.database.qdrant_db import vector_store
from src.tools.ocr_engine import OCREngine

# LangChain / AI
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

# --- 1. MONITORING TOOLS ---

class InvoiceWatcherTool(BaseTool):
    name: str = "Invoice-Watcher Tool"
    description: str = "Monitors a designated mailbox or file system to detect and retrieve emails containing invoice attachments."
    input_schema: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "watch_path": {"type": "string", "description": "Path to watch"}
        }
    }

# --- 2. EXTRACTION TOOLS ---

class DataHarvesterTool(BaseTool):
    name: str = "Data Harvester Tool"
    description: str = "Extracts data from a wide range of document formats using OCR."
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

# --- 3. TRANSLATION TOOLS ---

class LangBridgeTool(BaseTool):
    name: str = "Lang-Bridge Tool"
    description: str = "Converts extracted invoice content from various languages into English and standardizes JSON."
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
        prompt = """
        You are an expert Data Extraction Specialist.
        TASK: Extract structured data from this invoice text.
        OUTPUT: Raw JSON only. No Markdown.
        
        Fields required:
        - invoice_no, invoice_date, vendor_id, currency, total_amount
        - line_items: [{item_code, description, qty, unit_price, total}]
        
        Translate descriptions to English.
        """
        model = settings.TRANSLATION_MODEL
        try:
            response = completion(
                model=model,
                messages=[{"role": "user", "content": prompt + "\n\n" + text}],
                temperature=0.0
            )
            content = response.choices[0].message.content.strip()
            
            # Cleanup
            content = re.sub(r"```json\s*|```", "", content).strip()
            # Extract JSON block
            if "{" in content and "}" in content:
                content = content[content.find("{"):content.rfind("}")+1]
            
            data = json.loads(content)
            return {
                "extracted_data": data,
                "model": model
            }
        except Exception as e:
            logger.error(f"LangBridge Error: {e}")
            raise e

# --- 4. VALIDATION TOOLS ---

class DataCompletenessCheckerTool(BaseTool):
    name: str = "DataCompletenessChecker Tool"
    description: str = "Validates invoice data for completeness and accuracy based on predefined business rules."
    input_schema: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "invoice_data": {"type": "object"}
        },
        "required": ["invoice_data"]
    }

    @observe(name="DataCompletenessCheckerTool.run")
    def run(self, invoice_data: Dict[str, Any]) -> Dict[str, Any]:
        missing = []
        required_headers = ["invoice_no", "invoice_date", "total_amount", "vendor_id"]
        
        if not invoice_data:
            return {"validation_status": "invalid", "missing_fields": ["no_data"]}

        for field in required_headers:
            if not invoice_data.get(field):
                missing.append(field)
                
        items = invoice_data.get("line_items", [])
        if not items:
            missing.append("line_items")
        else:
            for i, item in enumerate(items):
                if not item.get("item_code"):
                    missing.append(f"line_item[{i}].item_code")
                if not item.get("total") and not item.get("unit_price"):
                    missing.append(f"line_item[{i}].price_info")
        
        is_valid = len(missing) == 0
        return {
            "validation_status": "valid" if is_valid else "invalid",
            "missing_fields": missing
        }

class BusinessValidationTool(BaseTool):
    name: str = "Business Validation Tool"
    description: str = "Cross-verifies extracted invoice data against enterprise systems."
    input_schema: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "line_items": {"type": "array"}
        }
    }

# --- 5. REPORTING TOOLS ---

class InsightReporterTool(BaseTool):
    name: str = "Insight Reporter Tool"
    description: str = "Generates comprehensive reports highlighting data gaps, validation results, safety checks, and recommendations."
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
        """Sanitizes text for FPDF (Latin-1) to prevent encoding crashes."""
        if text is None: return ""
        text = str(text)
        replacements = {
            "\u20ac": "EUR", "€": "EUR", "’": "'", "“": '"', "”": '"',
            "–": "-", "—": "-", "…": "...", "£": "GBP", "¥": "JPY", "₹": "INR"
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

        # 1. Determine Status
        status = "COMPLETED"
        if safety_report and not safety_report.get("is_safe"): status = "FLAGGED"
        elif validation_report and not validation_report.get("is_valid"): status = "DATA_INVALID"
        elif validation_report.get("business_status") == "mismatch": status = "BUSINESS_MISMATCH"

        # 2. JSON Dump
        report_data = {
            "meta": {
                "file_name": file_name,
                "status": status,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "metadata": metadata
            },
            "extraction": extracted_data,
            "validation": validation_report,
            "safety": safety_report
        }
        
        with open(json_path, 'w') as f:
            json.dump(report_data, f, indent=2)

        # 3. PDF Generation (Beautiful Version)
        pdf = FPDF()
        pdf.add_page()
        
        # Header
        pdf.set_font("Arial", 'B', 16)
        pdf.set_fill_color(240, 248, 255) # AliceBlue
        pdf.cell(0, 15, "AI Invoice Auditor Report", ln=1, align='C', fill=True, border=1)
        pdf.ln(5)

        # File Info & Status
        pdf.set_font("Arial", 'B', 10)
        pdf.cell(30, 8, "File Name:", border=0)
        pdf.set_font("Arial", '', 10)
        pdf.cell(0, 8, self._sanitize(file_name), border=0, ln=1)
        
        pdf.set_font("Arial", 'B', 10)
        pdf.cell(30, 8, "Status:", border=0)
        
        # Color Coded Status
        if status == "COMPLETED":
            pdf.set_text_color(34, 139, 34) # ForestGreen
        elif status == "FLAGGED":
            pdf.set_text_color(220, 20, 60) # Crimson
        else:
            pdf.set_text_color(255, 140, 0) # DarkOrange
            
        pdf.cell(0, 8, status, border=0, ln=1)
        pdf.set_text_color(0, 0, 0) # Reset
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

        # Extracted Data
        pdf.set_fill_color(230, 230, 250) # Lavender
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(0, 8, " Extracted Invoice Data", ln=1, fill=True, border=1)
        pdf.set_font("Arial", size=10)
        
        # Header Grid
        pdf.cell(40, 8, "Invoice #", border=1, fill=True)
        pdf.cell(55, 8, self._sanitize(extracted_data.get('invoice_no', 'N/A')), border=1)
        pdf.cell(40, 8, "Date", border=1, fill=True)
        pdf.cell(55, 8, self._sanitize(extracted_data.get('invoice_date', 'N/A')), border=1, ln=1)
        
        pdf.cell(40, 8, "Vendor", border=1, fill=True)
        pdf.cell(55, 8, self._sanitize(extracted_data.get('vendor_id', 'N/A')), border=1)
        pdf.cell(40, 8, "Total", border=1, fill=True)
        pdf.cell(55, 8, self._sanitize(f"{extracted_data.get('total_amount')} {extracted_data.get('currency')}"), border=1, ln=1)
        pdf.ln(5)

        # Line Items Table
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
                # Sanitize EVERY item field
                code = self._sanitize(item.get("item_code", ""))
                desc = self._sanitize(item.get("description", ""))[:50]
                qty = self._sanitize(item.get("qty", ""))
                price = self._sanitize(item.get("unit_price", ""))
                total = self._sanitize(item.get("total", ""))

                pdf.cell(30, 8, code, border=1)
                pdf.cell(90, 8, desc, border=1)
                pdf.cell(20, 8, str(qty), border=1, align='R')
                pdf.cell(25, 8, str(price), border=1, align='R')
                pdf.cell(25, 8, str(total), border=1, align='R', ln=1)
        pdf.ln(5)

        # Validation Results
        pdf.set_font("Arial", 'B', 12)
        pdf.set_fill_color(255, 250, 205) # LemonChiffon
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

# --- 6. SYSTEM TOOLS ---

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

# --- 7. RAG TOOLS ---

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
        # Simple Logic: prioritize docs with keywords
        def rank(d): return d.get('score', 0)
        ranked = sorted(docs, key=rank, reverse=True)
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
    description: str = "Evaluates RAG performance."
    input_schema: Dict[str, Any] = {
        "type": "object",
        "properties": {"query": {"type": "string"}, "answer": {"type": "string"}, "context": {"type": "string"}},
        "required": ["query", "answer", "context"]
    }

    @observe(name="RAGEvaluatorTool.run")
    def run(self, query: str, answer: str, context: str) -> str:
        try:
            from ragas import evaluate
            from ragas.metrics import faithfulness, answer_relevancy
            from ragas.llms import LangchainLLMWrapper
            from ragas.embeddings import LangchainEmbeddingsWrapper
            from datasets import Dataset
            
            bedrock_llm = ChatBedrockConverse(model=settings.VALIDATION_MODEL, temperature=0)
            bedrock_emb = BedrockEmbeddings(model_id=settings.EMBEDDING_MODEL)
            
            data = {"question": [query], "answer": [answer], "contexts": [[context]], "ground_truth": [answer]}
            dataset = Dataset.from_dict(data)
            
            results = evaluate(
                dataset=dataset,
                metrics=[faithfulness, answer_relevancy],
                llm=LangchainLLMWrapper(bedrock_llm),
                embeddings=LangchainEmbeddingsWrapper(bedrock_emb)
            )
            return json.dumps(dict(results))
        except Exception as e:
            return json.dumps({"error": str(e), "faithfulness": 0.0, "answer_relevancy": 0.0})