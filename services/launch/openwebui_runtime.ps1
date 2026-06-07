# ------------------------------------------------------------------
# Shared launcher helpers
# ------------------------------------------------------------------
$LaunchRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
if (
    (-not (Get-Command Set-UserEnvValue -ErrorAction SilentlyContinue)) -or
    (-not (Get-Command Clear-UserEnvValue -ErrorAction SilentlyContinue)) -or
    (-not (Get-Command Set-EnvironmentVariables -ErrorAction SilentlyContinue))
) { . (Join-Path $LaunchRoot "env.ps1") }
if (
    (-not (Get-Command Test-HttpEndpoint -ErrorAction SilentlyContinue)) -or
    (-not (Get-Command Test-HttpHealth -ErrorAction SilentlyContinue))
) { . (Join-Path $LaunchRoot "http.ps1") }
if (
    (-not (Get-Command Get-PortOwner -ErrorAction SilentlyContinue)) -or
    (-not (Get-Command Stop-PortOwner -ErrorAction SilentlyContinue)) -or
    (-not (Get-Command Start-OpenVINOProviderIfEnabled -ErrorAction SilentlyContinue)) -or
    (-not (Get-Command Start-NpuPhiServiceIfEnabled -ErrorAction SilentlyContinue))
) { . (Join-Path $LaunchRoot "process.ps1") }
if (
    (-not (Get-Command Test-OllamaEndpoint -ErrorAction SilentlyContinue)) -or
    (-not (Get-Command Start-EndpointScriptIfNeeded -ErrorAction SilentlyContinue)) -or
    (-not (Get-Command Ensure-OllamaModel -ErrorAction SilentlyContinue))
) { . (Join-Path $LaunchRoot "ollama.ps1") }

# ------------------------------------------------------------------
# Config persistente progetto
# ------------------------------------------------------------------

# ------------------------------------------------------------------
# Configuration constants
# ------------------------------------------------------------------

$config = @{
    AI_ROOT = "C:\Users\carmi\AI"
    HOSTNAME = "127.0.0.1"
    WEBUI_PORT = 8080
    OLLAMA_MAIN_PORT = 11434
    OLLAMA_TASK_PORT = 11435
    VULKAN_BRIDGE_PORT = 3571
    VULKAN_AGENT_PORT = 3572
    EXECUTOR_PORT = 3560
    OPENVINO_PORT = 3550
    NPU_PHI_PORT = 3551
    JUPYTER_PORT = 8889
    OPEN_TERMINAL_PORT = 8888
    CUDA_DEVICE = "GPU-751537aa-1f63-6ad0-db71-9727edd22244"
}

$AI_ROOT = Set-UserEnvValue "AI_ROOT" $config.AI_ROOT
$OPENWEBUI_EXE = Set-UserEnvValue "OPENWEBUI_EXE" "$AI_ROOT\venvs\openwebui\Scripts\open-webui.exe"
$OPENWEBUI_DATA_DIR = Set-UserEnvValue "OPENWEBUI_DATA_DIR" "$AI_ROOT\services\openwebui-data"
$WEBUI_SECRET_KEY = Get-OrCreate-WebUISecret

$USER_AGENT = Set-UserEnvValue "USER_AGENT" "OpenWebUI-local-carmi/1.0"
$OLLAMA_NO_CLOUD = Set-UserEnvValue "OLLAMA_NO_CLOUD" "1"
$OLLAMA_BASE_URL = Set-UserEnvValue "OLLAMA_BASE_URL" "http://$($config.HOSTNAME):$($config.OLLAMA_MAIN_PORT)"
$TASK_MODEL = Set-UserEnvValue "TASK_MODEL" "gpu0/qwen3-task-8k"
$RAG_EMBEDDING_BATCH_SIZE = Set-UserEnvValue "RAG_EMBEDDING_BATCH_SIZE" "4"
$ENABLE_QUERIES_CACHE = Set-UserEnvValue "ENABLE_QUERIES_CACHE" "True"
$MODELS_CACHE_TTL = Set-UserEnvValue "MODELS_CACHE_TTL" "1"
$RAG_SYSTEM_CONTEXT = Set-UserEnvValue "RAG_SYSTEM_CONTEXT" "True"

# Main NVIDIA RTX 5080 / Ollama runtime defaults.
# User-level defaults apply to Ollama Desktop/main only after Ollama Desktop restarts.
$CUDA_VISIBLE_DEVICES = Set-UserEnvDefault "CUDA_VISIBLE_DEVICES" $config.CUDA_DEVICE
$OLLAMA_NUM_PARALLEL = Set-UserEnvDefault "OLLAMA_NUM_PARALLEL" "1"
$OLLAMA_MAX_LOADED_MODELS = Set-UserEnvDefault "OLLAMA_MAX_LOADED_MODELS" "1"
$OLLAMA_FLASH_ATTENTION = Set-UserEnvDefault "OLLAMA_FLASH_ATTENTION" "1"
$OLLAMA_KV_CACHE_TYPE = Set-UserEnvDefault "OLLAMA_KV_CACHE_TYPE" "q8_0"

# Importante: niente OLLAMA_BASE_URLS. Gli endpoint multipli si gestiscono dalla UI con Prefix ID.
Clear-UserEnvValue "OLLAMA_BASE_URLS"
Remove-Item Env:OLLAMA_BASE_URLS -ErrorAction SilentlyContinue

# OpenVINO / NPU provider hook.
$OPENVINO_PYTHON_EXE = Set-UserEnvValue "OPENVINO_PYTHON_EXE" "$AI_ROOT\venvs\openvino\Scripts\python.exe"
$OPENVINO_ENV_SCRIPT = Set-UserEnvValue "OPENVINO_ENV_SCRIPT" "$AI_ROOT\services\openvino-env.ps1"
$OPENVINO_PROVIDER_SCRIPT = Set-UserEnvValue "OPENVINO_PROVIDER_SCRIPT" "$AI_ROOT\services\ovms-reranker-npu.ps1"
$OPENVINO_PROVIDER_PORT = Set-UserEnvValue "OPENVINO_PROVIDER_PORT" "$($config.OPENVINO_PORT)"
$OPENVINO_PROVIDER_DEVICE = Set-UserEnvValue "OPENVINO_PROVIDER_DEVICE" "GPU.0"
$OPENVINO_PROVIDER_HEALTH_URL = Set-UserEnvValue "OPENVINO_PROVIDER_HEALTH_URL" "http://$($config.HOSTNAME):$($config.OPENVINO_PORT)/v2/models/BAAI%2Fbge-reranker-v2-m3/ready"

# Default ON: provider OpenVINO/reranker esterno su 3550 quando il launcher lo avvia.
$ENABLE_OPENVINO_PROVIDER = Set-UserEnvValue "ENABLE_OPENVINO_PROVIDER" "1"
$ENABLE_EXTERNAL_RERANKER = Set-UserEnvValue "ENABLE_EXTERNAL_RERANKER" "1"
$RAG_RERANKING_MODEL = Set-UserEnvValue "RAG_RERANKING_MODEL" "BAAI/bge-reranker-v2-m3"
$RAG_EXTERNAL_RERANKER_URL = Set-UserEnvValue "RAG_EXTERNAL_RERANKER_URL" "http://$($config.HOSTNAME):$($config.OPENVINO_PORT)/v3/rerank"

if ($ENABLE_EXTERNAL_RERANKER -eq "1") {
    $RAG_RERANKING_ENGINE = Set-UserEnvValue "RAG_RERANKING_ENGINE" "external"
}
else {
    Clear-UserEnvValue "RAG_RERANKING_ENGINE"
    Remove-Item Env:RAG_RERANKING_ENGINE -ErrorAction SilentlyContinue
}

# NPU Phi diagnostic sidecar contract.
# This sidecar is separate from the 3550 OpenVINO/reranker provider and must
# always use the OpenVINO venv/env script. Default disabled until the sidecar
# script exists; enabling it must not change the 3550 RAG reranker wiring.
$NPU_PHI_PYTHON_EXE = Set-UserEnvValue "NPU_PHI_PYTHON_EXE" $OPENVINO_PYTHON_EXE
$NPU_PHI_ENV_SCRIPT = Set-UserEnvValue "NPU_PHI_ENV_SCRIPT" $OPENVINO_ENV_SCRIPT
$NPU_PHI_SERVICE_SCRIPT = Set-UserEnvValue "NPU_PHI_SERVICE_SCRIPT" "$AI_ROOT\services\npu-phi-service.ps1"
$NPU_PHI_HOST = Set-UserEnvValue "NPU_PHI_HOST" $config.HOSTNAME
$NPU_PHI_PORT = Set-UserEnvValue "NPU_PHI_PORT" "$($config.NPU_PHI_PORT)"
$NPU_PHI_BASE_URL = Set-UserEnvValue "NPU_PHI_BASE_URL" "http://$($config.HOSTNAME):$($config.NPU_PHI_PORT)"
$NPU_PHI_HEALTH_URL = Set-UserEnvValue "NPU_PHI_HEALTH_URL" "http://$($config.HOSTNAME):$($config.NPU_PHI_PORT)/healthz"
$NPU_PHI_MODEL_DIR = Set-UserEnvValue "NPU_PHI_MODEL_DIR" "$AI_ROOT\npu-models\Phi-3.5-mini-instruct-int4-cw-ov"
$NPU_PHI_CACHE_DIR = Set-UserEnvValue "NPU_PHI_CACHE_DIR" "$AI_ROOT\cache\openvino\npu_phi"
$NPU_PHI_SPOOL_DIR = Set-UserEnvValue "NPU_PHI_SPOOL_DIR" "$AI_ROOT\state\npu_phi\spool"
$NPU_PHI_QUEUE_MAXSIZE = Set-UserEnvDefault "NPU_PHI_QUEUE_MAXSIZE" "1"
$NPU_PHI_EXEC_TIMEOUT_SEC = Set-UserEnvDefault "NPU_PHI_EXEC_TIMEOUT_SEC" "12"
$NPU_PHI_GENERATE_HINT = Set-UserEnvDefault "NPU_PHI_GENERATE_HINT" "FAST_COMPILE"
$NPU_PHI_ENABLE_AOT_BLOB = Set-UserEnvDefault "NPU_PHI_ENABLE_AOT_BLOB" "1"
$ENABLE_NPU_PHI_SERVICE = Set-UserEnvDefault "ENABLE_NPU_PHI_SERVICE" "0"
$ENABLE_NPU_PHI_BROKER_DIAGNOSTICS = Set-UserEnvDefault "ENABLE_NPU_PHI_BROKER_DIAGNOSTICS" "0"
$NPU_PHI_BROKER_MODE = Set-UserEnvDefault "NPU_PHI_BROKER_MODE" "best_effort"

