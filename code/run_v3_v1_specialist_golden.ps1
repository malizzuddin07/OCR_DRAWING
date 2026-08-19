param(
    [Parameter(Mandatory = $true)]
    [string]$RunId,

    [Parameter(Mandatory = $true)]
    [string]$BaselineRoot
)

$ErrorActionPreference = "Stop"
$project = "C:\Users\izzuddin\Desktop\OCR DRAWING"
$python = "C:\Users\izzuddin\python311\python.exe"
$v3 = Join-Path $project "incoming_models\candidate_yolov8s_golden_v3_20260727\golden_detector_v3\weights\best.pt"
$v1 = Join-Path $project "incoming_models\candidate_yolov8s_golden_v1_20260723\best.pt"
$root = Join-Path $project "golden_tests\runs\v3_v1_specialist_$RunId"
$output = Join-Path $root "run_1"
$report = Join-Path $root "gate_report"
$log = Join-Path $root "suite_stdout.log"
$status = Join-Path $root "runner_status.txt"

foreach ($required in @($python, $v3, $v1, $BaselineRoot)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Required path was not found: $required"
    }
}
if (Test-Path -LiteralPath $root) {
    throw "Run folder already exists: $root"
}

New-Item -ItemType Directory -Path $root | Out-Null
Set-Content -LiteralPath $status -Value "RUNNING" -Encoding utf8

$env:ROBOFLOW_ENABLED = "0"
$env:YOLO_SYMBOL_MODEL_PATH = $v3
$env:YOLO_SYMBOL_ENSEMBLE_ADDITION_PATH = $v1
$env:YOLO_SYMBOL_ENSEMBLE_REQUIRED = "1"
$env:YOLO_SYMBOL_CONFIDENCE = "0.60"
$env:YOLO_SYMBOL_ENSEMBLE_ADDITION_CLASSES = "radius,gdt_frame"
$env:YOLO_SYMBOL_ENSEMBLE_PREFERRED_CLASSES = "radius,gdt_frame"
$env:YOLO_SYMBOL_ENSEMBLE_IOU_THRESHOLD = "0.30"
$env:YOLO_SYMBOL_ENSEMBLE_CONTAINMENT_THRESHOLD = "0.70"

Set-Location -LiteralPath $project
$ErrorActionPreference = "Continue"
& $python "code\run_golden_suite.py" `
    --output-root $output `
    --baseline-root $BaselineRoot `
    --report-dir $report `
    --candidate-id "v3-primary-v1-radius-gdt-specialist" 2>&1 |
    Tee-Object -FilePath $log
$exitCode = $LASTEXITCODE
$ErrorActionPreference = "Stop"

$suitePath = Join-Path $output "suite_run.json"
if (Test-Path -LiteralPath $suitePath) {
    $suite = Get-Content -LiteralPath $suitePath -Raw | ConvertFrom-Json
    if ($suite.status -in @("passed", "rejected")) {
        Set-Content -LiteralPath $status -Value "COMPLETED ($($suite.status))" -Encoding utf8
        exit 0
    }
}

Set-Content -LiteralPath $status -Value "FAILED (exit $exitCode)" -Encoding utf8
exit $exitCode
