# BatchZero — reproducible demo + benchmark (Windows PowerShell).
param([int]$Runs = 3)
$root = Split-Path -Parent $PSScriptRoot
$py = Join-Path $root "backend\.venv\Scripts\python.exe"

Write-Host "==> Live transcript" -ForegroundColor Cyan
& $py -m batchzero.demo.replay --tenant pmph_ops

Write-Host "`n==> Benchmark ($Runs runs)" -ForegroundColor Cyan
& $py -m batchzero.demo.replay --benchmark $Runs
