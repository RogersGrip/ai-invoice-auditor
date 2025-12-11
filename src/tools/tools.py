# ===== FILE: src/tools/tools.py =====
import json
import os
from typing import Dict, Any, List
from pathlib import Path
from datetime import datetime, timezone
from fpdf import FPDF

# --- Framework Imports ---
# These allow the tools to be used by the Google ADK Agents
from src.frameworks.google_adk.tools import BaseTool

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

# ==============================================================================
# 1. Invoice Watcher Tool
# ==============================================================================
class InvoiceWatcherTool(BaseTool):
    def __init__(self):
        super().__init__(
            name="Invoice-Watcher Tool", 
            description="Monitors a designated mailbox or file system for new invoices."
        )

    def run(self, args: Dict[str, Any]) -> str:
        path = args.get("path", str(settings.INVOICE_WATCH_DIR))
        if not os.path.exists(path):
            return f"Error: Path {path} does not exist."
        files = [f for f in os.listdir(path) if not f.startswith(".")]
        return json.dumps({"status": "monitoring", "path": path, "file_count": len(files)})

# ==============================================================================
# 2. Data Harvester Tool (OCR)
# ==============================================================================
class DataHarvesterTool(BaseTool):
    def __init__(self):
        super().__init__(
            name="Data Harvester Tool", 
            description="Extracts raw text from documents using OCR engine."
        )

    @observe(name="DataHarvesterTool.run")
    def run(self, args: Dict[str, Any]) -> str:
        file_path = args.get("file_path")
        if not file_path:
            return "Error: 'file_path' argument is required."
        try:
            engine = OCREngine()
            return engine.extract(file_path)
        except Exception as e:
            logger.error(f"Harvester Failed: {e}")
            return f"Error extracting text: {str(e)}"

# ==============================================================================
# 3. Lang-Bridge Tool (Translation)
# ==============================================================================
class LangBridgeTool(BaseTool):
    def __init__(self):
        super().__init__(
            name="Lang-Bridge Tool", 
            description="Standardizes invoice content to English JSON format."
        )

    @observe(name="LangBridgeTool.run")
    def run(self, args: Dict[str, Any]) -> Dict[str, Any]:
        text = args.get("text")
        if not text:
            return {"error": "No text provided"}
        
        try:
            parser = PydanticOutputParser(pydantic_object=InvoiceData)
            prompt = PromptTemplate(
                template="Extract structured data.\n{format_instructions}\nINVOICE:\n{text}",
                input_variables=["text"],
                partial_variables={"format_instructions": parser.get_format_instructions()},
            )
            # Corrected usage of BedrockLLMService
            llm_service = BedrockLLMService(model_id=settings.TRANSLATION_MODEL)
            chain = prompt | llm_service.get_llm() | parser
            
            invoice_data = chain.invoke({"text": text})
            return {"extracted_data": invoice_data.model_dump()}
        except Exception as e:
            logger.error(f"LangBridge Error: {e}")
            return {"extracted_data": InvoiceData().model_dump(), "error": str(e)}

# ==============================================================================
# 4. Data Completeness Checker Tool
# ==============================================================================
class DataCompletenessCheckerTool(BaseTool):
    def __init__(self):
        super().__init__(
            name="DataCompletenessChecker Tool", 
            description="Checks for missing mandatory fields in invoice data."
        )

    def run(self, args: Dict[str, Any]) -> Dict[str, Any]:
        invoice_data = args.get("invoice_data", {})
        if not invoice_data:
             return {"validation_status": "invalid", "missing_fields": ["NO_DATA"]}

        missing = []
        required_fields = ["invoice_no", "invoice_date", "total_amount", "vendor_id"]
        
        for f in required_fields:
            val = invoice_data.get(f)
            if not val or val == "None":
                missing.append(f)
        
        # Check line items
        items = invoice_data.get("line_items", [])
        if not items:
            missing.append("line_items")
        else:
            for i, item in enumerate(items):
                if not item.get("item_code"):
                    missing.append(f"line_items[{i}].item_code")

        return {
            "validation_status": "valid" if not missing else "invalid",
            "missing_fields": missing
        }

# ==============================================================================
# 5. Business Validation Tool (Wrapper)
# ==============================================================================
class BusinessValidationTool(BaseTool):
    def __init__(self):
        super().__init__(
            name="Business Validation Tool", 
            description="Cross-verifies extracted invoice data against enterprise systems."
        )
    
    def run(self, args: Dict[str, Any]) -> Dict[str, Any]:
        # This is a placeholder wrapper. The actual logic is in the Agent calling the MCP function directly.
        # However, for ADK compatibility, we return a standard response.
        return {"status": "use_agent_logic_instead"}

# ==============================================================================
# 6. Insight Reporter Tool
# ==============================================================================
class InsightReporterTool(BaseTool):
    def __init__(self):
        super().__init__(
            name="Insight Reporter Tool", 
            description="Generates high-fidelity PDF and JSON audit reports."
        )

    def _sanitize(self, text: Any) -> str:
        if text is None: return ""
        text = str(text)
        replacements = {"€": "EUR", "£": "GBP", "¥": "JPY", "₹": "INR", "‘": "'", "’": "'", "“": '"', "”": '"'}
        for char, repl in replacements.items():
            text = text.replace(char, repl)
        return text.encode('latin-1', 'replace').decode('latin-1')

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

            # Metadata
            pdf.set_font("Arial", 'B', 10)
            pdf.cell(30, 8, "File Name:", border=0)
            pdf.set_font("Arial", '', 10)
            pdf.cell(0, 8, self._sanitize(file_name), border=0, ln=1)
            pdf.set_font("Arial", 'B', 10)
            pdf.cell(30, 8, "Status:", border=0)
            
            if status == "COMPLETED": pdf.set_text_color(34, 139, 34)
            elif status == "FLAGGED": pdf.set_text_color(220, 20, 60)
            else: pdf.set_text_color(255, 140, 0)
            pdf.cell(0, 8, status, border=0, ln=1)
            pdf.set_text_color(0, 0, 0)
            pdf.ln(5)

            # Data
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

            # Validation
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
            
        return {"json": str(json_path), "pdf": str(pdf_path)}

