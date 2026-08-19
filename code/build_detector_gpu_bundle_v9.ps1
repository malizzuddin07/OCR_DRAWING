param(
    [string]$ProjectRoot = "C:\Users\izzuddin\Desktop\OCR DRAWING"
)

$ErrorActionPreference = "Stop"
$golden = Join-Path $ProjectRoot "golden_tests"
$package = Join-Path $golden "detector_training_package_v7"
$trainer = Join-Path $ProjectRoot "code\train_detector_candidate_v9.py"
$startingModel = Join-Path $ProjectRoot "yolov8s.pt"
$bundleName = "OCR_DETECTOR_GPU_TRAINING_BUNDLE_v9"
$stage = Join-Path $golden $bundleName
$zip = Join-Path $golden "$bundleName.zip"
$hashFile = Join-Path $golden "${bundleName}_SHA256.txt"

foreach ($required in @($package, $trainer, $startingModel)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Required Candidate V9 file is missing: $required"
    }
}
if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
if (Test-Path -LiteralPath $zip) { Remove-Item -LiteralPath $zip -Force }

New-Item -ItemType Directory -Path (Join-Path $stage "code") -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $stage "golden_tests") -Force | Out-Null
Copy-Item -LiteralPath $package -Destination (Join-Path $stage "golden_tests") -Recurse
Copy-Item -LiteralPath $trainer -Destination (Join-Path $stage "code")
Copy-Item -LiteralPath $startingModel -Destination (Join-Path $stage "yolov8s.pt")

@'
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
if (-not (Get-Command nvidia-smi -ErrorAction SilentlyContinue)) { throw "NVIDIA GPU driver was not found." }
nvidia-smi
if (-not (Get-Command py -ErrorAction SilentlyContinue)) { throw "Python 3.11 launcher was not found." }
py -3.11 --version
Write-Host "GPU and Python checks passed." -ForegroundColor Green
'@ | Set-Content -LiteralPath (Join-Path $stage "01_CHECK_GPU.ps1") -Encoding UTF8

@'
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path ".venv\Scripts\python.exe")) { py -3.11 -m venv .venv }
$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
& $python -m pip install --upgrade pip
& $python -m pip install torch==2.12.0 torchvision==0.27.0 --index-url https://download.pytorch.org/whl/cu126
& $python -m pip install ultralytics==8.4.69
& $python -c "import torch; print('cuda_available=', torch.cuda.is_available()); print('gpu=', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'NONE'); raise SystemExit(0 if torch.cuda.is_available() else 2)"
if ($LASTEXITCODE -ne 0) { throw "PyTorch cannot use the NVIDIA GPU." }
& $python code\train_detector_candidate_v9.py
if ($LASTEXITCODE -ne 0) { throw "Candidate V9 package validation failed." }
Write-Host "Setup complete. Training has NOT started." -ForegroundColor Green
'@ | Set-Content -LiteralPath (Join-Path $stage "02_SETUP_GPU_ENVIRONMENT.ps1") -Encoding UTF8

@'
param([int]$Batch = 4)
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { throw "Run 02_SETUP_GPU_ENVIRONMENT.ps1 first." }
$run = Join-Path $PSScriptRoot "runs\candidate_detector\golden_detector_v9"
if (Test-Path $run) {
    throw "Candidate V9 run folder already exists. Resume it with 04_RESUME_TRAINING.ps1, or rename it before starting a fresh run."
}
Write-Host "Starting general Candidate V9 with batch $Batch..." -ForegroundColor Cyan
Write-Host "Do not sleep or shut down this computer while Python is running." -ForegroundColor Yellow
& $python code\train_detector_candidate_v9.py --device 0 --batch $Batch --confirm-start 2>&1 | Tee-Object training_console_v9.log
if ($LASTEXITCODE -ne 0) { throw "Training stopped. If last.pt exists, use 04_RESUME_TRAINING.ps1." }
Write-Host "Training finished. Run 06_EVALUATE_HELD_OUT_TEST.ps1." -ForegroundColor Green
'@ | Set-Content -LiteralPath (Join-Path $stage "03_START_TRAINING.ps1") -Encoding UTF8

