# MUST BE THE FIRST LINE
import warnings
# Global Silence: Mute all warnings for this test script to keep output clean
warnings.simplefilter("ignore")

import sys
import os
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.append(str(PROJECT_ROOT))

# Now import the logic (warnings triggered here will now be silenced)
from src.mcp_server.rag import logic_ingest_invoice, logic_retrieve_context

def test_rag_flow():
    print("=== Testing RAG Agent (Embeddings + Vector DB) ===")
    
    # 1. Mock Data
    sample_text = """
    INVOICE #999
    Vendor: Acme Corp
    Date: 2025-01-01
    Item: Quantum Widget
    Price: $5000.00
    Terms: Net 30
    """
    
    # 2. Test Ingestion
    print("\n[1] Ingesting Document...")
    try:
        res = logic_ingest_invoice(sample_text, "invoice_999.txt")
        print(f"Result: {res}")
    except Exception as e:
        print(f"Ingestion Failed: {e}")
        return

    # 3. Test Retrieval
    print("\n[2] Retrieving Context ('Who is the vendor?')...")
    try:
        results = logic_retrieve_context("Who is the vendor?")
        for r in results:
            # Clean print of score/text
            print(f" - Found (Score {r['score']:.2f}): {r['text'].strip()[:50]}...")
            
        if results and "Acme Corp" in results[0]['text']:
            print("\n✅ RAG Verification PASSED")
        else:
            print("\n❌ RAG Verification FAILED (Context mismatch)")
            
    except Exception as e:
        print(f"Retrieval Failed: {e}")

if __name__ == "__main__":
    test_rag_flow()