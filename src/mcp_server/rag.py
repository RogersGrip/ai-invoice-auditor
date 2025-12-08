from fastmcp import FastMCP
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_aws import ChatBedrockConverse
from langchain_core.messages import HumanMessage

from src.database.qdrant_db import vector_store
from src.core.logger import logger
from src.core.config import settings

mcp = FastMCP("RAG Knowledge Agent")

text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000,
    chunk_overlap=200,
    separators=["\n\n", "\n", " ", ""]
)

class IngestionResult(BaseModel):
    success: bool
    chunks_count: int
    message: str

@mcp.tool()
def ingest_invoice(text: str, filename: str, metadata: Dict[str, Any] = {}) -> Dict[str, Any]:
    """
    Ingests invoice text into the Vector Database (Qdrant).
    """
    try:
        chunks = text_splitter.create_documents([text])
        for i, chunk in enumerate(chunks):
            meta = {
                "filename": filename,
                "chunk_id": i,
                "total_chunks": len(chunks),
                "sender": metadata.get("sender"),
                "subject": metadata.get("subject"),
                "language": metadata.get("language")
            }
            vector_store.add_document(
                text=chunk.page_content,
                metadata=meta
            )
        
        logger.info(f"Indexed {len(chunks)} chunks for {filename}")
        return IngestionResult(
            success=True, 
            chunks_count=len(chunks), 
            message=f"Successfully indexed {len(chunks)} chunks."
        ).model_dump()
        
    except Exception as e:
        logger.error(f"Ingestion failed: {e}")
        return IngestionResult(success=False, chunks_count=0, message=str(e)).model_dump()

@mcp.tool()
def retrieve_context(query: str, limit: int = 3) -> str:
    """
    Retrieves semantic context for a given query.
    Returns a JSON string of results.
    """
    logger.info(f"RAG Retrieval for: {query}")
    results = vector_store.search(query, limit=limit)
    return str(results)

@mcp.tool()
def ask_question(question: str) -> str:
    """
    High-level tool to ask a question about the invoices using RAG.
    """
    # 1. Retrieve
    context_items = vector_store.search(question, limit=3)
    context_str = "\n---\n".join([
        f"[Source: {r['metadata'].get('filename')}] {r['text']}" 
        for r in context_items
    ])
    
    if not context_str:
        return "I couldn't find any relevant invoice data to answer that."

    # 2. Generate
    prompt = f"""
    You are a helpful Invoice Assistant.
    Answer the question based ONLY on the context below.
    
    CONTEXT:
    {context_str}
    
    QUESTION: {question}
    
    ANSWER:
    """
    
    try:
        llm = ChatBedrockConverse(
            model="cohere.command-r-plus-v1:0",
            temperature=0.0
        )
        response = llm.invoke([HumanMessage(content=prompt)])
        return response.content
    except Exception as e:
        return f"Generation Error: {e}"

if __name__ == "__main__":
    mcp.run()