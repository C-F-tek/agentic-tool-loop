# services/aicarmine_broker

`services/aicarmine_broker/` is the internal 3572 broker/runtime. It owns job
lifecycle, planner prompt construction, validator-only gates, internal tool
dispatch, memory context, code-product contracts and job dashboards.

## Initial Reading Index

Start from these documents before changing runtime behavior:

- [AGENTS.md](../../AGENTS.md)
  - Workspace operating rules and non-negotiable runtime contract notes.
- [services/VALIDATOR_ONLY_AGENTIC_LOOP_CONTRACT.md](../VALIDATOR_ONLY_AGENTIC_LOOP_CONTRACT.md)
  - Core validator/controller contract for the agentic loop.
- [services/END_TO_END_AGENTIC_FLOW.md](../END_TO_END_AGENTIC_FLOW.md)
  - End-to-end flow between OpenWebUI, 3571, 3572, planner, tools, and final payload.
- [services/SERVICES_MODULE_TECHNICAL_REFERENCE.md](../SERVICES_MODULE_TECHNICAL_REFERENCE.md)
  - Service-level technical map and module references.
- [services/MODULE_TECHNICAL_DESCRIPTIONS.md](../MODULE_TECHNICAL_DESCRIPTIONS.md)
  - File-by-file technical descriptions for the `services/` tree.
- [services/CODEX_OPENWEBUI_PAYLOAD_LIMITATION.md](../CODEX_OPENWEBUI_PAYLOAD_LIMITATION.md)
  - Operational limit for Codex when inspecting large OpenWebUI payloads.
- [services/aicarmine_broker/MODULE_REFERENCE.md](MODULE_REFERENCE.md)
  - Broker module reference.
- [services/vulkan_bridge/MODULE_REFERENCE.md](../vulkan_bridge/MODULE_REFERENCE.md)
  - Public bridge module reference.
- [services/codex_bridge/MODULE_REFERENCE.md](../codex_bridge/MODULE_REFERENCE.md)
  - Codex bridge module reference.
- [services/launch/MODULE_REFERENCE.md](../launch/MODULE_REFERENCE.md)
  - Launch-script module reference.
- [services/model_export/MODULE_REFERENCE.md](../model_export/MODULE_REFERENCE.md)
  - Model export module reference.

Core code entry points:

- [services/vulkan_bridge/app.py](../vulkan_bridge/app.py)
  - Public OpenWebUI wrapper surface.
- [services/vulkan_bridge/agentic_v9.py](../vulkan_bridge/agentic_v9.py)
  - Agentic bridge integration surface.
- [services/aicarmine_broker/app.py](app.py)
  - Internal broker application.
- [services/aicarmine_broker/planner.py](planner.py)
  - Planner/controller contract and validation loop.
- [services/aicarmine_broker/repo_tools.py](repo_tools.py)
  - Repository inspection, command, validation, and code-product tool implementations.
- [services/aicarmine_broker/tool_registry.py](tool_registry.py)
  - Internal tool registry.
- [services/aicarmine_broker/tool_dispatch.py](tool_dispatch.py)
  - Tool dispatch layer.
- [services/aicarmine_broker/job_store.py](job_store.py)
  - Job state and artifact persistence.
- [services/aicarmine_broker/public_wrapper.py](public_wrapper.py)
  - Public result packaging support.
- [services/aicarmine_broker/planner_intrinsic_context.py](planner_intrinsic_context.py)
  - Intrinsic planner context builder.
- [services/aicarmine_broker/code_edit_proposal_contract.py](code_edit_proposal_contract.py)
  - Report-only code edit proposal contract.
- [services/aicarmine_broker/memory_tools.py](memory_tools.py)
  - Runtime memory tool support.

## Current Folder Structure

- [app.py](app.py)
  - FastAPI route layer for health, job pages and `/vulkan/agent`.
- [agent_entry.py](agent_entry.py)
  - Job entrypoint and worker lifecycle.
- [planner.py](planner.py)
  - Main planner/controller loop and validation flow.
- [planner_intrinsic_context.py](planner_intrinsic_context.py)
  - Pre-turn intrinsic context builder.
- [planner_core/](planner_core/)
  - Planner cache and JSON transport helpers.
- [repo_tools.py](repo_tools.py)
  - Deterministic repo, terminal, validation and code-product tool implementations.
- [code_edit_proposal_contract.py](code_edit_proposal_contract.py)
  - Complete report-only code edit proposal payload contract.
- [tool_registry.py](tool_registry.py), [tool_dispatch.py](tool_dispatch.py), [tool_contract.py](tool_contract.py), [tool_selection.py](tool_selection.py)
  - Tool schema, dispatch, normalization and selection support.
- [job_store.py](job_store.py), [job_html.py](job_html.py)
  - Job persistence, dashboards and IA Live Control View rendering.
- [memory_tools.py](memory_tools.py)
  - Scratchpad, SQLite memory and prompt-window support.