# ------------------------------------------------------------------
# Validazioni filesystem
# ------------------------------------------------------------------

if (-not (Test-Path $OPENWEBUI_EXE)) {
    throw "open-webui.exe non trovato: $OPENWEBUI_EXE"
}

if (-not (Test-Path $OPENVINO_PYTHON_EXE)) {
    Write-Warning "OPENVINO_PYTHON_EXE non trovato: $OPENVINO_PYTHON_EXE"
    Write-Warning "OpenVINO diagnostics/provider verranno saltati."
}

New-Item -ItemType Directory -Force -Path `
    $OPENWEBUI_DATA_DIR, `
    "$AI_ROOT\models-task", `
    "$AI_ROOT\logs", `
    "$AI_ROOT\cache\openvino", `
    "$AI_ROOT\cache\openvino\npu_phi", `
    "$AI_ROOT\cache\huggingface", `
    "$AI_ROOT\npu-models", `
    "$AI_ROOT\state\npu_phi\spool" | Out-Null

# ------------------------------------------------------------------
# Env runtime Open WebUI
# ------------------------------------------------------------------

$env:DATA_DIR = $OPENWEBUI_DATA_DIR
$env:WEBUI_SECRET_KEY = $WEBUI_SECRET_KEY
$env:USER_AGENT = $USER_AGENT
$env:OLLAMA_NO_CLOUD = $OLLAMA_NO_CLOUD
$env:OLLAMA_BASE_URL = $OLLAMA_BASE_URL
$env:TASK_MODEL = $TASK_MODEL
$env:RAG_EMBEDDING_BATCH_SIZE = $RAG_EMBEDDING_BATCH_SIZE
$env:ENABLE_QUERIES_CACHE = $ENABLE_QUERIES_CACHE
$env:MODELS_CACHE_TTL = $MODELS_CACHE_TTL
$env:RAG_SYSTEM_CONTEXT = $RAG_SYSTEM_CONTEXT

# Niente OLLAMA_BASE_URLS runtime.
Remove-Item Env:OLLAMA_BASE_URLS -ErrorAction SilentlyContinue

# CUDA_VISIBLE_DEVICES ÃƒÆ’Ã‚Â¨ persistente per Ollama Desktop al prossimo riavvio.
$env:CUDA_VISIBLE_DEVICES = $CUDA_VISIBLE_DEVICES
$env:OLLAMA_NUM_PARALLEL = $OLLAMA_NUM_PARALLEL
$env:OLLAMA_MAX_LOADED_MODELS = $OLLAMA_MAX_LOADED_MODELS
$env:OLLAMA_FLASH_ATTENTION = $OLLAMA_FLASH_ATTENTION
$env:OLLAMA_KV_CACHE_TYPE = $OLLAMA_KV_CACHE_TYPE

# OpenVINO env runtime.
$env:OPENVINO_PYTHON_EXE = $OPENVINO_PYTHON_EXE
$env:OPENVINO_PROVIDER_DEVICE = $OPENVINO_PROVIDER_DEVICE
$env:OPENVINO_PROVIDER_PORT = $OPENVINO_PROVIDER_PORT
$env:OPENVINO_PROVIDER_HEALTH_URL = $OPENVINO_PROVIDER_HEALTH_URL
$env:OPENVINO_PROVIDER_SCRIPT = $OPENVINO_PROVIDER_SCRIPT
$env:ENABLE_OPENVINO_PROVIDER = $ENABLE_OPENVINO_PROVIDER
$env:ENABLE_EXTERNAL_RERANKER = $ENABLE_EXTERNAL_RERANKER
$env:RAG_EXTERNAL_RERANKER_URL = $RAG_EXTERNAL_RERANKER_URL
$env:RAG_RERANKING_MODEL = $RAG_RERANKING_MODEL
$env:NPU_PHI_PYTHON_EXE = $NPU_PHI_PYTHON_EXE
$env:NPU_PHI_ENV_SCRIPT = $NPU_PHI_ENV_SCRIPT
$env:NPU_PHI_SERVICE_SCRIPT = $NPU_PHI_SERVICE_SCRIPT
$env:NPU_PHI_HOST = $NPU_PHI_HOST
$env:NPU_PHI_PORT = $NPU_PHI_PORT
$env:NPU_PHI_BASE_URL = $NPU_PHI_BASE_URL
$env:NPU_PHI_HEALTH_URL = $NPU_PHI_HEALTH_URL
$env:NPU_PHI_MODEL_DIR = $NPU_PHI_MODEL_DIR
$env:NPU_PHI_CACHE_DIR = $NPU_PHI_CACHE_DIR
$env:NPU_PHI_SPOOL_DIR = $NPU_PHI_SPOOL_DIR
$env:NPU_PHI_QUEUE_MAXSIZE = $NPU_PHI_QUEUE_MAXSIZE
$env:NPU_PHI_EXEC_TIMEOUT_SEC = $NPU_PHI_EXEC_TIMEOUT_SEC
$env:NPU_PHI_GENERATE_HINT = $NPU_PHI_GENERATE_HINT
$env:NPU_PHI_ENABLE_AOT_BLOB = $NPU_PHI_ENABLE_AOT_BLOB
$env:ENABLE_NPU_PHI_SERVICE = $ENABLE_NPU_PHI_SERVICE
$env:ENABLE_NPU_PHI_BROKER_DIAGNOSTICS = $ENABLE_NPU_PHI_BROKER_DIAGNOSTICS
$env:NPU_PHI_BROKER_MODE = $NPU_PHI_BROKER_MODE

if ($ENABLE_EXTERNAL_RERANKER -eq "1") {
    $env:RAG_RERANKING_ENGINE = "external"
}
else {
    Remove-Item Env:RAG_RERANKING_ENGINE -ErrorAction SilentlyContinue
}

if (Test-Path $OPENVINO_ENV_SCRIPT) {
    . $OPENVINO_ENV_SCRIPT
}
else {
    Write-Warning "openvino-env.ps1 non trovato: $OPENVINO_ENV_SCRIPT"
}

# ------------------------------------------------------------------
# Diagnostica OpenVINO
# ------------------------------------------------------------------

Write-Host ""
Write-Host "OpenVINO:"
Write-Host "  Python        = $OPENVINO_PYTHON_EXE"
Write-Host "  Env script    = $OPENVINO_ENV_SCRIPT"
Write-Host "  Device target = $OPENVINO_PROVIDER_DEVICE"
Write-Host "  Phi sidecar   = $NPU_PHI_BASE_URL (enabled=$ENABLE_NPU_PHI_SERVICE)"
Write-Host "  Phi Python    = $NPU_PHI_PYTHON_EXE"
Write-Host "  Phi model     = $NPU_PHI_MODEL_DIR"

if (Test-Path $OPENVINO_PYTHON_EXE) {
    try {
        & $OPENVINO_PYTHON_EXE -c "import openvino as ov; print('  Devices       = ' + str(ov.Core().available_devices))"
    }
    catch {
        Write-Warning "Diagnostica OpenVINO fallita: $($_.Exception.Message)"
    }
}

# ------------------------------------------------------------------
# Ollama endpoints
# ------------------------------------------------------------------

$OLLAMA_MAIN_URL = "http://$($config.HOSTNAME):$($config.OLLAMA_MAIN_PORT)"
$OLLAMA_TASK_GPU_URL = "http://$($config.HOSTNAME):$($config.OLLAMA_TASK_PORT)"
$OLLAMA_TASK_GPU_SCRIPT = Join-Path $AI_ROOT "services\ollama-task-vulkan.ps1"
$TASK_MODELFILE = Join-Path $AI_ROOT "modelfiles\Modelfile.qwen3task-8k"

if (Test-OllamaEndpoint $OLLAMA_MAIN_URL) {
    Write-Host "Ollama Desktop/main attivo su $OLLAMA_MAIN_URL"
}
else {
    Write-Warning "Ollama Desktop/main non risponde su $OLLAMA_MAIN_URL."
    Write-Warning "Apri o riavvia Ollama Desktop per usare i modelli main su RTX 5080."
}

Start-EndpointScriptIfNeeded `
    -Name "Ollama Task GPU0/Vulkan" `
    -Url $OLLAMA_TASK_GPU_URL `
    -Port $config.OLLAMA_TASK_PORT `
    -Script $OLLAMA_TASK_GPU_SCRIPT

