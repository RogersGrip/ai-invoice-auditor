# Startup Script for Windows Powershell

$venvPath = ".venv\Scripts\Activate.ps1"
if (Test-Path $venvPath) {
    . $venvPath
}

# Centralize Pycache
$env:PYTHONPYCACHEPREFIX = "$PWD\.pycache"
if (-not (Test-Path $env:PYTHONPYCACHEPREFIX)) {
    New-Item -ItemType Directory -Force -Path $env:PYTHONPYCACHEPREFIX | Out-Null
}

# Create dirs
New-Item -ItemType Directory -Force -Path "data/invoices" | Out-Null
New-Item -ItemType Directory -Force -Path "data/processed" | Out-Null
New-Item -ItemType Directory -Force -Path "outputs/reports" | Out-Null
New-Item -ItemType Directory -Force -Path "logs" | Out-Null

Write-Host "Starting AI Invoice Auditor..." -ForegroundColor Cyan
Write-Host "Pycache centralized at: $env:PYTHONPYCACHEPREFIX" -ForegroundColor Gray

# Start Backend (Shared Terminal)
Start-Process -FilePath "python" -ArgumentList "-m src.main" -NoNewWindow

# Start Frontend
Write-Host "Launching Dashboard..." -ForegroundColor Green
streamlit run src/frontend/app.py
