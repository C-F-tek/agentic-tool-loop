# Implementation Plan: Services Independent of OpenWebUI

## Overview
This plan documents all services in the `services/` directory that can operate independently of OpenWebUI, their startup sequences, port assignments, and dependencies. The goal is to provide a clear reference for launching services without requiring the OpenWebUI frontend.

## Scope
The agentic-tool-loop project contains multiple service layers: model providers (Ollama), inference bridges (Vulkan), job brokers (3572), executors, diagnostic sidecars, and coding backends (Jupyter/Open Terminal). OpenWebUI serves as the UI layer but is not required for most backend services. This plan identifies which services are self-contained and can be started independently.

## Types

### Service Categories
1. **Model Providers**: Ollama (11434) - External API surface (single instance only)
2. **Inference Bridges**: Vulkan Bridge (3571), Vulkan Agent/Broker (3572) - HTTP FastAPI services
3. **Utility Services**: Executor (3560), OVMS Reranker (3550), NPU Phi (3551) - Diagnostic/utility HTTP services
4. **Coding Backends**: Jupyter (8889), Open Terminal (8888) - WebSocket-based code execution
5. **MCP Servers**: codex_bridge stdio servers - Process-based tool interfaces

### Port Assignments
| Port | Service | Protocol | Dependencies |
|------|---------|----------|--------------|
| 11434 | Ollama Main | HTTP/API | None (single Ollama instance) |
| 3550 | OVMS Reranker | HTTP/gRPC | OpenVINO runtime |
| 3551 | NPU Phi Service | HTTP/FastAPI | OpenVINO venv |
| 3560 | Executor Server | HTTP/FastAPI | labtools venv |
| 3571 | Vulkan Bridge | HTTP/FastAPI | 3572 broker, Ollama Main |
| 3572 | Vulkan Agent/Broker | HTTP/FastAPI | Ollama Main |
| 8888 | Open Terminal | HTTP/WebSocket | Jupyter token |
| 8889 | Jupyter Code Interpreter | HTTP/WebSocket | Jupyter token |
| 8080 | OpenWebUI | HTTP/ASGI | All above services |

## Files

### Key Service Entry Points (Independent of OpenWebUI)
- `services/aicarmine_vulkan_tool_broker.py` - 3572 broker FastAPI app
- `services/aicarmine_vulkan_bridge_server.py` - 3571 bridge FastAPI app
- `services/aicarmine-executor-server.py` - 3560 executor FastAPI app
- `services/npu_phi_service/__main__.py` - 3551 NPU Phi entrypoint
- `services/launch/openwebui_runtime.ps1` - Main launcher (contains all service startup logic)
- `services/launch_all_brokers.ps1` - Alternative launcher for 3571/3572
- `services/launch_broker_3572.ps1` - Single broker launcher
- `services/launch_standalone_services.ps1` - Standalone launcher for all services

### Configuration Files
- `services/launch/env.ps1` - Environment variable management
- `services/launch/process.ps1` - Process/port ownership helpers
- `services/launch/http.ps1` - HTTP endpoint polling
- `services/launch/ollama.ps1` - Ollama endpoint management

### Documentation Files
- `services/SERVICES_MODULE_TECHNICAL_REFERENCE.md` - Complete service map
- `services/RUNTIME_SCRIPT_REFERENCE.md` - Script-level reference
- `services/MODULE_TECHNICAL_DESCRIPTIONS.md` - File-by-file descriptions
- `docs/START_HERE_RUNTIME.md` - Runtime navigation guide

## Functions

### Service Startup Functions (from `launch/openwebui_runtime.ps1`)
- `Start-AICarmineVulkanBridgeStack()` - Starts 3572 broker + 3571 bridge
- `Start-UvicornServiceIfNeeded($Name, $Port, $Module, $HealthCheck)` - Generic uvicorn starter
- `Start-AICarmineExecutor()` - Starts executor server on 3560
- `Start-AICarmineJupyter()` - Starts Jupyter Code Interpreter on 8889
- `Start-AICarmineOpenTerminal()` - Starts Open Terminal on 8888
- `Start-OpenVINOProviderIfEnabled()` - Starts OVMS reranker on 3550
- `Start-NpuPhiServiceIfEnabled()` - Starts NPU Phi sidecar on 3551
- `Test-AICarmineVulkanAgent()` - Health check for 3572
- `Test-AICarmineVulkanBridge()` - Health check for 3571
- `Test-AICarmineExecutor()` - Health check for 3560
- `Test-AICarmineJupyter()` - Health check for 8889

### Environment Management Functions
- `Set-UserEnvValue($Name, $Value)` - Set persistent environment variable
- `Set-UserEnvDefault($Name, $DefaultValue)` - Set env if not already set
- `Clear-UserEnvValue($Name)` - Clear environment variable
- `Get-AICarmineLabtoolsPython()` - Resolve labtools Python executable
- `Invoke-WithAICarmineLabtoolsPythonEnv($ScriptBlock)` - Execute with labtools venv isolation

## Classes

### Configuration Model (from `launch/openwebui_runtime.ps1`)
```powershell
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
```

