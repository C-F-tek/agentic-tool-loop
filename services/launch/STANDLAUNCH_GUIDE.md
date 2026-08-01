# Standalone Agentic Loop Launcher - Complete Guide

This guide covers how to launch the entire agentic broker loop without OpenWebUI, using only the broker on port 3579.

## Architecture

| Component | Port | Purpose |
|-----------|------|---------|
| Reranker (OVMS) | 3550 | BGE reranker for semantic search |
| Broker | 3579 | Agentic loop broker (no OpenWebUI) |
| Ollama Task | 11435 | GPU0 model for planner repair |
| Ollama Planner | 11434 | 30B planner model |

## Prerequisites

1. **Ollama installed** with models:
   ```powershell
   ollama pull mio-qwen-code3:latest
   # or
   ollama pull qwen3-task-8k
   ```

2. **Python 3.10+** installed and available in PATH

3. **Required Python packages**:
   ```powershell
   pip install uvicorn fastapi httpx
   ```

## Step 1: Set Permanent Environment Variables

Run this ONCE to set permanent environment variables in PowerShell profile:

```powershell
cd C:\Users\sanit\agentic-tool-loop\services\launch
.\set_env_vars.ps1
```

Then activate in current session:
```powershell
. $PROFILE
```

## Step 2: Create Workspace Directories

```powershell
mkdir -p C:\Users\sanit\AI\qwen-agent-workspace\vulkan-broker
mkdir -p C:\Users\sanit\AI\lab-worktrees\blender-audio-project-lab
```

## Step 3: Launch Standalone Agentic Loop

### Option A: Using the Launcher Script (Recommended)

```powershell
cd C:\Users\sanit\agentic-tool-loop\services
.\broker_standalone_3579.ps1
```

This script will:
1. Check if broker is already running on port 3579
2. Set environment variables
3. Start the broker
4. Verify health endpoints

### Option B: Using the Manual Command

```powershell
cd C:\Users\sanit\agentic-tool-loop\services
$env:AICARMINE_VULKAN_WORKSPACE = "C:\Users\sanit\AI\qwen-agent-workspace\vulkan-broker"
$env:AICARMINE_LAB_REPO = "C:\Users\sanit\AI\lab-worktrees\blender-audio-project-lab"
$env:AICARMINE_AGENT_JOB_ROOT = "C:\Users\sanit\AI\qwen-agent-workspace\vulkan-broker\agent-jobs"
$env:AICARMINE_AGENT_JOB_DB = "C:\Users\sanit\AI\qwen-agent-workspace\vulkan-broker\agent-jobs\agent_jobs.sqlite3"
$env:AICARMINE_AGENTIC_PLANNER_MODEL = "mio-qwen-code3:latest"
$env:AICARMINE_AGENTIC_PLANNER_NUM_CTX = "262144"
python -m uvicorn aicarmine_broker.app:app --host 127.0.0.1 --port 3579
```

## Step 4: Verify Components

Check health endpoints:
```powershell
# Reranker health
curl http://127.0.0.1:3550/v2/models/BAAI%2Fbge-reranker-v2-m3/ready

# Broker health
curl http://127.0.0.1:3579/health

# Ollama Task
curl http://127.0.0.1:11435/api/version

# Ollama Planner
curl http://127.0.0.1:11434/api/version
```

## Step 5: Use the Broker

### Via MCP Tools (Cline)

Use the following MCP tools:
- `aicarmine_agentic_loop_run` - Start a job
- `aicarmine_agentic_loop_status` - Check job status
- `aicarmine_agentic_loop_result` - Get job result
- `aicarmine_agentic_loop_ensure_broker` - Restart broker

### Via curl

```powershell
# Start a job
curl http://127.0.0.1:3579/vulkan/agent -H 'Content-Type: application/json' -d '{"task":"test","request":"prova"}'

# Check status
curl http://127.0.0.1:3579/health

# Get result
curl http://127.0.0.1:3579/vulkan/agent/result -H 'Content-Type: application/json' -d '{"job_id":"job-xxx"}'
```

## Troubleshooting

### Port Already in Use

If a port is already in use, the script will try to stop the existing process:
```powershell
# Find process using port
netstat -ano | findstr ":3579"

# Kill process
Stop-Process -Id <PID> -Force
```

### Broker Fails to Start

Check the logs:
```powershell
Get-Content C:\Users\sanit\agentic-tool-loop\logs\broker-3579-*.stderr.log -Tail 40
```

### Rerancer Fails to Start

Check the logs:
```powershell
Get-Content C:\Users\sanit\agentic-tool-loop\logs\ovms-3550-*.stderr.log -Tail 40
```

## Environment Variables

| Variable | Value | Purpose |
|----------|-------|---------|
| AICARMINE_LAB_REPO | C:\Users\sanit\AI\lab-worktrees\blender-audio-project-lab | Lab repository root |
| AICARMINE_VULKAN_WORKSPACE | C:\Users\sanit\AI\qwen-agent-workspace\vulkan-broker | Vulkan workspace |
| AICARMINE_AGENT_JOB_ROOT | C:\Users\sanit\AI\qwen-agent-workspace\vulkan-broker\agent-jobs | Agent job root |
| AICARMINE_AGENT_JOB_DB | C:\Users\sanit\AI\qwen-agent-workspace\vulkan-broker\agent-jobs\agent_jobs.sqlite3 | Agent job database |
| AICARMINE_AGENTIC_PLANNER_MODEL | mio-qwen-code3:latest | Planner model |
| AICARMINE_AGENTIC_PLANNER_NUM_CTX | 262144 | Context window size |
| AICARMINE_AGENTIC_PLANNER_ENABLED | 1 | Enable planner |
| AICARMINE_AGENTIC_PLANNER_NATIVE_TOOLS | 1 | Enable native tools |
| AICARMINE_AGENTIC_PLANNER_REQUIRE_NATIVE_TOOLS | 1 | Require native tools |
| AICARMINE_AGENTIC_PLANNER_URL | http://127.0.0.1:11435/api/chat | Planner URL |
| AICARMINE_VULKAN_BROKER_OLLAMA_URL | http://127.0.0.1:11435/api/chat | Ollama URL |
| AICARMINE_VULKAN_BROKER_MODEL | qwen3-task-8k | Broker model |
| AICARMINE_AGENT_DEFAULT_MAX_STEPS | 40 | Default max steps |
| AICARMINE_AGENT_MAX_STEPS | 100 | Max steps |

## Stopping the Broker

```powershell
# Stop broker process
Stop-Process -Id <PID> -Force

# Or kill all broker processes
Get-Process -Name "python" | Where-Object { $_.MainWindowTitle -like "*broker*" } | Stop-Process -Force