# ==============================================================================
# 7. Vector Indexer Tool
# ==============================================================================
class VectorIndexerTool(BaseTool):
    def __init__(self):
        super().__init__(name="Vector-Indexer Tool", description="Indexes documents into Qdrant.")
        self._text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)

    @observe(name="VectorIndexerTool.run")
    def run(self, args: Dict[str, Any]) -> int:
        text = args.get("text", "")
        metadata = args.get("metadata", {})
        if not text: return 0
        
        chunks = self._text_splitter.create_documents([text])
        for i, chunk in enumerate(chunks):
            vector_store.add_document(chunk.page_content, {**metadata, "chunk_id": i})
        return len(chunks)

# ==============================================================================
# 8. Semantic Retriever Tool
# ==============================================================================
class SemanticRetrieverTool(BaseTool):
    def __init__(self):
        super().__init__(name="Semantic-Retriever Tool", description="Performs semantic search.")

    @observe(name="SemanticRetrieverTool.run")
    def run(self, args: Dict[str, Any]) -> List[Dict]:
        query = args.get("query")
        limit = args.get("limit", 5)
        filename = args.get("filename")
        if not query: return []
        return vector_store.search(query, limit=limit, filename=filename)

# ==============================================================================
# 9. Chunk Ranker Tool
# ==============================================================================
class ChunkRankerTool(BaseTool):
    def __init__(self):
        super().__init__(name="Chunk-Ranker Tool", description="Re-ranks retrieved chunks.")

    @observe(name="ChunkRankerTool.run")
    def run(self, args: Dict[str, Any]) -> str:
        docs = args.get("docs", [])
        if not docs: return ""
        ranked = sorted(docs, key=lambda d: d.get('score', 0), reverse=True)
        return "\n---\n".join([f"Source: {d.get('metadata',{}).get('filename')}\n{d.get('text')}" for d in ranked])

# ==============================================================================
# 10. Response Synthesizer Tool
# ==============================================================================
class ResponseSynthesizerTool(BaseTool):
    def __init__(self):
        super().__init__(name="Response-Synthesizer Tool", description="Generates answers using LLM.")

    @observe(name="ResponseSynthesizerTool.run")
    def run(self, args: Dict[str, Any]) -> str:
        query = args.get("query")
        context = args.get("context")
        try:
            llm_service = BedrockLLMService(model_id=settings.REPORTING_MODEL)
            prompt = f"Context:\n{context}\n\nQuestion: {query}\n\nAnswer:"
            return llm_service.invoke(prompt)
        except Exception as e:
            return f"Error: {e}"

# ==============================================================================
# 11. RAG Evaluator Tool
# ==============================================================================
class RAGEvaluatorTool(BaseTool):
    def __init__(self):
        super().__init__(name="RAG-Evaluator Tool", description="Evaluates RAG performance using Ragas metrics.")

    @observe(name="RAGEvaluatorTool.run")
    def run(self, args: Dict[str, Any]) -> str:
        query = args.get("query")
        answer = args.get("answer")
        context = args.get("context")
        
        logger.info("Starting Ragas Evaluation...")
        try:
            bedrock_llm = ChatBedrockConverse(
                model=settings.VALIDATION_MODEL,
                temperature=0.0,
                region_name=os.getenv("AWS_DEFAULT_REGION", "us-east-1")
            )
            bedrock_emb = BedrockEmbeddings(
                model_id=settings.EMBEDDING_MODEL,
                region_name=os.getenv("AWS_DEFAULT_REGION", "us-east-1")
            )

            ragas_llm = LangchainLLMWrapper(bedrock_llm)
            ragas_emb = LangchainEmbeddingsWrapper(bedrock_emb)

            data = {
                "question": [query],
                "answer": [answer],
                "contexts": [[context]],
                "ground_truth": [answer]
            }
            dataset = Dataset.from_dict(data)

            results = evaluate(
                dataset=dataset,
                metrics=[faithfulness, answer_relevancy, context_precision, context_recall],
                llm=ragas_llm,
                embeddings=ragas_emb,
                raise_exceptions=False
            )
            
            res_dict = results.to_pandas().iloc[0].to_dict()
            clean_res = {k: float(v) if isinstance(v, (int, float)) else str(v) for k, v in res_dict.items()}
            return json.dumps(clean_res)
        except Exception as e:
            logger.error(f"RAGAS Failed: {e}")
            return json.dumps({"faithfulness": 0.0, "error": str(e)})

# ==============================================================================
# 12. System Stats Tool
# ==============================================================================
class SystemStatsTool(BaseTool):
    def __init__(self):
        super().__init__(name="System-Stats Tool", description="Aggregates system statistics.")

    def run(self, args: Dict[str, Any]) -> str:
        try:
            processed = list(settings.PROCESSED_DIR.glob("*.*"))
            reports = list(settings.OUTPUT_DIR.glob("*.pdf"))
            return f"Processed: {len(processed)}, Reports: {len(reports)}"
        except Exception as e:
            return f"Error: {e}"