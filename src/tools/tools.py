# ===== FILE: src/tools/tools.py =====
import json
import os
from typing import Dict, Any, List, Optional
from pathlib import Path
from datetime import datetime, timezone
from fpdf import FPDF
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_aws import ChatBedrockConverse, BedrockEmbeddings
from ragas import evaluate
from ragas.metrics import faithfulness, answer_relevancy, context_precision, context_recall
from ragas.llms import LangchainLLMWrapper
from ragas.embeddings import LangchainEmbeddingsWrapper
from datasets import Dataset

from src.core.protocol import MCPTool
from src.core.config import settings
from src.core.logger import logger
from src.database.qdrant_db import vector_store
from src.tools.ocr_engine import OCREngine
from src.core.state import InvoiceData
from src.core.llm_wrapper import BedrockLLMService

# Handle conditional import for Langfuse observability
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
    input_schema: Dict[str, Any] = {"type": "object", "properties": {"path": {"type": "string"}}}

class DataHarvesterTool(BaseTool):
    name: str = "Data Harvester Tool"
    description: str = "Extracts data from documents using OCR."
    input_schema: Dict[str, Any] = {
        "type": "object", 
        "properties": {"file_path": {"type": "string"}}, 
        "required": ["file_path"]
    }

    @observe(name="DataHarvesterTool.run")
    def run(self, file_path: str) -> str:
        engine = OCREngine()
        return engine.extract(file_path)

class LangBridgeTool(BaseTool):
    name: str = "Lang-Bridge Tool"
    description: str = "Standardizes invoice content to English JSON."
    input_schema: Dict[str, Any] = {
        "type": "object", 
        "properties": {"text": {"type": "string"}}, 
        "required": ["text"]
    }

    @observe(name="LangBridgeTool.run")
    def run(self, text: str) -> Dict[str, Any]:
        try:
            parser = PydanticOutputParser(pydantic_object=InvoiceData)
            prompt = PromptTemplate(
                template="Extract structured data.\n{format_instructions}\nINVOICE:\n{text}",
                input_variables=["text"],
                partial_variables={"format_instructions": parser.get_format_instructions()},
            )
            # Fix: BedrockLLMService is now imported and defined in llm_wrapper.py
            llm = BedrockLLMService(model_id=settings.TRANSLATION_MODEL).get_llm()
            chain = prompt | llm | parser
            invoice_data = chain.invoke({"text": text})
            return {"extracted_data": invoice_data.model_dump()}
        except Exception as e:
            logger.error(f"LangBridge Error: {e}")
            return {"extracted_data": InvoiceData().model_dump(), "error": str(e)}

