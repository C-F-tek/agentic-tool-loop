# ------------------------------------------------------------------
# Standalone Agentic Loop Launcher - Port 3579 (no OpenWebUI)
# ------------------------------------------------------------------
# Questo script avvia:
# 1. Ollama Task GPU0 (11435) se non già attivo
# 2. OpenVINO/Reranker (3550) - obbligatorio
# 3. Broker dedicato su porta 3579
# 4. Verifica health endpoints
#
# NON avvia:
# - OpenWebUI (8080)
# - Vulkan Bridge pubblico (3571)
# - Executor (3560)
# - Jupyter (8889)
# ------------------------------------------------------------------

$ErrorActionPreference = "Stop"

# ------------------------------------------------------------------
# Config
# ------------------------------------------------------------------
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$LaunchRoot = $ScriptRoot

# Usa il percorso del script come base, non il current working directory
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$LaunchDir = Split-Path -Parent $ScriptDir
$WORKSPACE_ROOT = Split-Path -Parent $LaunchDir
$AI_ROOT = $WORKSPACE_ROOT

# Verifica che il percorso esista
if (-not (Test-Path $AI_ROOT)) {
    Write-Host "[ERROR] AI_ROOT non esiste: $AI_ROOT"
    Write-Host "[ERROR] Verifica il percorso dello script"
    exit 1
}

# Verifica che services directory esista
$ServicesRoot = Join-Path $AI_ROOT "services"
if (-not (Test-Path $ServicesRoot)) {
    Write-Host "[ERROR] Services directory non esiste: $ServicesRoot"
    exit 1
}

$HOSTNAME = "127.0.0.1"
$OLLAMA_TASK_PORT = 11435
$BROKER_PORT = 3579
$BROKER_ENDPOINT = "http://$($HOSTNAME):$($BROKER_PORT)/vulkan/agent"
$HEALTH_ENDPOINT = "http://$($HOSTNAME):$($BROKER_PORT)/health"

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

# ------------------------------------------------------------------
# Config OpenVINO/Reranker
# ------------------------------------------------------------------
$OPENVINO_PORT = 3550
$OPENVINO_HEALTH_URL = "http://$($HOSTNAME):$($OPENVINO_PORT)/v2/models/BAAI%2Fbge-reranker-v2-m3/ready"
$OPENVINO_PROVIDER_SCRIPT = Join-Path $AI_ROOT "services\ovms-reranker-npu.ps1"
$OPENVINO_PYTHON_EXE = "python"

# ------------------------------------------------------------------
# Step 1: Avvia OpenVINO/Reranker (3550) - obbligatorio
# ------------------------------------------------------------------
Write-Host ""
Write-Host "============================================"
Write-Host "  Standalone Agentic Loop - Port 3579"
Write-Host "============================================"
Write-Host ""

