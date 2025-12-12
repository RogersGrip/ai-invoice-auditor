# ===== FILE: src/tools/tools.py =====
import json
import os
import warnings
from typing import Dict, Any, List, Optional
from pathlib import Path
from datetime import datetime, timezone
from fpdf import FPDF

# --- Official Google ADK Imports ---
from google.adk.tools import BaseTool
from google.genai.types import FunctionDeclaration, Schema, Type

# --- Core Imports ---
from src.core.config import settings
from src.core.logger import logger
from src.database.qdrant_db import vector_store
from src.tools.ocr_engine import OCREngine
from src.core.state import InvoiceData
from src.core.llm_wrapper import BedrockLLMService

# --- LangChain/AWS Imports ---
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_aws import ChatBedrockConverse, BedrockEmbeddings
from ragas import evaluate
from ragas.metrics import (
    faithfulness, 
    answer_relevancy, 
    context_precision, 
    context_recall, 
    answer_correctness
)
from ragas.llms import LangchainLLMWrapper
from ragas.embeddings import LangchainEmbeddingsWrapper
from datasets import Dataset

# --- Suppress Noise ---
warnings.filterwarnings("ignore", category=DeprecationWarning)

# --- Observability ---
try:
    if settings.LANGFUSE_PUBLIC_KEY:
        from langfuse import observe
    else:
        raise ImportError
except ImportError:
    def observe(*args, **kwargs):
        def decorator(func): return func
        return decorator

class InvoiceWatcherTool(BaseTool):
    def __init__(self): super().__init__(name="invoice_watcher_tool", description="Monitors invoices.")
    def _get_declaration(self): return FunctionDeclaration(name=self.name, description=self.description, parameters=Schema(type=Type.OBJECT, properties={"path": Schema(type=Type.STRING)}, required=["path"]))
    def run(self, args): return json.dumps({"status": "monitoring"})

class DataHarvesterTool(BaseTool):
    def __init__(self): super().__init__(name="data_harvester_tool", description="Extracts text.")
    def _get_declaration(self): return FunctionDeclaration(name=self.name, description=self.description, parameters=Schema(type=Type.OBJECT, properties={"file_path": Schema(type=Type.STRING)}, required=["file_path"]))
    def run(self, args): return OCREngine().extract(args.get("file_path"))

class LangBridgeTool(BaseTool):
    def __init__(self): super().__init__(name="lang_bridge_tool", description="Translates text.")
    def _get_declaration(self): return FunctionDeclaration(name=self.name, description=self.description, parameters=Schema(type=Type.OBJECT, properties={"text": Schema(type=Type.STRING)}, required=["text"]))
    def run(self, args):
        try:
            parser = PydanticOutputParser(pydantic_object=InvoiceData)
            prompt = PromptTemplate(template="{format_instructions}\n{text}", input_variables=["text"], partial_variables={"format_instructions": parser.get_format_instructions()})
            llm = BedrockLLMService(model_id=settings.TRANSLATION_MODEL, temperature=0.0).get_llm()
            res = (prompt | llm | parser).invoke({"text": args.get("text")})
            return {"extracted_data": res.model_dump()}
        except Exception as e: return {"extracted_data": InvoiceData().model_dump(), "error": str(e)}

class DataCompletenessCheckerTool(BaseTool):
    def __init__(self): super().__init__(name="data_completeness_checker_tool", description="Checks fields.")
    def _get_declaration(self): return FunctionDeclaration(name=self.name, description=self.description, parameters=Schema(type=Type.OBJECT, properties={"invoice_data": Schema(type=Type.OBJECT)}, required=["invoice_data"]))
    def run(self, args):
        data = args.get("invoice_data", {})
        missing = [f for f in ["invoice_no", "invoice_date", "total_amount", "vendor_id"] if not data.get(f)]
        return {"validation_status": "valid" if not missing else "invalid", "missing_fields": missing}

class BusinessValidationTool(BaseTool):
    def __init__(self): super().__init__(name="business_validation_tool", description="Checks ERP.")
    def run(self, args): return {"status": "placeholder"}

