import json
import logging
from typing import Dict, Any, Optional
from fastmcp import FastMCP, Context
from pydantic import BaseModel
from langchain_text_splitters import RecursiveCharacterTextSplitter
from src.database.qdrant_db import vector_store
from src.core.logger import logger

# Initialize FastMCP Server
mcp = FastMCP("RAG Knowledge Agent")

# Text Splitter Configuration
text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000, 
    chunk_overlap=200,
    separators=["\n\n", "\n", " ", ""]
)

class IngestionResult(BaseModel):
    success: bool
    chunks_count: int
    message: str

def logic_ingest_invoice(
    text: str, 
    filename: str, 
    metadata: Dict[str, Any] = None, 
    approval_context: Optional[str] = None
) -> str:
    """
    Core logic to ingest invoice text into the vector database.
    This function is callable directly by the Python workflow.
    """
    # Handle mutable default argument
    if metadata is None:
        metadata = {}

    try:
        # Prepend approval context if present
        final_text = text
        if approval_context:
            final_text = f"[[HUMAN_APPROVAL_NOTE: {approval_context}]]\n\n{text}"
            
        chunks = text_splitter.create_documents([final_text])
        
        for i, chunk in enumerate(chunks):
            meta = {
                "filename": filename,
                "chunk_id": i,
                "total_chunks": len(chunks),
                "sender": metadata.get("sender", "Unknown"),
                "subject": metadata.get("subject", "Unknown"),
                "has_approval": bool(approval_context)
            }
            vector_store.add_document(text=chunk.page_content, metadata=meta)
        
        logger.info(f"Indexed {len(chunks)} chunks for {filename} (Approved: {bool(approval_context)})")
        
        return json.dumps(IngestionResult(
            success=True, 
            chunks_count=len(chunks), 
            message=f"Successfully indexed {len(chunks)} chunks."
        ).model_dump())

    except Exception as e:
        logger.error(f"Ingestion failed: {e}")
        return json.dumps(IngestionResult(
            success=False, 
            chunks_count=0, 
            message=str(e)
        ).model_dump())

@mcp.tool()
def ingest_invoice(
    text: str, 
    filename: str, 
    metadata: Dict[str, Any] = None, 
    approval_context: Optional[str] = None
) -> str:
    """
    Ingests invoice text into the vector database.
    MCP Tool wrapper around the core logic.
    """
    return logic_ingest_invoice(text, filename, metadata, approval_context)

@mcp.tool()
async def retrieve_context(query: str, ctx: Context) -> str:
    """
    Retrieves semantic context from the vector database.
    Uses MCP Sampling to handle no-result scenarios.
    """
    logger.info(f"RAG Retrieval for: {query}")
    
    try:
        results = vector_store.search(query, limit=5)
        
        if not results:
            ctx.info(f"No results found for query: {query}")
            
            try:
                messages = [{
                    "role": "user",
                    "content": {
                        "type": "text",
                        "text": f"The user searched for '{query}' in the invoice database, but no records were found. Please generate a polite, concise message stating that no relevant invoice data was found."
                    }
                }]
                
                sampling_result = await ctx.session.send_sampling_request(
                    messages=messages,
                    max_tokens=100
                )
                
                if sampling_result and sampling_result.content:
                    return json.dumps({
                        "results": [],
                        "message": sampling_result.content.text,
                        "sampled": True
                    })
            except Exception as sample_err:
                logger.warning(f"Sampling request failed: {sample_err}")
                return json.dumps({"results": [], "message": "No matching invoice records found."})

        return json.dumps({"results": results, "count": len(results)}, default=str)

    except Exception as e:
        logger.error(f"Retrieval Error: {e}")
        return json.dumps({"error": str(e)})

if __name__ == "__main__":
    mcp.run()