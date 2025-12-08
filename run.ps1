# Startup Script for Windows Powershell

$venvPath = ".venv\Scripts\Activate.ps1"
if (Test-Path $venvPath) {
    . $venvPath
}

# CLEANUP: Aggressively remove all local __pycache__ and .cache folders
Write-Host "Cleaning up scattered __pycache__ and .cache..." -ForegroundColor Gray
Get-ChildItem -Path . -Recurse -Include "__pycache__",".cache" -Directory -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

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
    uv pip install fastapi uvicorn pydantic requests streamlit langchain-aws ragas fpdf qdrant-client loguru litellm
}

# Start Backend (New Terminal Window)
Write-Host "Launching A2A Backend Server (New Window)..." -ForegroundColor Cyan
$backend = Start-Process -FilePath "python" -ArgumentList "src/server.py" -PassThru

Start-Sleep -Seconds 2

Write-Host "Launching Dashboard..." -ForegroundColor Green

try {
    # Run Streamlit in a separate process so browser close won't kill PowerShell
    $streamlit = Start-Process "streamlit" "run src/frontend/app.py" -PassThru
    Wait-Process -Id $streamlit.Id
}
finally {
    Write-Host "Stopping Backend..." -ForegroundColor Yellow
    if ($backend) {
        Stop-Process -Id $backend.Id -ErrorAction SilentlyContinue
    }
}
