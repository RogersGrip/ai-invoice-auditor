#!/bin/bash
set -e

echo "Cleaning up..."
find . -type d \( -name "__pycache__" -o -name ".cache" \) -exec rm -rf {} + 2>/dev/null
rm -f data/checkpoints.sqlite*
mkdir -p data/invoices data/processed data/qdrant_storage outputs/reports logs

CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${CYAN}Starting AI Invoice Auditor System (Orchestrator: 8000, Agents: 8001/8002)...${NC}"

uv run python run_full_system.py &
SYSTEM_PID=$!

cleanup() {
    echo -e "\n${YELLOW}Shutting down...${NC}"
    kill $SYSTEM_PID 2>/dev/null
    exit
}

trap cleanup SIGINT SIGTERM

sleep 8

echo -e "${GREEN}Launching Dashboard (Port 8501)...${NC}"
uv run streamlit run src/frontend/app.py --server.headless false

cleanup