# ==============================================================================
# UPDATED: Insight Reporter Tool (Detailed PDF)
# ==============================================================================
class InsightReporterTool(BaseTool):
    def __init__(self):
        super().__init__(name="insight_reporter_tool", description="Generates reports.")

    def _get_declaration(self):
        return FunctionDeclaration(
            name=self.name, description=self.description,
            parameters=Schema(type=Type.OBJECT, properties={"file_name": Schema(type=Type.STRING)}, required=["file_name"])
        )

    def _sanitize(self, text: Any) -> str:
        if text is None: return "N/A"
        text = str(text)
        # Handle common currency/special chars
        replacements = {"€": "EUR", "£": "GBP", "¥": "JPY", "₹": "INR", "‘": "'", "’": "'", "“": '"', "”": '"'}
        for char, repl in replacements.items():
            text = text.replace(char, repl)
        # Force Latin-1 for FPDF
        return text.encode('latin-1', 'replace').decode('latin-1')

    def run(self, args: Dict[str, Any]) -> Dict[str, str]:
        file_name = args.get("file_name", "unknown_report")
        extracted_data = args.get("extracted_data", {})
        validation_report = args.get("validation_report", {})
        safety_report = args.get("safety_report", {})
        metadata = args.get("metadata", {})

        base_name = Path(file_name).stem
        json_path = settings.OUTPUT_DIR / f"{base_name}_report.json"
        pdf_path = settings.OUTPUT_DIR / f"{base_name}_report.pdf"
        
        status = "COMPLETED"
        if safety_report and not safety_report.get("is_safe"): status = "FLAGGED"
        elif validation_report and not validation_report.get("is_valid"): status = "DATA_INVALID"
        elif validation_report.get("business_status") == "mismatch": status = "BUSINESS_MISMATCH"

        # Save JSON
        report_data = {
            "meta": {
                "file_name": file_name,
                "status": status,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "metadata": metadata
            },
            "data": extracted_data,
            "validation": validation_report,
            "safety": safety_report
        }
        with open(json_path, 'w') as f:
            json.dump(report_data, f, indent=2)

        # Generate PDF
        try:
            pdf = FPDF()
            pdf.add_page()
            
            # 1. Header
            pdf.set_fill_color(240, 248, 255)
            pdf.set_font("Arial", 'B', 16)
            pdf.cell(0, 15, "AI Invoice Auditor Report", ln=1, align='C', fill=True, border=1)
            pdf.ln(5)

            # 2. Metadata
            pdf.set_font("Arial", 'B', 10)
            pdf.cell(30, 6, "File Name:", border=0)
            pdf.set_font("Arial", '', 10)
            pdf.cell(0, 6, self._sanitize(file_name), border=0, ln=1)
            
            pdf.set_font("Arial", 'B', 10)
            pdf.cell(30, 6, "Status:", border=0)
            
            if status == "COMPLETED": pdf.set_text_color(0, 128, 0) # Green
            elif status in ["FLAGGED", "DATA_INVALID"]: pdf.set_text_color(200, 0, 0) # Red
            else: pdf.set_text_color(255, 140, 0) # Orange
            
            pdf.cell(0, 6, status, border=0, ln=1)
            pdf.set_text_color(0, 0, 0) # Reset Black
            pdf.ln(5)

            # 3. Invoice Details
            pdf.set_fill_color(230, 230, 250)
            pdf.set_font("Arial", 'B', 12)
            pdf.cell(0, 8, " Extracted Invoice Data", ln=1, fill=True, border=1)
            pdf.set_font("Arial", '', 10)
            pdf.ln(2)
            
            # Simple Key-Value
            fields = ["invoice_no", "invoice_date", "vendor_id", "total_amount", "currency"]
            for field in fields:
                val = extracted_data.get(field, "N/A")
                pdf.cell(40, 6, field.replace("_", " ").title(), border=1)
                pdf.cell(0, 6, self._sanitize(val), border=1, ln=1)
            pdf.ln(2)
            
            # Line Items Table
            items = extracted_data.get("line_items", [])
            if items:
                pdf.set_font("Arial", 'B', 10)
                pdf.cell(0, 6, f"Line Items ({len(items)})", ln=1)
                pdf.set_font("Arial", '', 9)
                
                # Header
                pdf.set_fill_color(245, 245, 245)
                pdf.cell(90, 6, "Description / Code", border=1, fill=True)
                pdf.cell(20, 6, "Qty", border=1, fill=True)
                pdf.cell(30, 6, "Price", border=1, fill=True)
                pdf.cell(30, 6, "Total", border=1, fill=True, ln=1)
                
                # Rows
                for item in items:
                    desc = item.get("item_code") or item.get("description") or "Item"
                    qty = str(item.get("qty", 0))
                    price = str(item.get("unit_price", 0))
                    total = str(item.get("total", 0))
                    
                    pdf.cell(90, 6, self._sanitize(desc[:50]), border=1)
                    pdf.cell(20, 6, qty, border=1)
                    pdf.cell(30, 6, price, border=1)
                    pdf.cell(30, 6, total, border=1, ln=1)
            pdf.ln(5)

            # 4. Audit Results
            pdf.set_fill_color(255, 250, 205)
            pdf.set_font("Arial", 'B', 12)
            pdf.cell(0, 8, " Validation & Audit", ln=1, fill=True, border=1)
            pdf.set_font("Arial", '', 10)
            pdf.ln(2)
            
            valid = validation_report.get("is_valid", False)
            biz_status = validation_report.get("business_status", "N/A")
            
            pdf.cell(50, 6, "Data Integrity:", border=1)
            pdf.cell(0, 6, "PASS" if valid else "FAIL", border=1, ln=1)
            
            pdf.cell(50, 6, "ERP Match:", border=1)
            pdf.cell(0, 6, self._sanitize(biz_status.upper()), border=1, ln=1)
            
            discrepancies = validation_report.get("discrepancies", [])
            missing = validation_report.get("missing_fields", [])
            
            if discrepancies or missing:
                pdf.ln(2)
                pdf.set_text_color(200, 0, 0)
                pdf.set_font("Arial", 'B', 10)
                pdf.cell(0, 6, "Issues Found:", ln=1)
                pdf.set_font("Arial", '', 10)
                for d in discrepancies:
                    pdf.multi_cell(0, 6, f"- {self._sanitize(d)}")
                for m in missing:
                    pdf.multi_cell(0, 6, f"- Missing Field: {self._sanitize(m)}")
                pdf.set_text_color(0, 0, 0)

            pdf.output(str(pdf_path))
        except Exception as e:
            logger.error(f"PDF Gen failed: {e}")
        
        return {"json": str(json_path), "pdf": str(pdf_path)}

