# ===== FILE: /home/labuser/Desktop/Additional Capstone Project/ai-invoice-auditor/run.sh =====
#!/bin/bash

# Activate venv if exists
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# Cleanup
echo "Cleaning up..."
find . -type d \( -name "__pycache__" -o -name ".cache" \) -exec rm -rf {} + 2>/dev/null
# Clean old DBs
rm -f data/checkpoints.sqlite*
mkdir -p data/invoices data/processed data/qdrant_storage outputs/reports logs

# Dependencies check
if command -v uv &> /dev/null; then
    # Ensure pip exists in the active venv before letting uv try to install packages
    if python -c "import ensurepip, sys" >/dev/null 2>&1; then
        python -m ensurepip --upgrade >/dev/null 2>&1 || true
    fi

    # If pip still isn't present, try the get-pip.py fallback
    if ! python -c "import pip" >/dev/null 2>&1; then
        echo "pip missing in venv; attempting to bootstrap pip..."
        if command -v curl >/dev/null 2>&1; then
            curl -sS https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py && python /tmp/get-pip.py >/dev/null 2>&1 || true
        elif command -v wget >/dev/null 2>&1; then
            wget -qO /tmp/get-pip.py https://bootstrap.pypa.io/get-pip.py && python /tmp/get-pip.py >/dev/null 2>&1 || true
        else
            echo "Warning: curl/wget not available; cannot fetch get-pip.py. Skipping uv package bootstrap."
        fi
    fi

    # Only run uv add if pip is now available
    if python -c "import pip" >/dev/null 2>&1; then
        uv add a2a-sdk presidio-analyzer presidio-anonymizer fpdf2 fastapi uvicorn pydantic requests streamlit langchain-aws ragas qdrant-client loguru litellm > /dev/null 2>&1
    else
        echo "Warning: pip not available in venv; skipping automatic 'uv add' step. If services fail, activate your venv and install dependencies manually."
    fi
fi

# Colors
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${CYAN}Starting AI Invoice Auditor System (Orchestrator: 8000, Agents: 8001/8002)...${NC}"

# Start the full system launcher (manages all 3 backend processes)
python run_full_system.py &
SYSTEM_PID=$!

cleanup() {
    echo -e "\n${YELLOW}Shutting down...${NC}"
    # This kills the python launcher, which handles killing its subprocesses
    kill $SYSTEM_PID 2>/dev/null
    exit
}

trap cleanup SIGINT SIGTERM

# Give the backend services time to initialize
sleep 8

echo -e "${GREEN}Launching Dashboard (Port 8501)...${NC}"
# Use foreground process to handle Ctrl+C cleanly
streamlit run src/frontend/app.py --server.headless false

cleanup