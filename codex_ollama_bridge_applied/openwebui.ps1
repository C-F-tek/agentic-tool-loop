
# ------------------------------------------------------------------
# Hard cleanup: OVMS setupvars.ps1 puÃƒÆ’Ã‚Â² contaminare la shell con
# PYTHONHOME/PYTHONPATH e rompere i venv Python.
# Il launcher deve sempre partire con Python env pulito.
# ------------------------------------------------------------------

Remove-Item Env:PYTHONHOME -ErrorAction SilentlyContinue
Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
function Set-UserEnvValue {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,

        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string]$Value
    )

    # Speed: evita una scrittura registry User a ogni avvio quando il valore e' gia' corretto.
    # La semantica resta identica: al termine il valore User deve essere quello richiesto.
    $Current = [Environment]::GetEnvironmentVariable($Name, "User")

    if ($Current -ne $Value) {
        [Environment]::SetEnvironmentVariable($Name, $Value, "User")
    }

    return $Value
}

function Clear-UserEnvValue {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    # Speed: evita cancellazioni registry ripetute quando la variabile User e' gia' assente.
    if ($null -ne [Environment]::GetEnvironmentVariable($Name, "User")) {
        [Environment]::SetEnvironmentVariable($Name, $null, "User")
    }
}

function Set-UserEnvDefault {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,

        [Parameter(Mandatory = $true)]
        [string]$DefaultValue
    )

    $Current = [Environment]::GetEnvironmentVariable($Name, "User")

    if ([string]::IsNullOrWhiteSpace($Current)) {
        [Environment]::SetEnvironmentVariable($Name, $DefaultValue, "User")
        return $DefaultValue
    }

    return $Current
}

function Get-OrCreate-WebUISecret {
    $Current = [Environment]::GetEnvironmentVariable("WEBUI_SECRET_KEY", "User")

    if (-not [string]::IsNullOrWhiteSpace($Current)) {
        return $Current.Trim()
    }

    $SecretFile = "C:\Users\carmi\AI\venvs\openwebui\.webui_secret_key"

    if (Test-Path $SecretFile) {
        $Secret = (Get-Content $SecretFile -Raw).Trim()
    }
    else {
        $Bytes = New-Object byte[] 32
        [System.Security.Cryptography.RandomNumberGenerator]::Fill($Bytes)
        $Secret = ($Bytes | ForEach-Object { $_.ToString("x2") }) -join ""
    }

    $null = Set-UserEnvValue "WEBUI_SECRET_KEY" $Secret
    return $Secret
}

function Test-OllamaEndpoint {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Url
    )

    try {
        $Response = Invoke-RestMethod -Uri "$Url/api/tags" -TimeoutSec 5
        return ($null -ne $Response.models)
    }
    catch {
        return $false
    }
}

function Get-PortOwner {
    param(
        [Parameter(Mandatory = $true)]
        [int]$Port
    )

    try {
        $Conn = Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort $Port -State Listen -ErrorAction Stop |
            Select-Object -First 1

        if ($null -eq $Conn) {
            return $null
        }

        return Get-CimInstance Win32_Process -Filter "ProcessId=$($Conn.OwningProcess)" |
            Select-Object ProcessId,Name,CommandLine
    }
    catch {
        return $null
    }
}

function Stop-PortOwner {
    param(
        [Parameter(Mandatory = $true)]
        [int]$Port,

        [Parameter(Mandatory = $true)]
        [string]$Label
    )

    try {
        $conns = Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort $Port -State Listen -ErrorAction SilentlyContinue

        foreach ($conn in $conns) {
            if ($null -ne $conn.OwningProcess -and $conn.OwningProcess -gt 0) {
                Write-Host "Stop $Label port=$Port PID=$($conn.OwningProcess)"
                Stop-Process -Id $conn.OwningProcess -Force -ErrorAction SilentlyContinue
            }
        }
    }
    catch {
        Write-Warning "Impossibile controllare porta $Port ($Label): $($_.Exception.Message)"
    }
}

