#hi l'ha ==================================================================
# Standalone Services Launcher - Independent of OpenWebUI
# ==================================================================
# This script launches backend services that can operate independently
# without OpenWebUI. Each service is started and verified separately.
#
# Usage: powershell -ExecutionPolicy Bypass -File launch_standalone_services.ps1
# ==================================================================

$ErrorActionPreference = "Continue"

# ------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------
$RepoRoot = "C:\Users\someo\agentic-tool-loop"
$ServicesRoot = Join-Path $RepoRoot "services"
$LogsRoot = Join-Path $RepoRoot "logs"
New-Item -ItemType Directory -Force -Path $LogsRoot | Out-Null

$PYTHONPATH = "$RepoRoot;$env:PYTHONPATH"
$env:PYTHONPATH = $PYTHONPATH

# Python executable from current virtual environment
$PythonExe = ".venv\Scripts\python.exe"

# Fix OVMS environment variables for current user
$OVMS_ROOT = "C:\Users\someo\agentic-tool-loop\ovms-runtime\ovms"
$OVMS_EXE = Join-Path $OVMS_ROOT "ovms.exe"
$OVMS_SETUP = Join-Path $OVMS_ROOT "setupvars.ps1"
$OVMS_RERANK_MODELS = Join-Path $ServicesRoot "models-ovms-rerank"
$OPENVINO_PROVIDER_DEVICE = "GPU.0"

[Environment]::SetEnvironmentVariable("OVMS_ROOT", $OVMS_ROOT, "Process")
[Environment]::SetEnvironmentVariable("OVMS_EXE", $OVMS_EXE, "Process")
[Environment]::SetEnvironmentVariable("OVMS_SETUP", $OVMS_SETUP, "Process")
[Environment]::SetEnvironmentVariable("OVMS_RERANK_MODELS", $OVMS_RERANK_MODELS, "Process")
[Environment]::SetEnvironmentVariable("OPENVINO_PROVIDER_DEVICE", $OPENVINO_PROVIDER_DEVICE, "Process")

# Service definitions: Name, Port, Type, Command/Module, Health URL
$Services = @(
    @{
        Name = "Ollama Main"
        Port = 11434
        Type = "Ollama"
        Command = 'ollama list'
        HealthUrl = "http://127.0.0.1:11434/api/tags"
        StdoutLog = (Join-Path $LogsRoot "ollama-main-11434.stdout.log")
        StderrLog = (Join-Path $LogsRoot "ollama-main-11434.stderr.log")
    },
    @{
        Name = "OVMS Reranker"
        Port = 3550
        Type = "OVMS"
        Command = 'powershell -ExecutionPolicy Bypass -File services\ovms-reranker-npu.ps1'
        HealthUrl = "http://127.0.0.1:3550/v2/models/BAAI%2Fbge-reranker-v2-m3/ready"
        StdoutLog = (Join-Path $LogsRoot "ovms-reranker-3550.stdout.log")
        StderrLog = (Join-Path $LogsRoot "ovms-reranker-3550.stderr.log")
    },
    # OVMS Reranker removed - requires specific GPU environment setup (OVMS_ROOT, OPENVINO_PROVIDER_DEVICE)
    # See services/launch/setup_ovms_reranker.ps1 for full setup instructions
    # @{
    #     Name = "OVMS Reranker"
    #     Port = 3550
    #     Type = "OVMS"
    #     Command = 'powershell -ExecutionPolicy Bypass -File services\ovms-reranker-npu.ps1'
    #     HealthUrl = "http://127.0.0.1:3550/v2/models/BAAI%2Fbge-reranker-v2-m3/ready"
    #     StdoutLog = (Join-Path $LogsRoot "ovms-reranker-3550.stdout.log")
    #     StderrLog = (Join-Path $LogsRoot "ovms-reranker-3550.stderr.log")
    # },
    @{
        Name = "Vulkan Tool Broker"
        Port = 3572
        Type = "FastAPI"
        Module = "aicarmine_vulkan_tool_broker:app"
        HealthUrl = "http://127.0.0.1:3572/health"
        StdoutLog = (Join-Path $LogsRoot "broker-3572-standalone.stdout.log")
        StderrLog = (Join-Path $LogsRoot "broker-3572-standalone.stderr.log")
    },
    @{
        Name = "Vulkan Bridge"
        Port = 3571
        Type = "FastAPI"
        Module = "aicarmine_vulkan_bridge_server:app"
        HealthUrl = "http://127.0.0.1:3571/health"
        StdoutLog = (Join-Path $LogsRoot "bridge-3571-standalone.stdout.log")
        StderrLog = (Join-Path $LogsRoot "bridge-3571-standalone.stderr.log")
    },
    @{
        Name = "Executor Server"
        Port = 3560
        Type = "FastAPI"
        Module = "aicarmine-executor-server:app"
        HealthUrl = "http://127.0.0.1:3560/health"
        StdoutLog = (Join-Path $LogsRoot "executor-3560-standalone.stdout.log")
        StderrLog = (Join-Path $LogsRoot "executor-3560-standalone.stderr.log")
    }
)