### AICarminePersistentConfig (from `launch/openwebui_runtime.ps1`)
```powershell
$AICarminePersistentConfig = @{
    AICARMINE_VULKAN_TOOL_BROKER_OPENAPI = "http://127.0.0.1:3571/openapi.json"
    AICARMINE_VULKAN_TOOL_BROKER_URL = "http://127.0.0.1:3571"
    AICARMINE_VULKAN_AGENT_URL = "http://127.0.0.1:3572/vulkan/agent"
    AICARMINE_AGENT_PLANNER_URL = "http://127.0.0.1:11434/api/chat"
    AICARMINE_AGENT_PLANNER_MODEL = "qwen3.5:9b-coding"
    AICARMINE_OPENWEBUI_RETURN_MODEL = "qwen3.5:9b-coding"
    AICARMINE_AGENTIC_PLANNER_ENABLED = "1"
    AICARMINE_AGENTIC_PLANNER_NATIVE_TOOLS = "1"
    AICARMINE_AGENTIC_PLANNER_REQUIRE_NATIVE_TOOLS = "1"
    AICARMINE_AGENTIC_PLANNER_NUM_CTX = "262144"
    AICARMINE_AGENTIC_PLANNER_PROMPT_CHAR_BUDGET = 262144
    AICARMINE_AGENTIC_PLANNER_PROMPT_COMPACT_RATIO = "0.85"
    AICARMINE_AGENTIC_PLANNER_NUM_PREDICT = "-1"
    AICARMINE_AGENTIC_RESULT_COMPACT_CHARS = "50000"
    AICARMINE_AGENT_APPROVAL_MODE = "safe_write_lab"
    AICARMINE_CODEX_COMMAND_TIMEOUT = "1000"
    AICARMINE_CODEX_MAX_TOOL_RESULT_CHARS = "70000"
    AICARMINE_VULKAN_BROKER_OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
    AICARMINE_VULKAN_BROKER_MODEL = "qwen3.5:9b-coding"
    AICARMINE_VULKAN_BRIDGE_TIMEOUT_SECONDS = "12000"
    AICARMINE_AGENT_RETURN_WAIT_SECONDS = "9000"
}
```

## Dependencies

### Virtual Environments
| Venv | Path | Services |
|------|------|----------|
| labtools | `venvs\labtools` | 3571, 3572, 3560 broker services |
| openwebui | `venvs\openwebui` | OpenWebUI, Open Terminal |
| openvino | `venvs\openvino` | OVMS reranker, NPU Phi service |

### External Dependencies
- **Ollama**: Required for model serving (single instance on 11434)
- **OpenVINO**: Required for OVMS reranker and NPU Phi diagnostic sidecar
- **CUDA**: Required for GPU-accelerated Ollama models
- **Jupyter Token**: Required for Open Terminal and Jupyter Code Interpreter

### Service Dependency Chain
```
Ollama (11434) → Vulkan Broker (3572) → Vulkan Bridge (3571) → OpenWebUI (8080)
```
The broker (3572) requires Ollama Main (11434). The bridge (3571) requires the broker (3572). OpenWebUI (8080) consumes the bridge API. However, 3571 and 3572 can run independently without OpenWebUI. Note: Only one Ollama instance is available on port 11434.

## Testing

### Verification Steps
1. Verify Ollama Main (11434) - Check with `curl http://127.0.0.1:11434/api/tags`
2. Start Vulkan Broker (3572) - Verify with `http://127.0.0.1:3572/health`
3. Start Vulkan Bridge (3571) - Verify with `http://127.0.0.1:3571/health`
4. Start Executor (3560) - Verify with `http://127.0.0.1:3560/health`
5. Start OVMS Reranker (3550) - Verify with `http://127.0.0.1:3550/v2/models/BAAI%2Fbge-reranker-v2-m3/ready`
6. Start NPU Phi (3551) - Verify with `http://127.0.0.1:3551/healthz`
7. Start Jupyter (8889) - Verify with `http://127.0.0.1:8889/api/status?token=<token>`
8. Start Open Terminal (8888) - Verify with `http://127.0.0.1:8888/openapi.json`

### Independent Service Tests
Each service has a dedicated health check function. Verify port accessibility and health endpoint responses without launching OpenWebUI.

## Standalone Launcher Script

### Usage
```powershell
# Launch all standalone services
powershell -ExecutionPolicy Bypass -File services\launch_standalone_services.ps1

# Stop all uvicorn services
Get-Process python | Where-Object { $_.CommandLine -like '*uvicorn*' } | Stop-Process -Force
```

### Services Managed by Launcher
1. **Ollama Main (11434)** - Check status only (Ollama managed separately)
2. **OVMS Reranker (3550)** - Launch via `services/ovms-reranker-npu.ps1`
3. **Vulkan Tool Broker (3572)** - FastAPI via `aicarmine_vulkan_tool_broker:app`
4. **Vulkan Bridge (3571)** - FastAPI via `aicarmine_vulkan_bridge_server:app`
5. **Executor Server (3560)** - FastAPI via `aicarmine-executor-server:app`

### Log Files
Individual service logs are written to `C:\Users\sanit\agentic-tool-loop\logs\`:
- `broker-3572-standalone.stdout.log` / `.stderr.log`
- `bridge-3571-standalone.stdout.log` / `.stderr.log`
- `executor-3560-standalone.stdout.log` / `.stderr.log`
- `ovms-reranker-3550.stdout.log` / `.stderr.log`

## Implementation Order

1. **Document service ports and entry points** - Create reference table of all services, their ports, and Python/PowerShell entry points ✅
2. **Document environment requirements** - List venvs, env vars, and external dependencies per service ✅
3. **Document startup functions** - Extract and document each service's startup logic from launch scripts ✅
4. **Create standalone launcher scripts** - Create minimal launchers for individual services ✅
5. **Verify independent operation** - Test each service can start and respond to health checks without OpenWebUI ✅
6. **Document dependency chains** - Clarify which services require others vs which are fully self-contained ✅