function Start-EndpointScriptIfNeeded {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,

        [Parameter(Mandatory = $true)]
        [string]$Url,

        [Parameter(Mandatory = $true)]
        [int]$Port,

        [Parameter(Mandatory = $true)]
        [string]$Script
    )

    if (-not (Test-Path $Script)) {
        throw "$Name script non trovato: $Script"
    }

    if (Test-OllamaEndpoint $Url) {
        Write-Host "$Name giÃƒÆ’Ã‚Â  attivo e sano su $Url"
        return
    }

    $Owner = Get-PortOwner -Port $Port
    if ($null -ne $Owner) {
        Write-Warning "$($Name): porta $Port occupata ma endpoint non sano."
        Write-Warning "PID=$($Owner.ProcessId) Name=$($Owner.Name)"
        Write-Warning "CommandLine=$($Owner.CommandLine)"
        throw "$Name bloccato: porta $Port occupata da processo non sano."
    }

    Write-Host "Avvio $Name su $Url..."

    $Proc = Start-Process `
        -FilePath "powershell.exe" `
        -ArgumentList "-NoProfile -ExecutionPolicy Bypass -WindowStyle Minimized -File `"$Script`"" `
        -WindowStyle Minimized `
        -PassThru

    Write-Host "$Name processo avviato: PID=$($Proc.Id)"

    for ($i = 0; $i -lt 60; $i++) {
        if (Test-OllamaEndpoint $Url) {
            Write-Host "$Name attivo e sano su $Url"
            return
        }

        Start-Sleep -Seconds 1
    }

    throw "$Name non risponde correttamente su $Url dopo 60 secondi"
}

function Ensure-OllamaModel {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Url,

        [Parameter(Mandatory = $true)]
        [string]$HostPort,

        [Parameter(Mandatory = $true)]
        [string]$Model,

        [Parameter(Mandatory = $true)]
        [string]$BaseModel,

        [Parameter(Mandatory = $true)]
        [string]$ModelFile
    )

    if (-not (Test-Path $ModelFile)) {
        throw "Modelfile non trovato: $ModelFile"
    }

    if (-not (Test-OllamaEndpoint $Url)) {
        throw "Endpoint Ollama non sano: $Url"
    }

    $Tags = Invoke-RestMethod -Uri "$Url/api/tags" -TimeoutSec 10
    $Names = @($Tags.models | ForEach-Object { $_.name })

    if ($Names -contains $Model -or $Names -contains "$Model`:latest") {
        Write-Host "$Model giÃƒÆ’Ã‚Â  presente su $HostPort"
        return
    }

    $OllamaExe = (Get-Command ollama.exe -ErrorAction Stop).Source
    $PreviousOllamaHost = $env:OLLAMA_HOST

    try {
        $env:OLLAMA_HOST = $HostPort

        Write-Host "$Model non presente su $HostPort. Pull base model $BaseModel..."
        & $OllamaExe pull $BaseModel

        Write-Host "Creazione $Model su $HostPort..."
        & $OllamaExe create $Model -f $ModelFile
    }
    finally {
        if ([string]::IsNullOrWhiteSpace($PreviousOllamaHost)) {
            Remove-Item Env:OLLAMA_HOST -ErrorAction SilentlyContinue
        }
        else {
            $env:OLLAMA_HOST = $PreviousOllamaHost
        }
    }
}

function Test-HttpHealth {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Url
    )

    try {
        Invoke-RestMethod -Uri $Url -TimeoutSec 5 | Out-Null
        return $true
    }
    catch {
        return $false
    }
}

