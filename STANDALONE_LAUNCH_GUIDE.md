# AI-Carmine Standalone Launch Guide (Without OpenWebUI)

This guide covers launching the core infrastructure components **independently** of OpenWebUI. Use this for:
- Codex App integration via MCP on port 3579
- Direct agentic loop execution
- Isolated debugging of individual services

## Architecture Overview

```
┌─────────────────────┐     ┌──────────────────┐     ┌─────────────────────┐
│   Ollama Task       │     │   OVMS Reranker  │     │  Agentic Loop       │
│   Port: 11435       │     │   Port: 3550     │     │  Broker (3579)      │
│   Vulkan/Intel GPU  │     │   OpenVINO       │     │  Python + Uvicorn   │
│   Model: qwen3-task │     │   Model: BAAI    │     │  Depends on 3550    │
│   Context: 12288    │     │   bge-reranker   │     │  Reads config from  │
└─────────────────────┘     └──────────────────┘     │  env vars            │
                                                     └─────────────────────┘
```

## Prerequisites Checklist

Before launching, ensure these are installed:

| Component | Required Path | Status |
|---|---|---|
| Python 3.12+ | In PATH | ✅ Python 3.14 available — works for venvs |
| ollama.exe | In PATH | ✅ Already installed v0.31.2 |
| Git v2.55.0 | In PATH | ✅ Already installed |
| Ollama Desktop | Running on 11434 | ✅ Active — used for planner models |
| Virtual env `labtools` | `C:\Users\CarmineFaiola\AI\venvs\labtools\Scripts\python.exe` | ✅ Created |
| Virtual env `openvino` | `C:\Users\CarmineFaiola\AI\venvs\openvino` | ✅ Created |
| OVMS runtime | `C:\Users\CarmineFaiola\AI\ovms-runtime\ovms\bin\ovms.exe` | ✅ Installed |
| Model ONNX export | `models-ovms-rerank\bge-reranker-v2-m3\model.onnx` | ✅ Created |
| OVMS config | `models-ovms-rerank\config.json` | ✅ Created |

---

## Quick Launch (Recommended)

### Unified Single-Command Launch

```powershell
# Full stack (all services):
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\CarmineFaiola\AI\launch-standalone.ps1"

# Individual service restart after code updates:
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\CarmineFaiola\AI\launch-standalone.ps1" -Mode task
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\CarmineFaiola\AI\launch-standalone.ps1" -Mode reranker
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\CarmineFaiola\AI\launch-standalone.ps1" -Mode broker
```

**What the unified script does:**
1. Checks if Ollama Desktop (11434) is running — used for planner models
2. Launches Ollama Task on 11435 (Vulkan/Intel GPU) in a new minimized window
3. Creates `models-ovms-rerank\config.json` if missing
4. Launches OVMS Reranker on 3550 (OpenVINO GPU) in a new minimized window
5. Sets all process-local environment variables
6. Launches Agentic Loop Broker on 3579 in the current window

**Architecture:**
```
┌─────────────────────┐     ┌──────────────────┐     ┌─────────────────────┐
│   Ollama Desktop    │     │   Ollama Task    │     │   OVMS Reranker     │
│   Port: 11434       │     │   Port: 11435    │     │   Port: 3550        │
│   NVIDIA GPU        │     │   Vulkan/Intel   │     │   OpenVINO GPU      │
│   Planner models    │     │   qwen3-task-8k  │     │   bge-reranker-v2   │
│   bge-m3 (optional) │     │   bge-m3 (opt.)  │     │                     │
└─────────────────────┘     └──────────────────┘     └─────────────────────┘
                                                                │
                                                                ▼
                                                    ┌─────────────────────┐
                                                    │  Agentic Broker     │
                                                    │  Port: 3579         │
                                                    │  Python + Uvicorn   │
                                                    │  Depends on 3550    │
                                                    └─────────────────────┘
```

---

## Per-Service Launch (Manual Control)

Use these when you need granular control, debugging, or want to restart individual services after code updates.

### Step 1: Create Virtual Environments

### 1a. Labtools Venv (Required for MCP servers + broker)

```powershell
cd C:\Users\CarmineFaiola\AI
mkdir venvs

# Create labtools venv
python -m venv venvs\labtools

# Activate and install packages
venvs\labtools\Scripts\Activate.ps1
pip install --upgrade pip
pip install fastapi uvicorn httpx pydantic>=2.0 mcp tenacity tiktoken jsonschema orjson jinja2 tree-sitter tree-sitter-python

# Verify installation
python -c "import fastapi; import uvicorn; import mcp; print('OK')"
```

