# Scripts

```bash
# Create and activate virtualenv
uv venv
source .venv/bin/activate

# Cache directory
mkdir -p pycache
export PYTHONPYCACHEPREFIX="$PWD/pycache"
export PYTHONPYCACHEPREFIX="$(dirname "$(pwd)")/pycache"

# Clean bytecode
find . | grep -E "(__pycache__|\.pyc$)" | xargs rm -rf

# Install dependencies
uv add pydantic pydantic-settings langgraph langchain langchain-cohere langchain-community fastapi uvicorn python-dotenv loguru httpx qdrant-client pyyaml litellm pymupdf

# Run scripts
uv run python -m src.manual_run
export PYTHONPATH=$(pwd)
uv run python src/adk_agents/translator/main.py
```
