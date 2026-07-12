# AI-Carmine Standalone Launch Script (Without OpenWebUI)
# This script sets environment variables and launches the Agentic Loop Broker on port 3579
# Variables are process-local only - they are NOT persisted to the system registry.
# Each launch requires running this script again.
#
# Usage:
#   Full stack:    powershell -NoProfile -ExecutionPolicy Bypass -File "launch-standalone.ps1"
#   Broker only:   powershell -NoProfile -ExecutionPolicy Bypass -File "launch-standalone.ps1" -Mode broker
#   Reranker only: powershell -NoProfile -ExecutionPolicy Bypass -File "launch-standalone.ps1" -Mode reranker
#   Task only:     powershell -NoProfile -ExecutionPolicy Bypass -File "launch-standalone.ps1" -Mode task

param(
    [ValidateSet("all", "broker", "reranker", "task")]
    [string]$Mode = "all"
)

$ErrorActionPreference = "Stop"

$LabToolsPython = "C:\Users\CarmineFaiola\AI\venvs\labtools\Scripts\python.exe"
$OllamaExe = (Get-Command ollama.exe).Source
$HomeAI = Join-Path $env:USERPROFILE "AI"

function Write-Info { param($msg) Write-Host "[INFO] $msg" -ForegroundColor Cyan }
function Write-OK { param($msg) Write-Host "[OK] $msg" -ForegroundColor Green }
function Write-Warn { param($msg) Write-Host "[WARN] $msg" -ForegroundColor Yellow }
function Write-Err { param($msg) Write-Host "[ERR] $msg" -ForegroundColor Red }

function Test-ServiceHealthy {
    param($Url, $Name)
    try {
        $resp = Invoke-RestMethod -Uri $Url -TimeoutSec 3 -ErrorAction Stop
        return $true
    } catch {
        Write-Warn "$Name not responding at $Url"
        return $false
    }
}

# MODE: task - Launch Ollama Task (11435)
function Start-OllamaTask {
    Write-Info "=== Launching Ollama Task Server (port 11435, Vulkan/Intel GPU) ==="

    if (Test-ServiceHealthy "http://127.0.0.1:11435/api/tags" "Ollama Task") {
        Write-OK "Ollama Task already running on 11435"
        return
    }

    # Launch in new PowerShell window
    $scriptPath = Join-Path $HomeAI "services\ollama-task-vulkan.ps1"
    if (-not (Test-Path $scriptPath)) {
        Write-Err "ollama-task-vulkan.ps1 not found at $scriptPath"
        return
    }

    $windowScript = "Set-Location '$HomeAI'; powershell -NoProfile -ExecutionPolicy Bypass -File `'$scriptPath`'"
    Start-Process powershell -ArgumentList "-NoProfile", "-Command", $windowScript -WindowStyle Minimized
    Write-Info "Ollama Task launching in new minimized window..."

    # Wait for startup
    $maxWait = 30
    $elapsed = 0
    while ($elapsed -lt $maxWait) {
        if (Test-ServiceHealthy "http://127.0.0.1:11435/api/tags" "Ollama Task") {
            Write-OK "Ollama Task healthy on port 11435"

            # Pull models if not present
            try {
                $tags = Invoke-RestMethod -Uri "http://127.0.0.1:11435/api/tags"
                $modelNames = $tags.models | ForEach-Object { $_.name }

                if (-not ($modelNames -contains "qwen3-task-8k")) {
                    Write-Info "Creating qwen3-task-8k from Modelfile..."
                    $env:OLLAMA_HOST = "127.0.0.1:11435"
                    & $OllamaExe create qwen3-task-8k -f (Join-Path $HomeAI "modelfiles\Modelfile.qwen3task-8k")
                }

                if (-not ($modelNames -contains "bge-m3:latest")) {
                    Write-Info "Pulling bge-m3:latest (requires network access)..."
                    $env:OLLAMA_HOST = "127.0.0.1:11435"
                    & $OllamaExe pull bge-m3:latest -ErrorAction SilentlyContinue
                }
            } catch {
                Write-Warn "Model management skipped: $_"
            }
            return
        }
        Start-Sleep -Seconds 2
        $elapsed += 2
    }
    Write-Warn "Ollama Task may not have started - check the new PowerShell window"
}

