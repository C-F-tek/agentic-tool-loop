param(
    [string]$AIRoot = "$env:USERPROFILE\AI",
    [string]$ServiceRoot = "$env:USERPROFILE\AI\services",
    [string]$Python = "$env:USERPROFILE\AI\venvs\labtools\Scripts\python.exe",
    [string]$Model = "qwen3-coder:30b",
    [int]$BridgePort = 3581,
    [int]$BrokerPort = 3572,
    [switch]$InstallFiles,
    [switch]$SkipBroker,
    [switch]$NoStatefulBridge
)

$ErrorActionPreference = "Stop"

function Resolve-Python {
    param([string]$Candidate)
    if ($Candidate -and (Test-Path $Candidate)) { return $Candidate }
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    throw "Python non trovato. Imposta -Python con il path dell'interprete/venv."
}

function Test-HttpJson {
    param([string]$Url, [int]$TimeoutSec = 3)
    try {
        $r = Invoke-RestMethod -Uri $Url -TimeoutSec $TimeoutSec
        return ($null -ne $r)
    } catch { return $false }
}

function Get-PortListeners {
    param([int]$Port)
    return @(Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Sort-Object OwningProcess -Unique)
}

function Stop-PortOwner {
    param([int]$Port, [string]$Label)
    $listeners = Get-PortListeners -Port $Port
    if ($listeners.Count -eq 0) { return }
    foreach ($listener in $listeners) {
        $ownerPid = [int]$listener.OwningProcess
        if ($ownerPid -le 0) { continue }
        Write-Host "Stopping ${Label} on port ${Port} PID=$ownerPid"
        try { Stop-Process -Id $ownerPid -Force -ErrorAction Stop }
        catch { & taskkill.exe /PID $ownerPid /T /F | Out-Host }
    }
    Start-Sleep -Milliseconds 500
}

function Assert-Ollama {
    if (-not (Test-HttpJson "http://127.0.0.1:11434/api/version" 3)) {
        throw "Ollama non risponde su http://127.0.0.1:11434. Avvia prima Ollama."
    }
    $tags = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 5
    $names = @($tags.models | ForEach-Object { $_.name })
    if ($names -notcontains $Model) {
        Write-Warning "Il modello '$Model' non risulta in ollama list. Esegui: ollama pull $Model"
    }
}

