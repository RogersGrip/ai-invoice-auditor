# Scripts
- `export PYTHONPYCACHEPREFIX="$PWD/pycache"`
- `export PYTHONPYCACHEPREFIX="$(dirname "$(pwd)")/pycache"`

- `uv venv`
- `source .venv/bin/activate`
- `mkdir -p pycache`
- `export PYTHONPYCACHEPREFIX="$PWD/pycache"`
- `find . | grep -E "(__pycache__|\.pyc$)" | xargs rm -rf`