Ensure-OllamaModel `
    -Url $OLLAMA_TASK_GPU_URL `
    -HostPort "$($config.HOSTNAME):$($config.OLLAMA_TASK_PORT)" `
    -Model $TASK_MODEL `
    -BaseModel "qwen3:1.7b" `
    -ModelFile $TASK_MODELFILE

# ------------------------------------------------------------------
# AI-Carmine Codex-like local agent runtime
#
# 3571 = bridge pubblico OpenWebUI.
# 3572 = job manager / broker / runtime agentico controllato.
# 11434 = planner principale 30B.
# 11435 = Vulkan/GPU0 selector-normalizer leggero, NON planner principale.
# ------------------------------------------------------------------
$null = Set-UserEnvValue "AICARMINE_AGENT_DEFAULT_MAX_STEPS" "40"
$null = Set-UserEnvValue "AICARMINE_AGENT_MAX_STEPS" "100"

$env:AICARMINE_AGENT_DEFAULT_MAX_STEPS = "40"
$env:AICARMINE_AGENT_MAX_STEPS = "100"
$AICarminePersistentConfig = @{
    AICARMINE_VULKAN_TOOL_BROKER_OPENAPI = "http://$($config.HOSTNAME):$($config.VULKAN_BRIDGE_PORT)/openapi.json"
    AICARMINE_VULKAN_TOOL_BROKER_URL = "http://$($config.HOSTNAME):$($config.VULKAN_BRIDGE_PORT)"
    AICARMINE_VULKAN_AGENT_URL = "http://$($config.HOSTNAME):$($config.VULKAN_AGENT_PORT)/vulkan/agent"
    AICARMINE_AGENT_PLANNER_URL = "http://$($config.HOSTNAME):$($config.OLLAMA_MAIN_PORT)/api/chat"
    AICARMINE_AGENT_PLANNER_MODEL = "qwen3-coder:30b"
    #AICARMINE_AGENT_PLANNER_MODEL = "qwen2.5-coder:14b"
    #AICARMINE_AGENT_PLANNER_MODEL = "ia-carmine-gpu1-qwen3-coder-30b-a3b-q2-tools-4k:latest"
    AICARMINE_AGENTIC_PLANNER_ENABLED = "1"
    AICARMINE_AGENTIC_PLANNER_NATIVE_TOOLS = "1"
    AICARMINE_AGENTIC_PLANNER_REQUIRE_NATIVE_TOOLS = "1"
    AICARMINE_AGENTIC_PLANNER_NUM_CTX = "12288"
    AICARMINE_AGENTIC_PLANNER_NUM_CTX_CAP = "12288"
    AICARMINE_AGENTIC_PLANNER_PROMPT_CHAR_BUDGET = "48000"
    AICARMINE_AGENTIC_PLANNER_PROMPT_COMPACT_RATIO = "0.5"
    AICARMINE_AGENTIC_PLANNER_NUM_PREDICT = "-1"
    AICARMINE_AGENTIC_RESULT_COMPACT_CHARS = "50000"
    AICARMINE_AGENT_APPROVAL_MODE = "safe_write_lab"
    AICARMINE_CODEX_COMMAND_TIMEOUT = "1000"
    AICARMINE_CODEX_MAX_TOOL_RESULT_CHARS = "70000"
    AICARMINE_VULKAN_BROKER_OLLAMA_URL = "http://$($config.HOSTNAME):$($config.OLLAMA_TASK_PORT)/api/chat"
    AICARMINE_VULKAN_BROKER_MODEL = $TASK_MODEL
    AICARMINE_VULKAN_BRIDGE_TIMEOUT_SECONDS = "12000"
    AICARMINE_AGENT_RETURN_WAIT_SECONDS = "9000"
}

Set-EnvironmentVariables -Variables $AICarminePersistentConfig -Persistent

Clear-UserEnvValue "AICARMINE_AGENTIC_PLANNER_HISTORY_TAIL"
Remove-Item Env:AICARMINE_AGENTIC_PLANNER_HISTORY_TAIL -ErrorAction SilentlyContinue
$VulkanRuntimeConfig = @{
    AICARMINE_VULKAN_MAX_TOOL_RESULT_CHARS = "4000"
    AICARMINE_VULKAN_FINAL_TIMEOUT_SECONDS = "2400"
    AICARMINE_VULKAN_NUM_CTX = "1024"
    AICARMINE_VULKAN_NUM_PREDICT = "-1"
    AICARMINE_VULKAN_INTERPRETER_NUM_PREDICT = "1024"
    AICARMINE_VULKAN_WRAPPER_NUM_PREDICT = "1342"
    AICARMINE_VULKAN_TEMPERATURE = "0"
}

Set-EnvironmentVariables -Variables $VulkanRuntimeConfig


function Normalize-AICarminePath {
    param([string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path)) {
        return ""
    }
    try {
        return ([System.IO.Path]::GetFullPath($Path)).TrimEnd('\').ToLowerInvariant()
    }
    catch {
        return $Path.TrimEnd('\').ToLowerInvariant()
    }
}

function Get-AICarmineLabtoolsPython {
    $LabToolsRoot = "$AI_ROOT\venvs\labtools"
    $LabToolsScripts = "$LabToolsRoot\Scripts"
    $Py = "$LabToolsScripts\python.exe"

    if (-not (Test-Path -LiteralPath $Py)) {
        throw "Python labtools non trovato: $Py"
    }

    return $Py
}

function Invoke-WithAICarmineLabtoolsPythonEnv {
    param(
        [Parameter(Mandatory = $true)]
        [scriptblock]$ScriptBlock
    )

    $LabToolsRoot = "$AI_ROOT\venvs\labtools"
    $LabToolsScripts = "$LabToolsRoot\Scripts"
    $OldVirtualEnv = $env:VIRTUAL_ENV
    $OldPythonHome = $env:PYTHONHOME
    $OldPythonPath = $env:PYTHONPATH
    $OldPath = $env:PATH
    $OldLabtoolsPython = $env:AICARMINE_LABTOOLS_PYTHON

    try {
        $env:AICARMINE_LABTOOLS_PYTHON = Get-AICarmineLabtoolsPython
        $env:VIRTUAL_ENV = $LabToolsRoot
        Remove-Item Env:PYTHONHOME -ErrorAction SilentlyContinue
        Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue

        $normalizedLabToolsScripts = Normalize-AICarminePath $LabToolsScripts
        $venvScriptsRoot = Normalize-AICarminePath "$AI_ROOT\venvs"
        $pathParts = @($env:PATH -split ';' | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
        $cleanPathParts = @(
            $pathParts | Where-Object {
                $normalized = Normalize-AICarminePath $_
                ($normalized -ne $normalizedLabToolsScripts) -and
                    (-not ($normalized.StartsWith($venvScriptsRoot) -and $normalized.EndsWith("\scripts")))
            }
        )
        $env:PATH = (@($LabToolsScripts) + $cleanPathParts) -join ';'

        & $ScriptBlock
    }
    finally {
        if ($null -eq $OldVirtualEnv) { Remove-Item Env:VIRTUAL_ENV -ErrorAction SilentlyContinue } else { $env:VIRTUAL_ENV = $OldVirtualEnv }
        if ($null -eq $OldPythonHome) { Remove-Item Env:PYTHONHOME -ErrorAction SilentlyContinue } else { $env:PYTHONHOME = $OldPythonHome }
        if ($null -eq $OldPythonPath) { Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue } else { $env:PYTHONPATH = $OldPythonPath }
        if ($null -eq $OldPath) { Remove-Item Env:PATH -ErrorAction SilentlyContinue } else { $env:PATH = $OldPath }
        if ($null -eq $OldLabtoolsPython) { Remove-Item Env:AICARMINE_LABTOOLS_PYTHON -ErrorAction SilentlyContinue } else { $env:AICARMINE_LABTOOLS_PYTHON = $OldLabtoolsPython }
    }
}

function Test-AICarmineLabtoolsProcessEnv {
    $ExpectedPrefix = Normalize-AICarminePath "$AI_ROOT\venvs\labtools"
    $ActualPrefix = Invoke-WithAICarmineLabtoolsPythonEnv {
        & (Get-AICarmineLabtoolsPython) -c "import sys; print(sys.prefix)"
    }
    return ((Normalize-AICarminePath $ActualPrefix) -eq $ExpectedPrefix)
}

function Assert-AICarmineLabtoolsPython {
    if (-not (Test-AICarmineLabtoolsProcessEnv)) {
        throw "Python labtools non isola sys.prefix su $AI_ROOT\venvs\labtools"
    }
}

function Test-AICarmineLabtoolsHealth {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Url
    )

    $ExpectedPrefix = Normalize-AICarminePath "$AI_ROOT\venvs\labtools"
    try {
        $Response = Invoke-RestMethod -Uri $Url -TimeoutSec 5
        if ($null -eq $Response -or $Response.ok -ne $true) {
            return $false
        }
        $ActualPrefix = Normalize-AICarminePath ([string]$Response.python_prefix)
        if ([string]::IsNullOrWhiteSpace($ActualPrefix)) {
            Write-Warning "$Url sano ma non espone python_prefix; considero il servizio obsoleto e lo riavvio."
            return $false
        }
        if ($ActualPrefix -ne $ExpectedPrefix) {
            Write-Warning "$Url usa python_prefix inatteso: $($Response.python_prefix) atteso: $AI_ROOT\venvs\labtools"
            return $false
        }
        return $true
    }
    catch {
        return $false
    }
}

function Test-AICarmineVulkanAgent {
    return (Test-AICarmineLabtoolsHealth -Url "http://$($config.HOSTNAME):$($config.VULKAN_AGENT_PORT)/health")
}

function Test-AICarmineVulkanBridge {
    return (Test-AICarmineLabtoolsHealth -Url "http://$($config.HOSTNAME):$($config.VULKAN_BRIDGE_PORT)/health")
}

function Stop-PortOwnerIfUnhealthy {
    param(
        [Parameter(Mandatory = $true)]
        [int]$Port,

        [Parameter(Mandatory = $true)]
        [string]$Label
    )

    $Owner = Get-PortOwner -Port $Port
    if ($null -ne $Owner) {
        Write-Warning "$Label porta $Port occupata ma endpoint non sano. Termino PID=$($Owner.ProcessId)"
        Stop-Process -Id $Owner.ProcessId -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 1
    }
}

function Get-AICarmineLogTail {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,

        [int]$Lines = 120
    )

    if (-not (Test-Path $Path)) {
        return "<missing log: $Path>"
    }

    try {
        $Tail = Get-Content -Path $Path -Tail $Lines -ErrorAction Stop
        if ($null -eq $Tail -or $Tail.Count -eq 0) {
            return "<empty log: $Path>"
        }
        return ($Tail -join [Environment]::NewLine)
    }
    catch {
        return "<log read failed: $Path :: $($_.Exception.Message)>"
    }
}

function Format-UvicornStartupFailure {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,

        [Parameter(Mandatory = $true)]
        [int]$Port,

        [Parameter(Mandatory = $true)]
        [string]$Module,

        [Parameter(Mandatory = $true)]
        [string]$Python,

        [Parameter(Mandatory = $true)]
        [string]$ServicesRoot,

        [Parameter(Mandatory = $true)]
        [string]$StdoutPath,

        [Parameter(Mandatory = $true)]
        [string]$StderrPath,

        [int]$ProcessId = 0,

        [string]$ExitCode = "",

        [string]$Reason = "startup_failed"
    )

    $StdoutTail = Get-AICarmineLogTail -Path $StdoutPath -Lines 80
    $StderrTail = Get-AICarmineLogTail -Path $StderrPath -Lines 160

    return @"
$Name processo terminato durante startup.
Reason=$Reason
PID=$ProcessId
ExitCode=$ExitCode
Module=$Module
Port=$Port
Python=$Python
ServicesRoot=$ServicesRoot
StdoutLog=$StdoutPath
StderrLog=$StderrPath

--- stdout tail ---
$StdoutTail

--- stderr tail ---
$StderrTail
"@
}

function Start-UvicornServiceIfNeeded {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,

        [Parameter(Mandatory = $true)]
        [int]$Port,

        [Parameter(Mandatory = $true)]
        [string]$Module,

        [Parameter(Mandatory = $true)]
        [scriptblock]$HealthCheck
    )

    $ServicesRoot = "$AI_ROOT\\services"
    $Py = Get-AICarmineLabtoolsPython
    $LogRoot = Join-Path $AI_ROOT "logs"
    New-Item -ItemType Directory -Force -Path $LogRoot | Out-Null
    $SafeName = ($Name -replace '[^a-zA-Z0-9_.-]+', '_').Trim('_')
    if (-not $SafeName) {
        $SafeName = "uvicorn"
    }
    $Stamp = Get-Date -Format "yyyyMMdd_HHmmss_fff"
    $StdoutPath = Join-Path $LogRoot "$SafeName-$Port-$Stamp.stdout.log"
    $StderrPath = Join-Path $LogRoot "$SafeName-$Port-$Stamp.stderr.log"

    if (& $HealthCheck) {
        Write-Host "$Name gia' sano su porta $Port"
        return
    }

    Stop-PortOwnerIfUnhealthy -Port $Port -Label $Name

    Write-Host "Avvio $Name su $($config.HOSTNAME):$Port..."

    $Proc = Start-Process `
        -FilePath $Py `
        -ArgumentList @("-m", "uvicorn", "$Module`:app", "--host", $config.HOSTNAME, "--port", "$Port") `
        -WorkingDirectory $ServicesRoot `
        -RedirectStandardOutput $StdoutPath `
        -RedirectStandardError $StderrPath `
        -WindowStyle Minimized `
        -PassThru

    Write-Host "$Name processo avviato: PID=$($Proc.Id)"
    Write-Host "$Name stdout: $StdoutPath"
    Write-Host "$Name stderr: $StderrPath"

    for ($i = 0; $i -lt 60; $i++) {
        if ($Proc.HasExited) {
            throw (Format-UvicornStartupFailure `
                -Name $Name `
                -Port $Port `
                -Module $Module `
                -Python $Py `
                -ServicesRoot $ServicesRoot `
                -StdoutPath $StdoutPath `
                -StderrPath $StderrPath `
                -ProcessId $Proc.Id `
                -ExitCode "$($Proc.ExitCode)" `
                -Reason "process_exited_before_healthcheck")
        }
        if (& $HealthCheck) {
            Write-Host "$Name sano su porta $Port"
            return
        }
        Start-Sleep -Seconds 1
    }

    throw (Format-UvicornStartupFailure `
        -Name $Name `
        -Port $Port `
        -Module $Module `
        -Python $Py `
        -ServicesRoot $ServicesRoot `
        -StdoutPath $StdoutPath `
        -StderrPath $StderrPath `
        -ProcessId $Proc.Id `
        -ExitCode "still_running" `
        -Reason "healthcheck_timeout")
}

