$ErrorActionPreference = "Stop"

function Get-AICarmineEnvValue {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,

        [string]$Default = ""
    )

    foreach ($scope in @("Process", "User", "Machine")) {
        $value = [Environment]::GetEnvironmentVariable($Name, $scope)
        if (-not [string]::IsNullOrWhiteSpace($value)) {
            return $value
        }
    }
    return $Default
}

$HomeAI = Join-Path $env:USERPROFILE "AI"

# Python executable for the openvino venv (used for export_model.py)
$OpenVinoPython = Join-Path $HomeAI "venvs\openvino\Scripts\python.exe"
if (-not (Test-Path $OpenVinoPython)) {
    throw "openvino venv python not found: $OpenVinoPython"
}

$OVMS_ROOT = Get-AICarmineEnvValue "OVMS_ROOT"
$OVMS_EXE = Get-AICarmineEnvValue "OVMS_EXE"
$OVMS_SETUP = Get-AICarmineEnvValue "OVMS_SETUP"
$MODELS = Get-AICarmineEnvValue "OVMS_RERANK_MODELS"
$TARGET_DEVICE = Get-AICarmineEnvValue "OPENVINO_PROVIDER_DEVICE" "GPU.0"

if ([string]::IsNullOrWhiteSpace($OVMS_ROOT)) {
    $OVMS_ROOT = Join-Path $HomeAI "ovms-runtime\ovms"
}
if ([string]::IsNullOrWhiteSpace($OVMS_EXE)) {
    # Check both possible locations: bin\ovms.exe or ovms-root\ovms.exe
    $ovmsBinExe = Join-Path $OVMS_ROOT "bin\ovms.exe"
    if (Test-Path $ovmsBinExe) {
        $OVMS_EXE = $ovmsBinExe
    } else {
        $OVMS_EXE = Join-Path $OVMS_ROOT "ovms.exe"
    }
}
if ([string]::IsNullOrWhiteSpace($OVMS_SETUP)) {
    $OVMS_SETUP = Join-Path $OVMS_ROOT "setupvars.ps1"
}
if ([string]::IsNullOrWhiteSpace($MODELS)) {
    $MODELS = Join-Path $HomeAI "models-ovms-rerank"
}

$Config = Join-Path $MODELS "config.json"

# Guard: ensure all required paths are resolved before proceeding
if ([string]::IsNullOrWhiteSpace($Config)) {
    throw "OVMS config path is null after Join-Path."
}
if (-not (Test-Path $Config)) {
    throw "OVMS config non trovato: $Config"
}
if (-not (Test-Path $OVMS_SETUP)) {
    throw "OVMS setupvars non trovato: $OVMS_SETUP"
}
if (-not (Test-Path $OVMS_EXE)) {
    throw "OVMS exe non trovato: $OVMS_EXE"
}
if ([string]::IsNullOrWhiteSpace($TARGET_DEVICE)) {
    throw "OPENVINO_PROVIDER_DEVICE non configurato per OVMS reranker."
}

# === Model Preparation: Convert HuggingFace model to OpenVINO IR format ===
# OVMS requires OpenVINO IR format (.xml + .bin), not raw ONNX/PyTorch models.
# The export_model.py script downloads, converts, and quantizes the model.

$ExportScript = Join-Path $MODELS "export_model.py"
$ModelsRepo = Join-Path $MODELS "models"
$OvmsConfig = Join-Path $ModelsRepo "config.json"

if (-not (Test-Path $ExportScript)) {
    Write-Host "[INFO] Downloading export_model.py script..."
    $hfUrl = "https://raw.githubusercontent.com/openvinotoolkit/model_server/refs/heads/main/demos/common/export_models/export_model.py"
    Invoke-WebRequest -Uri $hfUrl -OutFile $ExportScript 2>&1 | Out-Null
    Write-Host "[OK] export_model.py downloaded to: $ExportScript"
}

# Create models repository directory
New-Item -ItemType Directory -Force -Path $ModelsRepo | Out-Null

# Run export_model.py to convert and quantize the model
Write-Host "[INFO] Converting model to OpenVINO IR format (target_device=$TARGET_DEVICE)..."
$sourceModel = "BAAI/bge-reranker-v2-m3"
$weightFormat = "fp16"

if ($TARGET_DEVICE -eq "GPU") {
    # GPU benefits from INT8 quantization for better performance
    $weightFormat = "int8"
}

& $OpenVinoPython "$ExportScript" rerank_ov `
    --source_model $sourceModel `
    --weight-format $weightFormat `
    --target_device $TARGET_DEVICE `
    --config_file_path $OvmsConfig `
    --model_repository_path $ModelsRepo

Write-Host "[OK] Model exported to: $ModelsRepo"
Write-Host "[OK] OVMS config generated at: $OvmsConfig"

# === Start OVMS ===

. $OVMS_SETUP

Set-Location $ModelsRepo

Write-Host "OVMS reranker target_device=$TARGET_DEVICE config=$OvmsConfig"

& $OVMS_EXE `
  --rest_port 3550 `
  --rest_bind_address 127.0.0.1 `
  --config_path $OvmsConfig