function Write-CodexConfigSnippet {
    param([string]$McpPath)
    $codexDir = Join-Path $env:USERPROFILE ".codex"
    New-Item -ItemType Directory -Force -Path $codexDir | Out-Null
    $snippet = Join-Path $codexDir "aicarmine-ollama.config.toml"
    $usefulRoot = Join-Path $ServiceRoot "useful_tools"
    $mcpEsc = $McpPath.Replace("\", "\\")
    $labEsc = "$AIRoot\lab-worktrees\blender-audio-project-lab".Replace("\", "\\")
    $realEsc = "$env:USERPROFILE\ProjectsDir\blender-audio-project".Replace("\", "\\")
    $usefulEsc = $usefulRoot.Replace("\", "\\")
@"
model_provider = "aicarmine_ollama_bridge"
model = "$Model"
approval_policy = "on-request"
sandbox_mode = "workspace-write"
model_context_window = 32768
model_auto_compact_token_limit = 24576
tool_output_token_limit = 12000
model_reasoning_summary = "none"
model_supports_reasoning_summaries = false

[model_providers.aicarmine_ollama_bridge]
name = "AI-Carmine Ollama Bridge"
base_url = "http://127.0.0.1:$BridgePort/v1"
wire_api = "responses"
request_max_retries = 1
stream_max_retries = 1
stream_idle_timeout_ms = 600000

[mcp_servers.aicarmine_tools]
command = "python"
args = ["$mcpEsc"]
env = { AICARMINE_VULKAN_AGENT_URL = "http://127.0.0.1:$BrokerPort/vulkan/agent", AICARMINE_BROKER_BASE_URL = "http://127.0.0.1:$BrokerPort", AICARMINE_LAB_REPO = "$labEsc", AICARMINE_REAL_REPO = "$realEsc", AICARMINE_USEFUL_TOOLS_ROOT = "$usefulEsc", AICARMINE_MCP_TOOL_TIMEOUT_SECONDS = "900" }
startup_timeout_sec = 20
tool_timeout_sec = 900
enabled = true

[mcp_servers.aicarmine_tools.tools.aicarmine_repo_apply_patch]
approval_mode = "prompt"

[mcp_servers.aicarmine_tools.tools.aicarmine_repo_write_file]
approval_mode = "prompt"

[mcp_servers.aicarmine_tools.tools.aicarmine_repo_command]
approval_mode = "prompt"

[mcp_servers.aicarmine_tools.tools.aicarmine_repo_validate]
approval_mode = "prompt"
"@ | Set-Content -Path $snippet -Encoding UTF8
    Write-Host "Config Codex generata: $snippet"
    Write-Host "Uniscila a: $env:USERPROFILE\.codex\config.toml"
}

$Py = Resolve-Python $Python
$ThisDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$McpSource = Join-Path $ThisDir "aicarmine_codex_mcp_server.py"
$BridgeSource = Join-Path $ThisDir "aicarmine_codex_ollama_responses_bridge.py"

if ($InstallFiles) {
    New-Item -ItemType Directory -Force -Path $ServiceRoot | Out-Null
    Copy-Item -Force $McpSource (Join-Path $ServiceRoot "aicarmine_codex_mcp_server.py")
    Copy-Item -Force $BridgeSource (Join-Path $ServiceRoot "aicarmine_codex_ollama_responses_bridge.py")
    if (Test-Path (Join-Path $ThisDir "..\useful_tools")) {
        if (Test-Path (Join-Path $ServiceRoot "useful_tools")) { Remove-Item -Recurse -Force (Join-Path $ServiceRoot "useful_tools") }
        Copy-Item -Recurse -Force (Join-Path $ThisDir "..\useful_tools") (Join-Path $ServiceRoot "useful_tools")
    }
    $McpPath = Join-Path $ServiceRoot "aicarmine_codex_mcp_server.py"
    $BridgePath = Join-Path $ServiceRoot "aicarmine_codex_ollama_responses_bridge.py"
} else {
    $McpPath = $McpSource
    $BridgePath = $BridgeSource
}

Assert-Ollama
Write-CodexConfigSnippet -McpPath $McpPath

$env:AICARMINE_OLLAMA_BASE_URL = "http://127.0.0.1:11434"
$env:AICARMINE_CODEX_BRIDGE_STATEFUL = if ($NoStatefulBridge) { "0" } else { "1" }
$env:AICARMINE_VULKAN_AGENT_URL = "http://127.0.0.1:$BrokerPort/vulkan/agent"
$env:AICARMINE_BROKER_BASE_URL = "http://127.0.0.1:$BrokerPort"
$env:AICARMINE_USEFUL_TOOLS_ROOT = Join-Path $ServiceRoot "useful_tools"
$env:AICARMINE_MCP_TOOL_TIMEOUT_SECONDS = "900"

$brokerProc = $null
$bridgeProc = $null
try {
    if (-not $SkipBroker) {
        if (-not (Test-HttpJson "http://127.0.0.1:$BrokerPort/health" 2)) {
            $brokerScript = Join-Path $ServiceRoot "aicarmine_vulkan_tool_broker.py"
            if (-not (Test-Path $brokerScript)) {
                $brokerScript = Join-Path (Split-Path -Parent $ThisDir) "aicarmine_vulkan_tool_broker.py"
            }
            if (-not (Test-Path $brokerScript)) {
                throw "Broker aicarmine_vulkan_tool_broker.py non trovato. Copia i file in $ServiceRoot o usa -SkipBroker se è già attivo."
            }
            Stop-PortOwner -Port $BrokerPort -Label "old AI-Carmine broker"
            Write-Host "Starting AI-Carmine broker on 127.0.0.1:$BrokerPort..."
            $brokerProc = Start-Process -FilePath $Py -ArgumentList "-m uvicorn aicarmine_vulkan_tool_broker:app --host 127.0.0.1 --port $BrokerPort" -WorkingDirectory (Split-Path -Parent $brokerScript) -WindowStyle Minimized -PassThru
            for ($i=0; $i -lt 60; $i++) { if (Test-HttpJson "http://127.0.0.1:$BrokerPort/health" 2) { break }; Start-Sleep -Seconds 1 }
            if (-not (Test-HttpJson "http://127.0.0.1:$BrokerPort/health" 2)) { throw "Broker non raggiungibile su /health" }
        }
    }

    Stop-PortOwner -Port $BridgePort -Label "old Codex Ollama bridge"
    Write-Host "Starting Codex/Ollama bridge on 127.0.0.1:$BridgePort..."
    $bridgeProc = Start-Process -FilePath $Py -ArgumentList "-m uvicorn aicarmine_codex_ollama_responses_bridge:app --host 127.0.0.1 --port $BridgePort" -WorkingDirectory (Split-Path -Parent $BridgePath) -WindowStyle Normal -PassThru
    for ($i=0; $i -lt 60; $i++) { if (Test-HttpJson "http://127.0.0.1:$BridgePort/health" 2) { break }; Start-Sleep -Seconds 1 }
    if (-not (Test-HttpJson "http://127.0.0.1:$BridgePort/health" 2)) { throw "Bridge non raggiungibile su /health" }

    Write-Host ""
    Write-Host "AI-Carmine Codex bridge attivo:"
    Write-Host "  Codex provider base_url = http://127.0.0.1:$BridgePort/v1"
    Write-Host "  Ollama base             = http://127.0.0.1:11434"
    Write-Host "  Broker tools            = http://127.0.0.1:$BrokerPort/vulkan/agent"
    Write-Host "  MCP server script       = $McpPath"
    Write-Host ""
    Write-Host "Ora puoi lanciare: codex"
    Write-Host "Per desktop app: codex app"
    Write-Host "Lascia questa finestra aperta finché usi Codex con il bridge."
    Wait-Process -Id $bridgeProc.Id
}
finally {
    if ($bridgeProc -and -not $bridgeProc.HasExited) { Stop-Process -Id $bridgeProc.Id -Force -ErrorAction SilentlyContinue }
    if ($brokerProc -and -not $brokerProc.HasExited) { Stop-Process -Id $brokerProc.Id -Force -ErrorAction SilentlyContinue }
}