function Start-AICarmineVulkanBridgeStack {
    $AgentPy = "$AI_ROOT\\services\\aicarmine_vulkan_tool_broker.py"
    $BridgePy = "$AI_ROOT\\services\\aicarmine_vulkan_bridge_server.py"

    if (-not (Test-Path $AgentPy)) {
        throw "Vulkan Agent Python non trovato: $AgentPy"
    }

    if (-not (Test-Path $BridgePy)) {
        throw "Vulkan Bridge Python non trovato: $BridgePy"
    }

    if (-not (Test-OllamaEndpoint "$OLLAMA_TASK_GPU_URL")) {
        throw "AI-Carmine Vulkan Bridge richiede Ollama Task GPU0/Vulkan sano su $OLLAMA_TASK_GPU_URL"
    }

    Start-UvicornServiceIfNeeded `
        -Name "AI-Carmine Vulkan Agent interno" `
        -Port $config.VULKAN_AGENT_PORT `
        -Module "aicarmine_vulkan_tool_broker" `
        -HealthCheck { Test-AICarmineVulkanAgent }

    Start-UvicornServiceIfNeeded `
        -Name "AI-Carmine Vulkan Bridge pubblico" `
        -Port $config.VULKAN_BRIDGE_PORT `
        -Module "aicarmine_vulkan_bridge_server" `
        -HealthCheck { Test-AICarmineVulkanBridge }

    Write-Host "AI-Carmine Vulkan Bridge pronto: http://$($config.HOSTNAME):$($config.VULKAN_BRIDGE_PORT)/openapi.json"
    Write-Host "AI-Carmine Vulkan Agent interno: http://$($config.HOSTNAME):$($config.VULKAN_AGENT_PORT)/health"
}

Start-AICarmineVulkanBridgeStack


# ------------------------------------------------------------------
# OpenVINO/NPU provider opzionale su 3550
# ------------------------------------------------------------------

Start-OpenVINOProviderIfEnabled `
    -Enabled $ENABLE_OPENVINO_PROVIDER `
    -Script $OPENVINO_PROVIDER_SCRIPT `
    -HealthUrl $OPENVINO_PROVIDER_HEALTH_URL `
    -Port $config.OPENVINO_PORT

# Phi-3.5 diagnostic sidecar: staged and disabled by default. When enabled,
# it must use the OpenVINO venv/env script and its dedicated 3551 port.
Start-NpuPhiServiceIfEnabled `
    -Enabled $ENABLE_NPU_PHI_SERVICE `
    -Script $NPU_PHI_SERVICE_SCRIPT `
    -HealthUrl $NPU_PHI_HEALTH_URL `
    -Port $config.NPU_PHI_PORT `
    -PythonExe $NPU_PHI_PYTHON_EXE `
    -EnvScript $NPU_PHI_ENV_SCRIPT

Set-Location $AI_ROOT

Write-Host ""
# ------------------------------------------------------------------
# Servizio: AI-Carmine Executor prima di Open WebUI
# ------------------------------------------------------------------

function Test-AICarmineExecutor {
    return Test-HttpEndpoint -Url "http://$($config.HOSTNAME):$($config.EXECUTOR_PORT)/health" -TimeoutSec 3
}

function New-AICarmineExecutorWrapper {
    $ExecutorScript = "$AI_ROOT\\services\\aicarmine-executor-server.ps1"
    $ExecutorPy = "$AI_ROOT\\services\\aicarmine-executor-server.py"
    $SafeRunner = "$AI_ROOT\\services\\aicarmine-run-safe-command.ps1"

    if (-not (Test-Path $ExecutorPy)) {
        throw "Executor Python server non trovato: $ExecutorPy"
    }

    if (-not (Test-Path $SafeRunner)) {
        throw "Safe command runner non trovato: $SafeRunner"
    }

    $Content = @'
$ErrorActionPreference = "Stop"

$AI_ROOT = "C:\Users\carmi\AI"


$Python = [Environment]::GetEnvironmentVariable("AICARMINE_EXECUTOR_PYTHON", "User")

if ([string]::IsNullOrWhiteSpace($Python)) {
    $Python = "$AI_ROOT\venvs\labtools\Scripts\python.exe"
}

if (-not (Test-Path $Python)) {
    throw "Python executor non trovato: $Python"
}

Remove-Item Env:PYTHONHOME -ErrorAction SilentlyContinue
Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue

$env:AICARMINE_SAFE_COMMAND_RUNNER = [Environment]::GetEnvironmentVariable("AICARMINE_SAFE_COMMAND_RUNNER", "User")
if ([string]::IsNullOrWhiteSpace($env:AICARMINE_SAFE_COMMAND_RUNNER)) {
    $env:AICARMINE_SAFE_COMMAND_RUNNER = "C:\Users\carmi\AI\services\aicarmine-run-safe-command.ps1"
}
$env:AICARMINE_LAB_REPO = [Environment]::GetEnvironmentVariable("AICARMINE_LAB_REPO", "User")
if ([string]::IsNullOrWhiteSpace($env:AICARMINE_LAB_REPO)) {
    $env:AICARMINE_LAB_REPO = "C:\Users\carmi\AI\"
}
$env:AICARMINE_REAL_REPO = [Environment]::GetEnvironmentVariable("AICARMINE_REAL_REPO", "User")
if ([string]::IsNullOrWhiteSpace($env:AICARMINE_REAL_REPO)) {
    $env:AICARMINE_REAL_REPO = "C:\Users\carmi\AI\"
}

Set-Location "$AI_ROOT\services"

& $Python -m uvicorn aicarmine-executor-server:app --host 127.0.0.1 --port 3560
'@

    # Speed: non riscrivere il wrapper a ogni avvio se il contenuto e' gia' identico.
    if ((-not (Test-Path $ExecutorScript)) -or ((Get-Content $ExecutorScript -Raw) -ne $Content)) {
        Set-Content -Path $ExecutorScript -Value $Content -Encoding UTF8
    }

    return $ExecutorScript
}

