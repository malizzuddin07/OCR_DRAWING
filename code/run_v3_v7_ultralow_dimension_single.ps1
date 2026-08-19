param(
    [Parameter(Mandatory = $true)]
    [string]$RunId,

    [Parameter(Mandatory = $false)]
    [string]$DrawingNumber = "W3-C111266801-01"
)

$ErrorActionPreference = "Stop"
$project = "C:\Users\izzuddin\Desktop\OCR DRAWING"
$python = "C:\Users\izzuddin\python311\python.exe"
$safeDrawingNumber = $DrawingNumber -replace '[^A-Za-z0-9._-]', '_'
$pdf = Join-Path $project "golden_tests\drawings\$DrawingNumber.pdf"
$v3 = Join-Path $project "incoming_models\candidate_yolov8s_golden_v3_20260727\golden_detector_v3\weights\best.pt"
$v7 = Join-Path $project "incoming_models\candidate_yolov8s_golden_v7_20260803\golden_detector_v7\weights\best.pt"
$root = Join-Path $project "golden_tests\runs\v3_v7_ultralow_dimension_single_${safeDrawingNumber}_$RunId"
$job = Join-Path $root "job"
$log = Join-Path $root "console.log"

foreach ($required in @($python, $pdf, $v3, $v7)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Required file was not found: $required"
    }
}
if (Test-Path -LiteralPath $root) {
    throw "Run folder already exists: $root"
}
New-Item -ItemType Directory -Path $root | Out-Null

# Protected experiment. V3 remains the normal primary detector. V7 can only
# propose dimension text at ultra-low confidence, and every proposal must pass
# Paddle recognition plus engineering-value parsing before report inclusion.
$env:ROBOFLOW_ENABLED = "0"
$env:YOLO_SYMBOL_MODEL_PATH = $v3
$env:YOLO_SYMBOL_CONFIDENCE = "0.60"
$env:YOLO_SYMBOL_ENSEMBLE_ADDITION_PATH = $v7
$env:YOLO_SYMBOL_ENSEMBLE_ADDITION_CONFIDENCE = "0.01"
$env:YOLO_SYMBOL_ENSEMBLE_ADDITION_CLASSES = "dimension_text"
$env:YOLO_SYMBOL_ENSEMBLE_REQUIRED = "1"
$env:YOLO_SYMBOL_ENSEMBLE_IOU_THRESHOLD = "0.50"
$env:YOLO_SYMBOL_ENSEMBLE_CONTAINMENT_ENABLED = "0"
$env:YOLO_SYMBOL_TILING_ENABLED = "1"
$env:YOLO_SYMBOL_TILE_SIZE = "1280"
$env:YOLO_SYMBOL_TILE_OVERLAP = "320"
$env:YOLO_TEXT_OCR_MIN_DETECTOR_CONFIDENCE = "0.01"
$env:YOLO_GDT_OCR_MIN_DETECTOR_CONFIDENCE = "0.20"
Remove-Item Env:YOLO_SYMBOL_ENSEMBLE_PREFERRED_CLASSES -ErrorAction SilentlyContinue

Set-Location -LiteralPath $project
$previousErrorActionPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"
try {
    & $python "code\run_single_tiled_candidate.py" `
        --pdf $pdf `
        --output-dir $job 2>&1 |
        Tee-Object -FilePath $log
    $pythonExitCode = $LASTEXITCODE
}
finally {
    $ErrorActionPreference = $previousErrorActionPreference
}

if ($pythonExitCode -ne 0) {
    throw "Protected OCR runner failed with exit code $pythonExitCode. See: $log"
}
exit 0