@'
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$last = Join-Path $PSScriptRoot "runs\candidate_detector\golden_detector_v9\weights\last.pt"
if (-not (Test-Path $last)) { throw "No last.pt exists. Start training first." }
& $python code\train_detector_candidate_v9.py --device 0 --resume --confirm-start 2>&1 | Tee-Object training_resume_console_v9.log
if ($LASTEXITCODE -ne 0) { throw "Resume training stopped with an error." }
'@ | Set-Content -LiteralPath (Join-Path $stage "04_RESUME_TRAINING.ps1") -Encoding UTF8

@'
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
Get-CimInstance Win32_Process | Where-Object { $_.Name -eq "python.exe" -and $_.CommandLine -like "*train_detector_candidate_v9.py*" } | Select-Object ProcessId,CommandLine | Format-List
$results = ".\runs\candidate_detector\golden_detector_v9\results.csv"
if (Test-Path $results) { Get-Content $results -Tail 3 } else { Write-Host "Training results do not exist yet." }
'@ | Set-Content -LiteralPath (Join-Path $stage "05_CHECK_STATUS.ps1") -Encoding UTF8

@'
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
& $python code\train_detector_candidate_v9.py --device 0 --batch 1 --evaluate-test --confirm-start 2>&1 | Tee-Object held_out_test_console_v9.log
if ($LASTEXITCODE -ne 0) { throw "Held-out test evaluation failed." }
'@ | Set-Content -LiteralPath (Join-Path $stage "06_EVALUATE_HELD_OUT_TEST.ps1") -Encoding UTF8

@'
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
$run = Join-Path $PSScriptRoot "runs\candidate_detector\golden_detector_v9"
$best = Join-Path $run "weights\best.pt"
if (-not (Test-Path $best)) { throw "Candidate V9 best.pt was not found." }
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$return = Join-Path $PSScriptRoot "return_results_v9_$stamp"
$zip = Join-Path $PSScriptRoot "RETURN_TO_OCR_LAPTOP_V9_$stamp.zip"
New-Item -ItemType Directory -Path $return | Out-Null
Copy-Item -LiteralPath $run -Destination $return -Recurse
foreach ($log in @("training_console_v9.log","training_resume_console_v9.log","held_out_test_console_v9.log")) { if (Test-Path $log) { Copy-Item $log $return } }
nvidia-smi | Out-File (Join-Path $return "GPU_INFO.txt") -Encoding utf8
Compress-Archive -LiteralPath $return -DestinationPath $zip -CompressionLevel Optimal
$hash = (Get-FileHash $zip -Algorithm SHA256).Hash
Write-Host "Return ZIP: $zip" -ForegroundColor Green
Write-Host "SHA256: $hash"
Write-Host "Copy this ZIP to the OCR laptop. Do not replace production manually."
'@ | Set-Content -LiteralPath (Join-Path $stage "07_PACKAGE_RESULTS.ps1") -Encoding UTF8

@'
# Candidate V9 - Best General Detector Attempt

This candidate starts fresh from YOLOv8s and uses all 17 approved drawings.
Validation and test drawings remain separated by drawing, not by random tile.

Run scripts 01 to 07 in order. To pause, press Ctrl+C once and wait for the
PowerShell prompt. Resume with 04_RESUME_TRAINING.ps1. If batch 4 causes an
out-of-memory error, restart a fresh run with:

    Rename-Item ".\runs\candidate_detector\golden_detector_v9" "golden_detector_v9_batch4_failed"
    .\03_START_TRAINING.ps1 -Batch 2

Candidate V9 does not modify the production model.
'@ | Set-Content -LiteralPath (Join-Path $stage "README_FIRST.md") -Encoding UTF8

Compress-Archive -LiteralPath $stage -DestinationPath $zip -CompressionLevel Optimal
$hash = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash
"$hash  $bundleName.zip" | Set-Content -LiteralPath $hashFile -Encoding ASCII
Remove-Item -LiteralPath $stage -Recurse -Force
Write-Host "Candidate V9 GPU bundle: $zip" -ForegroundColor Green
Write-Host "SHA256: $hash"