function Start-AICarmineExecutor {
    $ExecutorScript = New-AICarmineExecutorWrapper

    if (Test-AICarmineExecutor) {
        Write-Host "AI-Carmine Executor sano su http://127.0.0.1:3560/health"
        return
    }

    $existing = Get-CimInstance Win32_Process |
        Where-Object {
            $_.CommandLine -match "aicarmine-executor-server"
        }

    foreach ($proc in $existing) {
        Write-Warning "Executor trovato ma non sano. Termino PID=$($proc.ProcessId)"
        Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
    }

    $Owner = Get-PortOwner -Port 3560
    if ($null -ne $Owner) {
        Write-Warning "Executor porta 3560 occupata ma endpoint non sano. Termino PID=$($Owner.ProcessId)"
        Stop-Process -Id $Owner.ProcessId -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 1
    }

    Write-Host "Avvio AI-Carmine Executor su http://127.0.0.1:3560..."

    $p = Start-Process `
        -FilePath "powershell.exe" `
        -ArgumentList "-NoProfile -ExecutionPolicy Bypass -WindowStyle Minimized -File `"$ExecutorScript`"" `
        -WindowStyle Minimized `
        -PassThru

    Write-Host "AI-Carmine Executor processo avviato: PID=$($p.Id)"

    for ($i = 0; $i -lt 30; $i++) {
        if ($p.HasExited) {
            throw "AI-Carmine Executor terminato durante startup: PID=$($p.Id) ExitCode=$($p.ExitCode)"
        }
        if (Test-AICarmineExecutor) {
            Write-Host "AI-Carmine Executor sano su http://127.0.0.1:3560/health"
            return
        }

        Start-Sleep -Seconds 1
    }

    throw "AI-Carmine Executor non risponde su http://127.0.0.1:3560/health"
}

Start-AICarmineExecutor

# ------------------------------------------------------------------
# Servizio: AI-Carmine Jupyter Code Interpreter
# ------------------------------------------------------------------

$script:AICarmineJupyterTokenCache = $null

function New-AICarmineJupyterTokenFile {
    param([string]$Path)

    New-Item -ItemType Directory -Force -Path (Split-Path $Path) | Out-Null

    $Token = CODE_EXECUTION_JUPYTER_AUTH_TOKEN
    $Secure = ConvertTo-SecureString $Token -AsPlainText -Force
    $Secure | ConvertFrom-SecureString | Set-Content -Path $Path -Encoding ASCII

    return $Token
}

function Get-AICarmineJupyterToken {
    # Speed: nello stesso avvio il token non cambia; evita lettura DPAPI/decrypt a ogni health poll.
    if (-not [string]::IsNullOrWhiteSpace($script:AICarmineJupyterTokenCache)) {
        return $script:AICarmineJupyterTokenCache
    }

    $TokenFile = [Environment]::GetEnvironmentVariable("AICARMINE_JUPYTER_TOKEN_FILE", "User")

    if ([string]::IsNullOrWhiteSpace($TokenFile)) {
        $TokenFile = "C:\Users\carmi\AI\secrets\jupyter_code_token.dpapi"
        $null = Set-UserEnvValue "AICARMINE_JUPYTER_TOKEN_FILE" $TokenFile
    }

    if (-not (Test-Path $TokenFile)) {
        $script:AICarmineJupyterTokenCache = New-AICarmineJupyterTokenFile -Path $TokenFile
        return $script:AICarmineJupyterTokenCache
    }

    try {
        $RawToken = (Get-Content $TokenFile -Raw).Trim()
        $SecureToken = ConvertTo-SecureString -String $RawToken
        $Token = [System.Net.NetworkCredential]::new("", $SecureToken).Password

        if ([string]::IsNullOrWhiteSpace($Token) -or $Token.Length -lt 32) {
            throw "Token Jupyter vuoto o troppo corto"
        }

        $script:AICarmineJupyterTokenCache = $Token
        return $script:AICarmineJupyterTokenCache
    }
    catch {
        Write-Warning "Token Jupyter non valido o corrotto. Rigenero: $TokenFile"
        Remove-Item $TokenFile -Force -ErrorAction SilentlyContinue
        $script:AICarmineJupyterTokenCache = New-AICarmineJupyterTokenFile -Path $TokenFile
        return $script:AICarmineJupyterTokenCache
    }
}

function Test-AICarmineJupyter {
    try {
        $Token = Get-AICarmineJupyterToken
        return Test-HttpEndpoint -Url "http://$($config.HOSTNAME):$($config.JUPYTER_PORT)/api/status?token=$Token" -TimeoutSec 3
    }
    catch {
        return $false
    }
}

function Start-AICarmineJupyter {
    $JupyterScript = "$AI_ROOT\\services\\aicarmine-jupyter-codeinterpreter.ps1"

    if (-not (Test-Path $JupyterScript)) {
        throw "Jupyter Code Interpreter script non trovato: $JupyterScript"
    }

    if (Test-AICarmineJupyter) {
        Write-Host "AI-Carmine Jupyter gia' sano su http://$($config.HOSTNAME):$($config.JUPYTER_PORT)"
        return
    }

    $existing = Get-CimInstance Win32_Process |
        Where-Object {
            $_.CommandLine -match [regex]::Escape($JupyterScript)
        }

    foreach ($proc in $existing) {
        Write-Warning "Jupyter trovato ma non sano. Termino PID=$($proc.ProcessId)"
        Stop-Process -Id $proc.ProcessId -Force
    }

    $null = Set-UserEnvValue "AICARMINE_JUPYTER_PORT" ([string]$config.JUPYTER_PORT)
    $env:AICARMINE_JUPYTER_PORT = [string]$config.JUPYTER_PORT

    Write-Host "Avvio AI-Carmine Jupyter Code Interpreter su http://$($config.HOSTNAME):$($config.JUPYTER_PORT)..."

    $p = Start-Process `
        -FilePath "powershell.exe" `
        -ArgumentList "-NoProfile -ExecutionPolicy Bypass -WindowStyle Minimized -File `"$JupyterScript`"" `
        -WindowStyle Minimized `
        -PassThru

    Write-Host "AI-Carmine Jupyter processo avviato: PID=$($p.Id)"

    for ($i = 0; $i -lt 45; $i++) {
        if (Test-AICarmineJupyter) {
            Write-Host "AI-Carmine Jupyter sano su http://$($config.HOSTNAME):$($config.JUPYTER_PORT)"
            return
        }

        Start-Sleep -Seconds 1
    }

    throw "AI-Carmine Jupyter non risponde su http://$($config.HOSTNAME):$($config.JUPYTER_PORT)"
}


# >>> AIC_OPEN_TERMINAL_REPLACES_JUPYTER
# Open Terminal runs alongside Jupyter Code Interpreter on a distinct port.
# v3 invariant: this block must be top-level PowerShell code, not inside a here-string.

$script:AICOpenTerminalStarted = $false

function Get-AICFirstNonEmpty {
    param([object[]]$Values)
    foreach ($v in $Values) {
        if ($null -eq $v) { continue }
        $s = [string]$v
        if (-not [string]::IsNullOrWhiteSpace($s)) {
            $s = $s.Trim()
            if (($s.StartsWith('"') -and $s.EndsWith('"')) -or ($s.StartsWith("'") -and $s.EndsWith("'"))) {
                if ($s.Length -ge 2) { $s = $s.Substring(1, $s.Length - 2) }
            }
            if (-not [string]::IsNullOrWhiteSpace($s)) { return $s }
        }
    }
    return $null
}

function Resolve-AICOpenTerminalCommand {
    $venvScripts = $null

    if (-not [string]::IsNullOrWhiteSpace($AI_ROOT)) {
        $venvScripts = Join-Path $AI_ROOT "venvs\openwebui\Scripts"
    }

    if (-not [string]::IsNullOrWhiteSpace($venvScripts) -and (Test-Path -LiteralPath $venvScripts)) {
        foreach ($name in @("open-terminal.exe", "open-terminal.cmd", "open-terminal.ps1", "open-terminal")) {
            $candidate = Join-Path $venvScripts $name
            if (Test-Path -LiteralPath $candidate) {
                return $candidate
            }
        }
    }

    $cmd = Get-Command open-terminal -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }

    return $null
}

function Test-AICOpenTerminalReachable {
    param(
        [string]$HostAddress,
        [int]$Port
    )

    $baseUrl = ("http://{0}:{1}" -f $HostAddress, $Port)

    foreach ($suffix in @("/openapi.json", "/docs", "/")) {
        try {
            $r = Invoke-WebRequest -Uri ($baseUrl + $suffix) -TimeoutSec 2 -UseBasicParsing
            if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 500) {
                return $true
            }
        }
        catch {
            # try next endpoint
        }
    }

    return $false
}

function Start-AICOpenTerminal {
    param(
        [object]$ApiKeyCandidate = $null,
        [object]$PortCandidate = $null,
        [object]$HostCandidate = $null
    )

    if ($script:AICOpenTerminalStarted) {
        Write-Host "[open-terminal-replaces-jupyter] already started in this launcher session."
        return
    }

    $token = Get-AICFirstNonEmpty @(
        $ApiKeyCandidate,
        $env:OPEN_TERMINAL_API_KEY,
        $env:JUPYTER_TOKEN,
        $env:JUPYTER_SERVER_TOKEN,
        $env:NOTEBOOK_TOKEN,
        $env:OPENWEBUI_JUPYTER_TOKEN,
        $env:OPENWEBUI_CODE_EXECUTION_JUPYTER_TOKEN,
        $env:CODE_EXECUTION_JUPYTER_AUTH_TOKEN,
        $env:WEBUI_JUPYTER_TOKEN
    )

    if ([string]::IsNullOrWhiteSpace($token)) {
        throw "[open-terminal-replaces-jupyter] Missing token. Get-AICarmineJupyterToken did not return a usable token and no OPEN_TERMINAL_API_KEY/JUPYTER_TOKEN was set."
    }

    $portRaw = Get-AICFirstNonEmpty @($env:OPEN_TERMINAL_PORT, $PortCandidate)
    $port = 8888
    if (-not [string]::IsNullOrWhiteSpace($portRaw)) {
        try { $port = [int]$portRaw } catch { throw "[open-terminal-replaces-jupyter] Invalid port: $portRaw" }
    }

    $hostAddress = Get-AICFirstNonEmpty @($HostCandidate, $env:OPEN_TERMINAL_HOST, "127.0.0.1")
    $labRepoForTerminal = Get-AICFirstNonEmpty @(
        $env:AICARMINE_LAB_REPO,
        [Environment]::GetEnvironmentVariable("AICARMINE_LAB_REPO", "User"),
        "C:\Users\carmi\AI\lab-worktrees\blender-audio-project-lab"
    )
    $cwd = Get-AICFirstNonEmpty @($env:OPEN_TERMINAL_CWD, [Environment]::GetEnvironmentVariable("OPEN_TERMINAL_CWD", "User"), $labRepoForTerminal)
    if ([string]::IsNullOrWhiteSpace($cwd) -or -not (Test-Path -LiteralPath $cwd)) {
        throw "[open-terminal-replaces-jupyter] AICARMINE_LAB_REPO/Open Terminal cwd non valido: $cwd"
    }

    $cmd = Resolve-AICOpenTerminalCommand
    if ([string]::IsNullOrWhiteSpace($cmd) -or -not (Test-Path -LiteralPath $cmd)) {
        throw "[open-terminal-replaces-jupyter] open-terminal not found in $AI_ROOT\venvs\openwebui\Scripts or PATH. Install inside that venv: & `"$AI_ROOT\venvs\openwebui\Scripts\python.exe`" -m pip install open-terminal"
    }

    $baseUrl = ("http://{0}:{1}" -f $hostAddress, $port)
    if (Test-AICOpenTerminalReachable -HostAddress $hostAddress -Port $port) {
        Write-Host "[open-terminal-replaces-jupyter] Open Terminal already reachable at $baseUrl"
        $script:AICOpenTerminalStarted = $true
        return
    }

    $env:OPEN_TERMINAL_API_KEY = $token
    $env:OPEN_TERMINAL_CWD = $cwd
    $env:OPEN_TERMINAL_HOST = $hostAddress
    $env:OPEN_TERMINAL_PORT = "$port"

    Write-Host "[open-terminal-replaces-jupyter] launching Open Terminal"
    Write-Host "[open-terminal-replaces-jupyter] exe=$cmd"
    Write-Host "[open-terminal-replaces-jupyter] cwd=$cwd"
    Write-Host "[open-terminal-replaces-jupyter] url=$baseUrl"
    Write-Host "[open-terminal-replaces-jupyter] token_source=same-token-as-old-jupyter"
    Write-Host "[open-terminal-replaces-jupyter] Jupyter/JupyterLab runs separately on port $($config.JUPYTER_PORT)."

    $args = @("run", "--host", $hostAddress, "--port", "$port", "--api-key", "$token")

    if ($cmd.ToLowerInvariant().EndsWith(".ps1")) {
        Start-Process -FilePath "powershell.exe" -ArgumentList (@("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $cmd) + $args) -WorkingDirectory $cwd -WindowStyle Normal
    }
    else {
        Start-Process -FilePath $cmd -ArgumentList $args -WorkingDirectory $cwd -WindowStyle Normal
    }

    $script:AICOpenTerminalStarted = $true
}
# <<< AIC_OPEN_TERMINAL_REPLACES_JUPYTER

# ------------------------------------------------------------------
# Servizi: AI-Carmine Jupyter Code Interpreter + Open Terminal
#   Jupyter resta il backend coding di OpenWebUI; Open Terminal resta shell separata.
# ------------------------------------------------------------------

$OpenTerminalToken = Get-AICFirstNonEmpty @(
    $env:OPEN_TERMINAL_API_KEY,
    $env:CODE_INTERPRETER_JUPYTER_AUTH_TOKEN,
    $env:CODE_EXECUTION_JUPYTER_AUTH_TOKEN,
    [Environment]::GetEnvironmentVariable("OPEN_TERMINAL_API_KEY", "User"),
    [Environment]::GetEnvironmentVariable("CODE_INTERPRETER_JUPYTER_AUTH_TOKEN", "User"),
    [Environment]::GetEnvironmentVariable("CODE_EXECUTION_JUPYTER_AUTH_TOKEN", "User")
)
if ([string]::IsNullOrWhiteSpace($OpenTerminalToken)) {
    $OpenTerminalToken = Get-AICarmineJupyterToken
}
$OpenTerminalHost = Get-AICFirstNonEmpty @($env:OPEN_TERMINAL_HOST, $config.HOSTNAME, "127.0.0.1")
$OpenTerminalPort = [int]$config.OPEN_TERMINAL_PORT
$OpenTerminalPortRaw = Get-AICFirstNonEmpty @($env:OPEN_TERMINAL_PORT, $config.OPEN_TERMINAL_PORT)

if (-not [string]::IsNullOrWhiteSpace($OpenTerminalPortRaw)) {
    try { $OpenTerminalPort = [int]$OpenTerminalPortRaw } catch { throw "OPEN_TERMINAL_PORT non valido: $OpenTerminalPortRaw" }
}

if ($OpenTerminalPort -eq [int]$config.JUPYTER_PORT) {
    $OpenTerminalPort = [int]$config.OPEN_TERMINAL_PORT
}

$OpenTerminalUrl = ("http://{0}:{1}" -f $OpenTerminalHost, $OpenTerminalPort)
$JupyterUrl = "http://$($config.HOSTNAME):$($config.JUPYTER_PORT)"
$OpenTerminalCwd = $AI_ROOT
if ([string]::IsNullOrWhiteSpace($OpenTerminalCwd) -or -not (Test-Path -LiteralPath $OpenTerminalCwd)) {
    throw "AICARMINE_LAB_REPO/Open Terminal cwd non valido: $OpenTerminalCwd"
}

$null = Set-UserEnvValue "AICARMINE_JUPYTER_TOKEN_FILE" "C:\Users\carmi\AI\secrets\jupyter_code_token.dpapi"
$null = Set-UserEnvValue "AICARMINE_JUPYTER_URL" $JupyterUrl
$null = Set-UserEnvValue "AICARMINE_JUPYTER_PORT" ([string]$config.JUPYTER_PORT)
$null = Set-UserEnvValue "AICARMINE_JUPYTER_WORKDIR" $OpenTerminalCwd
$null = Set-UserEnvValue "ENABLE_CODE_EXECUTION" "true"
$null = Set-UserEnvValue "ENABLE_CODE_INTERPRETER" "true"
$null = Set-UserEnvValue "USER_PERMISSIONS_FEATURES_CODE_INTERPRETER" "true"
$null = Set-UserEnvValue "CODE_EXECUTION_ENGINE" "jupyter"
$null = Set-UserEnvValue "CODE_EXECUTION_JUPYTER_URL" $JupyterUrl
$null = Set-UserEnvValue "CODE_EXECUTION_JUPYTER_AUTH" "token"
$null = Set-UserEnvValue "CODE_EXECUTION_JUPYTER_AUTH_TOKEN" $OpenTerminalToken
$null = Set-UserEnvValue "CODE_EXECUTION_JUPYTER_AUTH_PASSWORD" ""
$null = Set-UserEnvValue "CODE_EXECUTION_JUPYTER_KERNEL" "python3"
$null = Set-UserEnvValue "CODE_EXECUTION_JUPYTER_TIMEOUT" "120"
$null = Set-UserEnvValue "CODE_INTERPRETER_ENGINE" "jupyter"
$null = Set-UserEnvValue "CODE_INTERPRETER_JUPYTER_URL" $JupyterUrl
$null = Set-UserEnvValue "CODE_INTERPRETER_JUPYTER_AUTH" "token"
$null = Set-UserEnvValue "CODE_INTERPRETER_JUPYTER_AUTH_TOKEN" $OpenTerminalToken
$null = Set-UserEnvValue "CODE_INTERPRETER_JUPYTER_AUTH_PASSWORD" ""
$null = Set-UserEnvValue "CODE_INTERPRETER_JUPYTER_TIMEOUT" "120"
$null = Set-UserEnvValue "OPEN_TERMINAL_API_KEY" $OpenTerminalToken
$null = Set-UserEnvValue "OPEN_TERMINAL_URL" $OpenTerminalUrl
$null = Set-UserEnvValue "OPEN_TERMINAL_HOST" $OpenTerminalHost
$null = Set-UserEnvValue "OPEN_TERMINAL_PORT" ([string]$OpenTerminalPort)
$null = Set-UserEnvValue "OPEN_TERMINAL_CWD" $OpenTerminalCwd
$null = Set-UserEnvValue "AICARMINE_OPEN_TERMINAL_URL" $OpenTerminalUrl
$null = Set-UserEnvValue "AICARMINE_OPEN_TERMINAL_WORKDIR" $OpenTerminalCwd

$env:AICARMINE_JUPYTER_URL = $JupyterUrl
$env:AICARMINE_JUPYTER_PORT = [string]$config.JUPYTER_PORT
$env:AICARMINE_JUPYTER_WORKDIR = $OpenTerminalCwd
$env:ENABLE_CODE_EXECUTION = "true"
$env:ENABLE_CODE_INTERPRETER = "true"
$env:USER_PERMISSIONS_FEATURES_CODE_INTERPRETER = "true"
$env:CODE_EXECUTION_ENGINE = "jupyter"
$env:CODE_EXECUTION_JUPYTER_URL = $JupyterUrl
$env:CODE_EXECUTION_JUPYTER_AUTH = "token"
$env:CODE_EXECUTION_JUPYTER_AUTH_TOKEN = $OpenTerminalToken
$env:CODE_EXECUTION_JUPYTER_AUTH_PASSWORD = ""
$env:CODE_EXECUTION_JUPYTER_KERNEL = "python3"
$env:CODE_EXECUTION_JUPYTER_TIMEOUT = "120"
$env:CODE_INTERPRETER_ENGINE = "jupyter"
$env:CODE_INTERPRETER_JUPYTER_URL = $JupyterUrl
$env:CODE_INTERPRETER_JUPYTER_AUTH = "token"
$env:CODE_INTERPRETER_JUPYTER_AUTH_TOKEN = $OpenTerminalToken
$env:CODE_INTERPRETER_JUPYTER_AUTH_PASSWORD = ""
$env:CODE_INTERPRETER_JUPYTER_TIMEOUT = "120"
$env:OPEN_TERMINAL_API_KEY = $OpenTerminalToken
$env:OPEN_TERMINAL_URL = $OpenTerminalUrl
$env:OPEN_TERMINAL_HOST = $OpenTerminalHost
$env:OPEN_TERMINAL_PORT = [string]$OpenTerminalPort
$env:OPEN_TERMINAL_CWD = $OpenTerminalCwd

Start-AICarmineJupyter
Start-AICOpenTerminal -ApiKeyCandidate $OpenTerminalToken -PortCandidate $OpenTerminalPort -HostCandidate $OpenTerminalHost

# ------------------------------------------------------------------
# Legacy model-facing tool server cleanup
#   3562/3563 LabTools/Qwen servers were replaced by 3571 helper_for_all.
# ------------------------------------------------------------------

$null = Set-UserEnvValue "ENABLE_AICARMINE_LABTOOLS" "0"
$null = Set-UserEnvValue "AICARMINE_LAB_PATCH_URL" ""
$null = Set-UserEnvValue "AICARMINE_LAB_PATCH_OPENAPI" ""
$null = Set-UserEnvValue "AICARMINE_LAB_GUIDE_URL" ""
$null = Set-UserEnvValue "AICARMINE_LAB_GUIDE_OPENAPI" ""
$null = Set-UserEnvValue "AICARMINE_QWEN_PATCH_URL" ""
$null = Set-UserEnvValue "AICARMINE_QWEN_PATCH_OPENAPI" ""
$null = Set-UserEnvValue "AICARMINE_QWEN_GUIDE_URL" ""
$null = Set-UserEnvValue "AICARMINE_QWEN_GUIDE_OPENAPI" ""
$ResolvedLabRepo = [Environment]::GetEnvironmentVariable("AICARMINE_LAB_REPO", "User")
if ([string]::IsNullOrWhiteSpace($ResolvedLabRepo)) {
    $ResolvedLabRepo = "C:\Users\carmi\AI\lab-worktrees\blender-audio-project-lab"
}
$ResolvedRealRepo = [Environment]::GetEnvironmentVariable("AICARMINE_REAL_REPO", "User")
if ([string]::IsNullOrWhiteSpace($ResolvedRealRepo)) {
    $ResolvedRealRepo = "C:\Users\carmi\ProjectsDir\blender-audio-project"
}
$null = Set-UserEnvValue "AICARMINE_LAB_REPO" $ResolvedLabRepo
$null = Set-UserEnvValue "AICARMINE_REAL_REPO" $ResolvedRealRepo

$env:AICARMINE_LAB_PATCH_URL = ""
$env:AICARMINE_LAB_PATCH_OPENAPI = ""
$env:AICARMINE_LAB_GUIDE_URL = ""
$env:AICARMINE_LAB_GUIDE_OPENAPI = ""
$env:AICARMINE_QWEN_PATCH_URL = ""
$env:AICARMINE_QWEN_PATCH_OPENAPI = ""
$env:AICARMINE_QWEN_GUIDE_URL = ""
$env:AICARMINE_QWEN_GUIDE_OPENAPI = ""
$env:AICARMINE_LAB_REPO = $ResolvedLabRepo
$env:AICARMINE_REAL_REPO = $ResolvedRealRepo

Stop-PortOwner -Port 3562 -Label "Legacy AI-Carmine Qwen Patch Tools"
Stop-PortOwner -Port 3563 -Label "Legacy AI-Carmine Qwen Guide Tools"

# ------------------------------------------------------------------
# Servizio: AI-Carmine Lab Mirror Watchdog
# ------------------------------------------------------------------

function Ensure-AICarmineLabMirrorScripts {
    $SyncScript = "C:\Users\carmi\AI\services\sync-lab-from-main.ps1"
    $WatchScript = "C:\Users\carmi\AI\services\watch-lab-mirror.ps1"

    if (-not (Test-Path $SyncScript)) {
        throw "Lab mirror sync script non trovato: $SyncScript"
    }

    if (-not (Test-Path $WatchScript)) {
        throw "Lab mirror watchdog script non trovato: $WatchScript"
    }
}

function Test-AICarmineLabMirrorWatchdog {
    $Script = "C:\Users\carmi\AI\services\watch-lab-mirror.ps1"
    $escaped = [regex]::Escape($Script)

    $existing = Get-CimInstance Win32_Process |
        Where-Object {
            $_.CommandLine -match $escaped
        } |
        Select-Object -First 1

    return ($null -ne $existing)
}

function Start-AICarmineLabMirrorWatchdog {
    Ensure-AICarmineLabMirrorScripts

    $enabled = [Environment]::GetEnvironmentVariable("ENABLE_AICARMINE_LAB_MIRROR", "User")

    if ([string]::IsNullOrWhiteSpace($enabled)) {
        $enabled = "0"
        $null = Set-UserEnvValue "ENABLE_AICARMINE_LAB_MIRROR" $enabled
    }

    if ($enabled -ne "1") {
        Write-Host "AI-Carmine Lab Mirror Watchdog disabilitato. ENABLE_AICARMINE_LAB_MIRROR=$enabled"
        return
    }

    $Script = "C:\Users\carmi\AI\services\watch-lab-mirror.ps1"

    if (Test-AICarmineLabMirrorWatchdog) {
        Write-Host "AI-Carmine Lab Mirror Watchdog giÃƒÆ’Ã‚Â  attivo."
        return
    }

    $interval = [Environment]::GetEnvironmentVariable("AICARMINE_LAB_MIRROR_INTERVAL_SECONDS", "User")
    if ([string]::IsNullOrWhiteSpace($interval)) {
        $interval = "60"
        $null = Set-UserEnvValue "AICARMINE_LAB_MIRROR_INTERVAL_SECONDS" $interval
    }

    Write-Host "Avvio AI-Carmine Lab Mirror Watchdog ogni $interval secondi..."

    $p = Start-Process `
        -FilePath "powershell.exe" `
        -ArgumentList "-NoProfile -ExecutionPolicy Bypass -WindowStyle Minimized -File `"$Script`" -IntervalSeconds $interval" `
        -WindowStyle Minimized `
        -PassThru

    Write-Host "AI-Carmine Lab Mirror Watchdog processo avviato: PID=$($p.Id)"
}

Start-AICarmineLabMirrorWatchdog

# ------------------------------------------------------------------
# GUIDED SHUTDOWN: chiude servizi gestiti dal launcher, escluso Ollama Desktop/main 11434
# ------------------------------------------------------------------

function Stop-ProcessByCommandLinePattern {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Label,

        [Parameter(Mandatory = $true)]
        [string]$Pattern
    )

    $foundProcesses = Get-CimInstance Win32_Process |
        Where-Object {
            $_.CommandLine -and ($_.CommandLine -match $Pattern)
        }

    foreach ($proc in $foundProcesses) {
        try {
            Write-Host "Stop $Label PID=$($proc.ProcessId)"
            Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
        }
        catch {
            Write-Warning "Impossibile fermare $Label PID=$($proc.ProcessId): $($_.Exception.Message)"
        }
    }
}

function Stop-AICarmineManagedServices {
    Write-Host ""
    Write-Host "Shutdown guidato AI-Carmine..."
    Write-Host "Nota: Ollama Desktop/main 11434 NON viene chiuso."

    try {
        $plannerUrl = $env:AICARMINE_AGENT_PLANNER_URL
        if ([string]::IsNullOrWhiteSpace($plannerUrl)) {
            $plannerUrl = $AICarminePersistentConfig.AICARMINE_AGENT_PLANNER_URL
        }
        $plannerModel = $env:AICARMINE_AGENT_PLANNER_MODEL
        if ([string]::IsNullOrWhiteSpace($plannerModel)) {
            $plannerModel = $AICarminePersistentConfig.AICARMINE_AGENT_PLANNER_MODEL
        }
        if (-not [string]::IsNullOrWhiteSpace($plannerUrl) -and -not [string]::IsNullOrWhiteSpace($plannerModel)) {
            $plannerBaseUrl = $plannerUrl.TrimEnd("/")
            foreach ($suffix in @("/api/chat", "/api/generate")) {
                if ($plannerBaseUrl.EndsWith($suffix)) {
                    $plannerBaseUrl = $plannerBaseUrl.Substring(0, $plannerBaseUrl.Length - $suffix.Length)
                    break
                }
            }
            $unloadEndpoint = "$plannerBaseUrl/api/generate"
            $unloadBody = @{
                model = $plannerModel
                prompt = ""
                stream = $false
                keep_alive = 0
            } | ConvertTo-Json -Compress
            Write-Host "Scarico modello planner da Ollama main: $plannerModel"
            Invoke-RestMethod `
                -Uri $unloadEndpoint `
                -Method Post `
                -ContentType "application/json" `
                -Body $unloadBody `
                -TimeoutSec 10 | Out-Null
            Write-Host "Scarico modello planner completato."
        }
        else {
            Write-Warning "Scarico modello planner saltato: planner URL/model non configurati."
        }
    }
    catch {
        Write-Warning "Scarico modello planner fallito: $($_.Exception.Message)"
    }

    # Servizi AI-Carmine.
    Stop-ProcessByCommandLinePattern -Label "AI-Carmine Vulkan Tool Broker wrapper" -Pattern "aicarmine-vulkan-tool-broker"
    Stop-ProcessByCommandLinePattern -Label "AI-Carmine Vulkan Agent uvicorn" -Pattern "aicarmine_vulkan_tool_broker"
    Stop-ProcessByCommandLinePattern -Label "AI-Carmine Vulkan Bridge uvicorn" -Pattern "aicarmine_vulkan_bridge_server"
    Stop-ProcessByCommandLinePattern -Label "AI-Carmine Ollama task runner" -Pattern "runner --ollama-engine.*models-task"
    Stop-ProcessByCommandLinePattern -Label "AI-Carmine Executor" -Pattern "aicarmine-executor-server"
    Stop-ProcessByCommandLinePattern -Label "Lab mirror watchdog" -Pattern "watch-lab-mirror"
    Stop-ProcessByCommandLinePattern -Label "Lab mirror sync" -Pattern "sync-lab-from-main"
    Stop-ProcessByCommandLinePattern -Label "AI-Carmine Open Terminal" -Pattern "open-terminal"
    Stop-ProcessByCommandLinePattern -Label "AI-Carmine Jupyter" -Pattern "aicarmine-jupyter-codeinterpreter"
    Stop-ProcessByCommandLinePattern -Label "OVMS reranker wrapper" -Pattern "ovms-reranker"

    # Porte gestite. NON includere OLLAMA_MAIN_PORT (11434).
    $portsToStop = @(
        @{ Port = $config.VULKAN_BRIDGE_PORT; Label = "AI-Carmine Vulkan Bridge pubblico" }
        @{ Port = $config.VULKAN_AGENT_PORT; Label = "AI-Carmine Vulkan Agent interno" }
        @{ Port = $config.OLLAMA_TASK_PORT; Label = "Ollama task GPU0/Vulkan" }
        @{ Port = $config.OPENVINO_PORT; Label = "OVMS reranker" }
        @{ Port = $config.EXECUTOR_PORT; Label = "AI-Carmine Executor" }
        @{ Port = 3562; Label = "Legacy AI-Carmine Qwen Patch Tools" }
        @{ Port = 3563; Label = "Legacy AI-Carmine Qwen Guide Tools" }
        @{ Port = $config.OPEN_TERMINAL_PORT; Label = "AI-Carmine Open Terminal" }
        @{ Port = $config.JUPYTER_PORT; Label = "Jupyter Code Interpreter" }
        @{ Port = $config.WEBUI_PORT; Label = "Open WebUI" }
    )

    foreach ($portInfo in $portsToStop) {
        Stop-PortOwner -Port $portInfo.Port -Label $portInfo.Label
    }

    Stop-ProcessByCommandLinePattern -Label "AI-Carmine Ollama task runner post-port-stop" -Pattern "runner --ollama-engine.*models-task"

    Remove-Item Env:PYTHONHOME -ErrorAction SilentlyContinue
    Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue

    Write-Host "Shutdown guidato completato."
}

