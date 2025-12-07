# Startup Script for Windows Powershell

$venvPath = ".venv\Scripts\Activate.ps1"
if (Test-Path $venvPath) {
    . $venvPath
}

# CLEANUP: Aggressively remove all local __pycache__ and .cache folders to enforce centralization
Write-Host "Cleaning up scattered __pycache__ and .cache..." -ForegroundColor Gray
Get-ChildItem -Path . -Recurse -Include "__pycache__",".cache" -Directory -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

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
$backend = Start-Process -FilePath "python" -ArgumentList "-m src.main" -NoNewWindow -PassThru

# Start Frontend
Write-Host "Launching Dashboard..." -ForegroundColor Green
try {
    streamlit run src/frontend/app.py
} finally {
    Write-Host "Stopping Backend..." -ForegroundColor Yellow
    if ($backend) {
        Stop-Process -Id $backend.Id -ErrorAction SilentlyContinue
    }
}
