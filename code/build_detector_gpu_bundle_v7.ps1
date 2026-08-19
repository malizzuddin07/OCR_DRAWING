param(
    [string]$ProjectRoot = "C:\Users\izzuddin\Desktop\OCR DRAWING"
)

$ErrorActionPreference = "Stop"
$golden = Join-Path $ProjectRoot "golden_tests"
$package = Join-Path $golden "detector_training_package_v7"
$trainingScript = Join-Path $ProjectRoot "code\train_detector_candidate_v7.py"
$startingModel = Join-Path $ProjectRoot "incoming_models\candidate_yolov8s_golden_v3_20260727\golden_detector_v3\weights\best.pt"
$bundleName = "OCR_DETECTOR_GPU_TRAINING_BUNDLE_v7"
$stage = Join-Path $golden $bundleName
$zip = Join-Path $golden "$bundleName.zip"
$hashFile = Join-Path $golden "${bundleName}_SHA256.txt"

foreach ($required in @(
    (Join-Path $package "training_package_manifest.json"),
    $trainingScript,
    $startingModel
)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Required V7 file is missing: $required"
    }
}
if (Test-Path -LiteralPath $stage) {
    throw "Temporary bundle folder already exists: $stage"
}
if (Test-Path -LiteralPath $zip) {
    throw "V7 bundle ZIP already exists: $zip"
}

New-Item -ItemType Directory -Path (Join-Path $stage "code") -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $stage "golden_tests") -Force | Out-Null
Copy-Item -LiteralPath $package -Destination (Join-Path $stage "golden_tests") -Recurse
Copy-Item -LiteralPath $trainingScript -Destination (Join-Path $stage "code")
Copy-Item -LiteralPath $startingModel -Destination (Join-Path $stage "candidate_detector_v3_best.pt")

@'
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
Write-Host "Checking NVIDIA GPU..." -ForegroundColor Cyan
if (-not (Get-Command nvidia-smi -ErrorAction SilentlyContinue)) {
    throw "nvidia-smi was not found. Install or update the NVIDIA graphics driver first."
}
nvidia-smi
Write-Host "`nChecking Python 3.11..." -ForegroundColor Cyan
if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    throw "Python launcher was not found. Install Python 3.11 for Windows first."
}
py -3.11 --version
Write-Host "`nGPU and Python basic checks passed." -ForegroundColor Green
'@ | Set-Content -LiteralPath (Join-Path $stage "01_CHECK_GPU.ps1") -Encoding UTF8

@'
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    throw "Python launcher was not found. Install Python 3.11 for Windows first."
}
if (-not (Test-Path -LiteralPath ".venv\Scripts\python.exe")) {
    Write-Host "Creating the private Python environment..." -ForegroundColor Cyan
    py -3.11 -m venv .venv
}
$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
& $python -m pip install --upgrade pip
& $python -m pip install torch==2.12.0 torchvision==0.27.0 --index-url https://download.pytorch.org/whl/cu126
& $python -m pip install ultralytics==8.4.69
& $python -c "import torch; print('torch=', torch.__version__); print('cuda_available=', torch.cuda.is_available()); print('gpu=', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'NONE'); raise SystemExit(0 if torch.cuda.is_available() else 2)"
if ($LASTEXITCODE -ne 0) {
    throw "PyTorch cannot use the GPU. Update the NVIDIA driver, then rerun this script."
}
& $python code\train_detector_candidate_v7.py
if ($LASTEXITCODE -ne 0) {
    throw "Training package V7 check failed."
}
Write-Host "`nSetup completed. Training has NOT started." -ForegroundColor Green
'@ | Set-Content -LiteralPath (Join-Path $stage "02_SETUP_GPU_ENVIRONMENT.ps1") -Encoding UTF8

@'
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    throw "The environment is missing. Run 02_SETUP_GPU_ENVIRONMENT.ps1 first."
}
Write-Host "Starting isolated Candidate V7 training on NVIDIA GPU 0..." -ForegroundColor Cyan
Write-Host "Approved source: 17 drawings and 966 human-approved labels." -ForegroundColor Cyan
Write-Host "Do not close, shut down, or sleep the GPU computer." -ForegroundColor Yellow
& $python code\train_detector_candidate_v7.py --device 0 --batch 4 --confirm-start 2>&1 |
    Tee-Object -FilePath "training_console_v7.log"
if ($LASTEXITCODE -ne 0) {
    throw "Training stopped with an error. Keep the runs folder and use 04_RESUME_TRAINING.ps1 if last.pt exists."
}
Write-Host "`nTraining finished. Run 06_PACKAGE_RESULTS.ps1." -ForegroundColor Green
'@ | Set-Content -LiteralPath (Join-Path $stage "03_START_TRAINING.ps1") -Encoding UTF8

