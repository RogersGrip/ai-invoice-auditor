import os
import shutil
from src.agents.monitor import InvoiceMonitorAgent
from src.agents.extractor import extractor_node
from src.core.state import InvoiceState, ProcessingStatus

def run_sprint_1():
    # Setup
    monitor = InvoiceMonitorAgent()
    
    source_invoice = "INV_EN_005_scan.pdf"
    if os.path.exists(source_invoice):
        shutil.copy(source_invoice, "data/invoices/")

    # 1. Scan for files
    files = monitor.scan()

    if files:
        job = files[0]
        file_path = job["file_path"]
        metadata = job["metadata"]
        
        initial_state: InvoiceState = {
            "file_path": file_path,
            "file_name": os.path.basename(file_path),
            "metadata": metadata,
            "raw_text": None,
            "extracted_data": {},
            "standardized_invoice": None,
            "validation_report": None,
            "current_step": "monitor",
            "status": ProcessingStatus.PENDING,
            "error": None
        }
        
        # 2. Extract
        final_state = extractor_node(initial_state)
        
        print("\n" + "="*50)
        print(f"OUTPUT FOR: {final_state['file_name']}")
        print("="*50)
        print(f"Status: {final_state['status']}")
        
        if final_state['raw_text']:
            print(f"Text Preview:\n{final_state['raw_text'][:500]}...")
        else:
            print("No text extracted (check logs for errors).")
            
    else:
        print("No invoices found to process.")

if __name__ == "__main__":
    run_sprint_1()