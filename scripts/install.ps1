param(
  [switch]$SkipFrontend
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"

Write-Host "==> BoetClaw install (Windows PowerShell)"

Set-Location $Backend
$versionOk = python -c "import sys; raise SystemExit(0 if (3, 11) <= sys.version_info[:2] < (3, 14) else 1)"
if ($LASTEXITCODE -ne 0) {
  Write-Error "BoetClaw backend 需要 Python 3.11-3.13。请安装 Python 3.12/3.13 后重试，例如：py -3.12 -m venv backend\.venv"
}

if (-not (Test-Path ".venv")) {
  Write-Host "==> Creating Python virtual environment"
  python -m venv .venv
}

Write-Host "==> Installing backend dependencies"
& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip
& ".\.venv\Scripts\python.exe" -m pip install -r requirements.txt

if (-not (Test-Path ".env")) {
  Write-Host "==> Initializing backend/.env from .env.example"
  Copy-Item ".env.example" ".env"
}

if (-not $SkipFrontend) {
  Set-Location $Frontend
  Write-Host "==> Installing frontend dependencies"
  npm install
}

Set-Location $Root
Write-Host ""
Write-Host "Install complete."
Write-Host "Backend:  cd backend; .\.venv\Scripts\python.exe run.py"
Write-Host "Frontend: cd frontend; npm run dev"