### 1b. OpenVINO Venv (Required for reranker)

```powershell
# Create openvino venv
python -m venv venvs\openvino

# Activate and install
venvs\openvino\Scripts\Activate.ps1
pip install --upgrade pip
pip install openvino openvino-dev

# Verify
python -c "import openvino; print('OK')"
```

---

## Step 2: Launch Ollama Task Server (Port 11435)

### 2a. Start the Task Instance

Open a **new PowerShell window** and run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\CarmineFaiola\AI\services\ollama-task-vulkan.ps1"
```

**What this script does (from `ollama-task-vulkan.ps1`):**
- Sets `OLLAMA_HOST=127.0.0.1:11435`
- Sets `OLLAMA_MODELS=C:\Users\CarmineFaiola\AI\models-task`
- Sets `OLLAMA_CONTEXT_LENGTH=12288`
- Sets `OLLAMA_KEEP_ALIVE=15m`
- Sets `OLLAMA_NO_CLOUD=1`
- Disables CUDA: `CUDA_VISIBLE_DEVICES=-1`
- Enables Vulkan: `OLLAMA_VULKAN=1`, `GGML_VK_VISIBLE_DEVICES=1`
- Runs `ollama.exe serve`

### 2b. Verify Health

In another terminal:

```powershell
curl http://127.0.0.1:11435/api/tags
```

Expected output: `{"models":[]}` (empty until models are pulled)

### 2c. Pull/Create Models

**⚠️ CRITICO:** Tutti i modelli vanno scaricati su **11435 (Intel GPU Vulkan)**, NON su 11434! Altrimenti i modelli si contendono le GPU.

```powershell
# Verifica che Ollama Task sia in esecuzione su 11435
curl http://127.0.0.1:11435/api/tags

# Imposta OLLAMA_HOST PRIMA di qualsiasi comando pull/create
$OllamaExe = (Get-Command ollama.exe).Source
$env:OLLAMA_HOST = "127.0.0.1:11435"

# Scarica modello base (se necessario)
& $OllamaExe pull qwen3:1.7b

# Crea modello task dal Modelfile
& $OllamaExe create qwen3-task-8k -f "C:\Users\CarmineFaiola\AI\modelfiles\Modelfile.qwen3task-8k"

# Scarica modello embedding BAAI/bge-m3 per RAG (stessa GPU Intel)
& $OllamaExe pull bge-m3:latest

# Verifica tutti i modelli su 11435
curl http://127.0.0.1:11435/api/tags
# Deve mostrare: qwen3-task-8k, qwen3:1.7b, bge-m3:latest
```

> **⚠️ ATTENZIONE:** `ollama pull` senza `$env:OLLAMA_HOST = "127.0.0.1:11435"` usa il default `11434`. Per scaricare su 11435 devi IMPOSTARE la variabile PRIMA del comando.

---

## Step 3: Install and Launch Reranker (Port 3550)

**Important:** The reranker runs on **OVMS/OpenVINO**, NOT on Ollama. It serves semantic reranking for the RAG pipeline.

### 3a. Download OVMS Runtime

Download OpenVINO Model Server from:
https://github.com/openvinotoolkit/model_server/releases

Extract to: `C:\Users\CarmineFaiola\AI\ovms-runtime\ovms`

Expected structure after extraction:
```
C:\Users\CarmineFaiola\AI\ovms-runtime\ovms\
  bin\
    ovms.exe
  setupvars.ps1
```

### 3b. Download Reranker Models

```powershell
# Create directories
mkdir C:\Users\CarmineFaiola\AI\models-ovms-rerank
mkdir C:\Users\CarmineFaiola\AI\cache\openvino
mkdir C:\Users\CarmineFaiola\AI\cache\huggingface

# Download from HuggingFace (safetensors format)
venvs\openvino\Scripts\Activate.ps1
pip install huggingface_hub
python -c "from huggingface_hub import snapshot_download; snapshot_download(repo_id='BAAI/bge-reranker-v2-m3', local_dir='C:/Users/CarmineFaiola/AI/models-ovms-rerank/bge-reranker-v2-m3')"

