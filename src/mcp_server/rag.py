from fastmcp import FastMCP
from typing import Dict, Any
from src.rag_engine.agents import rag_system
from loguru import logger

mcp = FastMCP("Advanced RAG Knowledge Agent")

@mcp.tool()
def ingest_invoice(text: str, filename: str, metadata: Dict[str, Any] = {}) -> str:
    """
    Ingests invoice text into the vector knowledge base.
    """
    # Ensure metadata has filename
    metadata["filename"] = filename
    try:
        return rag_system.add_knowledge(text, metadata)
    except Exception as e:
        logger.error(f"Ingest failed: {e}")
        return f"Error: {e}"

@mcp.tool()
def ask_question(question: str) -> str:
    """
    Answers a question about the invoices using RAG with Reranking and Reflection.
    Returns the answer text.
    """
    try:
        result = rag_system.ask(question)
        
        # Format the output to include the answer + reflection score
        answer = result["answer"]
        score = result["evaluation"]["overall_score"]
        passing = result["evaluation"]["is_passing"]
        
        footer = f"\n\n(Confidence: {score:.2f} | Verified: {passing})"
        return answer + footer
    except Exception as e:
        logger.error(f"RAG Query failed: {e}")
        return f"System Error: {e}"

@mcp.tool()
def get_retrieval_debug(question: str) -> str:
    """
    Returns detailed debugging info about what chunks were retrieved and how they were ranked.
    """
    result = rag_system.ask(question)
    return str(result)

if __name__ == "__main__":
    mcp.run()