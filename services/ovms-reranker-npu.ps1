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
        # base_path may be absolute or relative; handle both
        if ([System.IO.Path]::IsPathRooted($basePath)) {
            $graphPath = Join-Path $basePath "graph.pbtxt"
        } else {
            $graphPath = Join-Path (Join-Path $ModelsRoot $basePath) "graph.pbtxt"
        }
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

# Use dynamic path relative to current working directory instead of hardcoded paths
$CurrentDir = Split-Path -Parent (Get-Location)

# Determine the actual repo root:
# - Always prefer C:\Users\sanit\agentic-tool-loop as the canonical repo root
# - Fall back to CurrentDir if .git exists there
$CanonicalRepoRoot = "C:\Users\sanit\agentic-tool-loop"
if (Test-Path (Join-Path $CanonicalRepoRoot ".git")) {
    $ActualRepoRoot = $CanonicalRepoRoot
} elseif (Test-Path (Join-Path $CurrentDir ".git")) {
    # Already at repo root
    $ActualRepoRoot = $CurrentDir
} elseif ((Split-Path -Leaf $CurrentDir) -eq "agentic-tool-loop") {
    $PotentialRoot = Split-Path -Parent $CurrentDir
    if (Test-Path (Join-Path $PotentialRoot ".git")) {
        $ActualRepoRoot = $PotentialRoot
    } else {
        $ActualRepoRoot = $CurrentDir
    }
}

$OVMS_ROOT = Get-AICarmineEnvValue "OVMS_ROOT"
$OVMS_EXE = Get-AICarmineEnvValue "OVMS_EXE"
$OVMS_SETUP = Get-AICarmineEnvValue "OVMS_SETUP"
$MODELS = Get-AICarmineEnvValue "OVMS_RERANK_MODELS"
# Override env var if it points to wrong/stale location (not under agentic-tool-loop)
if ($MODELS -and $MODELS -notlike "*agentic-tool-loop*") {
    $MODELS = Join-Path $ActualRepoRoot "services\launch\models-ovms-rerank"
}
# Read OPENVINO_PROVIDER_DEVICE from User/Machine scope only (skip Process to avoid stale values)
$TARGET_DEVICE = ""
foreach ($scope in @("User", "Machine")) {
    $val = [Environment]::GetEnvironmentVariable("OPENVINO_PROVIDER_DEVICE", $scope)
    if (-not [string]::IsNullOrWhiteSpace($val)) {
        $TARGET_DEVICE = $val
        break
    }
}
if ([string]::IsNullOrWhiteSpace($TARGET_DEVICE)) {
    # Read from config.json if env var not set
    $ConfigPath = Join-Path $MODELS "config.json"
    if (Test-Path $ConfigPath) {
        $ConfigJson = Get-Content -LiteralPath $ConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
        $TARGET_DEVICE = [string]$ConfigJson.model_config_list[0].config.target_device
    }
}
if ([string]::IsNullOrWhiteSpace($TARGET_DEVICE)) {
    $TARGET_DEVICE = "GPU.0"
}

