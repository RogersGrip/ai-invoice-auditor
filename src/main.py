import time
import os
import sys
import warnings

# Suppress Pydantic deprecation warnings from libraries
warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")
warnings.filterwarnings("ignore", category=DeprecationWarning, module="pydantic")
# Debug prints
print("DEBUG: Handling imports...")
try:
    from loguru import logger
    print("DEBUG: Loguru imported")
    from src.agents.monitor import InvoiceMonitorAgent
    print("DEBUG: Monitor imported")
    from src.workflows.graph import create_invoice_graph
    print("DEBUG: Graph imported")
    from src.core.state import InvoiceState, ProcessingStatus
    print("DEBUG: State imported")
    from src.core.logger import logger as system_logger
    print("DEBUG: System logger imported")
except ImportError as e:
    print(f"DEBUG: Import Error: {e}")
    sys.exit(1)
except Exception as e:
    print(f"DEBUG: Critical Import Error: {e}")
    sys.exit(1)

def main():
    print("DEBUG: Entering main()")
    system_logger.info(">>> AI Invoice Auditor Started <<<")
    
    # 1. Initialize Components
    print("DEBUG: Initializing Monitor...")
    
    # Clean up old status
    if os.path.exists("data/status.json"):
        os.remove("data/status.json")
        
    try:
        monitor = InvoiceMonitorAgent()
        print("DEBUG: Monitor initialized")
    except Exception as e:
        print(f"DEBUG: Monitor Init Failed: {e}")
        return

    # Explicitly Initialize Vector DB (since we removed auto-init)
    try:
        from src.database.qdrant_db import vector_store
        vector_store._init_db()
        print("DEBUG: Vector DB initialized")
    except Exception as e:
        print(f"DEBUG: Vector DB Init Warning: {e}")

    print("DEBUG: Creating Graph...")
    try:
        app = create_invoice_graph()
        print("DEBUG: Graph created")
    except Exception as e:
        print(f"DEBUG: Graph Creation Failed: {e}")
        import traceback
        traceback.print_exc()
        return
    
    logger.info(f"Monitoring Inbox: {monitor.watch_dir}")
    logger.info(f"Archive Folder:   {monitor.processed_dir}")
    
    try:
        while True:
            # 2. Poll for files
            # print("DEBUG: Scanning...")
            pending_jobs = monitor.scan()
            
            if not pending_jobs:
                time.sleep(2)
                continue
                
            logger.info(f"Found {len(pending_jobs)} pending invoices. Processing...")

            for job in pending_jobs:
                file_path = job['file_path']
                
                if not os.path.exists(file_path):
                    continue

                # 2a. Prepare Unique Filename (Timestamped)
                from datetime import datetime
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                original_name = os.path.basename(file_path)
                processed_name = f"{timestamp}_{original_name}"
                
                logger.info(f"🚀 Starting Workflow for: {original_name} (ID: {processed_name})")
                
                # 3. Initialize State (Pydantic Model)
                initial_state = InvoiceState(
                    file_path=file_path,
                    file_name=processed_name, # Use the unique ID here so reports match archive
                    metadata=job['metadata'],
                    current_step="start",
                    status=ProcessingStatus.PENDING
                )
                
                # 4. Invoke Graph
                try:
                    # LangGraph with Pydantic state returns the updated state dict/model
                    final_state_output = app.invoke(initial_state)
                    
                    if isinstance(final_state_output, dict):
                         final_status = final_state_output.get("status")
                    else:
                         final_status = final_state_output.status
                          
                    logger.info(f"🏁 Workflow Finished. Status: {final_status}")
                     
                    # Force Update UI to Completed
                    from src.core.state import update_progress
                    update_progress(processed_name, "Completed", f"Done. Status: {final_status}")
                     
                except Exception as e:
                    logger.error(f"Workflow Critical Fail: {e}")
                
                # 5. Archive (Pass the same processed_name)
                monitor.archive(file_path, dest_name=processed_name)
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