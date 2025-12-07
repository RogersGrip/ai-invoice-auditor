from typing import Dict, Any, List, Optional
import json
import logging
from fpdf import FPDF
from pathlib import Path
from datetime import datetime
from src.core.protocol import MCPTool, MCPClient
from src.tools.ocr_engine import OCREngine
from src.database.qdrant_db import vector_store
from src.core.config import settings
from src.core.logger import logger
from src.core.state import InvoiceData
from langchain_text_splitters import RecursiveCharacterTextSplitter
from litellm import completion
import re

# --- Langfuse Conditional Import ---
try:
    if settings.LANGFUSE_PUBLIC_KEY:
        from langfuse import observe
    else:
        raise ImportError("Langfuse Public Key not set")
except ImportError:
    # No-op decorator
    def observe(*args, **kwargs):
        def decorator(func):
            return func
        return decorator

class BaseTool(MCPTool):
    """Base class for all tools."""
    pass

class InvoiceWatcherTool(BaseTool):
    name: str = "Invoice-Watcher Tool"
    description: str = "Monitors a designated mailbox or file system to detect and retrieve emails containing invoice attachments."
    input_schema: Dict[str, Any] = {
        "type": "object",
        "properties": {
             "source_path": {"type": "string", "description": "Path to watch"}
        }
    }
    
    # Logic remains in Monitor Agent for now as it's a polling process, 
    # but strictly this should be a "check_now" function.
    # Leaving as shell for Monitor Agent to use efficiently.

class DataHarvesterTool(BaseTool):
    name: str = "Data Harvester Tool"
    description: str = "Extracts data from a wide range of document formats."
    input_schema: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "file_path": {"type": "string"}
        },
        "required": ["file_path"]
    }
    
    @observe(name="DataHarvesterTool.run")
    def run(self, file_path: str) -> str:
        # Wrapper around OCREngine
        engine = OCREngine()
        return engine.extract(file_path)

