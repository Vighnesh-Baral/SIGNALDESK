$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    Write-Host "Virtual environment not found. Run setup_signaldesk.ps1 first." -ForegroundColor Yellow
    exit 1
}

if (-not (Test-Path (Join-Path $ProjectRoot ".env"))) {
    Copy-Item (Join-Path $ProjectRoot ".env.example") (Join-Path $ProjectRoot ".env")
    Write-Host "Created .env from .env.example. Edit it before public exposure." -ForegroundColor Yellow
}

Set-Location $ProjectRoot
& $Python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
