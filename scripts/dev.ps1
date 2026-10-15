# BatchZero — one-shot dev bootstrap (Windows PowerShell).
# Brings up FalkorDB, seeds the tenant graph, and starts the API.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root "backend"
$py = Join-Path $backend ".venv\Scripts\python.exe"

Write-Host "==> Starting FalkorDB" -ForegroundColor Cyan
docker compose -f (Join-Path $root "docker-compose.yml") up -d falkordb

Write-Host "==> Waiting for FalkorDB to be ready" -ForegroundColor Cyan
Start-Sleep -Seconds 4

Write-Host "==> Seeding Port Meridian fixture" -ForegroundColor Cyan
& $py -m batchzero.seed --reset

Write-Host "==> Starting API on http://localhost:8000" -ForegroundColor Green
& $py -m batchzero.api.app