function Start-OpenVINOProviderIfEnabled {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Enabled,

        [Parameter(Mandatory = $true)]
        [string]$Script,

        [Parameter(Mandatory = $true)]
        [string]$HealthUrl,

        [Parameter(Mandatory = $true)]
        [int]$Port
    )

    if ($Enabled -ne "1") {
        Write-Host "OpenVINO/NPU provider disabilitato. ENABLE_OPENVINO_PROVIDER=$Enabled"
        return
    }

    if (Test-HttpHealth $HealthUrl) {
        Write-Host "OpenVINO/NPU provider giÃƒÆ’Ã‚Â  attivo: $HealthUrl"
        return
    }

    if (-not (Test-Path $Script)) {
        throw "ENABLE_OPENVINO_PROVIDER=1 ma script provider non trovato: $Script"
    }

    $Owner = Get-PortOwner -Port $Port
    if ($null -ne $Owner) {
        Write-Warning "OpenVINO/NPU provider: porta $Port occupata ma health non sano."
        Write-Warning "PID=$($Owner.ProcessId) Name=$($Owner.Name)"
        Write-Warning "CommandLine=$($Owner.CommandLine)"
        throw "OpenVINO/NPU provider bloccato: porta $Port occupata da processo non sano."
    }

    Write-Host "Avvio OpenVINO/NPU provider su porta $Port..."

    $Proc = Start-Process `
        -FilePath "powershell.exe" `
        -ArgumentList "-NoProfile -ExecutionPolicy Bypass -WindowStyle Minimized -File `"$Script`"" `
        -WindowStyle Minimized `
        -PassThru

    Write-Host "OpenVINO/NPU provider processo avviato: PID=$($Proc.Id)"

    for ($i = 0; $i -lt 60; $i++) {
        if (Test-HttpHealth $HealthUrl) {
            Write-Host "OpenVINO/NPU provider attivo: $HealthUrl"
            return
        }

        Start-Sleep -Seconds 1
    }

    throw "OpenVINO/NPU provider non risponde su $HealthUrl dopo 60 secondi"
}

# ------------------------------------------------------------------
# Config persistente progetto
# ------------------------------------------------------------------

$AI_ROOT = Set-UserEnvValue "AI_ROOT" "C:\Users\carmi\AI"
$OPENWEBUI_EXE = Set-UserEnvValue "OPENWEBUI_EXE" "$AI_ROOT\venvs\openwebui\Scripts\open-webui.exe"
$OPENWEBUI_DATA_DIR = Set-UserEnvValue "OPENWEBUI_DATA_DIR" "$AI_ROOT\services\openwebui-data"
$WEBUI_SECRET_KEY = Get-OrCreate-WebUISecret

$USER_AGENT = Set-UserEnvValue "USER_AGENT" "OpenWebUI-local-carmi/1.0"
$OLLAMA_NO_CLOUD = Set-UserEnvValue "OLLAMA_NO_CLOUD" "1"
$OLLAMA_BASE_URL = Set-UserEnvValue "OLLAMA_BASE_URL" "http://127.0.0.1:11434"
$TASK_MODEL = Set-UserEnvValue "TASK_MODEL" "gpu0/qwen3-task-8k"
$RAG_EMBEDDING_BATCH_SIZE = Set-UserEnvValue "RAG_EMBEDDING_BATCH_SIZE" "4"

# Main NVIDIA RTX 5080. Vale per Ollama Desktop/main dopo riavvio Ollama Desktop.
$CUDA_VISIBLE_DEVICES = Set-UserEnvValue "CUDA_VISIBLE_DEVICES" "GPU-751537aa-1f63-6ad0-db71-9727edd22244"

# Importante: niente OLLAMA_BASE_URLS. Gli endpoint multipli si gestiscono dalla UI con Prefix ID.
Clear-UserEnvValue "OLLAMA_BASE_URLS"
Remove-Item Env:OLLAMA_BASE_URLS -ErrorAction SilentlyContinue

# OpenVINO / NPU provider hook.
$OPENVINO_PYTHON_EXE = Set-UserEnvValue "OPENVINO_PYTHON_EXE" "$AI_ROOT\venvs\openvino\Scripts\python.exe"
$OPENVINO_ENV_SCRIPT = Set-UserEnvValue "OPENVINO_ENV_SCRIPT" "$AI_ROOT\services\openvino-env.ps1"
$OPENVINO_PROVIDER_SCRIPT = Set-UserEnvValue "OPENVINO_PROVIDER_SCRIPT" "$AI_ROOT\services\ovms-reranker-npu.ps1"
$OPENVINO_PROVIDER_PORT = Set-UserEnvValue "OPENVINO_PROVIDER_PORT" "3550"
$OPENVINO_PROVIDER_DEVICE = Set-UserEnvValue "OPENVINO_PROVIDER_DEVICE" "GPU.0"
$OPENVINO_PROVIDER_HEALTH_URL = Set-UserEnvValue "OPENVINO_PROVIDER_HEALTH_URL" "http://127.0.0.1:3550/v2/models/BAAI%2Fbge-reranker-v2-m3/ready"

# Default OFF finchÃƒÆ’Ã‚Â© il provider NPU HTTP non esiste davvero.
$ENABLE_OPENVINO_PROVIDER = Set-UserEnvValue "ENABLE_OPENVINO_PROVIDER" "1"
$ENABLE_EXTERNAL_RERANKER = Set-UserEnvValue "ENABLE_EXTERNAL_RERANKER" "1"
$RAG_RERANKING_MODEL = Set-UserEnvValue "RAG_RERANKING_MODEL" "BAAI/bge-reranker-v2-m3"
$RAG_EXTERNAL_RERANKER_URL = Set-UserEnvValue "RAG_EXTERNAL_RERANKER_URL" "http://127.0.0.1:3550/v3/rerank"

if ($ENABLE_EXTERNAL_RERANKER -eq "1") {
    $RAG_RERANKING_ENGINE = Set-UserEnvValue "RAG_RERANKING_ENGINE" "external"
}
else {
    Clear-UserEnvValue "RAG_RERANKING_ENGINE"
    Remove-Item Env:RAG_RERANKING_ENGINE -ErrorAction SilentlyContinue
}

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
    "$AI_ROOT\cache\huggingface" | Out-Null

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

# Niente OLLAMA_BASE_URLS runtime.
Remove-Item Env:OLLAMA_BASE_URLS -ErrorAction SilentlyContinue

# CUDA_VISIBLE_DEVICES ÃƒÆ’Ã‚Â¨ persistente per Ollama Desktop al prossimo riavvio.
$env:CUDA_VISIBLE_DEVICES = $CUDA_VISIBLE_DEVICES

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

if (Test-Path $OPENVINO_PYTHON_EXE) {
    try {
        & $OPENVINO_PYTHON_EXE -c "import openvino as ov; print('  Devices       = ' + str(ov.Core().available_devices))"
    }
    catch {
        Write-Warning "Diagnostica OpenVINO fallita: $($_.Exception.Message)"
    }
}

# ------------------------------------------------------------------
# Ollama main: Desktop su 11434
# ------------------------------------------------------------------

$OLLAMA_MAIN_URL = "http://127.0.0.1:11434"

if (Test-OllamaEndpoint $OLLAMA_MAIN_URL) {
    Write-Host "Ollama Desktop/main attivo su $OLLAMA_MAIN_URL"
}
else {
    Write-Warning "Ollama Desktop/main non risponde su $OLLAMA_MAIN_URL."
    Write-Warning "Apri o riavvia Ollama Desktop per usare i modelli main su RTX 5080."
}

# ------------------------------------------------------------------
# Ollama task GPU0/Vulkan su 11435
# ------------------------------------------------------------------

$OLLAMA_TASK_GPU_URL = "http://127.0.0.1:11435"
$OLLAMA_TASK_GPU_SCRIPT = Join-Path $AI_ROOT "services\ollama-task-vulkan.ps1"
$TASK_MODELFILE = Join-Path $AI_ROOT "modelfiles\Modelfile.qwen3task-8k"

Start-EndpointScriptIfNeeded `
    -Name "Ollama Task GPU0/Vulkan" `
    -Url $OLLAMA_TASK_GPU_URL `
    -Port 11435 `
    -Script $OLLAMA_TASK_GPU_SCRIPT

Ensure-OllamaModel `
    -Url $OLLAMA_TASK_GPU_URL `
    -HostPort "127.0.0.1:11435" `
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
$null = Set-UserEnvValue "AICARMINE_VULKAN_TOOL_BROKER_OPENAPI" "http://127.0.0.1:3571/openapi.json"
$null = Set-UserEnvValue "AICARMINE_VULKAN_TOOL_BROKER_URL" "http://127.0.0.1:3571"
$null = Set-UserEnvValue "AICARMINE_VULKAN_AGENT_URL" "http://127.0.0.1:3572/vulkan/agent"