if ([string]::IsNullOrWhiteSpace($OVMS_ROOT)) {
    # Path 1: ovms-runtime/ovms at project root (C:\Users\sanit\agentic-tool-loop\ovms-runtime\ovms)
    $CandidateOVMSRoot = Join-Path $ActualRepoRoot "ovms-runtime\ovms"
    if (Test-Path $CandidateOVMSRoot) {
        $OVMS_ROOT = $CandidateOVMSRoot
    } else {
        # Path 2: ovms-runtime/ovms relative to current dir
        $CandidateOVMSRoot2 = Join-Path $CurrentDir "ovms-runtime\ovms"
        if (Test-Path $CandidateOVMSRoot2) {
            $OVMS_ROOT = $CandidateOVMSRoot2
        } else {
            # Path 3: services/launch/ovms-runtime
            $CandidateOVMSRoot3 = Join-Path $ActualRepoRoot "services\launch\ovms-runtime"
            if (Test-Path $CandidateOVMSRoot3) {
                $OVMS_ROOT = $CandidateOVMSRoot3
            } else {
                throw "OVMS root non trovato in nessun percorso noto"
            }
        }
    }
}
if ([string]::IsNullOrWhiteSpace($OVMS_EXE)) {
    # Path 1: ovms-runtime\ovms\ovms.exe (actual structure)
    $Candidate1 = Join-Path $OVMS_ROOT "ovms\ovms.exe"
    if (Test-Path $Candidate1) {
        $OVMS_EXE = $Candidate1
    } else {
        # Path 2: ovms-runtime\bin\ovms.exe (legacy structure)
        $OVMS_EXE = Join-Path $OVMS_ROOT "bin\ovms.exe"
    }
}
if ([string]::IsNullOrWhiteSpace($OVMS_SETUP)) {
    $OVMS_SETUP = Join-Path $OVMS_ROOT "setupvars.ps1"
}
if ([string]::IsNullOrWhiteSpace($MODELS)) {
    function Test-OvmsConfigValid {
        param([string]$Path)
        if (-not (Test-Path (Join-Path $Path "config.json"))) { return $false }
        try {
            $raw = Get-Content -LiteralPath (Join-Path $Path "config.json") -Raw -Encoding UTF8
            $j = $raw | ConvertFrom-Json
            if ($null -eq $j.model_config_list -or $j.model_config_list.Count -lt 1) { return $false }
            foreach ($entry in $j.model_config_list) {
                if ($null -eq $entry.config) { return $false }
                $cn = [string]$entry.config.name
                if ([string]::IsNullOrWhiteSpace($cn)) { return $false }
                $bp = [string]$entry.config.base_path
                if ([string]::IsNullOrWhiteSpace($bp)) { return $false }
                $td = [string]$entry.config.target_device
                if ([string]::IsNullOrWhiteSpace($td)) { return $false }
                # Verify graph file exists for this entry
                if ([System.IO.Path]::IsPathRooted($bp)) {
                    $gp = Join-Path $bp "graph.pbtxt"
                } else {
                    $gp = Join-Path (Join-Path $Path $bp) "graph.pbtxt"
                }
                if (-not (Test-Path -LiteralPath $gp)) { return $false }
            }
            return $true
        } catch {
            return $false
        }
    }

    # Path 1: services/launch/models-ovms-rerank at repo root
    $CandidateModels = Join-Path $ActualRepoRoot "services\launch\models-ovms-rerank"
    if (Test-OvmsConfigValid $CandidateModels) {
        $MODELS = $CandidateModels
    }
    if ([string]::IsNullOrWhiteSpace($MODELS)) {
        # Path 2: services/launch/models-ovms-rerank relative to current dir
        $CandidateModels2 = Join-Path $CurrentDir "services\launch\models-ovms-rerank"
        if (Test-OvmsConfigValid $CandidateModels2) {
            $MODELS = $CandidateModels2
        }
    }
    if ([string]::IsNullOrWhiteSpace($MODELS)) {
        # Path 3: launch/models-ovms-rerank relative to current dir
        $CandidateModels3 = Join-Path $CurrentDir "launch\models-ovms-rerank"
        if (Test-OvmsConfigValid $CandidateModels3) {
            $MODELS = $CandidateModels3
        }
    }
    if ([string]::IsNullOrWhiteSpace($MODELS)) {
        # Path 4: models-ovms-rerank at current dir
        $CandidateModels4 = Join-Path $CurrentDir "models-ovms-rerank"
        if (Test-OvmsConfigValid $CandidateModels4) {
            $MODELS = $CandidateModels4
        }
    }
    if ([string]::IsNullOrWhiteSpace($MODELS)) {
        throw "OVMS models non trovato o config.json invalido in nessun percorso noto"
    }
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