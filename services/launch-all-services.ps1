$ErrorActionPreference = "Stop"

# ------------------------------------------------------------------
# Unified Service Launcher - Avvia TUTTI i servizi locali
# ------------------------------------------------------------------
# Questo script avvia in sequenza:
# 1. OVMS Reranker su porta 3550
# 2. Vulkan Tool Broker su porta 3572
# 3. Vulkan Bridge su porta 3571
#
# COMANDO DA USARE (da directory services):
# cd C:\Users\sanit\agentic-tool-loop\services
# powershell -ExecutionPolicy Bypass -File launch-all-services.ps1
# ------------------------------------------------------------------

# ------------------------------------------------------------------
# Config
# ------------------------------------------------------------------
# Detect repo root: if .git exists in current dir or parent, use it
$repoRoot = $null
if (Test-Path (Join-Path (Get-Location) ".git")) {
    $repoRoot = Get-Location
} elseif ((Split-Path -Leaf (Get-Location)) -eq "services" -and (Test-Path (Join-Path (Split-Path -Parent (Get-Location)) ".git"))) {
    $repoRoot = Split-Path -Parent (Get-Location)
} else {
    # Try going up one level
    $parent = Split-Path -Parent (Get-Location)
    if (Test-Path (Join-Path $parent ".git")) {
        $repoRoot = $parent
    } else {
        $repoRoot = Get-Location
    }
}

$env:PYTHONPATH = "$repoRoot;$env:PYTHONPATH"

$HOSTNAME = "127.0.0.1"

# OVMS Reranker paths
$OVMS_RUNTIME = Join-Path $repoRoot "services\launch\ovms-runtime"
$OVMS_EXE = Join-Path $OVMS_RUNTIME "bin\ovms.exe"
$OVMS_SETUP = Join-Path $OVMS_RUNTIME "setupvars.ps1"
$OVMS_RERANK_MODELS = Join-Path $repoRoot "services\launch\models-ovms-rerank"
$OVMS_RERANK_CONFIG = Join-Path $OVMS_RERANK_MODELS "config.json"
$TARGET_DEVICE = $env:OPENVINO_PROVIDER_DEVICE
if ([string]::IsNullOrWhiteSpace($TARGET_DEVICE)) {
    $TARGET_DEVICE = "GPU.0"
}

$LOGS_DIR = Join-Path $repoRoot "services\logs"
if (-not (Test-Path $LOGS_DIR)) {
    New-Item -ItemType Directory -Force -Path $LOGS_DIR | Out-Null
}

# ------------------------------------------------------------------
# Helper functions
# ------------------------------------------------------------------
function Test-HttpEndpoint {
    param([string]$Url, [int]$TimeoutSec = 3)
    try {
        $request = [System.Net.HttpWebRequest]::Create($Url)
        $request.Timeout = $TimeoutSec * 1000
        $response = $request.GetResponse()
        $response.Close()
        return $true
    }
    catch { return $false }
}

function Stop-PortOwner {
    param([int]$Port, [string]$Label)
    try {
        $connections = netstat -ano | Where-Object { $_ -match ":\s*$Port\s+" -and $_ -match "LISTENING" }
        if ($connections) {
            $parts = ($connections -split '\s+')
            $processId = $parts[-1]
            if ($processId -match '^\d+$') {
                Write-Warning "$Label porta $Port occupata. Termino PID=$processId"
                Stop-Process -Id [int]$processId -Force -ErrorAction SilentlyContinue
                Start-Sleep -Seconds 2
            }
        }
    }
    catch { }
}

function Wait-ForEndpoint {
    param([string]$Url, [string]$Label, [int]$TimeoutSec = 60)
    Write-Host "[INFO] Attendo $Label su $Url..."
    for ($i = 0; $i -lt $TimeoutSec; $i++) {
        if (Test-HttpEndpoint -Url $Url -TimeoutSec 2) {
            Write-Host "[OK] $Label pronto su porta $($Url -split ':')[2]"
            return $true
        }
        Start-Sleep -Seconds 1
    }
    Write-Host "[ERROR] $Label non risponde dopo $TimeoutSec secondi"
    return $false
}

