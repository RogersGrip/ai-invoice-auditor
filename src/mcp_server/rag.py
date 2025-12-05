from fastmcp import FastMCP
from typing import List, Dict, Any
from langchain_text_splitters import RecursiveCharacterTextSplitter
from src.database.qdrant_db import vector_store
from loguru import logger

mcp = FastMCP("RAG Knowledge Agent")

# Initialize Splitter (Standard RAG Configuration)
text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000,
    chunk_overlap=200,
    separators=["\n\n", "\n", " ", ""]
)

def logic_ingest_invoice(text: str, filename: str) -> str:
    try:
        # Create standard chunks preserving context
        chunks = text_splitter.create_documents([text])
        
        for i, chunk in enumerate(chunks):
            vector_store.add_document(
                text=chunk.page_content, 
                metadata={"filename": filename, "chunk_index": i}
            )
        return f"Successfully indexed {len(chunks)} chunks from {filename}."
    except Exception as e:
        logger.error(f"Ingestion failed: {e}")
        return f"Error: {str(e)}"

def logic_retrieve_context(query: str) -> List[Dict[str, Any]]:
    logger.info(f"RAG Retrieval for: {query}")
    return vector_store.search(query, limit=3)

@mcp.tool()
def ingest_invoice(text: str, filename: str) -> str:
    """Ingests invoice text into the vector database for future retrieval."""
    return logic_ingest_invoice(text, filename)

@mcp.tool()
def retrieve_context(query: str) -> str:
    """Retrieves relevant invoice snippets based on a semantic query."""
    results = logic_retrieve_context(query)
    context_str = "\n---\n".join([f"[Source: {r['metadata']['filename']}] {r['text']}" for r in results])
    return context_str

if __name__ == "__main__":
    mcp.run()