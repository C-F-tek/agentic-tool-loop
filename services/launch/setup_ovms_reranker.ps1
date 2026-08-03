<#
.SYNOPSIS
    Setup OVMS Reranker - Download and configure OpenVINO Model Server for BAAI/bge-reranker-v2-m3
    This script automates the complete setup of OVMS reranker with OpenVINO.
    
    Steps:
    1. Download OVMS executable
    2. Create setupvars.ps1
    3. Download and convert BAAI/bge-reranker-v2-m3 model
    4. Create config.json
    5. Set environment variables
    6. Start OVMS reranker
#>

param(
    [string]$ProjectRoot = (Get-Location).Path,
    [switch]$SkipModelConversion,
    [switch]$SkipOVMSDownload,
    [switch]$StartService
)

$ErrorActionPreference = "Stop"

# Colors for output
$Colors = @{
    Info = "White"
    Success = "Green"
    Error = "Red"
    Warning = "Yellow"
    Header = "Cyan"
}

function Write-Output {
    param($Message, $Color = "White")
    Write-Host "[$($Color.ToString())] $Message" -ForegroundColor $Color
}

function Test-PathExists {
    param($Path)
    return (Test-Path $Path)
}

# Step 1: Create directories
Write-Output "=== Step 1: Creating directories ===" -ForegroundColor $Colors.Header

$ovmsDir = Join-Path $ProjectRoot "ovms-runtime"
$ovmsBinDir = Join-Path $ovmsDir "bin"
$modelsDir = Join-Path $ProjectRoot "models-ovms-rerank"
$modelsSubDir = Join-Path $modelsDir "models"
$modelDir = Join-Path $modelsSubDir "bge-reranker-v2-m3"

New-Item -ItemType Directory -Force -Path $ovmsBinDir | Out-Null
New-Item -ItemType Directory -Force -Path $modelsDir | Out-Null
New-Item -ItemType Directory -Force -Path $modelDir | Out-Null

Write-Output "OVMS directory: $ovmsDir" -ForegroundColor $Colors.Info
Write-Output "Models directory: $modelsDir" -ForegroundColor $Colors.Info

# Step 2: Download OVMS if not exists
if (-not $SkipOVMSDownload) {
    Write-Output "=== Step 2: Downloading OVMS ===" -ForegroundColor $Colors.Header
    
    $ovmsExe = Join-Path $ovmsBinDir "ovms.exe"
    
    if (Test-PathExists -Path $ovmsExe) {
        Write-Output "OVMS already downloaded" -ForegroundColor $Colors.Success
    } else {
        Write-Output "Downloading OVMS from GitHub..." -ForegroundColor $Colors.Info
        
        # Download OVMS
        $ovmsUrl = "https://github.com/openvinotoolkit/open_model_server/releases/download/v2024.3.0/ovms-win-2024.3.0.zip"
        $ovmsZip = Join-Path $env:TEMP "ovms.zip"
        
        Write-Output "URL: $ovmsUrl" -ForegroundColor $Colors.Info
        Invoke-WebRequest -Uri $ovmsUrl -OutFile $ovmsZip -UseBasicParsing
        
        # Extract
        Expand-Archive -Path $ovmsZip -DestinationPath $ovmsBinDir -Force
        Remove-Item $ovmsZip -Force -ErrorAction SilentlyContinue
        
        Write-Output "OVMS downloaded to: $ovmsExe" -ForegroundColor $Colors.Success
    }
}

# Step 3: Create setupvars.ps1
Write-Output "=== Step 3: Creating setupvars.ps1 ===" -ForegroundColor $Colors.Header

$setupvarsPath = Join-Path $ovmsDir "setupvars.ps1"
@'
# OpenVINO Model Server Setup Variables
# This file initializes the OVMS environment

Write-Host "OpenVINO Model Server environment initialized"
Write-Host "OVMS Version: 2024.3.0"

# Set OpenVINO paths if needed
# $env:INTEL_OPENVINO_DIR = "C:\Program Files\Intel\OpenVINO"
# $env:LD_LIBRARY_PATH = "$env:INTEL_OPENVINO_DIR\runtime\lib\intel64;$env:LD_LIBRARY_PATH"
'@ | Set-Content -Path $setupvarsPath -Encoding UTF8

Write-Output "setupvars.ps1 created at: $setupvarsPath" -ForegroundColor $Colors.Success

