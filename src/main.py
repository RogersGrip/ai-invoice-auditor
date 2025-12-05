import time
import os
import sys
from loguru import logger
from src.agents.monitor import InvoiceMonitorAgent
from src.workflows.graph import create_invoice_graph
from src.core.state import InvoiceState, ProcessingStatus
from src.core.logger import get_logger

# Initialize Logger
logger = get_logger()

def main():
    logger.info(">>> AI Invoice Auditor Started <<<")
    
    # 1. Initialize Components
    monitor = InvoiceMonitorAgent()
    app = create_invoice_graph()
    
    logger.info(f"Monitoring Inbox: {monitor.watch_dir}")
    logger.info(f"Archive Folder:   {monitor.processed_dir}")
    
    try:
        while True:
            # 2. Poll for files (Returns sorted list of current inbox)
            # Since we move files after processing, this list will naturally empty out.
            pending_jobs = monitor.scan()
            
            if not pending_jobs:
                # No files? Sleep and wait.
                time.sleep(2)
                continue
                
            logger.info(f"Found {len(pending_jobs)} pending invoices. Processing...")

            for job in pending_jobs:
                file_path = job['file_path']
                
                # Double check file still exists (race condition check)
                if not os.path.exists(file_path):
                    continue

                logger.info(f"🚀 Starting Workflow for: {os.path.basename(file_path)}")
                
                # 3. Initialize State
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
                
                # 4. Invoke Graph
                try:
                    final_state = app.invoke(initial_state)
                    logger.info(f"🏁 Workflow Finished. Status: {final_state['status']}")
                except Exception as e:
                    logger.error(f"Workflow Critical Fail: {e}")
                
                # 5. Archive the File (Move to Processed)
                # We archive regardless of success/failure to prevent blocking the queue.
                # Failed files will be in 'processed' with logs indicating the error.
                monitor.archive(file_path)
                
                logger.info("-" * 40)

            # Short pause after clearing a batch
            time.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("Shutting down gracefully...")
        sys.exit(0)
    except Exception as e:
        logger.critical(f"Fatal System Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()