$null = Set-UserEnvValue "AICARMINE_AGENT_PLANNER_URL" "http://127.0.0.1:11434/api/chat"
$null = Set-UserEnvValue "AICARMINE_AGENT_PLANNER_MODEL" "Qwen3-6-35B-A3B-UD-IQ2_M:latest"
$null = Set-UserEnvValue "AICARMINE_AGENTIC_PLANNER_ENABLED" "1"
$null = Set-UserEnvValue "AICARMINE_AGENTIC_PLANNER_NUM_CTX" "4096"
$null = Set-UserEnvValue "AICARMINE_AGENTIC_PLANNER_NUM_PREDICT" "-1"
$null = Set-UserEnvValue "AICARMINE_AGENTIC_RESULT_COMPACT_CHARS" "6000"
$null = Set-UserEnvValue "AICARMINE_AGENT_APPROVAL_MODE" "safe_write_lab"
$null = Set-UserEnvValue "AICARMINE_CODEX_COMMAND_TIMEOUT" "900"
$null = Set-UserEnvValue "AICARMINE_CODEX_MAX_TOOL_RESULT_CHARS" "60000"
Clear-UserEnvValue "AICARMINE_AGENTIC_PLANNER_HISTORY_TAIL"
$null = Set-UserEnvValue "AICARMINE_VULKAN_BROKER_OLLAMA_URL" "http://127.0.0.1:11435/api/chat"
$null = Set-UserEnvValue "AICARMINE_VULKAN_BROKER_MODEL" $TASK_MODEL

$env:AICARMINE_VULKAN_TOOL_BROKER_OPENAPI = "http://127.0.0.1:3571/openapi.json"
$env:AICARMINE_VULKAN_TOOL_BROKER_URL = "http://127.0.0.1:3571"
$env:AICARMINE_VULKAN_AGENT_URL = "http://127.0.0.1:3572/vulkan/agent"

$env:AICARMINE_AGENT_PLANNER_URL = "http://127.0.0.1:11434/api/chat"
$env:AICARMINE_AGENT_PLANNER_MODEL = "Qwen3-6-35B-A3B-UD-IQ2_M:latest"
$env:AICARMINE_AGENTIC_PLANNER_ENABLED = "1"
$null = Set-UserEnvValue "AICARMINE_VULKAN_BRIDGE_TIMEOUT_SECONDS" "12000"
$null = Set-UserEnvValue "AICARMINE_AGENT_RETURN_WAIT_SECONDS" "9000"

$env:AICARMINE_VULKAN_BRIDGE_TIMEOUT_SECONDS = "12000"
$env:AICARMINE_AGENT_RETURN_WAIT_SECONDS = "9000"
$env:AICARMINE_VULKAN_BROKER_OLLAMA_URL = "http://127.0.0.1:11435/api/chat"
$env:AICARMINE_VULKAN_BROKER_MODEL = $TASK_MODEL
$env:AICARMINE_VULKAN_MAX_TOOL_RESULT_CHARS = "6000"
$env:AICARMINE_VULKAN_FINAL_TIMEOUT_SECONDS = "2400"
$env:AICARMINE_VULKAN_NUM_CTX = "4096"
$env:AICARMINE_VULKAN_NUM_PREDICT = "-1"
$env:AICARMINE_VULKAN_INTERPRETER_NUM_PREDICT = "1024"
$env:AICARMINE_VULKAN_WRAPPER_NUM_PREDICT = "1536"
$env:AICARMINE_VULKAN_TEMPERATURE = "0"
$env:AICARMINE_AGENTIC_PLANNER_NUM_CTX = "4096"
$env:AICARMINE_AGENTIC_PLANNER_NUM_PREDICT = "-1"
$env:AICARMINE_AGENTIC_RESULT_COMPACT_CHARS = "6000"
$env:AICARMINE_AGENT_APPROVAL_MODE = "safe_write_lab"
$env:AICARMINE_CODEX_COMMAND_TIMEOUT = "900"
$env:AICARMINE_CODEX_MAX_TOOL_RESULT_CHARS = "60000"
Remove-Item Env:AICARMINE_AGENTIC_PLANNER_HISTORY_TAIL -ErrorAction SilentlyContinue
function Test-HttpEndpoint {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Url
    )

    try {
        $null = Invoke-RestMethod -Uri $Url -TimeoutSec 3
        return $true
    }
    catch {
        return $false
    }
}

function Test-AICarmineVulkanAgent {
    return (Test-HttpEndpoint "http://127.0.0.1:3572/health")
}

