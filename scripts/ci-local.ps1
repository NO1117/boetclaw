<#
.SYNOPSIS
  Reproduce the main GitHub Actions CI gates locally (Windows PowerShell).

.DESCRIPTION
  Uses a temporary / project venv and frontend node_modules. Does not rely on
  business workspace state. Real Provider / channel E2E is NOT included.

.PARAMETER SkipE2E
  Skip Playwright chromium E2E (still runs unit/coverage/build).

.PARAMETER SkipSecurity
  Skip pip-audit / npm audit.
#>
param(
  [switch]$SkipE2E,
  [switch]$SkipSecurity
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"
$failed = 0

function Invoke-Step {
  param([string]$Name, [scriptblock]$Block)
  Write-Host ""
  Write-Host "==> $Name" -ForegroundColor Cyan
  try {
    & $Block
    if ($LASTEXITCODE -ne 0 -and $null -ne $LASTEXITCODE) {
      throw "exit code $LASTEXITCODE"
    }
    Write-Host "OK: $Name" -ForegroundColor Green
  }
  catch {
    Write-Host "FAIL: $Name — $_" -ForegroundColor Red
    $script:failed++
  }
}

Write-Host "BoetClaw local CI gates (PLAN-420)"
Write-Host "Root: $Root"

# --- Backend ---
Set-Location $Backend
$Py = Join-Path $Backend ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) {
  Write-Host "==> Creating backend/.venv"
  python -m venv .venv
  if ($LASTEXITCODE -ne 0) { throw "venv creation failed (need Python 3.11-3.13)" }
}
& $Py -m pip install -q --upgrade pip
& $Py -m pip install -q -r requirements-dev.txt

$env:PYTHONPATH = $Backend

Invoke-Step "ruff check" { & $Py -m ruff check app tests scripts }
Invoke-Step "mypy" { & $Py -m mypy app --config-file pyproject.toml }
Invoke-Step "openapi breaking check" { & $Py scripts\check_openapi_breaking.py }
Invoke-Step "pytest" { & $Py -m pytest -q }

# --- Frontend ---
Set-Location $Frontend
if (-not (Test-Path "node_modules")) {
  Write-Host "==> npm ci"
  npm ci
  if ($LASTEXITCODE -ne 0) { npm install }
}

Invoke-Step "npm test -- --run" { npm test -- --run }
Invoke-Step "npm run test:coverage" { npm run test:coverage }
Invoke-Step "npm run build" { npm run build }

if (-not $SkipE2E) {
  Invoke-Step "playwright install chromium" { npx playwright install chromium }
  Invoke-Step "npm run test:e2e" { npm run test:e2e }
}
else {
  Write-Host "SKIP: E2E (-SkipE2E)"
}

# --- Compose ---
Set-Location $Root
Invoke-Step "docker compose config" { docker compose config --quiet }

# --- Security ---
if (-not $SkipSecurity) {
  Set-Location $Backend
  Invoke-Step "pip-audit" { & $Py -m pip_audit -r requirements.txt --progress-spinner off }
  Set-Location $Frontend
  Invoke-Step "npm audit (prod, high+)" { npm audit --omit=dev --audit-level=high }
}
else {
  Write-Host "SKIP: security (-SkipSecurity)"
}

Set-Location $Root
Write-Host ""
if ($failed -gt 0) {
  Write-Host "Local CI finished with $failed failure(s)." -ForegroundColor Red
  exit 1
}
Write-Host "Local CI finished OK. Cloud GitHub Actions still requires a git remote + Actions enabled." -ForegroundColor Green
exit 0