# Export to ONNX format
python export_onnx.py
```

### 3c. Create OVMS Config

Create file `C:\Users\CarmineFaiola\AI\models-ovms-rerank\config.json`:

```json
{
  "model_name": "bge-reranker-v2-m3",
  "model_path": "C:\\Users\\CarmineFaiola\\AI\\models-ovms-rerank\\bge-reranker-v2-m3",
  "model_file": "model.onnx",
  "model_format": "onnx",
  "batch_size": "8",
  "num_thread": 8,
  "target_device": "GPU.0",
  "service_config": {
    "rest_port": 3550,
    "rest_bind_address": "127.0.0.1"
  }
}
```

### 3d. Launch Reranker

Open a **new PowerShell window** and run:

```powershell
# Method 1: Using launcher script (recommended)
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\CarmineFaiola\AI\services\ovms-reranker-npu.ps1"

# Method 2: Direct OVMS command (if config exists)
& "C:\Users\CarmineFaiola\AI\ovms-runtime\ovms\bin\ovms.exe" `
  --rest_port 3550 `
  --rest_bind_address 127.0.0.1 `
  --config_path "C:\Users\CarmineFaiola\AI\models-ovms-rerank\config.json"
```

**What `ovms-reranker-npu.ps1` does (from source code):**
- Reads `OVMS_ROOT`, `OVMS_EXE`, `OVMS_SETUP`, `MODELS` from environment or uses defaults
- Default `OVMS_ROOT`: `C:\Users\CarmineFaiola\AI\ovms-runtime\ovms`
- Default `MODELS`: `C:\Users\CarmineFaiola\AI\models-ovms-rerank`
- Default `TARGET_DEVICE`: From env `OPENVINO_PROVIDER_DEVICE` or `"GPU.0"`
- Sources `setupvars.ps1` to set OpenVINO environment
- Runs `ovms.exe --rest_port 3550 --rest_bind_address 127.0.0.1 --config_path <config>`

### 3e. Verify Health

```powershell
# Check ready endpoint
curl http://127.0.0.1:3550/v2/models/BAAI%2Fbge-reranker-v2-m3/ready

# Test functional reranking
curl -X POST http://127.0.0.1:3550/v3/rerank `
  -H "Content-Type: application/json" `
  -d '{
    "model": "BAAI/bge-reranker-v2-m3",
    "query": "test query",
    "documents": ["doc1", "doc2"]
  }'
```

---

## Step 4: Launch Agentic Loop Broker (Port 3579)

### 4a. Quick Launch (Recommended — Single Script)

Run the standalone launch script which sets all environment variables, creates config.json if missing, and launches the broker:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\CarmineFaiola\AI\launch-standalone.ps1"
```

This script:
- Performs pre-flight checks for Ollama Task (11435) and OVMS Reranker (3550)
- Sets all process-local environment variables (NOT persisted to registry)
- Creates `models-ovms-rerank\config.json` if it doesn't exist
- Launches the Agentic Loop Broker on port 3579

### 4b. Manual Launch (Step-by-Step)

If you prefer manual control, open a **new PowerShell window** and run all these commands:

```powershell
# Core repo paths (from config/models.py defaults)
$env:AICARMINE_LAB_REPO = "C:\Users\CarmineFaiola\AI"
$env:AICARMINE_REAL_REPO = "C:\Users\CarmineFaiola\AI"
$env:AICARMINE_CODEX_MCP_REPO_ROOT = "C:\Users\CarmineFaiola\AI"
$env:OPEN_TERMINAL_CWD = "C:\Users\CarmineFaiola\AI"
$env:AICARMINE_OPEN_TERMINAL_WORKDIR = "C:\Users\CarmineFaiola\AI"

# Workspace and job storage paths
$workspaceRoot = "C:\Users\CarmineFaiola\AI\state\codex_bridge\agentic_loop_client\port-3579\workspace"
mkdir $workspaceRoot -Force
$env:AICARMINE_VULKAN_WORKSPACE = $workspaceRoot

$jobRoot = "$workspaceRoot\agent-jobs"
mkdir $jobRoot -Force
$env:AICARMINE_AGENT_JOB_ROOT = $jobRoot
$env:AICARMINE_AGENT_JOB_DB = "$jobRoot\agent_jobs.sqlite3"

