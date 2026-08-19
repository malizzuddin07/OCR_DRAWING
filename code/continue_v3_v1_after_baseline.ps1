param(
    [Parameter(Mandatory = $true)]
    [string]$BaselineRunId,

    [Parameter(Mandatory = $true)]
    [string]$CandidateRunId
)

$ErrorActionPreference = "Stop"
$project = "C:\Users\izzuddin\Desktop\OCR DRAWING"
$baselineRoot = Join-Path $project "golden_tests\runs\v3_only_baseline_$BaselineRunId"
$baselineOutput = Join-Path $baselineRoot "run_1"
$baselineStatus = Join-Path $baselineRoot "runner_status.txt"
$candidateScript = Join-Path $project "code\run_v3_v1_specialist_golden.ps1"
$sequenceStatus = Join-Path $baselineRoot "continuation_status.txt"
$expectedDrawings = @(
    "W3-C171246401-00",
    "C3010-035-250F",
    "W3-C111262801-2A",
    "W3-C111265901-03",
    "W3-C111266801-01"
)

foreach ($required in @($baselineRoot, $candidateScript)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Required path was not found: $required"
    }
}

Set-Content -LiteralPath $sequenceStatus -Value "WAITING_FOR_V3_BASELINE" -Encoding utf8

while ($true) {
    if (Test-Path -LiteralPath $baselineStatus) {
        $state = (Get-Content -LiteralPath $baselineStatus -Raw).Trim()
        if ($state.StartsWith("FAILED")) {
            Set-Content -LiteralPath $sequenceStatus -Value "BLOCKED: $state" -Encoding utf8
            exit 1
        }
        if ($state.StartsWith("COMPLETED")) {
            break
        }
    }
    Start-Sleep -Seconds 30
}

foreach ($drawing in $expectedDrawings) {
    $excel = Join-Path $baselineOutput "$drawing\fa_inspection_report.xlsx"
    $pdf = Join-Path $baselineOutput "$drawing\ballooned.pdf"
    if (-not (Test-Path -LiteralPath $excel) -or -not (Test-Path -LiteralPath $pdf)) {
        Set-Content -LiteralPath $sequenceStatus -Value "BLOCKED: incomplete baseline output for $drawing" -Encoding utf8
        exit 1
    }
}

Set-Content -LiteralPath $sequenceStatus -Value "STARTING_V3_V1_SPECIALIST" -Encoding utf8
& $candidateScript -RunId $CandidateRunId -BaselineRoot $baselineOutput
$exitCode = $LASTEXITCODE

if ($exitCode -eq 0) {
    Set-Content -LiteralPath $sequenceStatus -Value "SPECIALIST_RUN_COMPLETED" -Encoding utf8
} else {
    Set-Content -LiteralPath $sequenceStatus -Value "SPECIALIST_RUN_FAILED (exit $exitCode)" -Encoding utf8
}
exit $exitCode
