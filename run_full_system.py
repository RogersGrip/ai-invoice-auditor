import subprocess
import sys
import time
import os

if __name__ == "__main__":
    print(">>> Starting AI Invoice Auditor System (A2A Enabled) <<<")

    # 1. Start Extractor Agent
    print("   [1/3] Launching Extractor Agent...")
    extractor_process = subprocess.Popen(
        [sys.executable, "-m", "src.a2a_agents.extractor.server"],
        cwd=os.getcwd(),
        env=os.environ.copy()
    )

    # 2. Start Translator Agent
    print("   [2/3] Launching Translator Agent...")
    translator_process = subprocess.Popen(
        [sys.executable, "-m", "src.a2a_agents.translator.server"],
        cwd=os.getcwd(),
        env=os.environ.copy()
    )

    # Allow agents time to spin up and check for early crashes
    time.sleep(3)
    if extractor_process.poll() is not None:
        print("!!! FATAL: Extractor Agent failed to start. Check logs.")
        sys.exit(1)
    if translator_process.poll() is not None:
        print("!!! FATAL: Translator Agent failed to start. Check logs.")
        extractor_process.terminate()
        sys.exit(1)

    # 3. Start Main Server
    print("   [3/3] Launching Main Orchestrator...")
    orchestrator_process = subprocess.Popen(
        [sys.executable, "-m", "src.server"],
        cwd=os.getcwd(),
        env=os.environ.copy()
    )

    # Check Orchestrator
    time.sleep(2)
    if orchestrator_process.poll() is not None:
        print("!!! FATAL: Orchestrator failed to start (Port 8000 might be in use).")
        extractor_process.terminate()
        translator_process.terminate()
        sys.exit(1)

    print("\n>>> All Systems Go! <<<")
    print("Main Server:      http://localhost:8000")
    print("Extractor Agent:  http://localhost:8001")
    print("Translator Agent: http://localhost:8002")
    print("Press Ctrl+C to stop all services.")

    try:
        while True:
            time.sleep(1)
            # Continuous health check
            if orchestrator_process.poll() is not None:
                print("! Orchestrator process died unexpectedly.")
                break
            if extractor_process.poll() is not None:
                print("! Extractor process died unexpectedly.")
                break
            if translator_process.poll() is not None:
                print("! Translator process died unexpectedly.")
                break
    except KeyboardInterrupt:
        print("\nStopping services...")
    finally:
        if 'orchestrator_process' in locals() and orchestrator_process: orchestrator_process.terminate()
        if 'extractor_process' in locals() and extractor_process: extractor_process.terminate()
        if 'translator_process' in locals() and translator_process: translator_process.terminate()
        print("[Launcher] Cleanup Complete.")