# Broker identity and endpoints
$env:AICARMINE_AGENT_PUBLIC_BASE_URL = "http://127.0.0.1:3579"
$env:AICARMINE_VULKAN_AGENT_URL = "http://127.0.0.1:3579/vulkan/agent"
$env:AICARMINE_BROKER_SERVICE_NAME = "aicarmine-codex-agentic-loop-3579"
$env:AICARMINE_BROKER_APP_TITLE = "AI-Carmine Codex Agentic Loop 3579"
$env:AICARMINE_BROKER_UVICORN_RELOAD = "0"

# Reranker URLs (MUST point to port 3550)
$env:RAG_EXTERNAL_RERANKER_URL = "http://127.0.0.1:3550/v3/rerank"
$env:AICARMINE_RAG_RERANK_URL = "http://127.0.0.1:3550/v3/rerank"
$env:AICARMINE_CONTROLLER_RAG_RERANK_URL = "http://127.0.0.1:3550/v3/rerank"
$env:AICARMINE_RAG_RERANK_READY_URL = "http://127.0.0.1:3550/v2/models/BAAI%2Fbge-reranker-v2-m3/ready"

# Ollama Task URLs
$env:AICARMINE_OLLAMA_TASK_URL = "http://127.0.0.1:11435/api/chat"
$env:AICARMINE_VULKAN_BROKER_OLLAMA_URL = "http://127.0.0.1:11435/api/chat"
$env:AICARMINE_OLLAMA_TASK_MODEL = "qwen3-task-8k"
$env:AICARMINE_VULKAN_BROKER_MODEL = "qwen3-task-8k"
$env:AICARMINE_OLLAMA_KEEP_ALIVE = "24h"

# Planner URLs (points to main Ollama on 11434 if available)
$env:AICARMINE_AGENT_PLANNER_URL = "http://127.0.0.1:11434/api/chat"
$env:AICARMINE_PLANNER_MODEL = "qwen3.5:9b-coding-v5-1"

# Agentic planner settings
$env:AICARMINE_AGENTIC_PLANNER_ENABLED = "1"
$env:AICARMINE_AGENTIC_PLANNER_NATIVE_TOOLS = "1"
$env:AICARMINE_AGENTIC_PLANNER_REQUIRE_NATIVE_TOOLS = "1"
$env:AICARMINE_AGENTIC_PLANNER_NUM_CTX = "262144"
$env:AICARMINE_AGENTIC_PLANNER_NUM_CTX_CAP = "262144"
$env:AICARMINE_AGENTIC_PLANNER_PROMPT_CHAR_BUDGET = "262144"
$env:AICARMINE_AGENTIC_PLANNER_PROMPT_COMPACT_RATIO = "0.85"
$env:AICARMINE_AGENT_DEFAULT_MAX_STEPS = "40"
$env:AICARMINE_AGENT_MAX_STEPS = "100"

# Optional: OpenVINO provider settings
$env:OPENVINO_PROVIDER_DEVICE = "GPU.0"
$env:ENABLE_OPENVINO_PROVIDER = "1"
$env:ENABLE_EXTERNAL_RERANKER = "1"
```

### 4b. Launch Broker

In the same terminal:

```powershell
cd C:\Users\CarmineFaiola\AI\services
C:\Users\CarmineFaiola\AI\venvs\labtools\Scripts\python.exe -m uvicorn aicarmine_vulkan_tool_broker:app --host 127.0.0.1 --port 3579
```

**What this starts (from `aicarmine_broker/app.py` + `config/models.py`):**
- FastAPI app with title from `AICARMINE_BROKER_APP_TITLE`
- Health endpoint at `/health`
- Vulkan agent endpoint at `/vulkan/agent`
- Jobs index at `/jobs`
- Reads all configuration from environment variables listed above

### 4c. Verify Health

```powershell
curl http://127.0.0.1:3579/health
```

Expected output includes:
```json
{
  "ok": true,
  "service": "aicarmine-codex-agentic-loop-3579",
  "mode": "public_x_v6_vulkan_select_dispatcher_execute_deterministic_wrap",
  "ollama_task_url": "http://127.0.0.1:11435/api/chat",
  "ollama_task_model": "qwen3-task-8k",
  "planner_url": "http://127.0.0.1:11434/api/chat",
  "lab_repo": "C:\\Users\\CarmineFaiola\\AI",
  ...
}
```

---

## Step 5: Configure MCP Client (Optional — for Codex App)

If using Codex App, create `.codex/config.toml`:

```toml
[mcp_servers.agentic_loop_client]
command = "python"
args = ["C:\\Users\\CarmineFaiola\\AI\\services\\codex_bridge\\agentic_loop_client_mcp_server.py"]
cwd = "C:\\Users\\CarmineFaiola\\AI"
enabled = true
required = false
startup_timeout_sec = 20
tool_timeout_sec = 900

