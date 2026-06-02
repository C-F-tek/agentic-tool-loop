# Agentic Tool Loop

Repository for the local OpenWebUI agentic tool loop runtime.

This project contains the service code, contracts, launch scripts, model
templates, and documentation needed to run the local tool bridge and broker.
Machine-local data, generated artifacts, model binaries, virtual environments,
OpenWebUI data, and job outputs are intentionally excluded from Git.

## Top-Level Tree

```text
.
|-- AGENTS.md
|-- README.md
|-- .gitignore
|-- services/
|-- codex_ollama_bridge_applied/
|-- modelfiles/
|-- lab-worktrees/
|-- openwebui-data/
|-- qwen-agent-workspace/
|-- qwen-agent/
|-- qwen-context/
|-- code-interpreter-workdir/
|-- executor-runs/
|-- payloads/
|-- logs/
|-- cache/
|-- state/
|-- knowledge-*/
|-- models-*/
|-- ovms-runtime/
|-- lab-patches/
`-- venvs/
```

## Source And Runtime Code

### `services/`

Main service surface for the agentic loop.

Important submodules:

- `services/vulkan_bridge/`: public OpenWebUI-facing bridge surface, including
  the `vulkan_helper` wrapper flow.
- `services/aicarmine_broker/`: internal broker and planner loop, job store,
  tool registry, repo tools, memory tools, planner contracts, and code-product
  proposal support.
- `services/codex_bridge/`: Codex/Ollama bridge helpers.
- `services/model_export/`: local model export helpers.
- `services/launch/`: PowerShell runtime launch helpers.

Important documentation:

- `services/VALIDATOR_ONLY_AGENTIC_LOOP_CONTRACT.md`
- `services/END_TO_END_AGENTIC_FLOW.md`
- `services/SERVICES_MODULE_TECHNICAL_REFERENCE.md`
- `services/MODULE_TECHNICAL_DESCRIPTIONS.md`
- `services/CODEX_OPENWEBUI_PAYLOAD_LIMITATION.md`

### `codex_ollama_bridge_applied/`

Applied bridge scripts and copied tool/runtime material used as part of the
local Codex/Ollama/OpenWebUI integration.

### `modelfiles/`

Ollama Modelfile templates and model configuration examples. Actual model
binaries are not committed.

## External Or Local-Only Work Areas

These directories are represented by committed `README.md` descriptors only.
Their runtime contents are ignored by `.gitignore`.

### `lab-worktrees/`

Local controlled worktrees used by the agentic tool loop and OpenTerminal.
The worktree code itself is external and already versioned elsewhere.

### `openwebui-data/` and `services/openwebui-data/`

Local OpenWebUI data directories. They may contain chats, uploads, runtime
databases, caches, and generated state. Those contents are not source.

### `qwen-agent-workspace/`

Local job workspace for broker runs, tool results, planner streams, and final
artifacts.

### `qwen-agent/` and `qwen-context/`

Local Qwen context, reports, patches, and runtime state.

### `code-interpreter-workdir/`

Scratch workspace for code-interpreter style executions.

### `executor-runs/`, `payloads/`, `logs/`, `cache/`, `state/`

Runtime outputs, diagnostic captures, logs, caches, and local state.

### `knowledge-*/`

Generated knowledge packs, Markdown splits, upload batches, and synchronized
knowledge mirrors. Curated documentation should live in normal source docs
instead.

### `models-*/` and `ovms-runtime/`

Local model stores and OpenVINO Model Server runtime files. Model binaries and
runtime state are not committed.

### `lab-patches/`

Local patch experiments and proof artifacts.

### `venvs/`

Local Python virtual environments.

## Git Import Policy

The repository keeps source, scripts, contracts, and documentation. It excludes:

- OpenWebUI user/runtime data.
- Agent job artifacts and planner/tool result outputs.
- Virtual environments and dependency caches.
- Model binaries and runtime backends.
- SQLite databases, generated knowledge stores, logs, payload captures, and
  temporary files.
- External lab worktree contents.

Directory descriptors are committed where useful so the project tree remains
understandable without importing private or generated data.
