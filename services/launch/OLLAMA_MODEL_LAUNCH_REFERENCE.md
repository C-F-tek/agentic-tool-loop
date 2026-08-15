# Ollama Model Launch Reference

## Overview

This document describes how the AI-Carmine project launches Ollama servers with models for the agentic loop planner and task execution.

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│              Ollama Desktop / Main                       │
│              Port 11434                                  │
│                                                          │
│  - Hosts base models (main GPU: RTX 5080)              │
│  - Primary Ollama endpoint for general inference         │
│  - $env:OLLAMA_HOST defaults to this port               │
│                                                          │
│  Environment Variables:                                  │
│    OLLAMA_NO_CLOUD = "1"                                 │
│    CUDA_VISIBLE_DEVICES = "GPU-..."                     │
│    OLLAMA_NUM_PARALLEL = "1"                             │
│    OLLAMA_MAX_LOADED_MODELS = "1"                       │
│    OLLAMA_FLASH_ATTENTION = "1"                          │
│    OLLAMA_KV_CACHE_TYPE = "q8_0"                        │
└──────────────────────────────────────────────────────────┘
                            |
                            | HTTP API calls
                            v
┌──────────────────────────────────────────────────────────┐
│              Ollama Task GPU0 / Vulkan                   │
│              Port 11435                                  │
│                                                          │
│  - Dedicated task model for agentic loop                 │
│  - Runs on GPU.0 (Vulkan/OpenVINO provider)             │
│  - Model: gpu0/qwen3-task-8k                             │
│                                                          │
│  Launch via:                                             │
│    ollama.ps1 → Ensure-OllamaModel()                     │
│    openwebui_runtime.ps1 → Start-EndpointScript...       │
└──────────────────────────────────────────────────────────┘
```

## How Ollama Models Are Launched

### Step 1: Check if the model already exists

The launcher first checks whether the target model is already loaded by querying the `/api/tags` endpoint:

```powershell
# From services/launch/ollama.ps1
function Test-OllamaEndpoint {
    param($Url)
    try {
        $result = Invoke-RestMethod -Uri "$Url/api/tags" -TimeoutSec 10
        return $null -ne $result
    } catch {
        return $false
    }
}

function Ensure-OllamaModel {
    param(
        [string]$HostPort,
        [string]$Model,
        [string]$BaseUrl
    )

    # Check if model already exists on this port
    $url = "http://$HostPort"
    $Tags = Invoke-RestMethod -Uri "$url/api/tags" -TimeoutSec 10
    $Names = @($Tags.models | ForEach-Object { $_.name })

    if ($Names -contains $Model -or $Names -contains "$Model:latest") {
        Write-Host "$Model gia' presente su $HostPort"
        return
    }
}
```

### Step 2: Pull the base model (if needed)

If the model is not present, the launcher sets `OLLAMA_HOST` to target port and pulls the base model from HuggingFace:

```powershell
# Set OLLAMA_HOST to target port
$env:OLLAMA_HOST = "127.0.0.1:$HostPort"

