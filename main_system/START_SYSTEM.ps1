param(
    [string]$HostAddress = "127.0.0.1",
    [int]$Port = 8001
)

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    $python = "python"
}

& $python -m uvicorn webapp.server:app --host $HostAddress --port $Port