function Test-AICarmineVulkanBridge {
    return (Test-HttpEndpoint "http://127.0.0.1:3571/openapi.json")
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

    $ServicesRoot = "C:\Users\carmi\AI\services"
    $Py = "C:\Users\carmi\AI\venvs\labtools\Scripts\python.exe"

    if (-not (Test-Path $Py)) {
        throw "$Name richiede Python labtools non trovato: $Py"
    }

    if (& $HealthCheck) {
        Write-Host "$Name gia' sano su porta $Port"
        return
    }

    Stop-PortOwnerIfUnhealthy -Port $Port -Label $Name

    Write-Host "Avvio $Name su 127.0.0.1:$Port..."

    $Proc = Start-Process `
        -FilePath $Py `
        -ArgumentList @("-m", "uvicorn", "$Module`:app", "--host", "127.0.0.1", "--port", "$Port") `
        -WorkingDirectory $ServicesRoot `
        -WindowStyle Minimized `
        -PassThru

    Write-Host "$Name processo avviato: PID=$($Proc.Id)"

    for ($i = 0; $i -lt 60; $i++) {
        if (& $HealthCheck) {
            Write-Host "$Name sano su porta $Port"
            return
        }
        Start-Sleep -Seconds 1
    }

    throw "$Name non risponde su 127.0.0.1:$Port"
}

function Start-AICarmineVulkanBridgeStack {
    $AgentPy = "C:\Users\carmi\AI\services\aicarmine_vulkan_tool_broker.py"
    $BridgePy = "C:\Users\carmi\AI\services\aicarmine_vulkan_bridge_server.py"

    if (-not (Test-Path $AgentPy)) {
        throw "Vulkan Agent Python non trovato: $AgentPy"
    }

    if (-not (Test-Path $BridgePy)) {
        throw "Vulkan Bridge Python non trovato: $BridgePy"
    }

    if (-not (Test-OllamaEndpoint "http://127.0.0.1:11435")) {
        throw "AI-Carmine Vulkan Bridge richiede Ollama Task GPU0/Vulkan sano su http://127.0.0.1:11435"
    }

    Start-UvicornServiceIfNeeded `
        -Name "AI-Carmine Vulkan Agent interno" `
        -Port 3572 `
        -Module "aicarmine_vulkan_tool_broker" `
        -HealthCheck { Test-AICarmineVulkanAgent }

    Start-UvicornServiceIfNeeded `
        -Name "AI-Carmine Vulkan Bridge pubblico" `
        -Port 3571 `
        -Module "aicarmine_vulkan_bridge_server" `
        -HealthCheck { Test-AICarmineVulkanBridge }

    Write-Host "AI-Carmine Vulkan Bridge pronto: http://127.0.0.1:3571/openapi.json"
    Write-Host "AI-Carmine Vulkan Agent interno: http://127.0.0.1:3572/health"
}

Start-AICarmineVulkanBridgeStack


# ------------------------------------------------------------------
# OpenVINO/NPU provider opzionale su 3550
# ------------------------------------------------------------------

Start-OpenVINOProviderIfEnabled `
    -Enabled $ENABLE_OPENVINO_PROVIDER `
    -Script $OPENVINO_PROVIDER_SCRIPT `
    -HealthUrl $OPENVINO_PROVIDER_HEALTH_URL `
    -Port ([int]$OPENVINO_PROVIDER_PORT)

Set-Location $AI_ROOT

Write-Host ""
# ------------------------------------------------------------------
# Servizio: AI-Carmine Executor prima di Open WebUI
# ------------------------------------------------------------------

function Test-AICarmineExecutor {
    try {
        $r = Invoke-RestMethod -Uri "http://127.0.0.1:3560/health" -TimeoutSec 3
        return ($r.ok -eq $true)
    }
    catch {
        return $false
    }
}

function New-AICarmineExecutorWrapper {
    $ExecutorScript = "C:\Users\carmi\AI\services\aicarmine-executor-server.ps1"
    $ExecutorPy = "C:\Users\carmi\AI\services\aicarmine-executor-server.py"
    $SafeRunner = "C:\Users\carmi\AI\services\aicarmine-run-safe-command.ps1"

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

$env:AICARMINE_SAFE_COMMAND_RUNNER = "C:\Users\carmi\AI\services\aicarmine-run-safe-command.ps1"
$env:AICARMINE_LAB_REPO = "C:\Users\carmi\AI\lab-worktrees\blender-audio-project-lab"
$env:AICARMINE_REAL_REPO = "C:\Users\carmi\ProjectsDir\blender-audio-project"

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
        Write-Host "AI-Carmine Executor giÃƒÆ’Ã‚Â  sano su http://127.0.0.1:3560/health"
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

    $Token = -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 48 | ForEach-Object {[char]$_})
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
        $r = Invoke-RestMethod -Uri "http://127.0.0.1:8888/api/status?token=$Token" -TimeoutSec 3
        return ($null -ne $r)
    }
    catch {
        return $false
    }
}

function Start-AICarmineJupyter {
    $JupyterScript = "C:\Users\carmi\AI\services\aicarmine-jupyter-codeinterpreter.ps1"

    if (-not (Test-Path $JupyterScript)) {
        throw "Jupyter Code Interpreter script non trovato: $JupyterScript"
    }

    if (Test-AICarmineJupyter) {
        Write-Host "AI-Carmine Jupyter giÃƒÆ’Ã‚Â  sano su http://127.0.0.1:8888"
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

    Write-Host "Avvio AI-Carmine Jupyter Code Interpreter su http://127.0.0.1:8888..."

    $p = Start-Process `
        -FilePath "powershell.exe" `
        -ArgumentList "-NoProfile -ExecutionPolicy Bypass -WindowStyle Minimized -File `"$JupyterScript`"" `
        -WindowStyle Minimized `
        -PassThru

    Write-Host "AI-Carmine Jupyter processo avviato: PID=$($p.Id)"

    for ($i = 0; $i -lt 45; $i++) {
        if (Test-AICarmineJupyter) {
            Write-Host "AI-Carmine Jupyter sano su http://127.0.0.1:8888"
            return
        }

        Start-Sleep -Seconds 1
    }

    throw "AI-Carmine Jupyter non risponde su http://127.0.0.1:8888"
}

$JupyterToken = Get-AICarmineJupyterToken

$null = Set-UserEnvValue "AICARMINE_JUPYTER_TOKEN_FILE" "C:\Users\carmi\AI\secrets\jupyter_code_token.dpapi"
$null = Set-UserEnvValue "AICARMINE_JUPYTER_URL" "http://127.0.0.1:8888"
$null = Set-UserEnvValue "AICARMINE_JUPYTER_WORKDIR" "C:\Users\carmi\AI\code-interpreter-workdir"

$null = Set-UserEnvValue "ENABLE_CODE_EXECUTION" "true"
$null = Set-UserEnvValue "ENABLE_CODE_INTERPRETER" "true"
$null = Set-UserEnvValue "CODE_EXECUTION_ENGINE" "jupyter"
$null = Set-UserEnvValue "CODE_EXECUTION_JUPYTER_URL" "http://127.0.0.1:8888"
$null = Set-UserEnvValue "CODE_EXECUTION_JUPYTER_AUTH" "token"
$null = Set-UserEnvValue "CODE_EXECUTION_JUPYTER_AUTH_TOKEN" $JupyterToken
$null = Set-UserEnvValue "CODE_EXECUTION_JUPYTER_KERNEL" "aicarmine-code"
$null = Set-UserEnvValue "CODE_EXECUTION_JUPYTER_TIMEOUT" "180"

$env:ENABLE_CODE_EXECUTION = "true"
$env:ENABLE_CODE_INTERPRETER = "true"
$env:CODE_EXECUTION_ENGINE = "jupyter"
$env:CODE_EXECUTION_JUPYTER_URL = "http://127.0.0.1:8888"
$env:CODE_EXECUTION_JUPYTER_AUTH = "token"
$env:CODE_EXECUTION_JUPYTER_AUTH_TOKEN = $JupyterToken
$env:CODE_EXECUTION_JUPYTER_KERNEL = "aicarmine-code"
$env:CODE_EXECUTION_JUPYTER_TIMEOUT = "180"

Start-AICarmineJupyter

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
$null = Set-UserEnvValue "AICARMINE_LAB_REPO" "C:\Users\carmi\AI\lab-worktrees\blender-audio-project-lab"
$null = Set-UserEnvValue "AICARMINE_REAL_REPO" "C:\Users\carmi\ProjectsDir\blender-audio-project"

$env:AICARMINE_LAB_PATCH_URL = ""
$env:AICARMINE_LAB_PATCH_OPENAPI = ""
$env:AICARMINE_LAB_GUIDE_URL = ""
$env:AICARMINE_LAB_GUIDE_OPENAPI = ""
$env:AICARMINE_QWEN_PATCH_URL = ""
$env:AICARMINE_QWEN_PATCH_OPENAPI = ""
$env:AICARMINE_QWEN_GUIDE_URL = ""
$env:AICARMINE_QWEN_GUIDE_OPENAPI = ""
$env:AICARMINE_LAB_REPO = "C:\Users\carmi\AI\lab-worktrees\blender-audio-project-lab"
$env:AICARMINE_REAL_REPO = "C:\Users\carmi\ProjectsDir\blender-audio-project"

Stop-PortOwner -Port 3562 -Label "Legacy AI-Carmine Qwen Patch Tools"
Stop-PortOwner -Port 3563 -Label "Legacy AI-Carmine Qwen Guide Tools"

# ------------------------------------------------------------------
# Servizio: AI-Carmine Lab Mirror Watchdog
# ------------------------------------------------------------------

function Ensure-AICarmineLabMirrorScripts {
    $SyncScript = "C:\Users\carmi\AI\services\sync-lab-from-main.ps1"
    $WatchScript = "C:\Users\carmi\AI\services\watch-lab-mirror.ps1"

    if (-not (Test-Path $SyncScript)) {
        $SyncContent = @'
param(
    [switch]$Quiet
)

$ErrorActionPreference = "Stop"

$Main = "C:\Users\carmi\ProjectsDir\blender-audio-project"
$Lab  = "C:\Users\carmi\AI\lab-worktrees\blender-audio-project-lab"
$PatchDir = "C:\Users\carmi\AI\lab-patches"
$Patch = Join-Path $PatchDir "master-working-tree-to-lab.patch"

$LogDir = "C:\Users\carmi\AI\logs"
$LogFile = Join-Path $LogDir "lab-mirror-sync.log"
$LockFile = Join-Path $LogDir "lab-mirror-sync.lock"

New-Item -ItemType Directory -Force -Path $PatchDir, $LogDir | Out-Null

function Write-Log {
    param([string]$Message)

    $line = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $Message"
    Add-Content -Path $LogFile -Value $line -Encoding UTF8

    if (-not $Quiet) {
        Write-Host $line
    }
}

function Invoke-Git {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Repo,

        [Parameter(Mandatory = $true)]
        [string[]]$Args
    )

    & git -C $Repo @Args
    if ($LASTEXITCODE -ne 0) {
        throw "git -C `"$Repo`" $($Args -join ' ') failed with exit code $LASTEXITCODE"
    }
}

