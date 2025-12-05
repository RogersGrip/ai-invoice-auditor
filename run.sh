#!/bin/bash

export PYTHONPATH=$(pwd)

# 1. Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo "uv could not be found. Please install it."
    exit 1
fi

echo "--- Starting AI Invoice Auditor System ---"

# 2. Start Translation Agent (Background)
echo "[1/2] Launching Translator Agent (port 8001)..."
uv run python src/adk_agents/translator/main.py > logs/translator_agent.log 2>&1 &
TRANSLATOR_PID=$!

# Wait a moment for agent to spin up
sleep 3
echo "      Translator Agent PID: $TRANSLATOR_PID"

# 3. Start Main Application (Foreground)
echo "[2/2] Launching Main Orchestrator..."
uv run src/main.py

# 4. Cleanup on Exit
trap "kill $TRANSLATOR_PID" EXIT