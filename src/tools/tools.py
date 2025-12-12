# ===== FILE: src/tools/tools.py =====
import json
import os
from typing import Dict, Any, List, Optional
from pathlib import Path
from datetime import datetime, timezone
from fpdf import FPDF

# --- Official Google ADK Imports ---
from google.adk.tools import BaseTool, ToolContext
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
from ragas.metrics import faithfulness, answer_relevancy, context_precision, context_recall
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

class InvoiceWatcherTool(BaseTool):
    def __init__(self):
        super().__init__(name="invoice_watcher_tool", description="Monitors a mailbox/folder for invoices.")

    def _get_declaration(self):
        return FunctionDeclaration(
            name=self.name,
            description=self.description,
            parameters=Schema(type=Type.OBJECT, properties={"path": Schema(type=Type.STRING)}, required=["path"])
        )

    def run(self, args: Dict[str, Any]) -> str:
        path = args.get("path", str(settings.INVOICE_WATCH_DIR))
        if not os.path.exists(path): return f"Error: {path} not found."
        files = [f for f in os.listdir(path) if not f.startswith(".")]
        return json.dumps({"status": "monitoring", "path": path, "count": len(files)})

class DataHarvesterTool(BaseTool):
    def __init__(self):
        super().__init__(name="data_harvester_tool", description="Extracts text from documents.")

    def _get_declaration(self):
        return FunctionDeclaration(
            name=self.name,
            description=self.description,
            parameters=Schema(type=Type.OBJECT, properties={"file_path": Schema(type=Type.STRING)}, required=["file_path"])
        )

    @observe(name="DataHarvesterTool.run")
    def run(self, args: Dict[str, Any]) -> str:
        file_path = args.get("file_path")
        if not file_path: return "Error: file_path missing"
        try:
            return OCREngine().extract(file_path)
        except Exception as e:
            return f"Extraction Error: {e}"

class LangBridgeTool(BaseTool):
    def __init__(self):
        super().__init__(name="lang_bridge_tool", description="Standardizes invoice content to English JSON.")

    def _get_declaration(self):
        return FunctionDeclaration(
            name=self.name,
            description=self.description,
            parameters=Schema(type=Type.OBJECT, properties={"text": Schema(type=Type.STRING)}, required=["text"])
        )

    @observe(name="LangBridgeTool.run")
    def run(self, args: Dict[str, Any]) -> Dict[str, Any]:
        text = args.get("text")
        if not text: return {"error": "No text"}
        try:
            parser = PydanticOutputParser(pydantic_object=InvoiceData)
            prompt = PromptTemplate(
                template="Extract structured data.\n{format_instructions}\nINVOICE:\n{text}",
                input_variables=["text"],
                partial_variables={"format_instructions": parser.get_format_instructions()},
            )
            llm = BedrockLLMService(model_id=settings.TRANSLATION_MODEL).get_llm()
            chain = prompt | llm | parser
            res = chain.invoke({"text": text})
            return {"extracted_data": res.model_dump()}
        except Exception as e:
            return {"extracted_data": InvoiceData().model_dump(), "error": str(e)}

class DataCompletenessCheckerTool(BaseTool):
    def __init__(self):
        super().__init__(name="data_completeness_checker_tool", description="Checks for missing fields.")

    def _get_declaration(self):
        return FunctionDeclaration(
            name=self.name,
            description=self.description,
            parameters=Schema(type=Type.OBJECT, properties={"invoice_data": Schema(type=Type.OBJECT)}, required=["invoice_data"])
        )

    def run(self, args: Dict[str, Any]) -> Dict[str, Any]:
        data = args.get("invoice_data", {})
        missing = [f for f in ["invoice_no", "invoice_date", "total_amount", "vendor_id"] if not data.get(f)]
        items = data.get("line_items", [])
        if not items: missing.append("line_items")
        else:
            for i, item in enumerate(items):
                if not item.get("item_code"): missing.append(f"line_items[{i}].item_code")
        return {"validation_status": "valid" if not missing else "invalid", "missing_fields": missing}

class InsightReporterTool(BaseTool):
    def __init__(self):
        super().__init__(name="insight_reporter_tool", description="Generates reports.")

    def _get_declaration(self):
        # Simplified schema for brevity, allows flexible dicts
        return FunctionDeclaration(
            name=self.name,
            description=self.description,
            parameters=Schema(type=Type.OBJECT, properties={
                "file_name": Schema(type=Type.STRING),
                "extracted_data": Schema(type=Type.OBJECT),
                "validation_report": Schema(type=Type.OBJECT)
            }, required=["file_name"])
        )

    def _sanitize(self, text: Any) -> str:
        return str(text).encode('latin-1', 'replace').decode('latin-1') if text else ""

    @observe(name="InsightReporterTool.run")
    def run(self, args: Dict[str, Any]) -> Dict[str, str]:
        file_name = args.get("file_name", "report")
        data = args.get("extracted_data", {})
        val_res = args.get("validation_report", {})
        
        base = Path(file_name).stem
        json_path = settings.OUTPUT_DIR / f"{base}_report.json"
        pdf_path = settings.OUTPUT_DIR / f"{base}_report.pdf"
        
        with open(json_path, 'w') as f:
            json.dump({"meta": {"file": file_name}, "data": data, "validation": val_res}, f, indent=2)
            
        try:
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Arial", 'B', 16)
            pdf.cell(0, 10, "Invoice Report", ln=1, align='C')
            pdf.set_font("Arial", '', 12)
            pdf.cell(0, 10, f"File: {self._sanitize(file_name)}", ln=1)
            pdf.cell(0, 10, f"Status: {'VALID' if val_res.get('is_valid') else 'INVALID'}", ln=1)
            pdf.output(str(pdf_path))
        except Exception: pass
        
        return {"json": str(json_path), "pdf": str(pdf_path)}