# ------------------------------------------------------------------
# Riepilogo runtime
# ------------------------------------------------------------------

Write-Host ""
Write-Host "Runtime topology:"
Write-Host "  Open WebUI        = http://$($config.HOSTNAME):$($config.WEBUI_PORT)"
Write-Host "  Open Terminal     = http://$($config.HOSTNAME):$($config.OPEN_TERMINAL_PORT)"
Write-Host "  Jupyter coding    = http://$($config.HOSTNAME):$($config.JUPYTER_PORT)"
Write-Host "  Ollama main       = http://$($config.HOSTNAME):$($config.OLLAMA_MAIN_PORT)"
Write-Host "  Ollama GPU0 task  = http://$($config.HOSTNAME):$($config.OLLAMA_TASK_PORT)"
Write-Host "  CPU fallback      = disabled"
Write-Host "  OpenVINO/NPU      = $OPENVINO_PROVIDER_HEALTH_URL"
Write-Host "  NPU Phi sidecar   = $NPU_PHI_HEALTH_URL (enabled=$ENABLE_NPU_PHI_SERVICE)"
Write-Host ""
Write-Host "Environment:"
Write-Host "  DATA_DIR                 = $env:DATA_DIR"
Write-Host "  OLLAMA_BASE_URL           = $env:OLLAMA_BASE_URL"
Write-Host "  OLLAMA_BASE_URLS          = <disabled>"
Write-Host "  TASK_MODEL                = $env:TASK_MODEL"
Write-Host "  CUDA_VISIBLE_DEVICES      = $env:CUDA_VISIBLE_DEVICES"
Write-Host "  OLLAMA_NUM_PARALLEL       = $env:OLLAMA_NUM_PARALLEL"
Write-Host "  OLLAMA_MAX_LOADED_MODELS  = $env:OLLAMA_MAX_LOADED_MODELS"
Write-Host "  OLLAMA_FLASH_ATTENTION    = $env:OLLAMA_FLASH_ATTENTION"
Write-Host "  OLLAMA_KV_CACHE_TYPE      = $env:OLLAMA_KV_CACHE_TYPE"
Write-Host "  RAG_EMBEDDING_BATCH_SIZE  = $env:RAG_EMBEDDING_BATCH_SIZE"
Write-Host "  ENABLE_QUERIES_CACHE      = $env:ENABLE_QUERIES_CACHE"
Write-Host "  MODELS_CACHE_TTL          = $env:MODELS_CACHE_TTL"
Write-Host "  RAG_SYSTEM_CONTEXT        = $env:RAG_SYSTEM_CONTEXT"
Write-Host "  ENABLE_OPENVINO_PROVIDER  = $env:ENABLE_OPENVINO_PROVIDER"
Write-Host "  ENABLE_EXTERNAL_RERANKER  = $env:ENABLE_EXTERNAL_RERANKER"
Write-Host "  RAG_RERANKING_ENGINE      = $env:RAG_RERANKING_ENGINE"
Write-Host "  RAG_EXTERNAL_RERANKER_URL = $env:RAG_EXTERNAL_RERANKER_URL"
Write-Host "  ENABLE_NPU_PHI_SERVICE    = $env:ENABLE_NPU_PHI_SERVICE"
Write-Host "  NPU_PHI_PYTHON_EXE        = $env:NPU_PHI_PYTHON_EXE"
Write-Host "  NPU_PHI_MODEL_DIR         = $env:NPU_PHI_MODEL_DIR"
Write-Host ""

