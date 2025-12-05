#!/bin/bash

# Define colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}>>> AI Invoice Auditor: System Startup <<<${NC}"

# 1. Environment Check
if [ ! -f .env ]; then
    echo -e "${RED}Error: .env file not found!${NC}"
    exit 1
fi

# 2. Port Cleanup (Auto-Kill Process on 8001)
if lsof -i :8001 > /dev/null; then
    echo -e "${RED}Port 8001 is busy. Killing existing process...${NC}"
    lsof -ti:8001 | xargs kill -9
    sleep 1
fi

# 3. Start Standardization Agent (Background)
echo -e "${GREEN}[1/3] Starting Standardization Agent (Port 8001)...${NC}"
uv run python src/adk_agents/translator/main.py > logs/agent_stdout.log 2>&1 &
AGENT_PID=$!

# Wait for startup (Health check loop)
echo "Waiting for Agent to initialize..."
for i in {1..10}; do
    if curl -s http://localhost:8001/health > /dev/null; then
        echo -e "${GREEN}Agent is active!${NC}"
        break
    fi
    sleep 1
done

# Final check
if ! kill -0 $AGENT_PID > /dev/null 2>&1; then
    echo -e "${RED}Agent failed to start. Check logs/agent_stdout.log${NC}"
    exit 1
fi

# 4. Start Orchestrator
echo -e "${GREEN}[2/3] Starting Main Orchestrator...${NC}"
echo -e "${BLUE}Press Ctrl+C to stop the system.${NC}"
echo ""

# Trap Ctrl+C to kill the agent
trap "echo -e '${RED}\nShutting down...${NC}'; kill $AGENT_PID; exit" INT

uv run python src/main.py