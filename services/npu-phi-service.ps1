param(
    [switch]$Doctor
)

$ErrorActionPreference = "Stop"

$AI_ROOT = [Environment]::GetEnvironmentVariable("AI_ROOT", "Process")
if ([string]::IsNullOrWhiteSpace($AI_ROOT)) {
    $AI_ROOT = [Environment]::GetEnvironmentVariable("AI_ROOT", "User")
}
if ([string]::IsNullOrWhiteSpace($AI_ROOT)) {
    $AI_ROOT = "C:\Users\carmi\AI"
}

$Python = [Environment]::GetEnvironmentVariable("NPU_PHI_PYTHON_EXE", "Process")
if ([string]::IsNullOrWhiteSpace($Python)) {
    $Python = [Environment]::GetEnvironmentVariable("NPU_PHI_PYTHON_EXE", "User")
}
if ([string]::IsNullOrWhiteSpace($Python)) {
    $Python = Join-Path $AI_ROOT "venvs\openvino\Scripts\python.exe"
}

$EnvScript = [Environment]::GetEnvironmentVariable("NPU_PHI_ENV_SCRIPT", "Process")
if ([string]::IsNullOrWhiteSpace($EnvScript)) {
    $EnvScript = [Environment]::GetEnvironmentVariable("NPU_PHI_ENV_SCRIPT", "User")
}
if ([string]::IsNullOrWhiteSpace($EnvScript)) {
    $EnvScript = Join-Path $AI_ROOT "services\openvino-env.ps1"
}

$ModelDir = [Environment]::GetEnvironmentVariable("NPU_PHI_MODEL_DIR", "Process")
if ([string]::IsNullOrWhiteSpace($ModelDir)) {
    $ModelDir = [Environment]::GetEnvironmentVariable("NPU_PHI_MODEL_DIR", "User")
}
if ([string]::IsNullOrWhiteSpace($ModelDir)) {
    $ModelDir = Join-Path $AI_ROOT "npu-models\Phi-3.5-mini-instruct-int4-cw-ov"
}

$HostName = [Environment]::GetEnvironmentVariable("NPU_PHI_HOST", "Process")
if ([string]::IsNullOrWhiteSpace($HostName)) { $HostName = "127.0.0.1" }
$Port = [Environment]::GetEnvironmentVariable("NPU_PHI_PORT", "Process")
if ([string]::IsNullOrWhiteSpace($Port)) { $Port = "3551" }

if (-not (Test-Path $Python)) {
    throw "NPU Phi Python non trovato: $Python"
}
if (-not (Test-Path $EnvScript)) {
    throw "NPU Phi env script non trovato: $EnvScript"
}
if (-not (Test-Path (Join-Path $ModelDir "openvino_model.xml"))) {
    throw "NPU Phi openvino_model.xml non trovato: $ModelDir"
}
if (-not (Test-Path (Join-Path $ModelDir "openvino_model.bin"))) {
    throw "NPU Phi openvino_model.bin non trovato: $ModelDir"
}

. $EnvScript

$env:AI_ROOT = $AI_ROOT
$env:NPU_PHI_MODEL_DIR = $ModelDir
if ([string]::IsNullOrWhiteSpace($env:NPU_PHI_CACHE_DIR)) {
    $env:NPU_PHI_CACHE_DIR = Join-Path $AI_ROOT "cache\openvino\npu_phi"
}
if ([string]::IsNullOrWhiteSpace($env:NPU_PHI_SPOOL_DIR)) {
    $env:NPU_PHI_SPOOL_DIR = Join-Path $AI_ROOT "state\npu_phi\spool"
}
if ([string]::IsNullOrWhiteSpace($env:NPU_PHI_GENERATE_HINT)) {
    $env:NPU_PHI_GENERATE_HINT = "FAST_COMPILE"
}

New-Item -ItemType Directory -Force -Path `
    $env:NPU_PHI_CACHE_DIR, `
    $env:NPU_PHI_SPOOL_DIR | Out-Null

$ServicePath = Join-Path $AI_ROOT "services"
if ([string]::IsNullOrWhiteSpace($env:PYTHONPATH)) {
    $env:PYTHONPATH = $ServicePath
}
elseif ($env:PYTHONPATH -notlike "*$ServicePath*") {
    $env:PYTHONPATH = "$ServicePath;$env:PYTHONPATH"
}

$PortInt = [int]$Port
if ($Doctor) {
    Write-Host "Running NPU Phi sidecar doctor"
    Write-Host "  Python = $Python"
    Write-Host "  Model  = $ModelDir"
    Write-Host "  URL    = http://$HostName`:$Port"
    & $Python -m npu_phi_service --host $HostName --port $PortInt --doctor --pretty
    exit $LASTEXITCODE
}

Write-Host "Starting NPU Phi sidecar"
Write-Host "  Python = $Python"
Write-Host "  Model  = $ModelDir"
Write-Host "  URL    = http://$HostName`:$Port"

& $Python -m npu_phi_service --host $HostName --port $PortInt
