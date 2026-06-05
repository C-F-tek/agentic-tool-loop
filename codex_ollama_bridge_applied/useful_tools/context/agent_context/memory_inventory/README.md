# memory_inventory

`memory_inventory/` contains the CLI for rendering memory inventory reports.

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

Core code entry points:

- [services/vulkan_bridge/app.py](../../../../../services/vulkan_bridge/app.py)
  - Public OpenWebUI wrapper surface.
- [services/aicarmine_broker/planner.py](../../../../../services/aicarmine_broker/planner.py)
  - Planner/controller facade and high-risk loop entry; owner packages live under services/aicarmine_broker/application/.
- [services/aicarmine_broker/repo_tools.py](../../../../../services/aicarmine_broker/repo_tools.py)
  - Compatibility facade for repo/tool helpers; concrete implementations live under services/aicarmine_broker/tools/.
- [services/aicarmine_broker/memory_tools.py](../../../../../services/aicarmine_broker/memory_tools.py)
  - Runtime memory tool support.

## Current Folder Structure

- [cli.py](cli.py)
  - Memory inventory CLI.
- [__init__.py](__init__.py)
  - Package marker.
