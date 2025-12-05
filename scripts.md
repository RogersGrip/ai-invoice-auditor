# Scripts
- `export PYTHONPYCACHEPREFIX="$PWD/pycache"`
- `export PYTHONPYCACHEPREFIX="$(dirname "$(pwd)")/pycache"`

- `uv venv`
- `source .venv/bin/activate`
- `mkdir -p pycache`
- `export PYTHONPYCACHEPREFIX="$PWD/pycache"`
- `find . | grep -E "(__pycache__|\.pyc$)" | xargs rm -rf`
- `uv add pydantic pydantic-settings langgraph langchain langchain-cohere langchain-community fastapi uvicorn python-dotenv loguru httpx qdrant-client pyyaml litellm pymupdf`

- `uv run python -m src.manual_run`
- `export PYTHONPATH=$(pwd)`
- `uv run python src/adk_agents/translator/main.py`

- `curl -s http://localhost:8001/agent-card | jq .`