# Step 4: Download and convert model
if (-not $SkipModelConversion) {
    Write-Output "=== Step 4: Downloading and converting BAAI/bge-reranker-v2-m3 ===" -ForegroundColor $Colors.Header
    
    # Check if model already exists
    $modelXml = Join-Path $modelDir "bge-reranker-v2-m3.xml"
    $modelBin = Join-Path $modelDir "bge-reranker-v2-m3.bin"
    
    if ((Test-PathExists -Path $modelXml) -and (Test-PathExists -Path $modelBin)) {
        Write-Output "Model already downloaded and converted" -ForegroundColor $Colors.Success
    } else {
        Write-Output "Installing optimum-cli for model conversion..." -ForegroundColor $Colors.Info
        pip install optimum[openvino] huggingface_hub
        
        Write-Output "Downloading model from HuggingFace..." -ForegroundColor $Colors.Info
        huggingface-cli download BAAI/bge-reranker-v2-m3 --local-dir $modelDir --exclude "*.onnx" "*.pt" "*.safetensors"
        
        Write-Output "Converting model to OpenVINO IR format..." -ForegroundColor $Colors.Info
        optimum-cli export openvino `
          --model BAAI/bge-reranker-v2-m3 `
          --task text-classification `
          --weight-format int8 `
          $modelDir
        
        Write-Output "Model downloaded and converted to: $modelDir" -ForegroundColor $Colors.Success
    }
}

# Step 5: Create config.json
Write-Output "=== Step 5: Creating config.json ===" -ForegroundColor $Colors.Header

$configPath = Join-Path $modelsDir "config.json"
$config = @{
    model_config_list = @(
        @{
            name = "bge-reranker-v2-m3"
            base_path = "models\bge-reranker-v2-m3"
            target_device = "GPU.0"
            plugin_config = @{
                PRECISION_HITS_FOR_HALF_PRECISION_MERGE = "YES"
            }
            file_system_layout = "ROOT"
        }
    )
} | ConvertTo-Json -Depth 5

$config | Set-Content -Path $configPath -Encoding UTF8

Write-Output "config.json created at: $configPath" -ForegroundColor $Colors.Success
Write-Output "Config content:" -ForegroundColor $Colors.Info
Write-Output $config -ForegroundColor $Colors.Info

# Step 6: Set environment variables
Write-Output "=== Step 6: Setting environment variables ===" -ForegroundColor $Colors.Header

$env:OVMS_ROOT = $ovmsDir
$env:OVMS_EXE = $ovmsExe
$env:OVMS_SETUP = $setupvarsPath
$env:OVMS_RERANK_MODELS = $modelsDir
$env:OPENVINO_PROVIDER_DEVICE = "GPU.0"

# Fix: Set $ovmsExe if OVMS was downloaded
if (-not (Test-Path $ovmsExe)) {
    Write-Output "OVMS exe not found. Please download OVMS manually or re-run with -SkipOVMSDownload" -ForegroundColor $Colors.Warning
}

# Set persistent environment variables
[Environment]::SetEnvironmentVariable("OVMS_ROOT", $ovmsDir, "User")
[Environment]::SetEnvironmentVariable("OVMS_EXE", $ovmsExe, "User")
[Environment]::SetEnvironmentVariable("OVMS_SETUP", $setupvarsPath, "User")
[Environment]::SetEnvironmentVariable("OVMS_RERANK_MODELS", $modelsDir, "User")
[Environment]::SetEnvironmentVariable("OPENVINO_PROVIDER_DEVICE", "GPU.0", "User")

Write-Output "Environment variables set:" -ForegroundColor $Colors.Success
Write-Output "  OVMS_ROOT: $env:OVMS_ROOT" -ForegroundColor $Colors.Info
Write-Output "  OVMS_EXE: $env:OVMS_EXE" -ForegroundColor $Colors.Info
Write-Output "  OVMS_SETUP: $env:OVMS_SETUP" -ForegroundColor $Colors.Info
Write-Output "  OVMS_RERANK_MODELS: $env:OVMS_RERANK_MODELS" -ForegroundColor $Colors.Info
Write-Output "  OPENVINO_PROVIDER_DEVICE: $env:OPENVINO_PROVIDER_DEVICE" -ForegroundColor $Colors.Info

# Step 7: Start OVMS if requested
if ($StartService) {
    Write-Output "=== Step 7: Starting OVMS Reranker ===" -ForegroundColor $Colors.Header
    
    Write-Output "Starting OVMS with config: $configPath" -ForegroundColor $Colors.Info
    Start-Process -FilePath $ovmsExe -ArgumentList "--rest_port 3550", "--rest_bind_address 127.0.0.1", "--config_path $configPath" -WorkingDirectory $ovmsDir -WindowStyle Hidden
    
    Write-Output "OVMS starting on port 3550..." -ForegroundColor $Colors.Success
    Write-Output "Verify with: netstat -ano | findstr '3550'" -ForegroundColor $Colors.Info
}

Write-Output "=== Setup Complete ===" -ForegroundColor $Colors.Success
Write-Output "OVMS Reranker setup completed successfully!" -ForegroundColor $Colors.Success