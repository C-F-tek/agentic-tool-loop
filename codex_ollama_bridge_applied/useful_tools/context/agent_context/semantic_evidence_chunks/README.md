# semantic_evidence_chunks

`semantic_evidence_chunks/` contains semantic evidence chunking, rendering,
selection and summary helpers.

## Initial Reading Index

Start from these documents before changing runtime behavior:

- [AGENTS.md](../../../../../AGENTS.md)
  - Workspace operating rules and non-negotiable runtime contract notes.
- [services/VALIDATOR_ONLY_AGENTIC_LOOP_CONTRACT.md](../../../../../services/VALIDATOR_ONLY_AGENTIC_LOOP_CONTRACT.md)
  - Core validator/controller contract for the agentic loop.
- [services/END_TO_END_AGENTIC_FLOW.md](../../../../../services/END_TO_END_AGENTIC_FLOW.md)
  - End-to-end flow between OpenWebUI, 3571, 3572, planner, tools, and final payload.
- [services/SERVICES_MODULE_TECHNICAL_REFERENCE.md](../../../../../services/SERVICES_MODULE_TECHNICAL_REFERENCE.md)
  - Service-level technical map and module references.
- [services/MODULE_TECHNICAL_DESCRIPTIONS.md](../../../../../services/MODULE_TECHNICAL_DESCRIPTIONS.md)
  - File-by-file technical descriptions for the `services/` tree.
- [services/CODEX_OPENWEBUI_PAYLOAD_LIMITATION.md](../../../../../services/CODEX_OPENWEBUI_PAYLOAD_LIMITATION.md)
  - Operational limit for Codex when inspecting large OpenWebUI payloads.
- [services/aicarmine_broker/MODULE_REFERENCE.md](../../../../../services/aicarmine_broker/MODULE_REFERENCE.md)
  - Broker module reference.
- [services/vulkan_bridge/MODULE_REFERENCE.md](../../../../../services/vulkan_bridge/MODULE_REFERENCE.md)
  - Public bridge module reference.
- [services/codex_bridge/MODULE_REFERENCE.md](../../../../../services/codex_bridge/MODULE_REFERENCE.md)
  - Codex bridge module reference.
- [services/launch/MODULE_REFERENCE.md](../../../../../services/launch/MODULE_REFERENCE.md)
  - Launch-script module reference.
- [services/model_export/MODULE_REFERENCE.md](../../../../../services/model_export/MODULE_REFERENCE.md)
  - Model export module reference.

Core code entry points:

- [services/vulkan_bridge/app.py](../../../../../services/vulkan_bridge/app.py)
  - Public OpenWebUI wrapper surface.
- [services/vulkan_bridge/agentic_v9.py](../../../../../services/vulkan_bridge/agentic_v9.py)
  - Agentic bridge integration surface.
- [services/aicarmine_broker/app.py](../../../../../services/aicarmine_broker/app.py)
  - Internal broker application.
- [services/aicarmine_broker/planner.py](../../../../../services/aicarmine_broker/planner.py)
  - Planner/controller contract and validation loop.
- [services/aicarmine_broker/repo_tools.py](../../../../../services/aicarmine_broker/repo_tools.py)
  - Repository inspection, command, validation, and code-product tool implementations.
- [services/aicarmine_broker/tool_registry.py](../../../../../services/aicarmine_broker/tool_registry.py)
  - Internal tool registry.
- [services/aicarmine_broker/tool_dispatch.py](../../../../../services/aicarmine_broker/tool_dispatch.py)
  - Tool dispatch layer.
- [services/aicarmine_broker/job_store.py](../../../../../services/aicarmine_broker/job_store.py)
  - Job state and artifact persistence.
- [services/aicarmine_broker/public_wrapper.py](../../../../../services/aicarmine_broker/public_wrapper.py)
  - Public result packaging support.
- [services/aicarmine_broker/planner_intrinsic_context.py](../../../../../services/aicarmine_broker/planner_intrinsic_context.py)
  - Intrinsic planner context builder.
- [services/aicarmine_broker/code_edit_proposal_contract.py](../../../../../services/aicarmine_broker/code_edit_proposal_contract.py)
  - Report-only code edit proposal contract.
- [services/aicarmine_broker/memory_tools.py](../../../../../services/aicarmine_broker/memory_tools.py)
  - Runtime memory tool support.

## Current Folder Structure

- [chunker.py](chunker.py), [sections.py](sections.py), [summary.py](summary.py)
  - Chunking, section and summary helpers.
- [render.py](render.py), [archive.py](archive.py), [live_source.py](live_source.py)
  - Rendering, archive and live-source helpers.
- [select_code_chunks/](select_code_chunks/)
  - Code chunk selection CLI package.
- [cli.py](cli.py), [common.py](common.py)
  - CLI and shared utilities.