class VectorIndexerTool(BaseTool):
    def __init__(self):
        super().__init__(name="vector_indexer_tool", description="Indexes documents.")
        self._splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)

    def _get_declaration(self):
        return FunctionDeclaration(
            name=self.name,
            description=self.description,
            parameters=Schema(type=Type.OBJECT, properties={"text": Schema(type=Type.STRING)}, required=["text"])
        )

    @observe(name="VectorIndexerTool.run")
    def run(self, args: Dict[str, Any]) -> int:
        text = args.get("text", "")
        meta = args.get("metadata", {})
        if not text: return 0
        chunks = self._splitter.create_documents([text])
        for i, c in enumerate(chunks):
            vector_store.add_document(c.page_content, {**meta, "chunk_id": i})
        return len(chunks)

class SemanticRetrieverTool(BaseTool):
    def __init__(self):
        super().__init__(name="semantic_retriever_tool", description="Retrieves documents.")

    def _get_declaration(self):
        return FunctionDeclaration(
            name=self.name,
            description=self.description,
            parameters=Schema(type=Type.OBJECT, properties={"query": Schema(type=Type.STRING)}, required=["query"])
        )

    @observe(name="SemanticRetrieverTool.run")
    def run(self, args: Dict[str, Any]) -> List[Dict]:
        return vector_store.search(args.get("query", ""), limit=args.get("limit", 5), filename=args.get("filename"))

class ChunkRankerTool(BaseTool):
    def __init__(self):
        super().__init__(name="chunk_ranker_tool", description="Reranks documents.")

    def _get_declaration(self):
        return FunctionDeclaration(
            name=self.name,
            description=self.description,
            parameters=Schema(type=Type.OBJECT, properties={"docs": Schema(type=Type.ARRAY)}, required=["docs"])
        )

    @observe(name="ChunkRankerTool.run")
    def run(self, args: Dict[str, Any]) -> str:
        docs = args.get("docs", [])
        ranked = sorted(docs, key=lambda d: d.get('score', 0), reverse=True)
        return "\n---\n".join([f"Source: {d.get('metadata',{}).get('filename')}\n{d.get('text')}" for d in ranked])

class ResponseSynthesizerTool(BaseTool):
    def __init__(self):
        super().__init__(name="response_synthesizer_tool", description="Synthesizes answer.")

    def _get_declaration(self):
        return FunctionDeclaration(
            name=self.name,
            description=self.description,
            parameters=Schema(type=Type.OBJECT, properties={"query": Schema(type=Type.STRING), "context": Schema(type=Type.STRING)}, required=["query", "context"])
        )

    @observe(name="ResponseSynthesizerTool.run")
    def run(self, args: Dict[str, Any]) -> str:
        try:
            prompt = f"Context:\n{args.get('context')}\n\nQuestion: {args.get('query')}"
            return BedrockLLMService(model_id=settings.REPORTING_MODEL).invoke(prompt)
        except Exception as e: return str(e)

class RAGEvaluatorTool(BaseTool):
    def __init__(self):
        super().__init__(name="rag_evaluator_tool", description="Evaluates RAG.")

    def _get_declaration(self):
        return FunctionDeclaration(
            name=self.name,
            description=self.description,
            parameters=Schema(type=Type.OBJECT, properties={"query": Schema(type=Type.STRING)}, required=["query"])
        )

    @observe(name="RAGEvaluatorTool.run")
    def run(self, args: Dict[str, Any]) -> str:
        try:
            llm = ChatBedrockConverse(model=settings.VALIDATION_MODEL, temperature=0)
            emb = BedrockEmbeddings(model_id=settings.EMBEDDING_MODEL)
            data = {"question": [args["query"]], "answer": [args["answer"]], "contexts": [[args["context"]]]}
            res = evaluate(Dataset.from_dict(data), metrics=[faithfulness, answer_relevancy], llm=LangchainLLMWrapper(llm), embeddings=LangchainEmbeddingsWrapper(emb), raise_exceptions=False)
            return json.dumps({k: float(v) for k,v in res.items()})
        except Exception as e: return json.dumps({"error": str(e)})

class SystemStatsTool(BaseTool):
    def __init__(self):
        super().__init__(name="system_stats_tool", description="System stats.")

    def _get_declaration(self):
        return FunctionDeclaration(name=self.name, description=self.description, parameters=Schema(type=Type.OBJECT, properties={}))

    def run(self, args: Dict[str, Any]) -> str:
        return f"Processed: {len(list(settings.PROCESSED_DIR.glob('*.*')))}"