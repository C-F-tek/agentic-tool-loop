# ------------------------------------------------------------------
# Complete Standalone Agentic Loop Launcher
# ------------------------------------------------------------------
# Questo script lancia TUTTI i componenti necessari per il broker agentic loop:
# 1. Reranker (OVMS) su porta 3550
# 2. Ollama su porta 11434 con modello mio-qwen-code-toolnative:latest
# 3. Broker su porta 3579
#
# COMANDO DA USARE:
# cd C:\Users\sanit\agentic-tool-loop\services
# .\complete_standalone_launcher.ps1
# ------------------------------------------------------------------

$ErrorActionPreference = "Stop"

# ------------------------------------------------------------------
# Config
# ------------------------------------------------------------------
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$LaunchRoot = Split-Path -Parent $ScriptRoot
$HOSTNAME = "127.0.0.1"
$RERANKER_PORT = 3550
$OLLAMA_PORT = 11434
$BROKER_PORT = 3579
$RERANKER_ENDPOINT = "http://$($HOSTNAME):$($RERANKER_PORT)/v2/models/BAAI%2Fbge-reranker-v2-m3/ready"
$BROKER_ENDPOINT = "http://$($HOSTNAME):$($BROKER_PORT)/vulkan/agent"
$HEALTH_ENDPOINT = "http://$($HOSTNAME):$($BROKER_PORT)/health"
$OLLAMA_ENDPOINT = "http://$($HOSTNAME):$($OLLAMA_PORT)/api/version"
$LOGS_DIR = Join-Path $LaunchRoot "logs"

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

function Get-PortOwner {
    param([int]$Port)
    try {
        $connections = netstat -ano | Where-Object { $_ -match ":\s*$Port\s+" -and $_ -match "LISTENING" }
        if ($connections) {
            $parts = ($connections -split '\s+')
            $pid = $parts[-1]
            if ($pid -match '^\d+$') {
                $process = Get-Process -Id $pid -ErrorAction SilentlyContinue
                return @{ ProcessId = [int]$pid; ProcessName = $process?.ProcessName }
            }
        }
        return $null
    }
    catch {
        return $null
    }
}

function Stop-PortOwner {
    param(
        [int]$Port,
        [string]$Label
    )
    $owner = Get-PortOwner -Port $Port
    if ($null -ne $owner) {
        Write-Warning "$Label porta $Port occupata. Termino PID=$($owner.ProcessId)"
        Stop-Process -Id $owner.ProcessId -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 2
    }
}

