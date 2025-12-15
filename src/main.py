import time
import os
import sys
import warnings
from dotenv import load_dotenv
import litellm

# Load Env for Libraries (Langfuse, etc.)
load_dotenv()

# Configure LiteLLM to use Langfuse (OTel for v3 SDK)
if os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY"):
    litellm.callbacks = ["langfuse_otel"]
else:
    print("WARNING: Langfuse keys missing. Observability disabled.")

# Suppress Pydantic deprecation warnings from libraries
warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")
warnings.filterwarnings("ignore", category=DeprecationWarning, module="pydantic")
# Debug prints
print("DEBUG: Handling imports...")
try:
    from loguru import logger
    print("DEBUG: Loguru imported")
    from src.adk_agents.monitor_agent import InvoiceMonitorAgent
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
        # Track active threads for files in the inbox to prevent re-processing interrupted jobs
        active_threads: Dict[str, str] = {}
        
        while True:
            # 2. Poll for files
            # print("DEBUG: Scanning...")
            pending_jobs = monitor.scan()
            
            if not pending_jobs:
                time.sleep(2)
                continue
                
            # logger.info(f"Found {len(pending_jobs)} pending invoices. Processing...")

            for job in pending_jobs:
                file_path = job['file_path']
                
                if not os.path.exists(file_path):
                    if file_path in active_threads:
                        del active_threads[file_path]
                    continue

                # Check if we already have an active thread for this file
                if file_path in active_threads:
                    existing_thread_id = active_threads[file_path]
                    config = {"configurable": {"thread_id": existing_thread_id}}
                    try:
                        current_snapshot = app.get_state(config)
                        if current_snapshot.next:
                            # It's still interrupted/paused
                            # logger.debug(f"Skipping {os.path.basename(file_path)} (Thread: {existing_thread_id}) - Waiting for Approval")
                            continue
                        else:
                            # It finished? But file is still here?
                            # Maybe we should archive it if it's done?
                            # For HITL, if resumed and finished, it should have been archived.
                            # If it's here and finished, maybe something went wrong.
                            pass
                    except Exception:
                        # Thread state lost?
                        del active_threads[file_path]

                # 2a. Prepare Unique Filename (Timestamped)
                from datetime import datetime
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                original_name = os.path.basename(file_path)
                processed_name = f"{timestamp}_{original_name}"
                
                # Register new thread
                active_threads[file_path] = processed_name
                
                logger.info(f"Starting Workflow for: {original_name} (ID: {processed_name})")
                
                # 3a. Check for Existing Thread (Resume or Skip) - DEPRECATED via active_threads check above
                # But kept for safety if active_threads is cleared
                config = {"configurable": {"thread_id": processed_name}}
                
                try:
                    current_snapshot = app.get_state(config)
                    # If we are strictly "waiting for approval" (interrupted)
                    if current_snapshot.next:
                         logger.info(f"⏭️  Skipping {original_name}: Workflow is paused/interrupted. (Thread: {processed_name})")
                         # Optional: Add simple timeouts or checks here to not skip forever if we want to force retry
                         continue
                except Exception:
                     # No state exists, proceed to create new
                     pass

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
                    # invoke now returns the final state snapshot's values
                    final_state_output = app.invoke(initial_state, config=config)
                    
                    # Check if interrupted (HITL)
                    current_snapshot = app.get_state(config)
                    if current_snapshot.next:
                        logger.warning(f"⚠️ Workflow Interrupted at inputs: {current_snapshot.next}. Waiting for Approval.")
                        final_status = "awaiting_approval"
                        
                        from src.core.state import update_progress
                        update_progress(processed_name, "Approval Required", "Paused for Human Review")
                        
                        # IMPORTANT: Do NOT archive if interrupted. File stays in inbox.
                        # Do NOT remove from active_threads.
                        continue
                    
                    # Normal Completion
                    if isinstance(final_state_output, dict):
                         final_status = final_state_output.get("status")
                    else:
                         final_status = final_state_output.status
                          
                    logger.info(f"Workflow Finished. Status: {final_status}")
                     
                    # Force Update UI to Completed
                    from src.core.state import update_progress
                    update_progress(processed_name, "Completed", f"Done. Status: {final_status}")
                     
                    # 5. Archive (Only if completed/failed, not interrupted)
                    monitor.archive(file_path, dest_name=processed_name)
                    if file_path in active_threads:
                        del active_threads[file_path]
                        
                    logger.info("-" * 40)
                     
                except Exception as e:
                    logger.error(f"Workflow Critical Fail: {e}")
                    
                    # Force Update UI to Failed
                    from src.core.state import update_progress
                    update_progress(processed_name, "Failed", f"Error: {e}")
                    
                    # Start archiving on failure too so we don't loop forever on a crash
                    monitor.archive(file_path, dest_name=processed_name)
                    if file_path in active_threads:
                        del active_threads[file_path]
                
            time.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("Shutting down gracefully...")
        sys.exit(0)
    except Exception as e:
        logger.critical(f"Fatal System Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()