# Pull base model (e.g., qwen3:35b-codex-lean)
& ollama.exe pull $BaseModel
```

### Step 3: Create the custom model from Modelfile

The launcher then builds a custom model using a `Modelfile`:

```powershell
# Build custom model from Modelfile
& ollama.exe create $Model -f $ModelFile
```

After creation, `OLLAMA_HOST` is reset to its previous value or removed if it was unset.

## Launch Scripts

### Main Launcher: `openwebui_runtime.ps1`

Located at `services/launch/openwebui_runtime.ps1`, this script orchestrates the full startup sequence:

```powershell
# Load shared helpers
$LaunchRoot = (Split-Path -Parent $MyInvocation.MyCommand.Path)
. (Join-Path $LaunchRoot "ollama.ps1")   # Test-OllamaEndpoint, Ensure-OllamaModel
. (Join-Path $LaunchRoot "http.ps1")     # Test-HttpEndpoint, Test-HttpHealth
. (Join-Path $LaunchRoot "process.ps1")  # Start-EndpointScriptIfNeeded
```

### Configuration Constants

```powershell
$config = @{
    AI_ROOT          = "C:\Users\carmi\AI"
    HOSTNAME           = "127.0.0.1"
    WEBUI_PORT         = 8080
    OLLAMA_MAIN_PORT   = 11434       # Primary Ollama endpoint
    OLLAMA_TASK_PORT   = 11435       # Task/GPU0 Ollama endpoint
    VULKAN_BRIDGE_PORT = 3571       # Vulkan bridge
    VULKAN_AGENT_PORT  = 3572       # Agentic agent
    EXECUTOR_PORT      = 3560       # Executor
    OPENVINO_PORT      = 3550       # OpenVINO reranker provider
    NPU_PHI_PORT       = 3551       # NPU Phi diagnostic sidecar
    JUPYTER_PORT       = 8889       # Jupyter coding server
    CUDA_DEVICE        = "GPU-..."  # NVIDIA RTX 5080 GPU identifier
}
```

### Environment Variables Set at Runtime

| Variable | Value | Purpose |
|----------|-------|---------|
| `OLLAMA_NO_CLOUD` | `"1"` | Disable Ollama cloud features |
| `OLLAMA_BASE_URL` | `"http://127.0.0.1:11434"` | Default Ollama endpoint |
| `CUDA_VISIBLE_DEVICES` | `"GPU-..."` | Pin to specific NVIDIA GPU |
| `OLLAMA_NUM_PARALLEL` | `"1"` | Single parallel request handling |
| `OLLAMA_MAX_LOADED_MODELS` | `"1"` | Max loaded models at once |
| `OLLAMA_FLASH_ATTENTION` | `"1"` | Enable flash attention |
| `OLLAMA_KV_CACHE_TYPE` | `"q8_0"` | Quantized KV cache |
| `TASK_MODEL` | `"gpu0/qwen3-task-8k"` | Task model identifier |

## Modelfiles

Custom models are built from definitions stored in `modelfiles/`:

| Modelfile | Purpose |
|-----------|---------|
| `Modelfile.qwen3task-8k` | Task model for agentic loop planning |
| `Modelfile.qwen3coder-32k` | Code generation model |
| `Modelfile.Modelfile.qwen3task-8k` | Alternative task model configuration |

## Full Launch Sequence

1. **Load shared helpers** (`openwebui_runtime.ps1`):
   - `ollama.ps1` → `Test-OllamaEndpoint`, `Ensure-OllamaModel`
   - `http.ps1` → `Test-HttpEndpoint`, `Test-HttpHealth`
   - `process.ps1` → `Start-EndpointScriptIfNeeded`

2. **Set environment variables**:
   - `OLLAMA_NO_CLOUD`, `OLLAMA_BASE_URL`, `TASK_MODEL`
   - `CUDA_VISIBLE_DEVICES`, `OLLAMA_NUM_PARALLEL`, etc.

3. **Validate filesystem**:
   - Verify `open-webui.exe` exists
   - Create required directories (`models-task`, `logs`, `cache`, etc.)

4. **Start services** (in order):
   - OpenVINO reranker provider (port 3550) if enabled
   - NPU Phi diagnostic sidecar (port 3551) if enabled
   - OpenWebUI (port 8080)
   - Vulkan bridge (port 3571)
   - Agentic agent (port 3572)

## Health Checks

```powershell
# Check Ollama endpoint health
Test-OllamaEndpoint "http://127.0.0.1:11434"
# Internally calls: http://<host>:<port>/api/tags

# List loaded models
$Tags = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 10
$Names = @($Tags.models | ForEach-Object { $_.name })
```

## Unloading Models

```powershell
# Unload planner model from Ollama main
$unloadBody = @{
    model  = $plannerModel
    prompt = ""
} | ConvertTo-Json -Compress

Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/chat" `
    -Method Post `
    -Body $unloadBody `
    -TimeoutSec 10 | Out-Null
```

## Troubleshooting

### Model Not Found
If the task model is not present on port 11435, the launcher will:
1. Pull the base model from HuggingFace
2. Create the custom model using the Modelfile
3. Verify the model is loaded via `/api/tags`

### Port Already Occupied
If port 11435 is occupied but the endpoint is unhealthy:
```powershell
$Owner = Get-PortOwner -Port 11435
Write-Warning "PID=$($Owner.ProcessId) Name=$($Owner.Name)"
Write-Warning "CommandLine=$($Owner.CommandLine)"
throw "Ollama task GPU0/Vulkan blocked: port 11435 occupied by non-healthy process."
```

### Ollama Host Reset
After pulling/creating models, the `OLLAMA_HOST` environment variable is reset to its previous value or removed if it was previously unset.

## Related Files

| File | Purpose |
|------|---------|
| `services/launch/openwebui_runtime.ps1` | Main launcher script |
| `services/launch/ollama.ps1` | Ollama helper functions |
| `services/launch/process.ps1` | Process management helpers |
| `services/launch/http.ps1` | HTTP health check helpers |
| `modelfiles/Modelfile.qwen3task-8k` | Task model definition |