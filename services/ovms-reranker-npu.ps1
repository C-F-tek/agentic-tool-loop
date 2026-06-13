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

function Assert-OvmsRerankerDeviceContract {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ConfigPath,

        [Parameter(Mandatory = $true)]
        [string]$ModelsRoot,

        [Parameter(Mandatory = $true)]
        [string]$TargetDevice
    )

    $rawConfig = Get-Content -LiteralPath $ConfigPath -Raw -Encoding UTF8
    $config = $rawConfig | ConvertFrom-Json
    if ($null -eq $config.model_config_list -or $config.model_config_list.Count -lt 1) {
        throw "OVMS reranker config senza model_config_list: $ConfigPath"
    }

    foreach ($entry in $config.model_config_list) {
        if ($null -eq $entry.config) {
            throw "OVMS reranker config entry senza config: $ConfigPath"
        }
        $name = [string]$entry.config.name
        $basePath = [string]$entry.config.base_path
        $entryDevice = [string]$entry.config.target_device
        if ([string]::IsNullOrWhiteSpace($entryDevice)) {
            throw "OVMS reranker config '$name' senza target_device; atteso $TargetDevice."
        }
        if ($entryDevice -ne $TargetDevice) {
            throw "OVMS reranker config '$name' target_device=$entryDevice, atteso $TargetDevice."
        }
        if ([string]::IsNullOrWhiteSpace($basePath)) {
            throw "OVMS reranker config '$name' senza base_path."
        }
        $graphPath = Join-Path (Join-Path $ModelsRoot $basePath) "graph.pbtxt"
        if (-not (Test-Path -LiteralPath $graphPath)) {
            throw "OVMS reranker graph non trovato per '$name': $graphPath"
        }
        $graphText = Get-Content -LiteralPath $graphPath -Raw -Encoding UTF8
        $expectedGraphLine = "target_device: `"$TargetDevice`""
        if (-not $graphText.Contains($expectedGraphLine)) {
            throw "OVMS reranker graph '$graphPath' non dichiara $expectedGraphLine."
        }
    }
}

$OVMS_ROOT = Get-AICarmineEnvValue "OVMS_ROOT"
$OVMS_EXE = Get-AICarmineEnvValue "OVMS_EXE"
$OVMS_SETUP = Get-AICarmineEnvValue "OVMS_SETUP"
$MODELS = Get-AICarmineEnvValue "OVMS_RERANK_MODELS"
$TARGET_DEVICE = Get-AICarmineEnvValue "OPENVINO_PROVIDER_DEVICE" "GPU.0"

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
if ([string]::IsNullOrWhiteSpace($TARGET_DEVICE)) {
    throw "OPENVINO_PROVIDER_DEVICE non configurato per OVMS reranker."
}

Assert-OvmsRerankerDeviceContract `
  -ConfigPath $Config `
  -ModelsRoot $MODELS `
  -TargetDevice $TARGET_DEVICE

. $OVMS_SETUP

Set-Location $MODELS

Write-Host "OVMS reranker target_device=$TARGET_DEVICE config=$Config"

& $OVMS_EXE `
  --rest_port 3550 `
  --rest_bind_address 127.0.0.1 `
  --config_path $Config