if (Test-Path $LockFile) {
    $age = (Get-Date) - (Get-Item $LockFile).LastWriteTime

    if ($age.TotalMinutes -lt 10) {
        Write-Log "Sync giÃƒÆ’Ã‚Â  in corso o lock recente: $LockFile"
        exit 0
    }

    Write-Log "Lock stale rimosso: $LockFile"
    Remove-Item $LockFile -Force -ErrorAction SilentlyContinue
}

New-Item -ItemType File -Path $LockFile -Force | Out-Null

try {
    if (-not (Test-Path $Main)) {
        throw "Repo MAIN non trovata: $Main"
    }

    if (-not (Test-Path $Lab)) {
        throw "Repo LAB non trovata: $Lab"
    }

    Write-Log "Sync patch-based start MAIN -> LAB"

    Invoke-Git -Repo $Lab -Args @("reset", "--hard", "master")
    Invoke-Git -Repo $Lab -Args @("clean", "-fdx")

    Remove-Item $Patch -Force -ErrorAction SilentlyContinue

    $cmd = 'git -C "{0}" diff --binary HEAD > "{1}"' -f $Main, $Patch
    cmd.exe /d /c $cmd
    if ($LASTEXITCODE -ne 0) {
        throw "Creazione patch fallita con exit code $LASTEXITCODE"
    }

    $patchSize = 0
    if (Test-Path $Patch) {
        $patchSize = (Get-Item $Patch).Length
    }

    if ($patchSize -gt 0) {
        Invoke-Git -Repo $Lab -Args @("apply", "--check", $Patch)
        Invoke-Git -Repo $Lab -Args @("apply", $Patch)
    }

    $untracked = git -C $Main ls-files --others --exclude-standard
    foreach ($rel in $untracked) {
        if ([string]::IsNullOrWhiteSpace($rel)) {
            continue
        }

        $src = Join-Path $Main $rel
        $dst = Join-Path $Lab $rel

        if (Test-Path $src -PathType Leaf) {
            New-Item -ItemType Directory -Force -Path (Split-Path $dst) | Out-Null
            Copy-Item $src $dst -Force
            Write-Log "Copied untracked: $rel"
        }
    }

    Write-Log "MAIN status:`n$(git -C $Main status --short --branch | Out-String)"
    Write-Log "LAB status:`n$(git -C $Lab status --short --branch | Out-String)"
    Write-Log "LAB diff:`n$(git -C $Lab diff --stat HEAD | Out-String)"
    Write-Log "Sync patch-based complete."
}
catch {
    Write-Log "Sync ERROR: $($_.Exception.Message)"
    throw
}
finally {
    Remove-Item $LockFile -Force -ErrorAction SilentlyContinue
}
'@

        Set-Content -Path $SyncScript -Value $SyncContent -Encoding UTF8
    }

    if (-not (Test-Path $WatchScript)) {
        $WatchContent = @'
param(
    [int]$IntervalSeconds = 60
)

$ErrorActionPreference = "Continue"

$SyncScript = "C:\Users\carmi\AI\services\sync-lab-from-main.ps1"
$LogDir = "C:\Users\carmi\AI\logs"
$LogFile = Join-Path $LogDir "lab-mirror-watchdog.log"

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Write-Log {
    param([string]$Message)

    $line = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $Message"
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
    Write-Host $line
}

if (-not (Test-Path $SyncScript)) {
    throw "Sync script non trovato: $SyncScript"
}

Write-Log "Lab mirror watchdog avviato. IntervalSeconds=$IntervalSeconds"

while ($true) {
    $enabled = [Environment]::GetEnvironmentVariable("ENABLE_AICARMINE_LAB_MIRROR", "User")

    if ([string]::IsNullOrWhiteSpace($enabled)) {
        $enabled = "0"
        [Environment]::SetEnvironmentVariable("ENABLE_AICARMINE_LAB_MIRROR", $enabled, "User")
    }

    if ($enabled -eq "1") {
        try {
            Write-Log "Mirror enabled. Avvio sync."
            powershell -NoProfile -ExecutionPolicy Bypass -File $SyncScript -Quiet
            Write-Log "Sync OK."
        }
        catch {
            Write-Log "Sync ERROR: $($_.Exception.Message)"
        }
    }
    else {
        Write-Log "Mirror disabled. ENABLE_AICARMINE_LAB_MIRROR=$enabled"
    }

    Start-Sleep -Seconds $IntervalSeconds
}
'@

        Set-Content -Path $WatchScript -Value $WatchContent -Encoding UTF8
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

    $matches = Get-CimInstance Win32_Process |
        Where-Object {
            $_.CommandLine -and ($_.CommandLine -match $Pattern)
        }

    foreach ($proc in $matches) {
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

    # Servizi AI-Carmine.
    Stop-ProcessByCommandLinePattern -Label "AI-Carmine Vulkan Tool Broker wrapper" -Pattern "aicarmine-vulkan-tool-broker"
    Stop-ProcessByCommandLinePattern -Label "AI-Carmine Vulkan Agent uvicorn" -Pattern "aicarmine_vulkan_tool_broker"
    Stop-ProcessByCommandLinePattern -Label "AI-Carmine Vulkan Bridge uvicorn" -Pattern "aicarmine_vulkan_bridge_server"
    Stop-ProcessByCommandLinePattern -Label "AI-Carmine Ollama task runner" -Pattern "runner --ollama-engine.*models-task"
    Stop-ProcessByCommandLinePattern -Label "AI-Carmine Executor" -Pattern "aicarmine-executor-server"
    Stop-ProcessByCommandLinePattern -Label "Lab mirror watchdog" -Pattern "watch-lab-mirror"
    Stop-ProcessByCommandLinePattern -Label "Lab mirror sync" -Pattern "sync-lab-from-main"
    Stop-ProcessByCommandLinePattern -Label "AI-Carmine Jupyter" -Pattern "aicarmine-jupyter-codeinterpreter"
    Stop-ProcessByCommandLinePattern -Label "OVMS reranker wrapper" -Pattern "ovms-reranker"

    # Porte gestite. NON includere 11434.
    Stop-PortOwner -Port 3571  -Label "AI-Carmine Vulkan Bridge pubblico"
    Stop-PortOwner -Port 3572  -Label "AI-Carmine Vulkan Agent interno"
    Stop-PortOwner -Port 11435 -Label "Ollama task GPU0/Vulkan"
    Stop-ProcessByCommandLinePattern -Label "AI-Carmine Ollama task runner post-port-stop" -Pattern "runner --ollama-engine.*models-task"
    Stop-PortOwner -Port 3550  -Label "OVMS reranker"
    Stop-PortOwner -Port 3560  -Label "AI-Carmine Executor"
    Stop-PortOwner -Port 3562  -Label "Legacy AI-Carmine Qwen Patch Tools"
    Stop-PortOwner -Port 3563  -Label "Legacy AI-Carmine Qwen Guide Tools"
    Stop-PortOwner -Port 8888  -Label "Jupyter Code Interpreter"
    Stop-PortOwner -Port 8080  -Label "Open WebUI"

    Remove-Item Env:PYTHONHOME -ErrorAction SilentlyContinue
    Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue

    Write-Host "Shutdown guidato completato."
}

# ------------------------------------------------------------------
# Riepilogo runtime
# ------------------------------------------------------------------

Write-Host ""
Write-Host "Runtime topology:"
Write-Host "  Open WebUI        = http://127.0.0.1:8080"
Write-Host "  Ollama main       = http://127.0.0.1:11434"
Write-Host "  Ollama GPU0 task  = http://127.0.0.1:11435"
Write-Host "  CPU fallback      = disabled"
Write-Host "  OpenVINO/NPU      = $OPENVINO_PROVIDER_HEALTH_URL"
Write-Host ""
Write-Host "Environment:"
Write-Host "  DATA_DIR                 = $env:DATA_DIR"
Write-Host "  OLLAMA_BASE_URL           = $env:OLLAMA_BASE_URL"
Write-Host "  OLLAMA_BASE_URLS          = <disabled>"
Write-Host "  TASK_MODEL                = $env:TASK_MODEL"
Write-Host "  CUDA_VISIBLE_DEVICES      = $env:CUDA_VISIBLE_DEVICES"
Write-Host "  RAG_EMBEDDING_BATCH_SIZE  = $env:RAG_EMBEDDING_BATCH_SIZE"
Write-Host "  ENABLE_OPENVINO_PROVIDER  = $env:ENABLE_OPENVINO_PROVIDER"
Write-Host "  ENABLE_EXTERNAL_RERANKER  = $env:ENABLE_EXTERNAL_RERANKER"
Write-Host "  RAG_RERANKING_ENGINE      = $env:RAG_RERANKING_ENGINE"
Write-Host "  RAG_EXTERNAL_RERANKER_URL = $env:RAG_EXTERNAL_RERANKER_URL"
Write-Host ""

# Diagnostica main GPU.
try {
    Write-Host "Ollama main ps:"
    $PreviousOllamaHost = $env:OLLAMA_HOST
    $env:OLLAMA_HOST = "127.0.0.1:11434"
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

$env:HOST = "127.0.0.1"
$env:PORT = "8080"
$env:WEBUI_URL = "http://127.0.0.1:8080"

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

Stop-PortOwner -Port 8080 -Label "Open WebUI"

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

    if ((Test-Path $OpenWebUIPython) -and (Test-Path $OpenWebUIUvicornWrapper)) {
        Write-Host "Avvio Open WebUI tramite wrapper uvicorn con keepalive WebSocket esplicito..."
        & $OpenWebUIPython $OpenWebUIUvicornWrapper --host 127.0.0.1 --port 8080
    }
    else {
        Write-Warning "Wrapper uvicorn Open WebUI non disponibile. Fallback a open-webui serve."
        & $OPENWEBUI_EXE serve --host 127.0.0.1 --port 8080
    }
}
finally {
    Stop-AICarmineManagedServices
}