function Wait-ForEndpoint {
    param(
        [string]$Url,
        [string]$Label,
        [int]$TimeoutSec = 60
    )
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
# Step 1: Verifica componenti gia' attivi
# ------------------------------------------------------------------
Write-Host ""
Write-Host "============================================"
Write-Host "  Complete Standalone Agentic Loop Launcher"
Write-Host "============================================"
Write-Host ""

# ------------------------------------------------------------------
# Step 2: Avvia Reranker (OVMS) su 3550
# ------------------------------------------------------------------
Write-Host "[INFO] Verifico eventuale reranker su porta 3550..."
if (Test-HttpEndpoint -Url $RERANKER_ENDPOINT -TimeoutSec 2) {
    Write-Host "[OK] Reranker gia' attivo su porta 3550"
} else {
    Write-Host "[INFO] Avvio Reranker (OVMS) su porta 3550..."
    $OvmsScript = Join-Path $LaunchRoot "services" "ovms-reranker-npu.ps1"
    if (Test-Path $OvmsScript) {
        Write-Host "  Script: $OvmsScript"
        Write-Host ""
        # Nota: Questo e' un avvio in background. Il reranker richiede tempo per avviarsi.
        Write-Host "[INFO] Il reranker richiede tempo per avviarsi. Continua con l'avvio di Ollama..."
    } else {
        Write-Host "[WARN] Script ovms-reranker-npu.ps1 non trovato. Assicurati che il reranker sia avviato manualmente."
    }
}

# ------------------------------------------------------------------
# Step 3: Avvia Ollama su 11434
# ------------------------------------------------------------------
Write-Host "[INFO] Verifico eventuale Ollama su porta 11434..."
if (Test-HttpEndpoint -Url $OLLAMA_ENDPOINT -TimeoutSec 2) {
    Write-Host "[OK] Ollama gia' attivo su porta 11434"
} else {
    Write-Host "[INFO] Avvia Ollama su porta 11434..."
    Write-Host "  Assicurati che Ollama sia avviato con il modello mio-qwen-code3:latest."
    Write-Host "  Se Ollama non e' avviato, esegui:"
    Write-Host "    ollama run mio-qwen-code3:latest"
    Write-Host ""
}

# ------------------------------------------------------------------
# Step 4: Avvia Broker su 3579
# ------------------------------------------------------------------
Write-Host "[INFO] Verifico eventuale broker su porta 3579..."
if (Test-HttpEndpoint -Url $HEALTH_ENDPOINT -TimeoutSec 2) {
    Write-Host "[OK] Broker gia' attivo su porta 3579"
    Write-Host ""
    Write-Host "============================================"
    Write-Host "  Standalone Broker - Pronto"
    Write-Host "============================================"
    Write-Host ""
    Write-Host "Broker:    http://$($HOSTNAME):$BROKER_PORT"
    Write-Host "Endpoint:  $BROKER_ENDPOINT"
    Write-Host "Health:    $HEALTH_ENDPOINT"
    Write-Host "Logs:      $LOGS_DIR"
    Write-Host ""
    Write-Host "MCP Tools (Cline):"
    Write-Host "  aicarmine_agentic_loop_run        -> avvia job"
    Write-Host "  aicarmine_agentic_loop_status     -> controlla stato"
    Write-Host "  aicarmine_agentic_loop_result     -> ottieni risultato"
    Write-Host "  aicarmine_agentic_loop_ensure_broker -> riavvia broker"
    Write-Host ""
    Write-Host "Via curl:"
    Write-Host "  curl $BROKER_ENDPOINT -H 'Content-Type: application/json' -d '{\"task\":\"test\",\"request\":\"prova\"}'"
    Write-Host ""
    exit 0
}

# ------------------------------------------------------------------
# Step 5: Ferma eventuale broker vecchio su 3579
# ------------------------------------------------------------------
Write-Host "[INFO] Verifico eventuale broker vecchio su porta 3579..."
Stop-PortOwner -Port $BROKER_PORT -Label "Broker 3579"

# ------------------------------------------------------------------
# Step 6: Imposta variabili ambiente
# ------------------------------------------------------------------
Write-Host "[INFO] Imposto variabili ambiente..."

$env:AICARMINE_VULKAN_WORKSPACE = "C:\Users\sanit\AI\qwen-agent-workspace\vulkan-broker"
$env:AICARMINE_LAB_REPO = "C:\Users\sanit\AI\lab-worktrees\blender-audio-project-lab"
$env:AICARMINE_AGENT_JOB_ROOT = "C:\Users\sanit\AI\qwen-agent-workspace\vulkan-broker\agent-jobs"
$env:AICARMINE_AGENT_JOB_DB = "C:\Users\sanit\AI\qwen-agent-workspace\vulkan-broker\agent-jobs\agent_jobs.sqlite3"
$env:AICARMINE_AGENTIC_PLANNER_MODEL = "mio-qwen-code-toolnative:latest"
$env:AICARMINE_AGENTIC_PLANNER_NUM_CTX = "262144"

Write-Host "  AICARMINE_VULKAN_WORKSPACE = $env:AICARMINE_VULKAN_WORKSPACE"
Write-Host "  AICARMINE_LAB_REPO = $env:AICARMINE_LAB_REPO"
Write-Host "  AICARMINE_AGENT_JOB_ROOT = $env:AICARMINE_AGENT_JOB_ROOT"
Write-Host "  AICARMINE_AGENT_JOB_DB = $env:AICARMINE_AGENT_JOB_DB"
Write-Host "  AICARMINE_AGENTIC_PLANNER_MODEL = $env:AICARMINE_AGENTIC_PLANNER_MODEL"
Write-Host "  AICARMINE_AGENTIC_PLANNER_NUM_CTX = $env:AICARMINE_AGENTIC_PLANNER_NUM_CTX"
Write-Host ""

# ------------------------------------------------------------------
# Step 7: Avvia broker su 3579
# ------------------------------------------------------------------
Write-Host "[INFO] Avvio broker su $($HOSTNAME):$BROKER_PORT..."
Write-Host ""

$ServicesRoot = Join-Path $LaunchRoot "services"
New-Item -ItemType Directory -Force -Path $LOGS_DIR | Out-Null

$StdoutPath = Join-Path $LOGS_DIR "broker-3579-$(Get-Date -Format 'yyyyMMdd_HHmmss').stdout.log"
$StderrPath = Join-Path $LOGS_DIR "broker-3579-$(Get-Date -Format 'yyyyMMdd_HHmmss').stderr.log"

Write-Host "Python  = python"
Write-Host "Module  = aicarmine_broker.app:app"
Write-Host "Port    = $BROKER_PORT"
Write-Host "Stdout  = $StdoutPath"
Write-Host "Stderr  = $StderrPath"
Write-Host ""

$proc = Start-Process `
    -FilePath "python" `
    -ArgumentList @("-m", "uvicorn", "aicarmine_broker.app:app", "--host", $HOSTNAME, "--port", "$BROKER_PORT") `
    -WorkingDirectory $ServicesRoot `
    -RedirectStandardOutput $StdoutPath `
    -RedirectStandardError $StderrPath `
    -WindowStyle Minimized `
    -PassThru

Write-Host "Broker processo avviato: PID=$($proc.Id)"
Write-Host ""

# ------------------------------------------------------------------
# Step 8: Attendi health check
# ------------------------------------------------------------------
$healthMsg = "[INFO] Attendo che il broker diventi sano su " + $HEALTH_ENDPOINT + "..."
Write-Host $healthMsg

$healthOk = $false
for ($i = 0; $i -lt 60; $i++) {
    if ($proc.HasExited) {
        Write-Host ""
        Write-Host "[ERROR] Broker terminato durante startup. PID=$($proc.Id) ExitCode=$($proc.ExitCode)"
        Write-Host ""
        Write-Host "--- stderr tail ---"
        if (Test-Path $StderrPath) {
            Get-Content $StderrPath -Tail 40
        }
        Write-Host ""
        Write-Host "--- stdout tail ---"
        if (Test-Path $StdoutPath) {
            Get-Content $StdoutPath -Tail 20
        }
        exit 1
    }

    if (Test-HttpEndpoint -Url $HEALTH_ENDPOINT -TimeoutSec 2) {
        $healthOk = $true
        Write-Host "[OK] Broker sano su porta $BROKER_PORT"
        break
    }

    Start-Sleep -Seconds 1
}

if (-not $healthOk) {
    Write-Host ""
    $errHealth = "[ERROR] Broker non risponde su " + $HEALTH_ENDPOINT + " dopo 60 secondi"
    Write-Host $errHealth
    Write-Host ""
    Write-Host "--- stderr tail ---"
    if (Test-Path $StderrPath) {
        Get-Content $StderrPath -Tail 40
    }
    Write-Host ""
    Write-Host "--- stdout tail ---"
    if (Test-Path $StdoutPath) {
        Get-Content $StdoutPath -Tail 20
    }
    exit 1
}

# ------------------------------------------------------------------
# Step 9: Pronto
# ------------------------------------------------------------------
Write-Host ""
Write-Host "============================================"
Write-Host "  Complete Standalone Agentic Loop - Pronto"
Write-Host "============================================"
Write-Host ""
Write-Host "Reranker:  http://$($HOSTNAME):$RERANKER_PORT"
Write-Host "Ollama:    http://$($HOSTNAME):$OLLAMA_PORT"
Write-Host "Broker:    http://$($HOSTNAME):$BROKER_PORT"
Write-Host "Endpoint:  $BROKER_ENDPOINT"
Write-Host "Health:    $HEALTH_ENDPOINT"
Write-Host "Logs:      $LOGS_DIR"
Write-Host ""
Write-Host "MCP Tools (Cline):"
Write-Host "  aicarmine_agentic_loop_run        -> avvia job"
Write-Host "  aicarmine_agentic_loop_status     -> controlla stato"
Write-Host "  aicarmine_agentic_loop_result     -> ottieni risultato"
Write-Host "  aicarmine_agentic_loop_ensure_broker -> riavvia broker"
Write-Host ""
Write-Host "Via curl:"
Write-Host "  curl $BROKER_ENDPOINT -H 'Content-Type: application/json' -d '{\"task\":\"test\",\"request\":\"prova\"}'"
Write-Host ""
Write-Host "Per fermare il broker:"
Write-Host "  Stop-Process -Id $($proc.Id) -Force"
Write-Host ""