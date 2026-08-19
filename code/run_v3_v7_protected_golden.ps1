param(
    [Parameter(Mandatory = $true)]
    [string]$RunId
)

$ErrorActionPreference = "Stop"
$project = "C:\Users\izzuddin\Desktop\OCR DRAWING"
$python = "C:\Users\izzuddin\python311\python.exe"
$v3 = Join-Path $project "incoming_models\candidate_yolov8s_golden_v3_20260727\golden_detector_v3\weights\best.pt"
$v7 = Join-Path $project "incoming_models\candidate_yolov8s_golden_v7_20260803\golden_detector_v7\weights\best.pt"
$root = Join-Path $project "golden_tests\runs\v3_v7_protected_$RunId"
$output = Join-Path $root "run_1"
$report = Join-Path $root "gate_report"
$log = Join-Path $root "suite_stdout.log"
$status = Join-Path $root "runner_status.txt"

foreach ($required in @($python, $v3, $v7)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Required file was not found: $required"
    }
}
if (Test-Path -LiteralPath $root) {
    throw "Run folder already exists: $root"
}

New-Item -ItemType Directory -Path $root | Out-Null
Set-Content -LiteralPath $status -Value "RUNNING" -Encoding utf8

$env:ROBOFLOW_ENABLED = "0"
$env:YOLO_SYMBOL_MODEL_PATH = $v3
$env:YOLO_SYMBOL_CONFIDENCE = "0.60"
$env:YOLO_SYMBOL_ENSEMBLE_ADDITION_PATH = $v7
$env:YOLO_SYMBOL_ENSEMBLE_ADDITION_CONFIDENCE = "0.50"
$env:YOLO_SYMBOL_ENSEMBLE_REQUIRED = "1"
$env:YOLO_SYMBOL_ENSEMBLE_IOU_THRESHOLD = "0.50"
$env:YOLO_SYMBOL_ENSEMBLE_CONTAINMENT_ENABLED = "0"
$env:YOLO_SYMBOL_TILING_ENABLED = "1"
$env:YOLO_SYMBOL_TILE_SIZE = "1280"
$env:YOLO_SYMBOL_TILE_OVERLAP = "320"
Remove-Item Env:YOLO_SYMBOL_ENSEMBLE_ADDITION_CLASSES -ErrorAction SilentlyContinue
Remove-Item Env:YOLO_SYMBOL_ENSEMBLE_PREFERRED_CLASSES -ErrorAction SilentlyContinue

Set-Location -LiteralPath $project
$ErrorActionPreference = "Continue"
& $python "code\run_golden_suite.py" `
    --output-root $output `
    --report-dir $report `
    --candidate-id "v3-060-protected-v7-050" 2>&1 |
    Tee-Object -FilePath $log
$exitCode = $LASTEXITCODE
$ErrorActionPreference = "Stop"

if ($exitCode -eq 0) {
    Set-Content -LiteralPath $status -Value "COMPLETED" -Encoding utf8
} else {
    Set-Content -LiteralPath $status -Value "REJECTED_OR_FAILED (exit $exitCode)" -Encoding utf8
}
exit $exitCode
