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
        system_prompt = """You are an expert AI Invoice Auditor Assistant.
        Answer the user's question using ONLY the provided context.
        If the answer is not in the context, say "I don't have enough information in the provided documents."
        Include citations to filenames if possible.
        """
        
        user_prompt = f"""
        CONTEXT:
        {context}
        
        QUESTION: {query}
        
        ANSWER:
        """
        
        model = settings.REPORTING_MODEL
        if settings.MODEL_PROVIDER == "ollama":
            model = f"ollama/{settings.OLLAMA_MODEL}"
            
        response = completion(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        )
        return response.choices[0].message.content

class RAGEvaluatorTool(BaseTool):
    name: str = "RAG-Evaluator Tool"
    description: str = "Assesses generated responses using RAG metrics."
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
        prompt = f"""
        You are an expert RAG Evaluator. Rate the following interaction.
        
        CONTEXT: {context[:2000]}
        
        USER QUESTION: {query}
        AI ANSWER: {answer}
        
        Calculate 5 metrics: Context Precision, Context Recall, Faithfulness, Answer Relevance, Context Entity Recall.
        
        Return ONLY a JSON object with keys: 
        "context_precision", "context_recall", "faithfulness", "answer_relevance", "context_entity_recall", "reasoning".
        """
        
        model = settings.VALIDATION_MODEL
        if settings.MODEL_PROVIDER == "ollama":
            model = f"ollama/{settings.OLLAMA_MODEL}"

        response = completion(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            format="json"
        )
        
        content = response.choices[0].message.content
        if "```" in content:
            content = content.replace("```json", "").replace("```", "").strip()
            
        return content
