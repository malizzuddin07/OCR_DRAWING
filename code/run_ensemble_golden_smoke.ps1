param(
    [Parameter(Mandatory = $true)]
    [string]$RunId
)

$ErrorActionPreference = "Stop"
$project = "C:\Users\izzuddin\Desktop\OCR DRAWING"
$python = "C:\Users\izzuddin\python311\python.exe"
$v3 = Join-Path $project "incoming_models\candidate_yolov8s_golden_v3_20260727\golden_detector_v3\weights\best.pt"
$v5 = Join-Path $project "incoming_models\candidate_yolov8s_golden_v5_20260728\return_results_v5_20260728_165416\golden_detector_v5\weights\best.pt"
$root = Join-Path $project "golden_tests\runs\ensemble_v3_v5_smoke_$RunId"
$output = Join-Path $root "run_1"
$report = Join-Path $root "gate_report"
$log = Join-Path $root "suite_stdout.log"
$status = Join-Path $root "runner_status.txt"

foreach ($required in @($python, $v3, $v5)) {
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
$env:YOLO_SYMBOL_ENSEMBLE_ADDITION_PATH = $v5
$env:YOLO_SYMBOL_ENSEMBLE_REQUIRED = "1"
$env:YOLO_SYMBOL_CONFIDENCE = "0.60"
$env:YOLO_SYMBOL_ENSEMBLE_IOU_THRESHOLD = "0.30"
$env:YOLO_SYMBOL_ENSEMBLE_CONTAINMENT_THRESHOLD = "0.70"

Set-Location -LiteralPath $project
$ErrorActionPreference = "Continue"
& $python "code\run_golden_suite.py" `
    --output-root $output `
    --report-dir $report `
    --candidate-id "v3-priority-v5-ensemble" 2>&1 |
    Tee-Object -FilePath $log
$exitCode = $LASTEXITCODE
$ErrorActionPreference = "Stop"

if ($exitCode -eq 0) {
    Set-Content -LiteralPath $status -Value "COMPLETED" -Encoding utf8
} else {
    Set-Content -LiteralPath $status -Value "FAILED (exit $exitCode)" -Encoding utf8
}
exit $exitCode
