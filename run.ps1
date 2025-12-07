# Startup Script for Windows Powershell

$venvPath = ".venv\Scripts\Activate.ps1"
if (Test-Path $venvPath) {
    . $venvPath
}

# Create dirs
New-Item -ItemType Directory -Force -Path "data/invoices"
New-Item -ItemType Directory -Force -Path "data/processed"
New-Item -ItemType Directory -Force -Path "outputs/reports"
New-Item -ItemType Directory -Force -Path "logs"

Write-Host "Starting AI Invoice Auditor..." -ForegroundColor Cyan

# Start Backend (Shared Terminal)
Start-Process -FilePath "python" -ArgumentList "-m src.main" -NoNewWindow

# Start Frontend
Write-Host "Launching Dashboard..." -ForegroundColor Green
streamlit run src/frontend/app.py