env = {
  AICARMINE_LAB_REPO = "C:\\Users\\CarmineFaiola\\AI",
  AICARMINE_CODEX_MCP_REPO_ROOT = "C:\\Users\\CarmineFaiola\\AI",
  AICARMINE_AGENTIC_LOOP_CLIENT_URL = "http://127.0.0.1:3579/vulkan/agent",
  AICARMINE_AGENTIC_LOOP_CLIENT_HEALTH_URL = "http://127.0.0.1:3579/health",
  AICARMINE_AGENTIC_LOOP_CLIENT_PORT = "3579"
}
```

---

## Port Reference

| Service | Port | Purpose | Health Check |
|---|---|---|---|
| Ollama Task | 11435 | Model inference (Vulkan/Intel GPU) | `curl http://127.0.0.1:11435/api/tags` |
| OVMS Reranker | 3550 | Semantic reranking (OpenVINO GPU) | `curl http://127.0.0.1:3550/v2/models/BAAI%2Fbge-reranker-v2-m3/ready` |
| Agentic Broker | 3579 | Job orchestration + Vulkan agent | `curl http://127.0.0.1:3579/health` |

---

## Startup Order (Critical)

Services **must** be started in this order:

1. **Ollama Task** (11435) → Wait for `/api/tags` to return `{"models":[]}`
2. **Pull Models** → `ollama pull qwen3-task-8k` on port 11435
3. **OVMS Reranker** (3550) → Wait for `/v2/models/.../ready` returns `{"status":"READY"}`
4. **Agentic Broker** (3579) → Wait for `/health` returns `{"ok":true}`

Each service must report "healthy" before starting the next one.

---

## Stopping Services

### Method 1: Find and stop by port

```powershell
# Find processes using ports
netstat -ano | findstr ":3579"
netstat -ano | findstr ":3550"
netstat -ano | findstr ":11435"

# Stop by PID (replace <PID> with actual process ID)
Stop-Process -Id <PID> -Force
```

### Method 2: Kill by image name

```powershell
taskkill /F /IM ollama.exe
taskkill /F /IM ovms.exe
taskkill /F /IM python.exe
```

---

## Troubleshooting

### Port Already in Use

```powershell
# Check what's using a port
netstat -ano | findstr :3579
netstat -ano | findstr :3550
netstat -ano | findstr :11435

# Kill process (replace PID)
Stop-Process -Id <PID> -Force
```

### Reranker Not Responding

1. Verify OVMS config path is correct: `Test-Path C:\Users\CarmineFaiola\AI\models-ovms-rerank\config.json`
2. Check `target_device` matches your GPU (`GPU.0` for NVIDIA, `GPU` for Intel)
3. Ensure OpenVINO runtime is installed and `setupvars.ps1` exists
4. Check log output from the PowerShell window running `ovms-reranker-npu.ps1`

### Broker Fails to Start

1. Verify labtools Python exists: `Test-Path C:\Users\CarmineFaiola\AI\venvs\labtools\Scripts\python.exe`
2. Verify all env vars are set (especially reranker URLs pointing to 3550)
3. Check that port 3579 is free: `netstat -ano | findstr :3579`
4. Review startup output for specific error messages

### Ollama Task Not Starting

1. Verify `ollama.exe` is in PATH: `Get-Command ollama.exe`
2. Check Vulkan device availability: `dxdiag` → Display tab
3. Ensure `models-task` directory exists: `Test-Path C:\Users\CarmineFaiola\AI\models-task`
4. Check Windows Event Viewer for Vulkan errors

### "ModuleNotFoundError: No module named 'aicarmine_broker'"

This means the labtools venv doesn't have the required packages. Re-run:

```powershell
venvs\labtools\Scripts\Activate.ps1
pip install fastapi uvicorn httpx pydantic>=2.0 mcp tenacity tiktoken jsonschema orjson jinja2 tree-sitter tree-sitter-python
```

### "Connection refused" on health endpoints

- Ensure each service is running in its own PowerShell window
- Wait 5-10 seconds after starting each service before checking health
- Check that no firewall is blocking localhost connections
- Verify the port matches what you configured (11435, 3550, 3579)