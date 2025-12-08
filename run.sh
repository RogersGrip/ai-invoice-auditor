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
    uv pip install fastapi uvicorn pydantic requests streamlit langchain-aws ragas fpdf qdrant-client loguru litellm > /dev/null 2>&1
fi

# Colors
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${CYAN}Starting A2A Backend Server (Port 8000)...${NC}"
python src/server.py &
BACKEND_PID=$!

cleanup() {
    echo -e "\n${YELLOW}Shutting down...${NC}"
    kill $BACKEND_PID 2>/dev/null
    exit
}

trap cleanup SIGINT SIGTERM

sleep 2

echo -e "${GREEN}Launching Dashboard (Port 8501)...${NC}"
# Use foreground process to handle Ctrl+C cleanly
streamlit run src/frontend/app.py --server.headless false

cleanup