class DataCompletenessCheckerTool(BaseTool):
    name: str = "DataCompletenessChecker Tool"
    description: str = "Checks for missing mandatory fields."
    input_schema: Dict[str, Any] = {"type": "object", "properties": {"invoice_data": {"type": "object"}}}

    def run(self, invoice_data: Dict[str, Any]) -> Dict[str, Any]:
        missing = []
        required = ["invoice_no", "invoice_date", "total_amount", "vendor_id"]
        
        if not invoice_data:
             return {"validation_status": "invalid", "missing_fields": ["NO_DATA_PROVIDED"]}

        for f in required:
            val = invoice_data.get(f)
            if not val or val == "None":
                missing.append(f)
        
        # Check line items if they exist
        items = invoice_data.get("line_items", [])
        if items:
            for i, item in enumerate(items):
                if not item.get("item_code"):
                    missing.append(f"line_items[{i}].item_code")

        return {"validation_status": "valid" if not missing else "invalid", "missing_fields": missing}

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
        },
        "required": ["file_name", "extracted_data", "validation_report"]
    }

    def _sanitize(self, text: Any) -> str:
        if text is None: return ""
        text = str(text)
        replacements = {
            "€": "EUR", "£": "GBP", "¥": "JPY", "₹": "INR",
            "‘": "'", "’": "'", "“": '"', "”": '"', "–": "-"
        }
        for char, repl in replacements.items():
            text = text.replace(char, repl)
        return text.encode('latin-1', 'replace').decode('latin-1')

    @observe(name="InsightReporterTool.run")
    def run(self, file_name: str, extracted_data: Dict, validation_report: Dict, safety_report: Optional[Dict] = None, metadata: Dict = {}) -> Dict[str, str]:
        base_name = Path(file_name).stem
        json_path = settings.OUTPUT_DIR / f"{base_name}_report.json"
        pdf_path = settings.OUTPUT_DIR / f"{base_name}_report.pdf"
        
        # Determine Status
        status = "COMPLETED"
        if safety_report and not safety_report.get("is_safe"): status = "FLAGGED"
        elif validation_report and not validation_report.get("is_valid"): status = "DATA_INVALID"
        elif validation_report.get("business_status") == "mismatch": status = "BUSINESS_MISMATCH"

        # 1. JSON Report
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

        # 2. PDF Report
        try:
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Arial", 'B', 16)
            pdf.set_fill_color(240, 248, 255)
            pdf.cell(0, 15, "AI Invoice Auditor Report", ln=1, align='C', fill=True, border=1)
            pdf.ln(5)

            # Metadata Section
            pdf.set_font("Arial", 'B', 10)
            pdf.cell(30, 8, "File Name:", border=0)
            pdf.set_font("Arial", '', 10)
            pdf.cell(0, 8, self._sanitize(file_name), border=0, ln=1)
            
            pdf.set_font("Arial", 'B', 10)
            pdf.cell(30, 8, "Status:", border=0)
            
            # Color coding status
            if status == "COMPLETED": pdf.set_text_color(34, 139, 34)
            elif status == "FLAGGED": pdf.set_text_color(220, 20, 60)
            else: pdf.set_text_color(255, 140, 0)
            
            pdf.cell(0, 8, status, border=0, ln=1)
            pdf.set_text_color(0, 0, 0)
            pdf.ln(5)

            # Extracted Data Section
            pdf.set_font("Arial", 'B', 12)
            pdf.set_fill_color(230, 230, 250)
            pdf.cell(0, 8, " Extracted Data", ln=1, fill=True, border=1)
            pdf.set_font("Arial", size=10)
            
            fields = [
                ("Invoice #", extracted_data.get('invoice_no')),
                ("Date", extracted_data.get('invoice_date')),
                ("Vendor", extracted_data.get('vendor_id')),
                ("Total", f"{extracted_data.get('total_amount')} {extracted_data.get('currency', '')}")
            ]
            
            for label, value in fields:
                pdf.cell(40, 8, label, border=1)
                pdf.cell(0, 8, self._sanitize(value), border=1, ln=1)
            
            pdf.ln(5)

            # Validation Results
            pdf.set_font("Arial", 'B', 12)
            pdf.set_fill_color(255, 250, 205)
            pdf.cell(0, 8, " Validation Results", ln=1, fill=True, border=1)
            pdf.set_font("Arial", size=10)
            
            discrepancies = validation_report.get("discrepancies", [])
            missing = validation_report.get("missing_fields", [])
            
            if not discrepancies and not missing:
                pdf.set_text_color(0, 100, 0)
                pdf.cell(0, 8, " [PASS] All validations passed.", ln=1)
            else:
                pdf.set_text_color(200, 0, 0)
                for d in discrepancies:
                    pdf.cell(0, 8, f" [FAIL] {self._sanitize(d)}", ln=1)
                for m in missing:
                     pdf.cell(0, 8, f" [MISSING] Field: {self._sanitize(m)}", ln=1)
            
            pdf.output(str(pdf_path))
            
        except Exception as e:
            logger.error(f"PDF Generation Failed: {e}")
            # Even if PDF fails, return JSON path
            
        return {"json": str(json_path), "pdf": str(pdf_path)}

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
            # Using the vector_store singleton from qdrant_db.py
            vector_store.add_document(chunk.page_content, {**metadata, "chunk_id": i})
        return len(chunks)

class SemanticRetrieverTool(BaseTool):
    name: str = "Semantic-Retriever Tool"
    description: str = "Performs semantic search."
    input_schema: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "query": {"type": "string"}, 
            "limit": {"type": "integer"}, 
            "filename": {"type": "string"}
        },
        "required": ["query"]
    }

    @observe(name="SemanticRetrieverTool.run")
    def run(self, query: str, limit: int = 5, filename: Optional[str] = None) -> List[Dict]:
        return vector_store.search(query, limit=limit, filename=filename)