# Diagnostica main GPU.
try {
    Write-Host "Ollama main ps:"
    $PreviousOllamaHost = $env:OLLAMA_HOST
    $env:OLLAMA_HOST = "$($config.HOSTNAME):$($config.OLLAMA_MAIN_PORT)"
    & ollama ps
}
catch {
    Write-Warning "ollama ps fallito: $($_.Exception.Message)"
}
finally {
    if ([string]::IsNullOrWhiteSpace($PreviousOllamaHost)) {
        Remove-Item Env:OLLAMA_HOST -ErrorAction SilentlyContinue
    }
    else {
        $env:OLLAMA_HOST = $PreviousOllamaHost
    }
}

try {
    if (Get-Command nvidia-smi.exe -ErrorAction SilentlyContinue) {
        Write-Host ""
        Write-Host "nvidia-smi snapshot:"
        & nvidia-smi.exe --query-gpu=name,uuid,utilization.gpu,memory.used,memory.total --format=csv,noheader
    }
}
catch {
    Write-Warning "nvidia-smi fallito: $($_.Exception.Message)"
}

# ------------------------------------------------------------------
# LOCALHOST-ONLY Open WebUI policy
# ------------------------------------------------------------------

$env:HOST = $config.HOSTNAME
$env:PORT = $config.WEBUI_PORT
$env:WEBUI_URL = "http://$($config.HOSTNAME):$($config.WEBUI_PORT)"

