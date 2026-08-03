# codex_ollama_bridge_applied/codex_ollama_bridge

`codex_ollama_bridge_applied/codex_ollama_bridge/` contains the applied
Codex/Ollama bridge package, compatibility entrypoints and bridge-specific
documentation.

## Initial Reading Index

Start from these documents before changing runtime behavior:

- [AGENTS.md](../../AGENTS.md)
  - Workspace operating rules and non-negotiable runtime contract notes.
- [services/VALIDATOR_ONLY_AGENTIC_LOOP_CONTRACT.md](../../services/VALIDATOR_ONLY_AGENTIC_LOOP_CONTRACT.md)
  - Core validator/controller contract for the agentic loop.
- [services/END_TO_END_AGENTIC_FLOW.md](../../services/END_TO_END_AGENTIC_FLOW.md)
  - End-to-end flow between OpenWebUI, 3571, 3572, planner, tools, and final payload.
- [services/SERVICES_MODULE_TECHNICAL_REFERENCE.md](../../services/SERVICES_MODULE_TECHNICAL_REFERENCE.md)
  - Service-level technical map and module references.
- [services/MODULE_TECHNICAL_DESCRIPTIONS.md](../../services/MODULE_TECHNICAL_DESCRIPTIONS.md)
  - File-by-file technical descriptions for the `services/` tree.
- [services/CODEX_OPENWEBUI_PAYLOAD_LIMITATION.md](../../services/CODEX_OPENWEBUI_PAYLOAD_LIMITATION.md)
  - Operational limit for Codex when inspecting large OpenWebUI payloads.
- [services/aicarmine_broker/MODULE_REFERENCE.md](../../services/aicarmine_broker/MODULE_REFERENCE.md)
  - Broker module reference.
- [services/vulkan_bridge/MODULE_REFERENCE.md](../../services/vulkan_bridge/MODULE_REFERENCE.md)
  - Public bridge module reference.
- [services/codex_bridge/MODULE_REFERENCE.md](../../services/codex_bridge/MODULE_REFERENCE.md)
  - Codex bridge module reference.
- [services/codex_bridge/MCP_GUIDE.md](../../services/codex_bridge/MCP_GUIDE.md)
  - Codex MCP server/tool map, client JSON compatibility, confirmation gates
    and debug playbooks.
- [services/launch/MODULE_REFERENCE.md](../../services/launch/MODULE_REFERENCE.md)
  - Launch-script module reference.
- [services/model_export/MODULE_REFERENCE.md](../../services/model_export/MODULE_REFERENCE.md)
  - Model export module reference.

Core code entry points:

- [services/vulkan_bridge/app.py](../../services/vulkan_bridge/app.py)
  - Public OpenWebUI wrapper surface.
- [services/vulkan_bridge/agentic_v9.py](../../services/vulkan_bridge/agentic_v9.py)
  - Agentic bridge integration surface.
- [services/aicarmine_broker/app.py](../../services/aicarmine_broker/app.py)
  - Internal broker application.
- [services/aicarmine_broker/planner.py](../../services/aicarmine_broker/planner.py)
  - Planner/controller facade and high-risk loop entry; owner packages live under services/aicarmine_broker/application/.
- [services/aicarmine_broker/repo_tools.py](../../services/aicarmine_broker/repo_tools.py)
  - Compatibility facade for repo/tool helpers; concrete implementations live under services/aicarmine_broker/tools/.
- [services/aicarmine_broker/tool_registry.py](../../services/aicarmine_broker/tool_registry.py)
  - Internal tool registry.
- [services/aicarmine_broker/tool_dispatch.py](../../services/aicarmine_broker/tool_dispatch.py)
  - Compatibility facade for the explicit registry dispatcher in services/aicarmine_broker/application/tool_surface/dispatcher.py.
- [services/aicarmine_broker/job_store.py](../../services/aicarmine_broker/job_store.py)
  - Job state and artifact persistence.
- [services/aicarmine_broker/public_wrapper.py](../../services/aicarmine_broker/public_wrapper.py)
  - Public result packaging support.
- [services/aicarmine_broker/planner_intrinsic_context.py](../../services/aicarmine_broker/planner_intrinsic_context.py)
  - Intrinsic planner context builder.
- [services/aicarmine_broker/code_edit_proposal_contract.py](../../services/aicarmine_broker/code_edit_proposal_contract.py)
  - Report-only code edit proposal contract.
- [services/aicarmine_broker/memory_tools.py](../../services/aicarmine_broker/memory_tools.py)
  - Runtime memory tool support.

## Current Folder Structure

- [README-CODEX-OLLAMA-BRIDGE.md](README-CODEX-OLLAMA-BRIDGE.md)
  - Bridge-specific README.
- [APPLIED-MAPPING.md](APPLIED-MAPPING.md)
  - Applied bridge mapping.
- [aicarmine_codex_mcp_server.py](aicarmine_codex_mcp_server.py)
  - Applied MCP server entrypoint.
- [aicarmine_codex_ollama_responses_bridge.py](aicarmine_codex_ollama_responses_bridge.py)
  - Applied Responses bridge entrypoint.
- [codex.aicarmine-ollama.config.toml](codex.aicarmine-ollama.config.toml)
  - Codex/Ollama bridge config template.
- [start-codex-ollama-bridge.ps1](start-codex-ollama-bridge.ps1)
  - Bridge startup script.
