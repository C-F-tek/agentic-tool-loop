# services/codex_bridge

`services/codex_bridge/` contains optional Codex-facing bridge helpers. It is
not the public OpenWebUI 3571 bridge and not the 3572 planner runtime.

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
- [services/aicarmine_broker/MODULE_REFERENCE.md](../aicarmine_broker/MODULE_REFERENCE.md)
  - Broker module reference.
- [services/vulkan_bridge/MODULE_REFERENCE.md](../vulkan_bridge/MODULE_REFERENCE.md)
  - Public bridge module reference.
- [services/codex_bridge/MODULE_REFERENCE.md](MODULE_REFERENCE.md)
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
- [services/aicarmine_broker/app.py](../aicarmine_broker/app.py)
  - Internal broker application.
- [services/aicarmine_broker/planner.py](../aicarmine_broker/planner.py)
  - Planner/controller facade and high-risk loop entry; owner modules live under application/.
- [services/aicarmine_broker/repo_tools.py](../aicarmine_broker/repo_tools.py)
  - Compatibility facade for repo/tool helpers; concrete implementations live under services/aicarmine_broker/tools/.
- [services/aicarmine_broker/tool_registry.py](../aicarmine_broker/tool_registry.py)
  - Internal tool registry.
- [services/aicarmine_broker/tool_dispatch.py](../aicarmine_broker/tool_dispatch.py)
  - Compatibility facade for the explicit registry dispatcher in application/tool_surface/dispatcher.py.
- [services/aicarmine_broker/job_store.py](../aicarmine_broker/job_store.py)
  - Job state and artifact persistence.
- [services/aicarmine_broker/public_wrapper.py](../aicarmine_broker/public_wrapper.py)
  - Public result packaging support.
- [services/aicarmine_broker/planner_intrinsic_context.py](../aicarmine_broker/planner_intrinsic_context.py)
  - Intrinsic planner context builder.
- [services/aicarmine_broker/code_edit_proposal_contract.py](../aicarmine_broker/code_edit_proposal_contract.py)
  - Report-only code edit proposal contract.
- [services/aicarmine_broker/memory_tools.py](../aicarmine_broker/memory_tools.py)
  - Runtime memory tool support.

## Current Folder Structure

- [mcp_server.py](mcp_server.py)
  - JSON-RPC/MCP server implementation for Codex integration.
- [ollama_responses_bridge.py](ollama_responses_bridge.py)
  - OpenAI Responses-compatible adapter around Ollama.
- [jsonrpc.py](jsonrpc.py), [responses_proxy.py](responses_proxy.py), [storage.py](storage.py)
  - Compatibility facades for historical import paths.
- [MODULE_REFERENCE.md](MODULE_REFERENCE.md)
  - Detailed module reference.
