from fastmcp import FastMCP
from typing import List, Dict, Any
from langchain_text_splitters import RecursiveCharacterTextSplitter
from src.database.qdrant_db import vector_store
from litellm import completion
import os
from loguru import logger

mcp = FastMCP("RAG Knowledge Agent")

text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000,
    chunk_overlap=200,
    separators=["\n\n", "\n", " ", ""]
)

def logic_ingest_invoice(text: str, filename: str, metadata: Dict[str, Any]) -> str:
    try:
        chunks = text_splitter.create_documents([text])
        for i, chunk in enumerate(chunks):
            # Enriched Metadata
            meta = {
                "filename": filename,
                "chunk_index": i,
                "sender": metadata.get("sender"),
                "subject": metadata.get("subject"),
                "language": metadata.get("language")
            }
            vector_store.add_document(
                text=chunk.page_content,
                metadata=meta
            )
        return f"Successfully indexed {len(chunks)} chunks from {filename}."
    except Exception as e:
        logger.error(f"Ingestion failed: {e}")
        return f"Error: {str(e)}"

def logic_retrieve_context(query: str) -> List[Dict[str, Any]]:
    logger.info(f"RAG Retrieval for: {query}")
    return vector_store.search(query, limit=3)

def logic_generate_answer(query: str) -> str:
    context_items = logic_retrieve_context(query)
    context_str = "\n---\n".join([
        f"[Source: {r['metadata'].get('filename')}] {r['text']}" 
        for r in context_items
    ])
    
    prompt = f"""
    You are a helpful Invoice Assistant. Answer the question based ONLY on the context below.
    
    CONTEXT:
    {context_str}
    
    QUESTION: {query}
    
    ANSWER:
    """
    
    try:
        response = completion(
            model=os.getenv("REPORTING_MODEL", "bedrock/cohere.command-r-plus-v1:0"),
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Generation Error: {e}"

@mcp.tool()
def ingest_invoice(text: str, filename: str, metadata: Dict[str, Any] = {}) -> str:
    return logic_ingest_invoice(text, filename, metadata)

@mcp.tool()
def retrieve_context(query: str) -> str:
    results = logic_retrieve_context(query)
    return str(results)

@mcp.tool()
def ask_question(question: str) -> str:
    return logic_generate_answer(question)

if __name__ == "__main__":
    mcp.run()