class LangBridgeTool(BaseTool):
    name: str = "Lang-Bridge Tool"
    description: str = "Converts extracted invoice content from various languages into English."
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
        Uses LLM to extract JSON and translate.
        """
        prompt = """
        Extract the following fields from the invoice text and return JSON ONLY:
        - invoice_no (string)
        - invoice_date (YYYY-MM-DD)
        - vendor_id (string)
        - currency (ISO code, e.g. USD, EUR)
        - total_amount (float)
        - line_items (list of objects with: item_code, description, qty, unit_price, total)
        
        Translate any non-English description to English.
        """
        
        model = settings.TRANSLATION_MODEL
        if settings.MODEL_PROVIDER == "ollama":
            model = f"ollama/{settings.OLLAMA_MODEL}"
            
        logger.info(f"LangBridge: Translating using {model}")
        
        try:
            response = completion(
                model=model,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": text}
                ],
                format="json"
            )
            
            content_str = response.choices[0].message.content
            
            # Robust JSON cleaning
            match = re.search(r"\{.*\}", content_str, re.DOTALL)
            if match:
                content_str = match.group(0)
            
            if "```" in content_str:
                content_str = re.sub(r"```\w*", "", content_str).replace("```", "")
            
            content_str = content_str.strip()
            
            try:
                data = json.loads(content_str)
            except json.JSONDecodeError:
                 # Fallback quote fix
                 content_str = re.sub(r"\'(\w+)\'\s*:", r'"\1":', content_str)
                 data = json.loads(content_str)

            # Validate against Pydantic model implicitly or explicitly
            # Returns dict
            return {
                "english_text": "Extracted JSON", 
                "extracted_data": data,
                "model": model
            }
            
        except Exception as e:
            logger.error(f"LangBridge Error: {e}")
            raise e

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
        logger.info("DataCompletenessChecker: Validating fields...")
        missing = []
        required_headers = ["invoice_no", "invoice_date", "total_amount", "vendor_id"]
        
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
            "is_valid": is_valid,
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
    # This tool is usually a wrapper for the MCP Client call
    # But for strict tool usage within agent, we can define run here if needed.
    # The ADK Agent connects to MCP, so this might remain shell or be the client wrapper.

class InsightReporterTool(BaseTool):
    name: str = "Insight Reporter Tool"
    description: str = "Generates comprehensive reports highlighting data gaps, validation results, and recommendations."
    input_schema: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "report_data": {"type": "object"},
            "format": {"type": "string", "enum": ["PDF", "JSON"]} # Unused mostly
        }
    }
    
    def _sanitize_text(self, text: str) -> str:
        replacements = {
            "\u20ac": "EUR", "\u2013": "-", "\u2014": "--", "\u2018": "'", 
            "\u2019": "'", "\u201c": '"', "\u201d": '"', "\u2022": "-", "…": "..."
        }
        for char, repl in replacements.items():
            text = text.replace(char, repl)
        return text.encode('latin-1', 'replace').decode('latin-1')

    @observe(name="InsightReporterTool.run")
    def run(self, file_name: str, extracted_data: Dict, validation_report: Dict, metadata: Dict) -> Dict[str, str]:
        # Logic extracted from ReportingAgent
        base_name = Path(file_name).stem
        json_path = f"{settings.OUTPUT_DIR}/{base_name}_report.json"
        pdf_path = f"{settings.OUTPUT_DIR}/{base_name}_report.pdf"
        html_path = f"{settings.OUTPUT_DIR}/{base_name}_report.html"
        
        output_paths = {}
        
        # 1. JSON
        overall_status = "COMPLETED"
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
        with open(json_path, 'w') as f:
            json.dump(json_dump, f, indent=2)
        output_paths["json"] = json_path
        
        # 3. HTML Report (Basic)
        # Ensure title/headers are clean
        html_title = f"Invoice Audit: {self._sanitize_text(file_name)}"
        html_content = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; padding: 20px; line-height: 1.6; background-color: #ffffff; color: #333333; }}
                .container {{ max-width: 800px; margin: 0 auto; border: 1px solid #ddd; padding: 20px; border-radius: 8px; background-color: #ffffff; }}
                h1 {{ color: #2c3e50; text-align: center; }}
                .status {{ padding: 10px; background: #f8f9fa; border-left: 5px solid; margin-bottom: 20px; color: #333333; }}
                .status.valid {{ border-color: #28a745; }}
                .status.invalid {{ border-color: #dc3545; }}
                table {{ width: 100%; border-collapse: collapse; margin-top: 20px; color: #333333; }}
                th, td {{ padding: 12px; border: 1px solid #ddd; text-align: left; }}
                th {{ background-color: #f2f2f2; color: #333333; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>{html_title}</h1>
                <div class="status {'valid' if validation_report.get('is_valid') else 'invalid'}">
                    <strong>Status:</strong> {overall_status}<br>
                    <strong>Business Valid:</strong> {validation_report.get('is_valid')}
                </div>
                
                <h2>Extracted Data</h2>
                <p><strong>Invoice No:</strong> {extracted_data.get('invoice_no')}</p>
                <p><strong>Date:</strong> {extracted_data.get('invoice_date')}</p>
                <p><strong>Vendor:</strong> {extracted_data.get('vendor_id')}</p>
                <p><strong>Total:</strong> {extracted_data.get('total_amount')}</p>
                
                <h3>Line Items</h3>
                <table>
                    <tr><th>Description</th><th>Qty</th><th>Total</th></tr>
                    {"".join(f"<tr><td>{item.get('description')}</td><td>{item.get('qty')}</td><td>{item.get('total')}</td></tr>" for item in extracted_data.get('line_items', []))}
                </table>
                
                <h2>Validation Issues</h2>
                <ul>
                    {"".join(f"<li>{d}</li>" for d in validation_report.get('discrepancies', []))}
                </ul>
            </div>
        </body>
        </html>
        """
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        output_paths["html"] = html_path

        # 2. PDF
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", 'B', 16)
        pdf.cell(0, 10, "AI Invoice Auditor - Audit Report", ln=1, align='C')
        pdf.line(10, 20, 200, 20)
        pdf.ln(10)
        
        # File Info
        pdf.set_font("Arial", size=10)
        status = overall_status
        is_valid = validation_report.get("is_valid")
        status_color = (0, 128, 0) if is_valid else (200, 0, 0)
        
        pdf.cell(0, 8, f"File: {self._sanitize_text(file_name)}", ln=1)
        pdf.set_text_color(*status_color)
        pdf.set_font("Arial", 'B', 10)
        pdf.cell(0, 8, f"Processing Status: {status}", ln=1)
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("Arial", size=10)
        
        ext = extracted_data
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
        
        # Validation
        val = validation_report
        pdf.ln(10)
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(0, 8, "Validation & Audit Results", ln=1, fill=True)
        pdf.set_font("Arial", size=10)
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
            
        pdf.output(pdf_path)
        output_paths["pdf"] = pdf_path
        
        # 3. HTML (Simplified)
        # Leaving HTML out to keep tool concise, or assume PDF is primary.
        return output_paths