$env:NO_PROXY = "127.0.0.1,localhost"
$env:no_proxy = "127.0.0.1,localhost"
$env:HTTP_PROXY = ""
$env:HTTPS_PROXY = ""
$env:http_proxy = ""
$env:https_proxy = ""

$env:SCARF_NO_ANALYTICS = "true"
$env:DO_NOT_TRACK = "true"
$env:ANONYMIZED_TELEMETRY = "false"
$env:ENABLE_VERSION_UPDATE_CHECK = "false"

Stop-PortOwner -Port $config.WEBUI_PORT -Label "Open WebUI"

Write-Host "Avvio Open WebUI..."
# Pulizia finale prima di avviare Open WebUI.
# Necessaria perchÃƒÆ’Ã‚Â© OVMS usa un proprio Python embedded.
Remove-Item Env:PYTHONHOME -ErrorAction SilentlyContinue
Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue

try {
    $OpenWebUIPython = "$AI_ROOT\venvs\openwebui\Scripts\python.exe"
    $OpenWebUIUvicornWrapper = "$AI_ROOT\services\aicarmine-openwebui-serve.py"

    $env:AICARMINE_OPENWEBUI_WS_PING_INTERVAL = Set-UserEnvDefault "AICARMINE_OPENWEBUI_WS_PING_INTERVAL" "30"
    $env:AICARMINE_OPENWEBUI_WS_PING_TIMEOUT = Set-UserEnvDefault "AICARMINE_OPENWEBUI_WS_PING_TIMEOUT" "120"
    $env:AICARMINE_OPENWEBUI_HTTP_KEEP_ALIVE = Set-UserEnvDefault "AICARMINE_OPENWEBUI_HTTP_KEEP_ALIVE" "75"
    $env:AICARMINE_OPENWEBUI_DISABLE_WS_DEFLATE = Set-UserEnvDefault "AICARMINE_OPENWEBUI_DISABLE_WS_DEFLATE" "1"

    if (-not (Test-Path $OpenWebUIPython)) {
        throw "Open WebUI Python non trovato: $OpenWebUIPython"
    }
    if (-not (Test-Path $OpenWebUIUvicornWrapper)) {
        throw "Open WebUI uvicorn wrapper non trovato: $OpenWebUIUvicornWrapper"
    }

    Write-Host "Avvio Open WebUI tramite wrapper uvicorn con keepalive WebSocket esplicito..."
    & $OpenWebUIPython $OpenWebUIUvicornWrapper --host 127.0.0.1 --port 8080
}
finally {
    Stop-AICarmineManagedServices
}
