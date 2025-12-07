import time
import os
import sys
from loguru import logger
from src.agents.monitor import InvoiceMonitorAgent
from src.workflows.graph import create_invoice_graph
from src.core.state import InvoiceState, ProcessingStatus
from src.core.logger import get_logger
from src.core.utils import visualize_graph # <--- NEW IMPORT

logger = get_logger()

def main():
    logger.info(">>> AI Invoice Auditor Started <<<")
    
    # Initialize Graph & Visualize
    app = create_invoice_graph()
    visualize_graph(app) # <--- Generate PNG on startup

    monitor = InvoiceMonitorAgent()
    logger.info(f"Monitoring Inbox: {monitor.watch_dir}")
    logger.info(f"Archive Folder:   {monitor.processed_dir}")

    try:
        while True:
            pending_jobs = monitor.scan()
            if not pending_jobs:
                time.sleep(2)
                continue
            
            logger.info(f"Found {len(pending_jobs)} pending invoices. Processing...")
            
            for job in pending_jobs:
                file_path = job['file_path']
                if not os.path.exists(file_path): 
                    continue
                thread_id = os.path.splitext(os.path.basename(file_path))[0]
                config = {"configurable": {"thread_id": thread_id}}
                
                # Check existing state to handle Resume/Archival from external interactions (App)
                try:
                    current_snap = app.get_state(config)
                    if current_snap.values:
                        current_status = current_snap.values.get("status")
                        
                        # Case 1: Already Completed (e.g. Resumed by App)
                        if current_status == ProcessingStatus.COMPLETED or current_status == "COMPLETED":
                            logger.info(f"✅ Found Completed Workflow for {thread_id}. Archiving...")
                            monitor.archive(file_path)
                            continue
                            
                        # Case 2: Paused (Waiting for HITL)
                        if current_snap.next:
                            logger.info(f"⏳ Workflow for {thread_id} is PAUSED at {current_snap.next}. Waiting for App approval...")
                            continue
                except Exception as check_e:
                    logger.warning(f"State check failed (assuming new): {check_e}")

                initial_state: InvoiceState = {
                    "file_path": file_path,
                    "file_name": os.path.basename(file_path),
                    "metadata": job['metadata'],
                    "raw_text": None,
                    "extracted_data": {},
                    "standardized_invoice": None,
                    "validation_report": None,
                    "current_step": "start",
                    "status": ProcessingStatus.PENDING,
                    "error": None
                }
                
                try:
                    # Use invoke with config to persist state
                    # invoke() returns the final state of THIS execution step.
                    final_state = app.invoke(initial_state, config=config)
                    logger.info(f"🏁 Workflow Step Finished. Status: {final_state.get('status')}")
                    
                    # Re-check state to see if valid pause or really finished
                    final_snap = app.get_state(config)
                    
                    if final_snap.next:
                         logger.info(f"⏸️ Workflow Paused at: {final_snap.next}")
                         # Do NOT archive yet. Wait for human approval.
                         continue
                    
                    # If we got here and no next, likely finished. 
                    if final_state.get("status") == ProcessingStatus.COMPLETED or final_state.get("status") == "COMPLETED":
                        monitor.archive(file_path)
                        
                except Exception as e:
                    logger.error(f"Workflow Exception: {e}")
                    # If it's just an interrupt, we presumably moved on. But 'invoke' behavior varies.
                    # Assuming standard behavior: returns state.
                
                logger.info("-" * 40)
            
            time.sleep(1)

    except KeyboardInterrupt:
        logger.info("Shutting down gracefully...")
        sys.exit(0)
    except Exception as e:
        logger.critical(f"Fatal System Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()