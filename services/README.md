# services

`services/` is the main runtime surface for the local OpenWebUI agentic tool
loop. It contains the public bridge, internal broker, launcher modules, model
export helpers, Codex bridge helpers, operational scripts and contract
documentation.

## Initial Reading Index

Start from these documents before changing runtime behavior:

- [AGENTS.md](../AGENTS.md)
  - Workspace operating rules and non-negotiable runtime contract notes.
- [services/VALIDATOR_ONLY_AGENTIC_LOOP_CONTRACT.md](VALIDATOR_ONLY_AGENTIC_LOOP_CONTRACT.md)
  - Core validator/controller contract for the agentic loop.
- [services/END_TO_END_AGENTIC_FLOW.md](END_TO_END_AGENTIC_FLOW.md)
  - End-to-end flow between OpenWebUI, 3571, 3572, planner, tools, and final payload.
- [services/SERVICES_MODULE_TECHNICAL_REFERENCE.md](SERVICES_MODULE_TECHNICAL_REFERENCE.md)
  - Service-level technical map and module references.
- [services/MODULE_TECHNICAL_DESCRIPTIONS.md](MODULE_TECHNICAL_DESCRIPTIONS.md)
  - File-by-file technical descriptions for the `services/` tree.
- [services/CODEX_OPENWEBUI_PAYLOAD_LIMITATION.md](CODEX_OPENWEBUI_PAYLOAD_LIMITATION.md)
  - Operational limit for Codex when inspecting large OpenWebUI payloads.
- [services/aicarmine_broker/MODULE_REFERENCE.md](aicarmine_broker/MODULE_REFERENCE.md)
  - Broker module reference.
- [services/vulkan_bridge/MODULE_REFERENCE.md](vulkan_bridge/MODULE_REFERENCE.md)
  - Public bridge module reference.
- [services/codex_bridge/MODULE_REFERENCE.md](codex_bridge/MODULE_REFERENCE.md)
  - Codex bridge module reference.
- [services/launch/MODULE_REFERENCE.md](launch/MODULE_REFERENCE.md)
  - Launch-script module reference.
- [services/model_export/MODULE_REFERENCE.md](model_export/MODULE_REFERENCE.md)
  - Model export module reference.

Core code entry points:

- [services/vulkan_bridge/app.py](vulkan_bridge/app.py)
  - Public OpenWebUI wrapper surface.
- [services/vulkan_bridge/agentic_v9.py](vulkan_bridge/agentic_v9.py)
  - Agentic bridge integration surface.
- [services/aicarmine_broker/app.py](aicarmine_broker/app.py)
  - Internal broker application.
- [services/aicarmine_broker/planner.py](aicarmine_broker/planner.py)
  - Planner/controller contract and validation loop.
- [services/aicarmine_broker/repo_tools.py](aicarmine_broker/repo_tools.py)
  - Repository inspection, command, validation, and code-product tool implementations.
- [services/aicarmine_broker/tool_registry.py](aicarmine_broker/tool_registry.py)
  - Internal tool registry.
- [services/aicarmine_broker/tool_dispatch.py](aicarmine_broker/tool_dispatch.py)
  - Tool dispatch layer.
- [services/aicarmine_broker/job_store.py](aicarmine_broker/job_store.py)
  - Job state and artifact persistence.
- [services/aicarmine_broker/public_wrapper.py](aicarmine_broker/public_wrapper.py)
  - Public result packaging support.
- [services/aicarmine_broker/planner_intrinsic_context.py](aicarmine_broker/planner_intrinsic_context.py)
  - Intrinsic planner context builder.
- [services/aicarmine_broker/code_edit_proposal_contract.py](aicarmine_broker/code_edit_proposal_contract.py)
  - Report-only code edit proposal contract.
- [services/aicarmine_broker/memory_tools.py](aicarmine_broker/memory_tools.py)
  - Runtime memory tool support.

## Current Folder Structure

- [aicarmine_broker/](aicarmine_broker/)
  - Internal 3572 broker/runtime, planner loop, validator, tools and job views.
- [vulkan_bridge/](vulkan_bridge/)
  - Public 3571 OpenWebUI bridge and terminal payload wrapper.
- [codex_bridge/](codex_bridge/)
  - Optional Codex-facing MCP and Responses-compatible bridge helpers.
- [launch/](launch/)
  - PowerShell launcher modules and runtime process/env helpers.
- [model_export/](model_export/)
  - CLI-oriented model export helpers.
- [openwebui-data/](openwebui-data/README.md)
  - Local OpenWebUI data descriptor only; runtime contents are ignored.
- [RUNTIME_SCRIPT_REFERENCE.md](RUNTIME_SCRIPT_REFERENCE.md)
  - Reference for top-level scripts.
- [requirements-agentic-optional.txt](requirements-agentic-optional.txt)
  - Optional runtime dependency list.
