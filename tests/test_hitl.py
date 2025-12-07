import sys
import os
import uuid
from typing import Dict, Any

# Add project root to path
sys.path.append(os.getcwd())

from src.workflows.graph import create_invoice_graph
from src.core.state import InvoiceState, ProcessingStatus

def test_hitl_flow():
    print(">>> Initializing Graph with Checkpointer...")
    app = create_invoice_graph()
    
    thread_id = f"test_hitl_{uuid.uuid4()}"
    config = {"configurable": {"thread_id": thread_id}}
    
    print(f">>> Starting Workflow (Thread: {thread_id})...")
    
    initial_state = InvoiceState(
        file_path="tests/mock_invoice.pdf",
        file_name="mock_invoice.pdf",
        metadata={},
        current_step="start",
        status=ProcessingStatus.PENDING
    )
    
    # 1. Run Initial - Should Stop Before Reporting
    # Mocking agents is hard here without patching, so we assume they run or fail gracefully.
    # To ensure it reaches reporting, we simulate a state update via minimal run?
    # Actually, real agents will try to run. 
    # For this test, we must ensure 'extraction' -> ... -> 'reporting' path is taken.
    
    # Let's hope the mock extractors/agents handle missing files gracefully or we create a dummy file.
    with open("tests/mock_invoice.pdf", "w") as f:
        f.write("DUMMY INVOICE CONTENT")
        
    try:
        # We expect it to run until 'reporting' node and STOP.
        # extraction -> translation -> validation -> business_validation -> [INTERRUPT] -> reporting
        
        # NOTE: If we don't have real AI keys, this might fail earlier.
        # But we updated config to use Ollama mock maybe?
        
        print(">>> Invoking Graph (Phase 1)...")
        # Recursion limit might be needed?
        result = app.invoke(initial_state, config=config)
        
        # If it finished, that's bad (unless it skipped reporting?)
        print(f"!!! Unexpected Finish: {result['status']}")
        
    except Exception as e:
        pass # It might not raise exception on interrupt, invoke just returns.
        
    # Check Snapshot
    print(">>> Checking State Snapshot...")
    snapshot = app.get_state(config)
    print(f"Next Node: {snapshot.next}")
    
    if "reporting" in snapshot.next:
        print(">>> ✅ Verified: Workflow Interrupted before 'reporting'")
    else:
        print(f"!!! Failed: Next node is {snapshot.next}, expected 'reporting'")
        # If it failed earlier, we can't verify HITL.
        # Assuming for now execution reaches here.
        return False
        
    # 2. Resume
    print(">>> Resuming Workflow (Phase 2)...")
    # To resume, we invoke with Command or None? 
    # Just invoke(None, config) resumes with current state.
    
    final_result = app.invoke(None, config=config)
    
    print(f"Final Status: {final_result['status']}")
    
    if final_result['status'] == ProcessingStatus.COMPLETED:
        print(">>> ✅ Verified: Workflow Resumed and Completed")
        return True
    else:
        print("!!! Failed: Workflow did not complete after resume.")
        return False

if __name__ == "__main__":
    if test_hitl_flow():
        sys.exit(0)
    else:
        sys.exit(1)
