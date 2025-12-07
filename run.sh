#!/bin/bash

# Activate venv if exists
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# Create directories
mkdir -p data/invoices data/processed outputs/reports logs

# Start Backend in background
echo "Starting Backend Agent..."
python -m src.main &
BACKEND_PID=$!

# Start Frontend
echo "Starting Frontend..."
streamlit run src/frontend/app.py

# Cleanup on exit
kill $BACKEND_PID