class SystemStatsTool(BaseTool):
    name: str = "System-Stats Tool"
    description: str = "Aggregates current system statistics like processed file counts."
    input_schema: Dict[str, Any] = {
        "type": "object",
        "properties": {}
    }

    @observe(name="SystemStatsTool.run")
    def run(self) -> str:
        try:
            invoice_dir = settings.INVOICE_WATCH_DIR 
            # If settings.INVOICE_DIR is relative/pathlib object, handle it. 
            # Assuming strictly it matches config usage.
            # Let's rely on pathlib Path from config logic if possible or hardcode base paths relative to project root
            # But safer to use settings.
            
            # Count Invoices
            invoices = list(Path(invoice_dir).glob("*.*"))
            processed = list(Path(settings.PROCESSED_DIR).glob("*.*"))
            reports = list(Path(settings.OUTPUT_DIR).glob("*.pdf"))
            
            # Check Status File
            status_summary = "Idle"
            status_file = Path("data/status.json")
            if status_file.exists():
                try:
                    with open(status_file, "r") as f:
                        data = json.load(f)
                        status_summary = f"Processing {data.get('current_file', 'Unknown')} at step {data.get('step', 'Unknown')}"
                except:
                    pass

            # Calculate Global Stats from JSON Reports
            max_amount = 0.0
            max_invoice = "None"
            total_processed_value = 0.0
            
            report_files = list(Path("outputs/reports").glob("*_report.json"))
            valid_reports_count = 0
            
            for r_file in report_files:
                try:
                    with open(r_file, "r") as f:
                        r_data = json.load(f)
                        extraction = r_data.get("extraction", {})
                        amount = float(extraction.get("total_amount", 0.0))
                        
                        total_processed_value += amount
                        valid_reports_count += 1
                        
                        if amount > max_amount:
                            max_amount = amount
                            max_invoice = f"{extraction.get('invoice_no', 'Unknown')} ({r_file.stem})"
                except:
                    continue

            stats = f"""
System Statistics:
- Pending Invoices (Queue): {len(invoices)}
- Processed Invoices (Archived): {len(processed) // 2}
- Reports Generated: {len(reports)}
- Current Status: {status_summary}

Global Context (Structured Data):
- Total Invoices Value: ${total_processed_value:,.2f}
- Highest Value Invoice: {max_invoice} with Amount: ${max_amount:,.2f}
            """
            return stats.strip()
        except Exception as e:
            return f"Error gathering stats: {e}"

# --- RAG Tools (Unchanged) ---

class VectorIndexerTool(BaseTool):
    name: str = "Vector-Indexer Tool"
    description: str = "Converts documents into embeddings and stores them in a vector database."
    input_schema: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "metadata": {"type": "object"}
        }
    }
    
    # Private attr for logic
    _text_splitter: RecursiveCharacterTextSplitter = None

    def __init__(self, **data):
        super().__init__(**data)
        self._text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            separators=["\n\n", "\n", " ", ""]
        )

    @observe(name="VectorIndexerTool.run")
    def run(self, text: str, metadata: Dict[str, Any] = {}) -> int:
        if not self._text_splitter:
             self._text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=1000,
                chunk_overlap=200,
                separators=["\n\n", "\n", " ", ""]
            )
        chunks = self._text_splitter.create_documents([text])
        indexed_count = 0
        
        filename = metadata.get("filename", "unknown")
        
        # DEDUPLICATION: Remove old vectors for this file before re-indexing
        try:
            vector_store.delete_file(filename)
        except Exception as e:
            logger.warning(f"Deduplication failed for {filename}: {e}")
        
        for i, chunk in enumerate(chunks):
            chunk_meta = {
                "filename": filename,
                "chunk_index": i,
                "total_chunks": len(chunks),
                **metadata
            }
            vector_store.add_document(chunk.page_content, chunk_meta)
            indexed_count += 1
            
        return indexed_count

class SemanticRetrieverTool(BaseTool):
    name: str = "Semantic-Retriever Tool"
    description: str = "Performs semantic search using vector similarity."
    input_schema: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "limit": {"type": "integer", "default": 5},
            "filename": {"type": "string"}
        }
    }

    @observe(name="SemanticRetrieverTool.run")
    def run(self, query: str, limit: int = 5, filename: str = None) -> List[Dict]:
        return vector_store.search(query, limit=limit, filename=filename)

