from typing import Dict, Any, List, Optional
import json
from src.core.protocol import MCPTool, MCPClient
from src.tools.ocr_engine import OCREngine
from src.database.qdrant_db import vector_store
from src.core.config import settings
from src.core.logger import logger
from langchain_text_splitters import RecursiveCharacterTextSplitter
from litellm import completion
from langfuse import observe

# Dummy imports for wrappers - enabling dependency injection
# from src.agents.translator import Translator (Need to decouple)
# from src.mcp_server.erp import mcp as erp_mcp

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

class BusinessValidationTool(BaseTool):
    name: str = "Business Validation Tool"
    description: str = "Cross-verifies extracted invoice data against enterprise systems."
    input_schema: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "line_items": {"type": "array"}
        }
    }

class InsightReporterTool(BaseTool):
    name: str = "Insight Reporter Tool"
    description: str = "Generates comprehensive reports highlighting data gaps, validation results, and recommendations."
    input_schema: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "report_data": {"type": "object"},
            "format": {"type": "string", "enum": ["PDF", "JSON"]}
        }
    }

# --- RAG Tools ---

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
        
        # Split into system/user if needed, or just send as user message.
        # The prompt file was written as a single block. Let's send it as user for simplicity 
        # or split it if we want strict system/user separation. 
        # Given the previous code had split, let's just use the whole thing as instructions.
        
        model = settings.REPORTING_MODEL
        if settings.MODEL_PROVIDER == "ollama":
            model = f"ollama/{settings.OLLAMA_MODEL}"
            
        response = completion(
            model=model,
            messages=[
                {"role": "user", "content": full_content}
            ]
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
            from src.core.config import settings
            import logging
            
            # --- 1a. Safe Ollama Wrapper (Fix for n=1 warning & Parsing) ---
            # --- 1a. Safe Ollama Wrapper (Fix for n=1 warning & Parsing) ---
            class SafeOllamaWrapper(ChatLiteLLM):
                def _generate(
                    self,
                    messages: List[BaseMessage],
                    stop: Optional[List[str]] = None,
                    run_manager: Any = None,
                    **kwargs: Any,
                ) -> ChatResult:
                    n = kwargs.get("n", 1)
                    if n > 1:
                        logger.debug(f"SafeOllamaWrapper (Sync): Emulating n={n} generations for Ragas")

                    generations_list = []
                    for i in range(max(1, n)):
                        kwargs["n"] = 1
                        kwargs["response_format"] = {"type": "json_object"}
                        result = super()._generate(messages, stop, run_manager, **kwargs)
                        self._clean_generations(result)
                        generations_list.extend(result.generations)

                    return ChatResult(generations=generations_list)

                async def _agenerate(
                    self,
                    messages: List[BaseMessage],
                    stop: Optional[List[str]] = None,
                    run_manager: Any = None,
                    **kwargs: Any,
                ) -> ChatResult:
                    n = kwargs.get("n", 1)
                    if n > 1:
                        logger.debug(f"SafeOllamaWrapper (Async): Emulating n={n} generations for Ragas")

                    generations_list = []
                    for i in range(max(1, n)):
                        kwargs["n"] = 1
                        # FORCE JSON MODE for Ollama
                        kwargs["response_format"] = {"type": "json_object"}
                        
                        # Await parent async call
                        result = await super()._agenerate(messages, stop, run_manager, **kwargs)
                        self._clean_generations(result)
                        generations_list.extend(result.generations)

                    return ChatResult(generations=generations_list)

                def _clean_generations(self, result: ChatResult):
                    for gen in result.generations:
                        clean_content = gen.text.strip()
                        if clean_content.startswith("```json"):
                            clean_content = clean_content[7:]
                        if clean_content.startswith("```"):
                            clean_content = clean_content[3:]
                        if clean_content.endswith("```"):
                            clean_content = clean_content[:-3]
                        clean_content = clean_content.strip()
                        
                        # Debug Log
                        if len(clean_content) < 500:
                            logger.debug(f"Ollama Cleaned: {clean_content}")

                        gen.text = clean_content
                        if hasattr(gen, 'message'):
                            gen.message.content = clean_content

            # --- 1b. Custom LiteLLM Embeddings Wrapper ---
            class LiteLLMEmbeddings(Embeddings):
                def __init__(self, model_name: str):
                    self.model = model_name

                def embed_documents(self, texts: List[str]) -> List[List[float]]:
                    return [self.embed_query(txt) for txt in texts]

                def embed_query(self, text: str) -> List[float]:
                    try:
                        response = litellm_embedding(
                            model=self.model,
                            input=[text]
                        )
                        data_item = response.data[0]
                        if isinstance(data_item, dict):
                            return data_item['embedding']
                        elif hasattr(data_item, 'embedding'):
                            return data_item.embedding
                        return data_item[0]
                    except Exception as e:
                        logger.error(f"Embedding failed: {e}")
                        raise e

            # --- 2. Configure LLM Judge ---
            model_name = settings.VALIDATION_MODEL
            if settings.MODEL_PROVIDER == "ollama":
                model_name = f"ollama/{settings.OLLAMA_MODEL}"
                logging.info(f"Using Ollama for RAGAS Eval: {model_name}")
            
            # Use the Safe Wrapper
            llm_judge = SafeOllamaWrapper(
                model=model_name, 
                temperature=0,
                api_key="ollama" if settings.MODEL_PROVIDER == "ollama" else None,
                base_url=settings.OLLAMA_BASE_URL if settings.MODEL_PROVIDER == "ollama" else None
            )

            # --- 3. Configure Embeddings ---
            embed_model_name = settings.EMBEDDING_MODEL
            if settings.MODEL_PROVIDER == "ollama":
                embed_model_name = f"ollama/{settings.OLLAMA_EMBEDDING_MODEL}"
            
            embeddings_wrapper = LiteLLMEmbeddings(model_name=embed_model_name)

            # --- 4. Generate Synthetic Ground Truth ---
            gt_prompt = (
                f"Question: {query}\n"
                f"Context: {context}\n"
                "Task: Generate a precise, comprehensive, and factual answer to the question "
                "based SOLELY on the provided context. Do not add outside information."
            )
            
            from langchain_core.messages import HumanMessage
            gt_response = llm_judge.invoke([HumanMessage(content=gt_prompt)])
            synthetic_ground_truth = gt_response.content
            
            # --- 5. Prepare Data ---
            data_dict = {
                "question": [query],
                "answer": [answer],
                "contexts": [[context]],
                "ground_truth": [synthetic_ground_truth]
            }
            ds = Dataset.from_dict(data_dict)

            # --- 6. Evaluate ---
            metrics = [
                faithfulness, 
                answer_relevancy, 
                context_precision, 
                context_recall, 
                context_entity_recall
            ]
            
            results = evaluate(
                ds,
                metrics=metrics,
                llm=llm_judge,
                embeddings=embeddings_wrapper,
                raise_exceptions=False
            )
            
            # 4a. Format Output
            # Ragas 0.4.0 Result object implements __getitem__ but not get()
            # It also likely has a to_pandas() method or behaves as a dict.
            # We convert to a standard dict to be safe.
            try:
                scores = dict(results)
            except Exception:
                # Fallback if dict() casting fails
                scores = {}
                for m in ["faithfulness", "answer_relevancy", "context_precision", "context_recall", "context_entity_recall"]:
                     if m in results:
                         scores[m] = results[m]

            def safe_get(key):
                val = scores.get(key, 0.0)
                # Check for NaN (math.isnan checks floats, but val could be string or None)
                try:
                    import math
                    if isinstance(val, float) and math.isnan(val):
                        return 0.0
                except:
                    pass
                return val

            final_metrics = {
                "faithfulness": safe_get("faithfulness"),
                "answer_relevance": safe_get("answer_relevancy"),
                "context_precision": safe_get("context_precision"),
                "context_recall": safe_get("context_recall"),
                "context_entity_recall": safe_get("context_entity_recall"),
                "reasoning": f"Evaluated using {model_name} (Ollama)"
            }
            
            return json.dumps(final_metrics)

        except (ImportError, Exception) as e:
            logger.warning(f"RAGAS evaluation failed ({e}). Falling back to LLM Prompt.")
            
            # Fallback
            try:
                from src.core.prompts import load_prompt
                raw_prompt = load_prompt("rag_evaluator.txt")
                formatted_prompt = raw_prompt.format(
                    context_snippet=context[:2000],
                    query=query,
                    answer=answer
                )
                
                model = settings.VALIDATION_MODEL
                if settings.MODEL_PROVIDER == "ollama":
                    model = f"ollama/{settings.OLLAMA_MODEL}"

                response = completion(
                    model=model,
                    messages=[{"role": "user", "content": formatted_prompt}],
                    format="json"
                )
                content = response.choices[0].message.content
                if "```" in content:
                    content = content.replace("```json", "").replace("```", "").strip()
                return content
            except Exception as fallback_error:
                return json.dumps({
                    "error": f"Both RAGAS and Fallback failed. Ragas: {e}",
                    "faithfulness": 0
                })
