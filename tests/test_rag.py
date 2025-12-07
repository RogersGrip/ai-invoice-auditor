import sys
import os
from loguru import logger

# Add project root to sys.path
sys.path.append(os.getcwd())

from src.core.config import settings
from src.workflows.rag_graph import create_rag_graph

def test_rag_flow():
    logger.info(">>> Testing RAG Workflow <<<")
    
    # Ensure provider is ollama
    settings.MODEL_PROVIDER = "ollama"
    settings.OLLAMA_MODEL = "llama3:8b" # Adjust if user has different tag
    
    query = "What is the invoice number and total amount?"
    
    logger.info(f"Query: {query}")
    
    try:
        app = create_rag_graph()
        response = app.invoke({"query": query})
        
        logger.info("--- Response ---")
        logger.info(f"Answer: {response.get('answer')}")
        logger.info(f"Context Length: {len(response.get('context', ''))}")
        logger.info(f"Evaluation: {response.get('evaluation')}")
        
        if response.get("answer"):
            logger.success("✔ RAG Flow Test PASSED")
        else:
            logger.error("✘ RAG Flow Test FAILED (No Answer)")
            
    except Exception as e:
        logger.error(f"RAG Test Crash: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_rag_flow()