class VectorIndexerTool(BaseTool):
    def __init__(self): super().__init__(name="vector_indexer_tool", description="Indexes docs.")
    def _get_declaration(self): return FunctionDeclaration(name=self.name, description=self.description, parameters=Schema(type=Type.OBJECT, properties={"text": Schema(type=Type.STRING)}, required=["text"]))
    def run(self, args):
        chunks = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200).create_documents([args.get("text", "")])
        for i, c in enumerate(chunks): vector_store.add_document(c.page_content, {**args.get("metadata", {}), "chunk_id": i})
        return len(chunks)

class SemanticRetrieverTool(BaseTool):
    def __init__(self): super().__init__(name="semantic_retriever_tool", description="Retrieves docs.")
    def _get_declaration(self): return FunctionDeclaration(name=self.name, description=self.description, parameters=Schema(type=Type.OBJECT, properties={"query": Schema(type=Type.STRING)}, required=["query"]))
    def run(self, args): return vector_store.search(args.get("query", ""), limit=args.get("limit", 5), filename=args.get("filename"))

class ChunkRankerTool(BaseTool):
    def __init__(self): super().__init__(name="chunk_ranker_tool", description="Reranks docs.")
    def _get_declaration(self): return FunctionDeclaration(name=self.name, description=self.description, parameters=Schema(type=Type.OBJECT, properties={"docs": Schema(type=Type.ARRAY)}, required=["docs"]))
    def run(self, args): return "\n".join([f"Source: {d.get('metadata',{}).get('filename')}\n{d.get('text')}" for d in sorted(args.get("docs", []), key=lambda d: d.get('score', 0), reverse=True)])

class ResponseSynthesizerTool(BaseTool):
    def __init__(self): super().__init__(name="response_synthesizer_tool", description="Synthesizes answer.")
    def _get_declaration(self): return FunctionDeclaration(name=self.name, description=self.description, parameters=Schema(type=Type.OBJECT, properties={"query": Schema(type=Type.STRING), "context": Schema(type=Type.STRING)}, required=["query", "context"]))
    def run(self, args): return BedrockLLMService(model_id=settings.REPORTING_MODEL).invoke(f"Context:\n{args.get('context')}\n\nQuestion: {args.get('query')}")

class RAGEvaluatorTool(BaseTool):
    def __init__(self): super().__init__(name="rag_evaluator_tool", description="Evaluates RAG.")
    def _get_declaration(self): return FunctionDeclaration(name=self.name, description=self.description, parameters=Schema(type=Type.OBJECT, properties={"query": Schema(type=Type.STRING)}, required=["query"]))
    def run(self, args):
        try:
            eval_llm = LangchainLLMWrapper(ChatBedrockConverse(
                model=settings.VALIDATION_MODEL, 
                temperature=0.0, 
                region_name="us-east-1"
            ))
            
            eval_embeddings = LangchainEmbeddingsWrapper(BedrockEmbeddings(
                model_id=settings.EMBEDDING_MODEL, 
                region_name="us-east-1"
            ))

            data = {
                "question": [args["query"]], 
                "answer": [args["answer"]], 
                "contexts": [[args["context"]]],
                "ground_truth": [args["answer"]] # Placeholder for consistency
            }
            dataset = Dataset.from_dict(data)
            
            # --- 5 METRICS ---
            res = evaluate(
                dataset=dataset, 
                metrics=[faithfulness, answer_relevancy, context_precision, context_recall, answer_correctness], 
                llm=eval_llm, 
                embeddings=eval_embeddings, 
                raise_exceptions=False
            )
            
            df = res.to_pandas()
            if df.empty: return json.dumps({"status": "empty_eval"})
            
            row = df.iloc[0].to_dict()
            metrics = {k: (float(v) if v == v else 0.0) for k, v in row.items() 
                       if isinstance(v, (int, float)) and k not in ["question", "answer", "contexts", "ground_truth"]}
            
            return json.dumps(metrics)
            
        except Exception as e:
            logger.warning(f"Ragas Evaluation Failed: {e}")
            return json.dumps({"faithfulness": 0.0, "error": str(e)})

class SystemStatsTool(BaseTool):
    def __init__(self): super().__init__(name="system_stats_tool", description="System stats.")
    def _get_declaration(self): return FunctionDeclaration(name=self.name, description=self.description, parameters=Schema(type=Type.OBJECT, properties={}))
    def run(self, args): return f"Processed: {len(list(settings.PROCESSED_DIR.glob('*.*')))}"