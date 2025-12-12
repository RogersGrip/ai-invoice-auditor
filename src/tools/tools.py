# ===== FILE: src/tools/tools.py =====
import json
import os
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
from ragas.metrics import faithfulness, answer_relevancy
from ragas.llms import LangchainLLMWrapper
from ragas.embeddings import LangchainEmbeddingsWrapper
from datasets import Dataset

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

class InsightReporterTool(BaseTool):
    def __init__(self):
        super().__init__(name="insight_reporter_tool", description="Generates reports.")

    def _get_declaration(self):
        return FunctionDeclaration(
            name=self.name,
            description=self.description,
            parameters=Schema(type=Type.OBJECT, properties={"file_name": Schema(type=Type.STRING)}, required=["file_name"])
        )

    def _sanitize(self, text: Any) -> str:
        return str(text).encode('latin-1', 'replace').decode('latin-1') if text else ""

    @observe(name="InsightReporterTool.run")
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

        report_data = {
            "meta": {
                "file_name": file_name, # Standardized Key
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

        try:
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Arial", 'B', 16)
            pdf.cell(0, 10, "Invoice Report", ln=1, align='C')
            pdf.set_font("Arial", '', 12)
            pdf.cell(0, 10, f"File: {self._sanitize(file_name)}", ln=1)
            pdf.cell(0, 10, f"Status: {status}", ln=1)
            pdf.output(str(pdf_path))
        except Exception: pass
        
        return {"json": str(json_path), "pdf": str(pdf_path)}

# ... (Include other tools like InvoiceWatcherTool, DataHarvesterTool, LangBridgeTool, DataCompletenessCheckerTool, BusinessValidationTool, VectorIndexerTool, SemanticRetrieverTool, ChunkRankerTool, ResponseSynthesizerTool, RAGEvaluatorTool, SystemStatsTool exactly as they were in the previous successful iteration)
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
            res = (prompt | BedrockLLMService(model_id=settings.TRANSLATION_MODEL).get_llm() | parser).invoke({"text": args.get("text")})
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
            res = evaluate(Dataset.from_dict({"question": [args["query"]], "answer": [args["answer"]], "contexts": [[args["context"]]]}), metrics=[faithfulness, answer_relevancy], llm=LangchainLLMWrapper(ChatBedrockConverse(model=settings.VALIDATION_MODEL, temperature=0, region_name="us-east-1")), embeddings=LangchainEmbeddingsWrapper(BedrockEmbeddings(model_id=settings.EMBEDDING_MODEL, region_name="us-east-1")), raise_exceptions=False)
            return json.dumps({k: float(v) for k,v in res.items()})
        except Exception as e: return json.dumps({"faithfulness": 0.0, "error": str(e)})

class SystemStatsTool(BaseTool):
    def __init__(self): super().__init__(name="system_stats_tool", description="System stats.")
    def _get_declaration(self): return FunctionDeclaration(name=self.name, description=self.description, parameters=Schema(type=Type.OBJECT, properties={}))
    def run(self, args): return f"Processed: {len(list(settings.PROCESSED_DIR.glob('*.*')))}"