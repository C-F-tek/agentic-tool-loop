$ErrorActionPreference = "Stop"

$OVMS_ROOT = [Environment]::GetEnvironmentVariable("OVMS_ROOT", "User")
$OVMS_EXE = [Environment]::GetEnvironmentVariable("OVMS_EXE", "User")
$OVMS_SETUP = [Environment]::GetEnvironmentVariable("OVMS_SETUP", "User")
$MODELS = [Environment]::GetEnvironmentVariable("OVMS_RERANK_MODELS", "User")

if ([string]::IsNullOrWhiteSpace($OVMS_ROOT)) {
    $OVMS_ROOT = "C:\Users\carmi\AI\ovms-runtime\ovms"
}
if ([string]::IsNullOrWhiteSpace($OVMS_EXE)) {
    $OVMS_EXE = Join-Path $OVMS_ROOT "bin\ovms.exe"
}
if ([string]::IsNullOrWhiteSpace($OVMS_SETUP)) {
    $OVMS_SETUP = Join-Path $OVMS_ROOT "setupvars.ps1"
}
if ([string]::IsNullOrWhiteSpace($MODELS)) {
    $MODELS = "C:\Users\carmi\AI\models-ovms-rerank"
}

$Config = Join-Path $MODELS "config.json"

if (-not (Test-Path $OVMS_SETUP)) {
    throw "OVMS setupvars non trovato: $OVMS_SETUP"
}
if (-not (Test-Path $OVMS_EXE)) {
    throw "OVMS exe non trovato: $OVMS_EXE"
}
if (-not (Test-Path $Config)) {
    throw "OVMS config non trovato: $Config"
}

. $OVMS_SETUP

Set-Location $MODELS

& $OVMS_EXE `
  --rest_port 3550 `
  --rest_bind_address 127.0.0.1 `
  --config_path $Config