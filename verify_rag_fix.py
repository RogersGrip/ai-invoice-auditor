import time
import sys
from unittest.mock import MagicMock

# Mock dependencies to avoid environment issues
sys.modules["pytesseract"] = MagicMock()
sys.modules["PIL"] = MagicMock()
sys.modules["PIL.Image"] = MagicMock()

from src.workflows.graph import create_invoice_graph
from src.workflows.rag_graph import create_rag_graph

thread_id = "INV_RAG_TEST"
config = {"configurable": {"thread_id": thread_id}}

print(f"Waiting for {thread_id} to reach PAUSE state...")
app = create_invoice_graph()

# Poll for state
max_retries = 20
for i in range(max_retries):
    try:
        state = app.get_state(config)
        if state.next:
            print(f"Workflow paused at: {state.next}")
            if "ingestion" in state.next or "reporting" in state.next: # "ingestion" is target
                 print("Resuming workflow...")
                 app.invoke(None, config=config)
                 print("Workflow Resumed and Completed (Ingestion should be done).")
                 break
    except Exception as e:
        pass
    time.sleep(2)
else:
    print("Timeout waiting for pause.")
    sys.exit(1)

# Now Verify RAG
print("\n--- Verifying RAG Retrieval ---")
rag = create_rag_graph()
query = "What is the total amount of the invoice?"
print(f"Query: {query}")

response = rag.invoke({"query": query})
print(f"Answer: {response.get('answer')}")

# Check context for structured data
context = response.get('context', '')
if "[STRUCTURED DATA]" in context:
    print("SUCCESS: Structured Data found in RAG Context!")
else:
    print("FAILURE: structured data NOT found in context.")
    print(f"Context Snippet: {context[:200]}...")
