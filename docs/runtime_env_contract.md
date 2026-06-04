# Runtime Environment Contract

This document records the verified runtime boundaries that the refactor must
preserve.

## Process Roles

| Role | Endpoint | Owner | Expected runtime |
| --- | --- | --- | --- |
| Public OpenWebUI tool bridge | `127.0.0.1:3571` | `services/vulkan_bridge/app.py` | `venvs/labtools` |
| Internal agent broker | `127.0.0.1:3572` | `services/aicarmine_broker/app.py` | `venvs/labtools` |
| Main planner Ollama | `127.0.0.1:11434` | external Ollama Desktop/main process | external Ollama |
| Repair/task Ollama | `127.0.0.1:11435` | `ollama-task-vulkan.ps1` | external Ollama task instance |
| OpenWebUI UI | usually `127.0.0.1:8080` | `services/aicarmine-openwebui-serve.py` | `venvs/openwebui` |

## Environment Sources

The broker/bridge Python services use values parsed in
`services/aicarmine_broker/config.py` and `services/vulkan_bridge/app.py`.
Launcher scripts may set process/user env before startup, but live behavior is
determined by the environment inherited by the running process.

Critical planner defaults documented in the current code/docs:

- `AICARMINE_AGENTIC_PLANNER_NUM_CTX=12288`
- `AICARMINE_AGENTIC_PLANNER_NUM_CTX_CAP=12288`
- `AICARMINE_AGENTIC_PLANNER_PROMPT_CHAR_BUDGET=48000`
- `AICARMINE_AGENTIC_PLANNER_PROMPT_COMPACT_RATIO=0.5`

The refactor must not change model, context, launcher order or service venv as
part of code-structure cleanup. Those changes require separate runtime proof.

## Payload Isolation

OpenWebUI receives only the public 3571 response. It cannot inspect:

- `C:\Users\...` local paths;
- job workspaces;
- SQLite prompt documents;
- `reads/*.json` or `tool-results/*.json`;
- 3572-only dashboards.

Any payload required by OpenWebUI must be expanded inline before the 3571
response leaves the bridge.
