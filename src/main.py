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
    
    logger.info("System Watchdog Active. Waiting for invoices in 'data/invoices'...")
    
    try:
        while True:
            # 2. Poll for files
            new_jobs = monitor.scan()
            
            for job in new_jobs:
                logger.info(f"🚀 Starting Workflow for: {job['file_path']}")
                
                # 3. Initialize State
                initial_state: InvoiceState = {
                    "file_path": job['file_path'],
                    "file_name": os.path.basename(job['file_path']),
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
                # invoke() blocks until the graph reaches END
                final_state = app.invoke(initial_state)
                
                logger.info(f"🏁 Workflow Finished. Status: {final_state['status']}")
                logger.info("=" * 40)

            # Polling interval to prevent CPU spiking
            time.sleep(2)
            
    except KeyboardInterrupt:
        logger.info("Shutting down gracefully...")
        sys.exit(0)
    except Exception as e:
        logger.critical(f"Fatal System Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()