# MODE: reranker - Launch OVMS Reranker (3550)
function Start-OVMSReranker {
    Write-Info "=== Launching OVMS Reranker (port 3550, OpenVINO GPU) ==="

    if (Test-ServiceHealthy "http://127.0.0.1:3550/v2/models/BAAI%2Fbge-reranker-v2-m3/ready" "OVMS Reranker") {
        Write-OK "OVMS Reranker already running on 3550"
        return
    }

    # ovms-reranker-npu.ps1 handles export_model.py conversion + OVMS startup
    # No manual config creation needed — the script downloads export_model.py,
    # converts the model to OpenVINO IR format, and starts OVMS automatically.

    # Launch reranker script in new window
    $rerankerScript = Join-Path $HomeAI "services\ovms-reranker-npu.ps1"
    if (Test-Path $rerankerScript) {
        $windowScript = "Set-Location '$HomeAI'; powershell -NoProfile -ExecutionPolicy Bypass -File `'$rerankerScript`'"
        Start-Process powershell -ArgumentList "-NoProfile", "-Command", $windowScript -WindowStyle Minimized
        Write-Info "OVMS Reranker launching in new minimized window..."

        # OVMS needs ~4s to load the model; extend wait to 60s and poll every 3s
        $maxWait = 60
        $elapsed = 0
        while ($elapsed -lt $maxWait) {
            if (Test-ServiceHealthy "http://127.0.0.1:3550/v2/models/BAAI%2Fbge-reranker-v2-m3/ready" "OVMS Reranker") {
                Write-OK "OVMS Reranker healthy on port 3550"
                return
            }
            Start-Sleep -Seconds 3
            $elapsed += 3
        }
        Write-Warn "OVMS Reranker may not have started - check the new PowerShell window"
    } else {
        Write-Err "ovms-reranker-npu.ps1 not found at $rerankerScript"
    }
}

