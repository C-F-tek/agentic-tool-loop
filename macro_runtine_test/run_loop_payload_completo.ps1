param(
    [string]$Seed = "",
    [int]$WaitSeconds = 240,
    [int]$MaxSteps = 8,
    [string]$OnlyTool = "",
    [int]$MaxTools = 0,
    [string]$RunId = ""
)

$ErrorActionPreference = "Stop"

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptRoot "..")

$PythonCandidates = @(
    (Join-Path $RepoRoot "venvs\labtools\Scripts\python.exe"),
    (Join-Path $RepoRoot ".venv\Scripts\python.exe"),
    "python"
)

$Python = $null
foreach ($candidate in $PythonCandidates) {
    if ($candidate -eq "python") {
        $Python = $candidate
        break
    }
    if (Test-Path $candidate) {
        $Python = $candidate
        break
    }
}

if (-not $Python) {
    throw "Python runtime not found."
}

$env:AICARMINE_OPERATOR_PRESENT = "1"
$env:LOOP_PAYLOAD_WAIT_SECONDS = [string]$WaitSeconds
$env:LOOP_PAYLOAD_MAX_STEPS = [string]$MaxSteps
if ($Seed) { $env:LOOP_PAYLOAD_SEED = $Seed }
if ($OnlyTool) { $env:LOOP_PAYLOAD_ONLY_TOOL = $OnlyTool }
if ($MaxTools -gt 0) { $env:LOOP_PAYLOAD_MAX_TOOLS = [string]$MaxTools }
$LaunchNonce = "{0}-{1}" -f (Get-Date -Format "yyyyMMddHHmmssffff"), ([guid]::NewGuid().ToString("N").Substring(0, 12))
if ($RunId) {
    $EffectiveRunId = "{0}-{1}" -f $RunId, $LaunchNonce
} else {
    $EffectiveRunId = $LaunchNonce
}
$env:LOOP_PAYLOAD_RUN_ID = $EffectiveRunId
$env:LOOP_PAYLOAD_LAUNCH_ID = $LaunchNonce

Write-Host "Running operator-only macro loop payload test"
Write-Host "Repo root: $RepoRoot"
Write-Host "Python: $Python"
Write-Host "WaitSeconds: $WaitSeconds MaxSteps: $MaxSteps"
if ($Seed) { Write-Host "Seed: $Seed" }
if ($OnlyTool) { Write-Host "OnlyTool: $OnlyTool" }
if ($MaxTools -gt 0) { Write-Host "MaxTools: $MaxTools" }
Write-Host "RunId: $EffectiveRunId"

& $Python -m pytest (Join-Path $ScriptRoot "test_loop_payload_completo.py") -q -s --tb=short
exit $LASTEXITCODE
