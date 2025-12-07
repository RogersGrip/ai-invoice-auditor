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

# Start Backend in background
echo "Starting Backend Agent..."
python -m src.main &
BACKEND_PID=$!

# Cleanup function
cleanup() {
    echo "Stopping Backend (PID: $BACKEND_PID)..."
    kill $BACKEND_PID
    exit
}

# Trap SIGINT and SIGTERM
trap cleanup SIGINT SIGTERM

# Start Frontend
echo "Starting Frontend..."
streamlit run src/frontend/app.py

# Ensure cleanup if streamlit exits normally
cleanup