# ------------------------------------------------------------------
# Main launcher
# ------------------------------------------------------------------
Write-Host ""
Write-Host "================================================" -ForegroundColor Green
Write-Host "  Unified Service Launcher" -ForegroundColor Green
Write-Host "================================================" -ForegroundColor Green
Write-Host ""
Write-Host "Repo root: $repoRoot" -ForegroundColor Cyan
Write-Host "PYTHONPATH: $env:PYTHONPATH" -ForegroundColor Cyan
Write-Host ""

$startedProcesses = @{}

# ------------------------------------------------------------------
# 1. Start OVMS Reranker (port 3550)
# ------------------------------------------------------------------
Write-Host ""
Write-Host "[1/3] OVMS Reranker" -ForegroundColor Yellow

if (-not (Test-Path $OVMS_EXE)) {
    Write-Host "[ERROR] OVMS exe non trovato: $OVMS_EXE" -ForegroundColor Red
} elseif (-not (Test-Path $OVMS_RERANK_CONFIG)) {
    Write-Host "[ERROR] OVMS config non trovato: $OVMS_RERANK_CONFIG" -ForegroundColor Red
} else {
    $isRunning = Test-HttpEndpoint -Url "http://$($HOSTNAME):3550" -TimeoutSec 1
    if ($isRunning) {
        Write-Host "[OK] OVMS Reranker gia' attivo su porta 3550" -ForegroundColor Green
    } else {
        Stop-PortOwner -Port 3550 -Label "OVMS Reranker"
        
        $rerankerStdout = Join-Path $LOGS_DIR "ovms-reranker-3550-$(Get-Date -Format 'yyyyMMdd_HHmmss').stdout.log"
        $rerankerStderr = Join-Path $LOGS_DIR "ovms-reranker-3550-$(Get-Date -Format 'yyyyMMdd_HHmmss').stderr.log"
        
        . $OVMS_SETUP
        Set-Location $OVMS_RERANK_MODELS
        
        Start-Process `
            -FilePath $OVMS_EXE `
            -ArgumentList "--rest_port 3550", "--rest_bind_address 127.0.0.1", "--config_path $OVMS_RERANK_CONFIG" `
            -WorkingDirectory $OVMS_RERANK_MODELS `
            -RedirectStandardOutput $rerankerStdout `
            -RedirectStandardError $rerankerStderr `
            -WindowStyle Hidden `
            -PassThru | Out-Null
        
        Write-Host "[INFO] OVMS Reranker avviato su porta 3550..." -ForegroundColor Green
    }
}

# ------------------------------------------------------------------
# 2. Start Vulkan Tool Broker (port 3572)
# ------------------------------------------------------------------
Write-Host ""
Write-Host "[2/3] Vulkan Tool Broker" -ForegroundColor Yellow

$healthUrl3572 = "http://$($HOSTNAME):3572/health"
$isRunning3572 = Test-HttpEndpoint -Url $healthUrl3572 -TimeoutSec 1

if ($isRunning3572) {
    Write-Host "[OK] Vulkan Tool Broker gia' attivo su porta 3572" -ForegroundColor Green
} else {
    Stop-PortOwner -Port 3572 -Label "Vulkan Tool Broker"
    
    $stdout3572 = Join-Path $LOGS_DIR "broker-3572-$(Get-Date -Format 'yyyyMMdd_HHmmss').stdout.log"
    $stderr3572 = Join-Path $LOGS_DIR "broker-3572-$(Get-Date -Format 'yyyyMMdd_HHmmss').stderr.log"
    
    Write-Host "[INFO] Avvio Vulkan Tool Broker su porta 3572..." -ForegroundColor Green
    
    Start-Process `
        -FilePath "python" `
        -ArgumentList @("-m", "uvicorn", "services.aicarmine_vulkan_tool_broker:app", "--host", $HOSTNAME, "--port", "3572") `
        -WorkingDirectory $repoRoot `
        -RedirectStandardOutput $stdout3572 `
        -RedirectStandardError $stderr3572 `
        -WindowStyle Hidden `
        -PassThru | Out-Null
    
    Write-Host "[INFO] Vulkan Tool Broker avviato..." -ForegroundColor Green
}

# ------------------------------------------------------------------
# 3. Start Vulkan Bridge (port 3571)
# ------------------------------------------------------------------
Write-Host ""
Write-Host "[3/3] Vulkan Bridge" -ForegroundColor Yellow

$healthUrl3571 = "http://$($HOSTNAME):3571/health"
$isRunning3571 = Test-HttpEndpoint -Url $healthUrl3571 -TimeoutSec 1

if ($isRunning3571) {
    Write-Host "[OK] Vulkan Bridge gia' attivo su porta 3571" -ForegroundColor Green
} else {
    Stop-PortOwner -Port 3571 -Label "Vulkan Bridge"
    
    $stdout3571 = Join-Path $LOGS_DIR "broker-3571-$(Get-Date -Format 'yyyyMMdd_HHmmss').stdout.log"
    $stderr3571 = Join-Path $LOGS_DIR "broker-3571-$(Get-Date -Format 'yyyyMMdd_HHmmss').stderr.log"
    
    Write-Host "[INFO] Avvio Vulkan Bridge su porta 3571..." -ForegroundColor Green
    
    Start-Process `
        -FilePath "python" `
        -ArgumentList @("-m", "uvicorn", "services.aicarmine_vulkan_bridge_server:app", "--host", $HOSTNAME, "--port", "3571") `
        -WorkingDirectory $repoRoot `
        -RedirectStandardOutput $stdout3571 `
        -RedirectStandardError $stderr3571 `
        -WindowStyle Hidden `
        -PassThru | Out-Null
    
    Write-Host "[INFO] Vulkan Bridge avviato..." -ForegroundColor Green
}

# ------------------------------------------------------------------
# Health checks
# ------------------------------------------------------------------
Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "  Health Checks" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

$allOk = $true

$rerankerOk = Wait-ForEndpoint -Url "http://$($HOSTNAME):3550" -Label "OVMS Reranker" -TimeoutSec 30
if (-not $rerankerOk) { $allOk = $false }

$brokerOk = Wait-ForEndpoint -Url $healthUrl3572 -Label "Vulkan Tool Broker" -TimeoutSec 30
if (-not $brokerOk) { $allOk = $false }

$bridgeOk = Wait-ForEndpoint -Url $healthUrl3571 -Label "Vulkan Bridge" -TimeoutSec 30
if (-not $bridgeOk) { $allOk = $false }

# ------------------------------------------------------------------
# Summary
# ------------------------------------------------------------------
Write-Host ""
Write-Host "================================================" -ForegroundColor Green
Write-Host "  Launch Complete" -ForegroundColor Green
Write-Host "================================================" -ForegroundColor Green
Write-Host ""

$rerankerStatus = if (Test-HttpEndpoint -Url "http://$($HOSTNAME):3550" -TimeoutSec 1) { "OK" } else { "FAILED" }
$rerankerColor = if ($rerankerStatus -eq "OK") { "Green" } else { "Red" }
Write-Host "$('OVMS Reranker',-25) http://$($HOSTNAME):3550 [$rerankerStatus]" -ForegroundColor $rerankerColor

$brokerStatus = if (Test-HttpEndpoint -Url $healthUrl3572 -TimeoutSec 1) { "OK" } else { "FAILED" }
$brokerColor = if ($brokerStatus -eq "OK") { "Green" } else { "Red" }
Write-Host "$('Vulkan Tool Broker',-25) http://$($HOSTNAME):3572 [$brokerStatus]" -ForegroundColor $brokerColor

$bridgeStatus = if (Test-HttpEndpoint -Url $healthUrl3571 -TimeoutSec 1) { "OK" } else { "FAILED" }
$bridgeColor = if ($bridgeStatus -eq "OK") { "Green" } else { "Red" }
Write-Host "$('Vulkan Bridge',-25) http://$($HOSTNAME):3571 [$bridgeStatus]" -ForegroundColor $bridgeColor

Write-Host ""
Write-Host "Per fermare i servizi:" -ForegroundColor Yellow
Write-Host "  Stop-Process -Name python -Force  # ferma uvicorn" -ForegroundColor Yellow
Write-Host "  Stop-Process -Id <PID> -Force     # ferma OVMS reranker" -ForegroundColor Yellow
Write-Host ""

if (-not $allOk) {
    Write-Host "[WARN] Alcuni servizi non sono pronti. Controlla i log in: $LOGS_DIR" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Agentic-loop Client MCP (porta 3579) e Executor non sono inclusi qui." -ForegroundColor Yellow
Write-Host "Per Executor: powershell -ExecutionPolicy Bypass -File aicarmine-executor-server.ps1" -ForegroundColor Yellow
Write-Host ""