if (Test-HttpEndpoint -Url $OPENVINO_HEALTH_URL -TimeoutSec 2) {
    Write-Host "[OK] OpenVINO/Reranker già attivo su porta $OPENVINO_PORT"
}
else {
    Write-Host "[INFO] Avvio OpenVINO/Reranker su porta $OPENVINO_PORT..."
    
    # Initialize LogRoot before using it
    $LogRoot = Join-Path $AI_ROOT "logs"
    New-Item -ItemType Directory -Force -Path $LogRoot | Out-Null
    
    $ovmsStdout = Join-Path $LogRoot "ovms-3550-$(Get-Date -Format 'yyyyMMdd_HHmmss').stdout.log"
    $ovmsStderr = Join-Path $LogRoot "ovms-3550-$(Get-Date -Format 'yyyyMMdd_HHmmss').stderr.log"
    
    if (Test-Path $OPENVINO_PROVIDER_SCRIPT) {
        Write-Host "  Script  = $OPENVINO_PROVIDER_SCRIPT"
        Write-Host "  Stdout  = $ovmsStdout"
        Write-Host "  Stderr  = $ovmsStderr"
        Write-Host ""
        
        $ovmsProc = Start-Process `
            -FilePath "powershell.exe" `
            -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$OPENVINO_PROVIDER_SCRIPT`"" `
            -WorkingDirectory (Split-Path $OPENVINO_PROVIDER_SCRIPT -Parent) `
            -RedirectStandardOutput $ovmsStdout `
            -RedirectStandardError $ovmsStderr `
            -WindowStyle Minimized `
            -PassThru
        
        Write-Host "  PID     = $($ovmsProc.Id)"
        Write-Host ""
        
        # Attendi health check OpenVINO
        $healthMsg = "[INFO] Attendo OpenVINO/Reranker sano su " + $OPENVINO_HEALTH_URL + "..."
        Write-Host $healthMsg
        $ovmsOk = $false
        for ($i = 0; $i -lt 90; $i++) {
            if (Test-HttpEndpoint -Url $OPENVINO_HEALTH_URL -TimeoutSec 2) {
                $ovmsOk = $true
                Write-Host "[OK] OpenVINO/Reranker sano su porta $OPENVINO_PORT"
                break
            }
            Start-Sleep -Seconds 1
        }
        
        if (-not $ovmsOk) {
            Write-Host ""
            $errMsg = "[ERROR] OpenVINO/Reranker non risponde su " + $OPENVINO_HEALTH_URL + " dopo 90 secondi"
            Write-Host $errMsg
            Write-Host ""
            Write-Host "--- stderr tail ---"
            if (Test-Path $ovmsStderr) { Get-Content $ovmsStderr -Tail 40 }
            Write-Host ""
            Write-Host "--- stdout tail ---"
            if (Test-Path $ovmsStdout) { Get-Content $ovmsStdout -Tail 20 }
            exit 1
        }
    }
    else {
        Write-Host "[ERROR] OpenVINO provider script non trovato: $OPENVINO_PROVIDER_SCRIPT"
        exit 1
    }
}
Write-Host ""

# ------------------------------------------------------------------
# Step 2: Verifica se broker 3579 è già attivo
# ------------------------------------------------------------------
if (Test-HttpEndpoint -Url $HEALTH_ENDPOINT -TimeoutSec 2) {
    Write-Host "[OK] Broker 3579 già attivo e sano su $HEALTH_ENDPOINT"
    Write-Host ""
    Write-Host "============================================"
    Write-Host "  Loop agentico pronto"
    Write-Host "============================================"
    Write-Host ""
    Write-Host "Usa gli MCP tool aicarmine-agentic-loop-client:"
    Write-Host "  - aicarmine_agentic_loop_run  -> avvia un job"
    Write-Host "  - aicarmine_agentic_loop_status -> controlla stato"
    Write-Host "  - aicarmine_agentic_loop_result -> ottieni risultato"
    Write-Host ""
    Write-Host "Oppure via curl:"
    Write-Host "  curl $BROKER_ENDPOINT -H 'Content-Type: application/json' -d '{\"task\":\"test\",\"request\":\"prova\"}'"
    Write-Host ""
    exit 0
}

# ------------------------------------------------------------------
# Step 3: Ferma eventuale broker vecchio su 3579
# ------------------------------------------------------------------
Write-Host "[INFO] Verifico eventuale broker vecchio su porta 3579..."
Stop-PortOwner -Port $BROKER_PORT -Label "Broker 3579"

# ------------------------------------------------------------------
# Step 4: Avvia broker dedicato su 3579
# ------------------------------------------------------------------
Write-Host "[INFO] Avvio broker dedicato su $($HOSTNAME):$BROKER_PORT..."
Write-Host ""

$ServicesRoot = Join-Path $AI_ROOT "services"
$LogRoot = Join-Path $AI_ROOT "logs"
New-Item -ItemType Directory -Force -Path $LogRoot | Out-Null

$StdoutPath = Join-Path $LogRoot "broker-3579-$(Get-Date -Format 'yyyyMMdd_HHmmss').stdout.log"
$StderrPath = Join-Path $LogRoot "broker-3579-$(Get-Date -Format 'yyyyMMdd_HHmmss').stderr.log"