# MODE: broker - Launch Agentic Loop Broker (3579)
function Start-AgenticBroker {
    Write-Info "=== Launching Agentic Loop Broker (port 3579) ==="

    # Check prerequisites
    if (-not (Test-Path $LabToolsPython)) {
        Write-Err "Labtools Python not found: $LabToolsPython"
        Write-Info "Run: python -m venv venvs\labtools && venvs\labtools\Scripts\Activate.ps1 && pip install fastapi uvicorn httpx pydantic mcp tenacity tiktoken jsonschema orjson jinja2 tree-sitter tree-sitter-python"
        return
    }

    # Verify Ollama Task is healthy
    if (-not (Test-ServiceHealthy "http://127.0.0.1:11435/api/tags" "Ollama Task")) {
        Write-Warn "Ollama Task (11435) not healthy - broker may not work correctly"
        Write-Info "Start it first: powershell -NoProfile -ExecutionPolicy Bypass -File `'$HomeAI\services\ollama-task-vulkan.ps1`'"
    } else {
        Write-OK "Ollama Task (11435) is healthy"
    }

    # Verify OVMS Reranker is healthy
    if (-not (Test-ServiceHealthy "http://127.0.0.1:3550/v2/models/BAAI%2Fbge-reranker-v2-m3/ready" "OVMS Reranker")) {
        Write-Warn "OVMS Reranker (3550) not healthy - reranking will fail"
        Write-Info "Start it first: powershell -NoProfile -ExecutionPolicy Bypass -File `'$HomeAI\services\ovms-reranker-npu.ps1`'"
    } else {
        Write-OK "OVMS Reranker (3550) is healthy"
    }

    # Set environment variables (process-local only)
    $env:AICARMINE_LAB_REPO = $HomeAI
    $env:AICARMINE_REAL_REPO = $HomeAI
    $env:AICARMINE_CODEX_MCP_REPO_ROOT = $HomeAI
    $env:OPEN_TERMINAL_CWD = $HomeAI
    $env:AICARMINE_OPEN_TERMINAL_WORKDIR = $HomeAI

    $workspaceRoot = Join-Path $HomeAI "state\codex_bridge\agentic_loop_client\port-3579\workspace"
    New-Item -ItemType Directory -Force -Path $workspaceRoot | Out-Null
    $env:AICARMINE_VULKAN_WORKSPACE = $workspaceRoot

    $jobRoot = Join-Path $workspaceRoot "agent-jobs"
    New-Item -ItemType Directory -Force -Path $jobRoot | Out-Null
    $env:AICARMINE_AGENT_JOB_ROOT = $jobRoot
    $env:AICARMINE_AGENT_JOB_DB = Join-Path $jobRoot "agent_jobs.sqlite3"

    $env:AICARMINE_AGENT_PUBLIC_BASE_URL = "http://127.0.0.1:3579"
    $env:AICARMINE_VULKAN_AGENT_URL = "http://127.0.0.1:3579/vulkan/agent"
    $env:AICARMINE_BROKER_SERVICE_NAME = "aicarmine-codex-agentic-loop-3579"
    $env:AICARMINE_BROKER_APP_TITLE = "AI-Carmine Codex Agentic Loop 3579"
    $env:AICARMINE_BROKER_UVICORN_RELOAD = "0"

    # Reranker URLs - OVMS 3550
    $env:RAG_EXTERNAL_RERANKER_URL = "http://127.0.0.1:3550/v3/rerank"
    $env:AICARMINE_RAG_RERANK_URL = "http://127.0.0.1:3550/v3/rerank"
    $env:AICARMINE_CONTROLLER_RAG_RERANK_URL = "http://127.0.0.1:3550/v3/rerank"
    $env:AICARMINE_RAG_RERANK_READY_URL = "http://127.0.0.1:3550/v2/models/BAAI%2Fbge-reranker-v2-m3/ready"

    # OVMS health check URL (used by Start-OVMSReranker)
    $env:OVMS_RERANK_HEALTH_URL = "http://127.0.0.1:3550/v2/models/BAAI%2Fbge-reranker-v2-m3/ready"

    $env:AICARMINE_OLLAMA_TASK_URL = "http://127.0.0.1:11435/api/chat"
    $env:AICARMINE_VULKAN_BROKER_OLLAMA_URL = "http://127.0.0.1:11435/api/chat"
    $env:AICARMINE_OLLAMA_TASK_MODEL = "qwen3-task-8k"
    $env:AICARMINE_VULKAN_BROKER_MODEL = "qwen3-task-8k"
    $env:AICARMINE_OLLAMA_KEEP_ALIVE = "24h"

    $env:AICARMINE_AGENT_PLANNER_URL = "http://127.0.0.1:11434/api/chat"
    $env:AICARMINE_PLANNER_MODEL = "qwen3.5:9b-coding-v5-1"

    $env:AICARMINE_AGENTIC_PLANNER_ENABLED = "1"
    $env:AICARMINE_AGENTIC_PLANNER_NATIVE_TOOLS = "1"
    $env:AICARMINE_AGENTIC_PLANNER_REQUIRE_NATIVE_TOOLS = "1"
    $env:AICARMINE_AGENTIC_PLANNER_NUM_CTX = "262144"
    $env:AICARMINE_AGENTIC_PLANNER_NUM_CTX_CAP = "262144"
    $env:AICARMINE_AGENTIC_PLANNER_PROMPT_CHAR_BUDGET = "262144"
    $env:AICARMINE_AGENTIC_PLANNER_PROMPT_COMPACT_RATIO = "0.85"
    $env:AICARMINE_AGENT_DEFAULT_MAX_STEPS = "40"
    $env:AICARMINE_AGENT_MAX_STEPS = "100"

    $env:OPENVINO_PROVIDER_DEVICE = "GPU.0"
    $env:ENABLE_OPENVINO_PROVIDER = "1"
    $env:ENABLE_EXTERNAL_RERANKER = "1"

    Write-OK "Environment variables set (process-local)"

    # Launch broker
    Write-Info "Launching Agentic Loop Broker on port 3579..."
    Set-Location (Join-Path $HomeAI "services")
    & $LabToolsPython -m uvicorn aicarmine_vulkan_tool_broker:app --host 127.0.0.1 --port 3579
}

# Main execution based on mode
switch ($Mode) {
    "task" { Start-OllamaTask }
    "reranker" { Start-OVMSReranker }
    "broker" { Start-AgenticBroker }
    "all" {
        Write-Info "=== AI-Carmine Standalone Infrastructure (Full Stack) ==="
        Write-Info "Ollama Desktop (11434) detected as running - used for planner models"

        Start-OllamaTask
        Start-OVMSReranker
        Start-AgenticBroker

        Write-OK "=== Full stack launched ==="
        Write-Info ""
        Write-Info "Health checks:"
        Write-Info "  Ollama Task (11435): curl http://127.0.0.1:11435/api/tags"
        Write-Info "  OVMS Reranker (3550): curl http://127.0.0.1:3550/v2/models/bge-reranker-v2-m3/ready"
        Write-Info "  Agentic Broker (3579): curl http://127.0.0.1:3579/health"
        Write-Info ""
        Write-Info "To restart individual services after code updates, run this script with -Mode parameter:"
        Write-Info "  .\launch-standalone.ps1 -Mode task      # Restart Ollama Task only"
        Write-Info "  .\launch-standalone.ps1 -Mode reranker   # Restart OVMS Reranker only"
        Write-Info "  .\launch-standalone.ps1 -Mode broker     # Restart Agentic Broker only"
    }
}