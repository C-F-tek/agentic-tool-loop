$ErrorActionPreference = "Stop"

$AI_ROOT = "C:\Users\carmi\AI"


$Python = [Environment]::GetEnvironmentVariable("AICARMINE_EXECUTOR_PYTHON", "User")

if ([string]::IsNullOrWhiteSpace($Python)) {
    $Python = "$AI_ROOT\venvs\labtools\Scripts\python.exe"
}

if (-not (Test-Path $Python)) {
    throw "Python executor non trovato: $Python"
}

Remove-Item Env:PYTHONHOME -ErrorAction SilentlyContinue
Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue

$env:AICARMINE_SAFE_COMMAND_RUNNER = [Environment]::GetEnvironmentVariable("AICARMINE_SAFE_COMMAND_RUNNER", "User")
if ([string]::IsNullOrWhiteSpace($env:AICARMINE_SAFE_COMMAND_RUNNER)) {
    $env:AICARMINE_SAFE_COMMAND_RUNNER = "C:\Users\carmi\AI\services\aicarmine-run-safe-command.ps1"
}
$env:AICARMINE_LAB_REPO = [Environment]::GetEnvironmentVariable("AICARMINE_LAB_REPO", "User")
if ([string]::IsNullOrWhiteSpace($env:AICARMINE_LAB_REPO)) {
    $env:AICARMINE_LAB_REPO = "C:\Users\carmi\AI\"
}
$env:AICARMINE_REAL_REPO = [Environment]::GetEnvironmentVariable("AICARMINE_REAL_REPO", "User")
if ([string]::IsNullOrWhiteSpace($env:AICARMINE_REAL_REPO)) {
    $env:AICARMINE_REAL_REPO = "C:\Users\carmi\AI\"
}

Set-Location "$AI_ROOT\services"

& $Python -m uvicorn aicarmine-executor-server:app --host 127.0.0.1 --port 3560