# ------------------------------------------------------------------
# Helper functions
# ------------------------------------------------------------------

function Test-HttpEndpoint {
    param(
        [string]$Url,
        [int]$TimeoutSec = 3
    )
    try {
        $request = [System.Net.HttpWebRequest]::Create($Url)
        $request.Timeout = $TimeoutSec * 1000
        $response = $request.GetResponse()
        $response.Close()
        return $true
    }
    catch {
        return $false
    }
}

function Stop-ExistingProcess {
    param(
        [int]$PortNum,
        [string]$SvcLabel
    )
    try {
        $netOutput = netstat -ano 2>&1
        $matchingLines = $netOutput | Where-Object { $_ -match ":$PortNum\s" -and $_ -match "LISTENING" }
        if ($matchingLines) {
            $lineParts = ($matchingLines -split '\s+')
            $targetPid = $lineParts[-1]
            if ($targetPid -match '^\d+$') {
                Write-Host "  [$SvcLabel] Port $PortNum occupied by PID $targetPid. Stopping..."
                Stop-Process -Id ([int]$targetPid) -Force -ErrorAction SilentlyContinue
                Start-Sleep -Seconds 2
            }
        }
    }
    catch {
        Write-Host "  [$SvcLabel] Error checking port $PortNum" -ForegroundColor Red
    }
}

function Wait-ForHealth {
    param(
        [string]$Url,
        [string]$SvcLabel,
        [int]$TimeoutSec = 60
    )
    Write-Host "  [$SvcLabel] Waiting for health check..."
    for ($i = 0; $i -lt $TimeoutSec; $i++) {
        if (Test-HttpEndpoint -Url $Url -TimeoutSec 2) {
            $portNum = [string]($Url -split ':')[2]
            Write-Host "  [$SvcLabel] OK - healthy on port $portNum"
            return $true
        }
        Start-Sleep -Seconds 1
    }
    Write-Host "  [$SvcLabel] TIMEOUT - not responding after $TimeoutSec seconds"
    return $false
}

# ------------------------------------------------------------------
# Main launcher
# ------------------------------------------------------------------

Write-Host ""
Write-Host "================================================" -ForegroundColor Green
Write-Host "  Standalone Services Launcher" -ForegroundColor Green
Write-Host "================================================" -ForegroundColor Green
Write-Host ""
Write-Host "Repo root: $RepoRoot" -ForegroundColor Cyan
Write-Host "Python: $PythonExe" -ForegroundColor Cyan
Write-Host "PYTHONPATH: $env:PYTHONPATH" -ForegroundColor Cyan
Write-Host ""

$ProcessIds = @{}