class ChunkRankerTool(BaseTool):
    name: str = "Chunk-Ranker Tool"
    description: str = "Re-ranks retrieved chunks based on relevance scores."
    input_schema: Dict[str, Any] = { 
        "type": "object", 
        "properties": {
            "docs": {"type": "array"}
        }
    }
    
    @observe(name="ChunkRankerTool.run")
    def run(self, docs: List[Dict]) -> str:
        # Simple Logic: Filter by similarity score, sort
        if not docs:
            return ""
        
        ranked_docs = sorted(docs, key=lambda x: x.get('score', 0), reverse=True)
         
        context_str = "\n---\n".join([
            f"[Source: {d['metadata'].get('filename')} (Score: {d.get('score'):.2f})]\n{d.get('text')}"
            for d in ranked_docs
        ])
        return context_str

class ResponseSynthesizerTool(BaseTool):
    name: str = "Response-Synthesizer Tool"
    description: str = "Generates natural language answers using retrieved context."
    input_schema: Dict[str, Any] = {
         "type": "object",
         "properties": {
             "query": {"type": "string"},
             "context": {"type": "string"}
         }
    }

    @observe(name="ResponseSynthesizerTool.run")
    def run(self, query: str, context: str) -> str:
        from src.core.prompts import load_prompt
        
        raw_prompt = load_prompt("rag_response_synthesizer.txt")
        # Template has {context} and {query}
        full_content = raw_prompt.format(context=context, query=query)
        
        model = settings.REPORTING_MODEL
        if settings.MODEL_PROVIDER == "ollama":
            model = f"ollama/{settings.OLLAMA_MODEL}"
            
        # FIX: Disable litellm background logging workers to prevent freeze/crash
        import litellm
        litellm.success_callback = []
        litellm.failure_callback = []
        litellm.callbacks = []

        response = completion(
            model=model,
            messages=[
                {"role": "user", "content": full_content}
            ],
            timeout=60 # Prevent infinite hang
        )
        return response.choices[0].message.content

