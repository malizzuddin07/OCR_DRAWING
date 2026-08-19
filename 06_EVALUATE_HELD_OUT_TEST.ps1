$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
& $python code\train_detector_candidate_v9.py --device 0 --batch 1 --evaluate-test --confirm-start 2>&1 | Tee-Object held_out_test_console_v9.log
if ($LASTEXITCODE -ne 0) { throw "Held-out test evaluation failed." }
