# Startup Script for Windows Powershell

$venvPath = ".venv\Scripts\Activate.ps1"
if (Test-Path $venvPath) {
    . $venvPath
}

# CLEANUP: Aggressively remove all local __pycache__ and .cache folders
Write-Host "Cleaning up scattered __pycache__ and .cache..." -ForegroundColor Gray
Get-ChildItem -Path . -Recurse -Include "__pycache__",".cache" -Directory -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

# Clean old DBs (Matching run.sh)
if (Test-Path "data/checkpoints.sqlite*") {
    Remove-Item "data/checkpoints.sqlite*" -Force -ErrorAction SilentlyContinue
}

# Centralize Pycache
$env:PYTHONPYCACHEPREFIX = "$PWD\.pycache"
if (-not (Test-Path $env:PYTHONPYCACHEPREFIX)) {
    New-Item -ItemType Directory -Force -Path $env:PYTHONPYCACHEPREFIX | Out-Null
}

# Create dirs
New-Item -ItemType Directory -Force -Path "data/invoices", "data/processed", "data/qdrant_storage", "outputs/reports", "logs" | Out-Null

Write-Host "Starting AI Invoice Auditor..." -ForegroundColor Cyan
Write-Host "Pycache centralized at: $env:PYTHONPYCACHEPREFIX" -ForegroundColor Gray

# Install dependencies if needed
if (Get-Command uv -ErrorAction SilentlyContinue) {
    Write-Host "Ensuring dependencies are installed..." -ForegroundColor Gray
    uv pip install fastapi uvicorn pydantic requests streamlit langchain-aws langchain-community ragas fpdf qdrant-client loguru litellm
}

# Start Backend (Background Job to mimic &)
Write-Host "Launching A2A Backend Server (Port 8000)..." -ForegroundColor Cyan
$backendProcess = Start-Process -FilePath "python" -ArgumentList "-W ignore src/server.py" -PassThru -NoNewWindow

Start-Sleep -Seconds 2

Write-Host "Launching Dashboard (Port 8501)..." -ForegroundColor Green

try {
    # Run Streamlit in the foreground, blocking until user exits
    # We use python -m streamlit to ensure we use the venv's streamlit if active
    & streamlit run src/frontend/app.py --server.headless false
}
finally {
    Write-Host "`nShutting down..." -ForegroundColor Yellow
    if ($backendProcess -and -not $backendProcess.HasExited) {
        Stop-Process -Id $backendProcess.Id -Force -ErrorAction SilentlyContinue
    }
}
