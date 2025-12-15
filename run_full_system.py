import subprocess
import sys
import time
import os

if __name__ == "__main__":
    print(">>> Starting AI Invoice Auditor System (A2A Enabled) <<<")
    
    # 1. Start Extractor Agent (8001)
    extractor_process = subprocess.Popen(
        [sys.executable, "-m", "src.a2a_agents.extractor.server"],
        cwd=os.getcwd(),
        env=os.environ.copy()
    )
    
    # 2. Start Translator Agent (8002)
    translator_process = subprocess.Popen(
        [sys.executable, "-m", "src.a2a_agents.translator.server"],
        cwd=os.getcwd(),
        env=os.environ.copy()
    )
    
    time.sleep(5) # Wait for agents to initialize
    
    # 3. Start Main Orchestrator Server (8000)
    orchestrator_process = subprocess.Popen(
        [sys.executable, "-m", "src.server"],
        cwd=os.getcwd(),
        env=os.environ.copy()
    )
    
    print(">>> All Systems Go! <<<")
    print("Main Server: http://localhost:8000")
    print("Extractor Agent: http://localhost:8001")
    print("Translator Agent: http://localhost:8002")
    print("Press Ctrl+C to stop all services.")
    
    try:
        # Keep main thread alive
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping services...")
    finally:
        # Graceful Shutdown
        if 'orchestrator_process' in locals(): orchestrator_process.terminate()
        if 'extractor_process' in locals(): extractor_process.terminate()
        if 'translator_process' in locals(): translator_process.terminate()
        print("[Launcher] Cleanup Complete.")