class ChunkRankerTool(BaseTool):
    name: str = "Chunk-Ranker Tool"
    description: str = "Re-ranks retrieved chunks based on score."
    input_schema: Dict[str, Any] = {
        "type": "object", 
        "properties": {"docs": {"type": "array"}}
    }

    @observe(name="ChunkRankerTool.run")
    def run(self, docs: List[Dict]) -> str:
        if not docs: return ""
        # Sort by score descending
        ranked = sorted(docs, key=lambda d: d.get('score', 0), reverse=True)
        # Format for Context String
        return "\n---\n".join([
            f"Source: {d.get('metadata',{}).get('filename', 'unknown')}\n{d.get('text')}" 
            for d in ranked
        ])

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
            llm_service = BedrockLLMService(model_id=settings.REPORTING_MODEL)
            prompt = f"Context:\n{context}\n\nQuestion: {query}\n\nAnswer:"
            return llm_service.invoke(prompt)
        except Exception as e:
            return f"Error synthesizing response: {e}"

class RAGEvaluatorTool(BaseTool):
    name: str = "RAG-Evaluator Tool"
    description: str = "Evaluates RAG performance using Ragas metrics."
    input_schema: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "query": {"type": "string"}, 
            "answer": {"type": "string"}, 
            "context": {"type": "string"}
        },
        "required": ["query", "answer", "context"]
    }

    @observe(name="RAGEvaluatorTool.run")
    def run(self, query: str, answer: str, context: str) -> str:
        logger.info("Starting Ragas Evaluation...")
        try:
            # 1. Setup Bedrock for Ragas
            # Use ChatBedrockConverse for better stability with Ragas
            bedrock_llm = ChatBedrockConverse(
                model=settings.VALIDATION_MODEL, # e.g. cohere.command-r-plus-v1:0
                temperature=0.0,
                region_name=os.getenv("AWS_DEFAULT_REGION", "us-east-1")
            )
            bedrock_emb = BedrockEmbeddings(
                model_id=settings.EMBEDDING_MODEL, # e.g. amazon.titan-embed-text-v1
                region_name=os.getenv("AWS_DEFAULT_REGION", "us-east-1")
            )

            # 2. Wrap for Ragas
            ragas_llm = LangchainLLMWrapper(bedrock_llm)
            ragas_emb = LangchainEmbeddingsWrapper(bedrock_emb)

            # 3. Create Dataset (Strict Format)
            data = {
                "question": [query],
                "answer": [answer],
                "contexts": [[context]], # Must be list of lists
                "ground_truth": [answer] # Optional, using answer as proxy if GT missing
            }
            dataset = Dataset.from_dict(data)

            # 4. Evaluate
            results = evaluate(
                dataset=dataset,
                metrics=[faithfulness, answer_relevancy, context_precision, context_recall],
                llm=ragas_llm,
                embeddings=ragas_emb,
                raise_exceptions=False # Prevent crash on single metric fail
            )
            
            # 5. Clean Result
            res_dict = results.to_pandas().iloc[0].to_dict()
            # Remove non-serializable objects if any
            clean_res = {k: float(v) if isinstance(v, (int, float)) else str(v) for k, v in res_dict.items()}
            
            logger.success(f"Ragas Metrics: {clean_res}")
            return json.dumps(clean_res)

        except Exception as e:
            logger.error(f"RAGAS Eval Critical Failure: {e}")
            # Return zeroed metrics so flow doesn't break
            return json.dumps({
                "faithfulness": 0.0,
                "answer_relevancy": 0.0,
                "context_precision": 0.0, 
                "context_recall": 0.0,
                "error": str(e)
            })

class SystemStatsTool(BaseTool):
    name: str = "System-Stats Tool"
    description: str = "Aggregates current system statistics."
    input_schema: Dict[str, Any] = {"type": "object", "properties": {}}

    @observe(name="SystemStatsTool.run")
    def run(self) -> str:
        try:
            processed = list(settings.PROCESSED_DIR.glob("*.*"))
            reports = list(settings.OUTPUT_DIR.glob("*.pdf"))
            return f"Processed Files: {len(processed)}, Generated Reports: {len(reports)}"
        except Exception as e:
            return f"Error reading stats: {e}"