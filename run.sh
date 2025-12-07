#!/bin/bash

# Activate venv if exists
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# Centralize Pycache
export PYTHONPYCACHEPREFIX="$(pwd)/.pycache"
mkdir -p "$PYTHONPYCACHEPREFIX"
echo "Pycache centralized at: $PYTHONPYCACHEPREFIX"

# Create directories
mkdir -p data/invoices data/processed outputs/reports logs

# Colors
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
GRAY='\033[0;90m'
NC='\033[0m' # No Color

# Start Backend in background
echo -e "${CYAN}Starting Backend Agent...${NC}"
python -m src.main &
BACKEND_PID=$!

# Cleanup function
cleanup() {
    echo -e "${YELLOW}Stopping Backend (PID: $BACKEND_PID)...${NC}"
    kill $BACKEND_PID
    exit
}

# Trap SIGINT and SIGTERM
trap cleanup SIGINT SIGTERM

# Start Frontend
echo -e "${GREEN}Launching Dashboard...${NC}"
streamlit run src/frontend/app.py

# Ensure cleanup if streamlit exits normally
cleanup