# Imposta variabili ambiente PERMANENTI per il broker
$env:AICARMINE_LAB_REPO = "C:\Users\sanit\AI\lab-worktrees\blender-audio-project-lab"
$env:AICARMINE_VULKAN_WORKSPACE = "C:\Users\sanit\AI\qwen-agent-workspace\vulkan-broker"
$env:AICARMINE_AGENT_JOB_ROOT = "C:\Users\sanit\AI\qwen-agent-workspace\vulkan-broker\agent-jobs"
$env:AICARMINE_AGENT_JOB_DB = "C:\Users\sanit\AI\qwen-agent-workspace\vulkan-broker\agent-jobs\agent_jobs.sqlite3"
$env:AICARMINE_AGENTIC_PLANNER_MODEL = "mio-qwen-code3:latest"
$env:AICARMINE_AGENTIC_PLANNER_NUM_CTX = "262144"
$env:AICARMINE_AGENTIC_PLANNER_ENABLED = "1"
$env:AICARMINE_AGENTIC_PLANNER_NATIVE_TOOLS = "1"
$env:AICARMINE_AGENTIC_PLANNER_REQUIRE_NATIVE_TOOLS = "1"
$env:AICARMINE_AGENTIC_PLANNER_URL = "http://$($HOSTNAME):$($OLLAMA_TASK_PORT)/api/chat"
$env:AICARMINE_VULKAN_BROKER_OLLAMA_URL = "http://$($HOSTNAME):$($OLLAMA_TASK_PORT)/api/chat"
$env:AICARMINE_VULKAN_BROKER_MODEL = "qwen3-task-8k"
$env:AICARMINE_AGENT_DEFAULT_MAX_STEPS = "40"
$env:AICARMINE_AGENT_MAX_STEPS = "100"

# Avvia il processo broker
$pythonExe = "python"
$brokerModule = "aicarmine_broker.app:app"

Write-Host "Python  = $pythonExe"
Write-Host "Module  = $brokerModule"
Write-Host "Port    = $BROKER_PORT"
Write-Host "Stdout  = $StdoutPath"
Write-Host "Stderr  = $StderrPath"
Write-Host ""

$proc = Start-Process `
    -FilePath $pythonExe `
    -ArgumentList @("-m", "uvicorn", $brokerModule, "--host", $HOSTNAME, "--port", "$BROKER_PORT") `
    -WorkingDirectory $ServicesRoot `
    -RedirectStandardOutput $StdoutPath `
    -RedirectStandardError $StderrPath `
    -WindowStyle Minimized `
    -PassThru

Write-Host "Broker processo avviato: PID=$($proc.Id)"
Write-Host ""

# ------------------------------------------------------------------
# Step 5: Attendi health check
# ------------------------------------------------------------------
$healthMsg2 = "[INFO] Attendo che il broker diventi sano su " + $HEALTH_ENDPOINT + "..."
Write-Host $healthMsg2

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
# Step 6: Pronto
# ------------------------------------------------------------------
Write-Host ""
Write-Host "============================================"
Write-Host "  Standalone Agentic Loop - Pronto"
Write-Host "============================================"
Write-Host ""
Write-Host "Broker:    http://$($HOSTNAME):$BROKER_PORT"
Write-Host "Endpoint:  $BROKER_ENDPOINT"
Write-Host "Health:    $HEALTH_ENDPOINT"
Write-Host "Logs:      $LogRoot"
Write-Host ""
Write-Host "MCP Tools (Cline):"
Write-Host "  aicarmine_agentic_loop_run        -> avvia job"
Write-Host "  aicarmine_agentic_loop_status     -> controlla stato"
Write-Host "  aicarmine_agentic_loop_result     -> ottieni risultato"
Write-Host "  aicarmine_agentic_loop_ensure_broker -> riavvia broker"
Write-Host ""
Write-Host "Via curl:"
Write-Host "  curl $BROKER_ENDPOINT -H 'Content-Type: application/json' -d '{""task"":""test"",""request"":""prova""}'"
Write-Host ""
Write-Host "Per fermare il broker:"
Write-Host "  Stop-Process -Id $($proc.Id) -Force"
Write-Host ""