@'
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$last = Join-Path $PSScriptRoot "runs\candidate_detector\golden_detector_v7\weights\last.pt"
if (-not (Test-Path -LiteralPath $python)) {
    throw "The environment is missing. Run 02_SETUP_GPU_ENVIRONMENT.ps1 first."
}
if (-not (Test-Path -LiteralPath $last)) {
    throw "No V7 last.pt exists. Start with 03_START_TRAINING.ps1."
}
Write-Host "Resuming Candidate V7 from last.pt..." -ForegroundColor Cyan
& $python code\train_detector_candidate_v7.py --device 0 --resume --confirm-start 2>&1 |
    Tee-Object -FilePath "training_resume_console_v7.log"
if ($LASTEXITCODE -ne 0) {
    throw "Resume training stopped with an error."
}
Write-Host "`nTraining finished. Run 06_PACKAGE_RESULTS.ps1." -ForegroundColor Green
'@ | Set-Content -LiteralPath (Join-Path $stage "04_RESUME_TRAINING.ps1") -Encoding UTF8

@'
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
Write-Host "Candidate V7 training processes:" -ForegroundColor Cyan
Get-CimInstance Win32_Process |
    Where-Object { $_.Name -eq "python.exe" -and $_.CommandLine -like "*train_detector_candidate_v7.py*" } |
    Select-Object ProcessId, CommandLine |
    Format-List
$results = Join-Path $PSScriptRoot "runs\candidate_detector\golden_detector_v7\results.csv"
if (Test-Path -LiteralPath $results) {
    Write-Host "Latest Candidate V7 results:" -ForegroundColor Cyan
    Get-Content -LiteralPath $results -Tail 3
} else {
    Write-Host "results.csv does not exist yet. Training may still be starting." -ForegroundColor Yellow
}
'@ | Set-Content -LiteralPath (Join-Path $stage "05_CHECK_STATUS.ps1") -Encoding UTF8

@'
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
$run = Join-Path $PSScriptRoot "runs\candidate_detector\golden_detector_v7"
$best = Join-Path $run "weights\best.pt"
if (-not (Test-Path -LiteralPath $best)) {
    throw "Candidate V7 best.pt was not found. Training has not produced a usable model."
}
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$stage = Join-Path $PSScriptRoot "return_results_v7_$stamp"
$zip = Join-Path $PSScriptRoot "RETURN_TO_OCR_LAPTOP_V7_$stamp.zip"
New-Item -ItemType Directory -Path $stage | Out-Null
$resultStage = Join-Path $stage "golden_detector_v7"
New-Item -ItemType Directory -Path $resultStage | Out-Null
Get-ChildItem -LiteralPath $run -File | Copy-Item -Destination $resultStage
New-Item -ItemType Directory -Path (Join-Path $resultStage "weights") | Out-Null
Copy-Item -LiteralPath (Join-Path $run "weights\best.pt") -Destination (Join-Path $resultStage "weights")
Copy-Item -LiteralPath (Join-Path $run "weights\last.pt") -Destination (Join-Path $resultStage "weights")
Copy-Item -LiteralPath ".\golden_tests\detector_training_package_v7\training_package_manifest.json" -Destination $stage
foreach ($log in @("training_console_v7.log", "training_resume_console_v7.log")) {
    if (Test-Path -LiteralPath $log) {
        Copy-Item -LiteralPath $log -Destination $stage
    }
}
nvidia-smi | Out-File -LiteralPath (Join-Path $stage "GPU_INFO.txt") -Encoding utf8
Compress-Archive -LiteralPath $stage -DestinationPath $zip -CompressionLevel Optimal
$hash = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash
Write-Host "`nCandidate V7 return ZIP created:" -ForegroundColor Green
Write-Host $zip
Write-Host "SHA256: $hash"
Write-Host "Copy this ZIP back to the OCR laptop. Do not replace production manually."
'@ | Set-Content -LiteralPath (Join-Path $stage "06_PACKAGE_RESULTS.ps1") -Encoding UTF8

@'
# Candidate V7 GPU Training Bundle

Run the numbered PowerShell scripts in order. Candidate V7 starts from V3,
keeps all 966 approved labels, adds diverse regression rehearsal, and does not
change the production model.

To pause safely, press Ctrl+C once and wait for PowerShell to return. Resume
later with 04_RESUME_TRAINING.ps1. Never sleep or shut down while Python is
still training.
'@ | Set-Content -LiteralPath (Join-Path $stage "README_FIRST.md") -Encoding UTF8

Compress-Archive -LiteralPath $stage -DestinationPath $zip -CompressionLevel Optimal
$hash = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash
"$hash  $bundleName.zip" | Set-Content -LiteralPath $hashFile -Encoding ASCII

$report = [ordered]@{
    schema_version = 7
    status = "gpu_bundle_ready_not_trained"
    bundle = $zip
    sha256 = $hash
    starting_model = "candidate_detector_v3_best.pt"
    approved_labels = 966
    production_model_will_change = $false
}
$report | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $golden "V7_GPU_BUNDLE_REPORT.json") -Encoding UTF8
Remove-Item -LiteralPath $stage -Recurse -Force

Write-Host "V7 GPU training bundle created:" -ForegroundColor Green
Write-Host $zip
Write-Host "SHA256: $hash"