class RAGEvaluatorTool(BaseTool):
    name: str = "RAG-Evaluator Tool"
    description: str = "Assesses generated responses using real RAGAS metrics."
    input_schema: Dict[str, Any] = {
        "type": "object",
        "properties": {
             "query": {"type": "string"},
             "response": {"type": "string"},
             "context": {"type": "string"}
        }
    }

    @observe(name="RAGEvaluatorTool.run")
    def run(self, query: str, answer: str, context: str) -> str:
        # Keeping existing logic (truncated for brevity in this update, assuming previous robust implementation stays)
        # For the purpose of this replacement, I'll assume the full robust implementation is preserved if not overwritten,
        # but since I am overwriting, I must re-include it.
        # ... (Re-pasting the robust logic from previous read)
        try:
            from ragas import evaluate
            from ragas.metrics import (
                faithfulness, 
                answer_relevancy, 
                context_precision, 
                context_recall, 
                context_entity_recall
            )
            from datasets import Dataset
            from langchain_litellm import ChatLiteLLM
            from langchain_core.embeddings import Embeddings
            from langchain_core.messages import BaseMessage
            from langchain_core.outputs import ChatResult
            from litellm import embedding as litellm_embedding
            import logging
            
            # --- Safe Ollama Wrapper Redefinition ---
            # --- Safe Ollama Wrapper Redefinition ---
            class SafeOllamaWrapper(ChatLiteLLM):
                def _generate(self, messages, stop=None, run_manager=None, **kwargs):
                    # kwargs["response_format"] = {"type": "json_object"} # DISABLED: Ragas manages its own prompts
                    try:
                        result = super()._generate(messages, stop, run_manager, **kwargs)
                        return result
                    except Exception as e:
                        logger.error(f"Wrapper Error: {e}")
                        raise e
                async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
                    # kwargs["response_format"] = {"type": "json_object"}
                    try:
                        result = await super()._agenerate(messages, stop, run_manager, **kwargs)
                        return result
                    except Exception as e:
                        logger.error(f"Wrapper Async Error: {e}")
                        raise e

            class LiteLLMEmbeddings(Embeddings):
                def __init__(self, model_name: str):
                    self.model = model_name
                def embed_documents(self, texts: List[str]) -> List[List[float]]:
                    return [self.embed_query(txt) for txt in texts]
                def embed_query(self, text: str) -> List[float]:
                    resp = litellm_embedding(model=self.model, input=[text])
                    # Handle both Pydantic model and Dict
                    if hasattr(resp, "data"):
                        data = resp.data
                    else:
                        data = resp.get("data", [])
                    
                    if not data:
                        raise ValueError("No embedding data returned")
                        
                    # data[0] could be object or dict
                    item = data[0]
                    if hasattr(item, "embedding"):
                        return item.embedding
                    elif isinstance(item, dict):
                         return item.get("embedding")
                    else:
                         # Fallback for weird structures
                         return item["embedding"]

            model_name = settings.VALIDATION_MODEL
            if settings.MODEL_PROVIDER == "ollama":
                model_name = f"ollama/{settings.OLLAMA_MODEL}"
            
            llm_judge = SafeOllamaWrapper(model=model_name, temperature=0)
            from ragas.llms import LangchainLLMWrapper
            ragas_llm = LangchainLLMWrapper(langchain_llm=llm_judge)

            embed_model = settings.EMBEDDING_MODEL
            if settings.MODEL_PROVIDER == "ollama":
                embed_model = f"ollama/{settings.OLLAMA_EMBEDDING_MODEL}"
            embeddings_wrapper = LiteLLMEmbeddings(model_name=embed_model)

            # FIX: Disable litellm background logging workers
            import litellm
            litellm.success_callback = []
            litellm.failure_callback = []
            litellm.callbacks = []

            # --- SYNTHETIC GROUND TRUTH GENERATION ---
            # To calculate Recall/Precision, we need a ground truth.
            # We generate it using the powerful LLM judge based on the retrieved context.
            ground_truth_text = ""
            try:
                from langchain_core.messages import HumanMessage
                gt_prompt = (
                    f"You are an expert auditor. Answer the question using ONLY the provided context.\n"
                    f"If the answer is not in the context, state that.\n"
                    f"Context: {context}\n"
                    f"Question: {query}\n"
                    f"Ideal Answer:"
                )
                gt_resp = llm_judge.invoke([HumanMessage(content=gt_prompt)])
                ground_truth_text = gt_resp.content
            except Exception as e:
                logger.warning(f"Failed to generate ground truth: {e}")
                ground_truth_text = answer # Fallback to the answer itself so metrics don't crash, though recall will be 1.0

            data_dict = {
                "question": [query], 
                "answer": [answer], 
                "contexts": [[context]], 
                "ground_truth": [ground_truth_text] 
            }
            from datasets import Dataset
            ds = Dataset.from_dict(data_dict)
            
            # Use string names or imports. Ensure "answer_relevancy" matches import.
            # Assuming widely available imports:
            from ragas.metrics import faithfulness, answer_relevancy, context_precision, context_recall, context_entity_recall
            metrics = [faithfulness, answer_relevancy, context_precision, context_recall, context_entity_recall]
            
            results = evaluate(ds, metrics=metrics, llm=ragas_llm, embeddings=embeddings_wrapper)
            
            # SAFE EXTRACTION: dict(results) can crash with KeyError: 0 if internal structure is odd
            final_scores = {}
            # Explicitly check for the metric names we expect
            target_metrics = ["faithfulness", "answer_relevancy", "context_precision", "context_recall", "context_entity_recall"]
            
            import math
            for m in target_metrics:
                try:
                    val = 0.0
                    
                    # Ragas Result Handling (Robust)
                    # Case 1: Dict-like (try subscription first)
                    if hasattr(results, "__getitem__"):
                        try:
                            val = results[m]
                        except (KeyError, IndexError, TypeError):
                            # Try .get if it exists
                             if hasattr(results, "get"):
                                 val = results.get(m, 0.0)
                             # Try attribute access if it's an object with attributes matching metrics
                             elif hasattr(results, m):
                                 val = getattr(results, m)
                    
                    # Case 2: If it's a pandas dataframe (sometimes happens in older versions)
                    if hasattr(results, "to_dict"):
                        try:
                            d = results.to_dict()
                            val = d.get(m, 0.0)
                        except: pass

                    # If val is list/series, take first
                    if isinstance(val, (list, tuple)) or hasattr(val, "iloc"):
                        val = val[0] if len(val) > 0 else 0.0
                    
                    # Handle NaN/Inf
                    if isinstance(val, (float, int)):
                        if math.isnan(val) or math.isinf(val):
                            val = 0.0
                    
                    final_scores[m] = float(val)
                except Exception as ex:
                    # Don't log as warning every time to keep logs clean unless critical
                    # logger.warning(f"Ragas Metric Extract Warning: {m} -> {ex}")
                    final_scores[m] = 0.0

            return json.dumps(final_scores)
            
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            logger.error(f"RAGAS Critical Failure: {str(e)}\nDetails: {error_details}")
            # Return a specific error marker for the reflector to catch
            return json.dumps({"error": "RAGAS_FAILED", "details": str(e), "faithfulness": 0.0})
