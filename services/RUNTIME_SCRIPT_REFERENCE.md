<!-- AICARMINE_NON_NEGOTIABLE_CONTRACT_START -->
Regole operative non negoziabili:
1. Il contratto non va modificato se non richiesto da Carmine esplicitamente.
2. Il prodotto finale puo' essere arricchito come gia' viene fatto; non cambiare logica senza richiesta esplicita.
3. Non devi presupporre nulla: non e' il tuo compito.
<!-- AICARMINE_NON_NEGOTIABLE_CONTRACT_END -->
# Runtime Script Reference

Updated: 2026-06-02

This document covers top-level service scripts under `C:\Users\carmi\AI\services`
that are not package modules. These scripts are entrypoints, compatibility
wrappers, diagnostics or operational helpers.

## Python Entrypoints And Wrappers

| File | Technical description |
| --- | --- |
| `aicarmine_vulkan_bridge_server.py` | Uvicorn import target for the 3571 public bridge. It keeps the historical module path stable while implementation lives in `vulkan_bridge.app`. |
| `aicarmine_vulkan_tool_broker.py` | Uvicorn import target for the 3572 broker/runtime. It keeps the historical module path stable while implementation lives in `aicarmine_broker.app`. |
| `aicarmine-executor-server.py` | FastAPI safe-command executor. It exposes `/health`, `/run`, `/payload_health` and `/run_payload_file`, validates bearer token when configured and calls `aicarmine-run-safe-command.ps1`. |
| `aicarmine-openwebui-serve.py` | OpenWebUI ASGI boot wrapper. It prepares OpenWebUI environment defaults and launches OpenWebUI through the OpenWebUI venv. |
| `aicarmine_codex_mcp_server.py` | Historical entrypoint that delegates to `codex_bridge.mcp_server`. |
| `aicarmine_codex_ollama_responses_bridge.py` | Historical entrypoint that delegates to `codex_bridge.ollama_responses_bridge`. |
| `export_model.py` | Historical CLI entrypoint that delegates to `model_export.cli`. |
| `apply_openwebui_ps1_open_terminal.py` | Text/zip patcher for OpenWebUI PowerShell artifacts so Open Terminal integration replaces the older Jupyter integration where configured. |

## PowerShell Entrypoints And Diagnostics

| File | Technical description |
| --- | --- |
| `openwebui.ps1` | Thin compatibility wrapper for `launch\openwebui_runtime.ps1`. Shortcuts should keep using this path, while implementation stays in `launch`. |
| `aicarmine-vulkan-tool-broker.ps1` | Standalone Vulkan helper stack launcher: starts/checks 3572 broker/runtime, then runs the 3571 public bridge using labtools Python or `AICARMINE_LABTOOLS_PYTHON`. |
| `aicarmine-executor-server.ps1` | Starts the executor service using `AICARMINE_EXECUTOR_PYTHON` or labtools Python. |
| `aicarmine-run-safe-command.ps1` | Guarded command runner used by the executor. It enforces repo mode, timeout and consent-oriented safety checks before command execution. |
| `aicarmine-jupyter-codeinterpreter.ps1` | Legacy code-interpreter/Jupyter launcher. Current Open Terminal integration should not accidentally re-enable this path. |
| `ollama-task-vulkan.ps1` | Starts/checks the task Ollama process used for Vulkan selector/repair flows on the task port. This is the GPU0 Intel task lane: `ollama.exe serve` on `127.0.0.1:11435` with `models-task` and Vulkan env. `GGML_VK_VISIBLE_DEVICES` must target the resolved Intel Vulkan device index; do not infer it from NVIDIA/Windows numbering. Keep separate from main planner Ollama and from labtools/openwebui Python checks. |
| `openvino-env.ps1` | Sets OpenVINO/cache/HuggingFace environment variables for diagnostics/provider processes. |
| `ovms-reranker-npu.ps1` | Starts OpenVINO Model Server reranker/NPU serving based on configured OVMS env. |
| `npu-phi-service.ps1` | Starts the Phi-3.5 OpenVINO/NPU diagnostic sidecar on 3551 through `venvs\openvino`; validates model IR files and runs `python -m npu_phi_service`. |
| `check-dev-toolchain.ps1` | Developer diagnostic for main/lab repo paths and local toolchain assumptions. |
| `sync-lab-from-main.ps1` | Synchronizes lab worktree from the main project tree. High data-risk script: verify source and destination before running. |
| `watch-lab-mirror.ps1` | Periodic watcher around lab mirror synchronization. Long-running operational helper. |

## Dependency And Documentation Files

| File | Technical description |
| --- | --- |
| `requirements-agentic-optional.txt` | Optional dependency list for agentic/runtime features. Install only into the intended venv and verify imports afterward. |
| `VALIDATOR_ONLY_AGENTIC_LOOP_CONTRACT.md` | Contract for planner/controller validation, finalization and OpenWebUI evidence transport. |
| `END_TO_END_AGENTIC_FLOW.md` | Code-backed runtime flow from OpenWebUI to 3571, 3572, 11434/11435, dispatcher, validation and terminal 3571 response. |
| `AGENTIC_LOOP_PATCH_NOTES.md` | Patch notes for current agentic loop behavior and recent changes. |
| `AGENTIC_LOOP_V5_OPERATIONAL_MEMORY_NOTES.md` | Notes for planner turn memory, `done_reason` capture and real tool-result transport. |
| `SERVICES_MODULE_TECHNICAL_REFERENCE.md` | Central service module map linking package-level references. |
| `npu_phi_service\MODULE_REFERENCE.md` | Package-local reference for the Phi-3.5 OpenVINO/NPU diagnostic sidecar. |

## Operational Rule

When a script fails at runtime, do not patch by assumption. First prove:

1. Which script path was invoked.
2. Which Python/PowerShell executable was used.
3. Which venv and user/process env values were active.
4. Which port/process was already running.
5. Whether the file being edited is actually loaded by that process.
