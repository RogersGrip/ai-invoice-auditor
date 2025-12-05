#!/bin/bash
# Usage: ./inspect.sh erp  OR  ./inspect.sh rag

if [ "$1" == "erp" ]; then
    echo "Starting MCP Inspector for ERP Agent..."
    npx @modelcontextprotocol/inspector uv run fastmcp run src/mcp_server/erp.py
elif [ "$1" == "rag" ]; then
    echo "Starting MCP Inspector for RAG Agent..."
    npx @modelcontextprotocol/inspector uv run fastmcp run src/mcp_server/rag.py
else
    echo "Usage: ./inspect.sh [erp|rag]"
fi