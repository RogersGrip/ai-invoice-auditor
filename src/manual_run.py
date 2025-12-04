import os
import shutil
from src.agents.monitor import InvoiceMonitorAgent
from src.agents.extractor import extractor_node
from src.core.state import InvoiceState, ProcessingStatus

def run_sprint_1():
    # Setup
    monitor = InvoiceMonitorAgent()
    
    # Ensure a test file exists
    source_invoice = "Actual_invoice.pdf"
    if os.path.exists(source_invoice):
        shutil.copy(source_invoice, "data/invoices/")
        print(f"Copied {source_invoice} to data/invoices/")

    # 1. Scan
    files = monitor.scan()

    if files:
        target_file = files[0]
        
        # 2. Init State
        initial_state: InvoiceState = {
            "file_path": target_file,
            "file_name": os.path.basename(target_file),
            "raw_text": None,
            "extracted_data": {},
            "standardized_invoice": None,
            "validation_report": None,
            "current_step": "monitor",
            "status": ProcessingStatus.PENDING,
            "error": None
        }
        
        # 3. Extract
        final_state = extractor_node(initial_state)
        
        print("\n" + "="*50)
        print(f"OUTPUT FOR: {final_state['file_name']}")
        print("="*50)
        print(f"Status: {final_state['status']}")
        if final_state['raw_text']:
            print(f"Text Preview:\n{final_state['raw_text'][:500]}...")
    else:
        print("No invoices found to process.")

if __name__ == "__main__":
    run_sprint_1()