foreach ($svc in $Services) {
    $svcName = $svc.Name
    $svcPort = $svc.Port
    $svcModule = $svc.Module
    $svcHealthUrl = $svc.HealthUrl
    $svcStderrLog = $svc.StderrLog

    Write-Host "--- Starting $svcName on port $svcPort ---"
    
    # Check if already running
    if (Test-HttpEndpoint -Url $svcHealthUrl -TimeoutSec 1) {
        Write-Host "  [$svcName] Already running and healthy"
        continue
    }
    
    # Stop any existing process on the port
    Stop-ExistingProcess -PortNum $svcPort -SvcLabel $svcName
    
    # Start the service based on type
    Write-Host "  Starting $svcName..."
    try {
        if ($svc.Type -eq "Ollama") {
            # Ollama main service - verify it's running
            Write-Host "  [$svcName] Checking Ollama Main status..."
            $result = Wait-ForHealth -Url $svcHealthUrl -SvcLabel $svcName -TimeoutSec 5
            if ($result) {
                Write-Host "  [$svcName] SUCCESS - Ollama Main responding on port $svcPort"
            } else {
                Write-Host "  [$svcName] SKIPPED - Ollama Main not available on port $svcPort (requires: ollama serve)"
            }
        } elseif ($svc.Type -eq "OVMS") {
            # OVMS reranker - run PowerShell script
            $ovmsScript = Join-Path $ServicesRoot "ovms-reranker-npu.ps1"
            if (Test-Path $ovmsScript) {
                Write-Host "  [$svcName] Launching OVMS reranker via script: $ovmsScript"
                $proc = Start-Process `
                    -FilePath "powershell" `
                    -ArgumentList @("-ExecutionPolicy", "Bypass", "-File", $ovmsScript) `
                    -WorkingDirectory $ServicesRoot `
                    -WindowStyle Hidden `
                    -PassThru
                
                $ProcessIds[$svcPort] = $proc.Id
                Write-Host "  [$svcName] Process started: PID=$($proc.Id)"
                
                $result = Wait-ForHealth -Url $svcHealthUrl -SvcLabel $svcName -TimeoutSec 30
                if ($result) {
                    Write-Host "  [$svcName] SUCCESS - running on http://127.0.0.1:$svcPort"
                } else {
                    Write-Host "  [$svcName] FAILED - check log: $($svc.StderrLog)"
                    Get-Content $svc.StderrLog -Tail 20 | Write-Host
                }
            } else {
                Write-Host "  [$svcName] SCRIPT NOT FOUND: $ovmsScript"
            }
        } else {
            # FastAPI/uvicorn services
            $proc = Start-Process `
                -FilePath $PythonExe `
                -ArgumentList @("-m", "uvicorn", $svc.Module, "--host", "127.0.0.1", "--port", "$svcPort") `
                -WorkingDirectory $ServicesRoot `
                -RedirectStandardOutput $svc.StdoutLog `
                -RedirectStandardError $svc.StderrLog `
                -WindowStyle Hidden `
                -PassThru
            
            $ProcessIds[$svcPort] = $proc.Id
            Write-Host "  [$svcName] Process started: PID=$($proc.Id)"
            
            # Wait for health check
            $result = Wait-ForHealth -Url $svcHealthUrl -SvcLabel $svcName -TimeoutSec 30
            
            if ($result) {
                Write-Host "  [$svcName] SUCCESS - running on http://127.0.0.1:$svcPort"
            } else {
                Write-Host "  [$svcName] FAILED - check log: $svcStderrLog"
                Get-Content $svcStderrLog -Tail 20 | Write-Host
            }
        }
    }
    catch {
        Write-Host "  [$svcName] ERROR: $_" -ForegroundColor Red
    }
    
    Write-Host ""
}

# ------------------------------------------------------------------
# Summary
# ------------------------------------------------------------------

Write-Host "================================================" -ForegroundColor Green
Write-Host "  Launch Summary" -ForegroundColor Green
Write-Host "================================================" -ForegroundColor Green
Write-Host ""

foreach ($svc in $Services) {
    $running = Test-HttpEndpoint -Url $svc.HealthUrl -TimeoutSec 1
    $status = if ($running) { "[OK]" } else { "[FAILED]" }
    Write-Host "$($svc.Name) - $status http://127.0.0.1:$($svc.Port)"
}

Write-Host ""
Write-Host "To stop all services, run:" -ForegroundColor Yellow
Write-Host "  Get-Process python | Where-Object { `"$_`".CommandLine -like '*uvicorn*' } | Stop-Process -Force" -ForegroundColor Yellow
Write-Host ""
Write-Host "Ollama is managed separately - check with: ollama list" -ForegroundColor Yellow
Write-Host ""
Write-Host "Individual service logs are in: $LogsRoot" -ForegroundColor Yellow
Write-Host ""