# services/vulkan_bridge

`services/vulkan_bridge/` is the public 3571 OpenWebUI-facing bridge. It exposes
the `vulkan_helper` public tool, forwards work to 3572 and returns inline
model-usable terminal evidence.

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
- [services/vulkan_bridge/MODULE_REFERENCE.md](MODULE_REFERENCE.md)
  - Public bridge module reference.
- [services/codex_bridge/MODULE_REFERENCE.md](../codex_bridge/MODULE_REFERENCE.md)
  - Codex bridge module reference.
- [services/launch/MODULE_REFERENCE.md](../launch/MODULE_REFERENCE.md)
  - Launch-script module reference.
- [services/model_export/MODULE_REFERENCE.md](../model_export/MODULE_REFERENCE.md)
  - Model export module reference.

Core code entry points:

- [services/vulkan_bridge/app.py](app.py)
  - Public OpenWebUI wrapper surface.
- [services/vulkan_bridge/agentic_v9.py](agentic_v9.py)
  - Agentic bridge integration surface.
- [services/aicarmine_broker/app.py](../aicarmine_broker/app.py)
  - Internal broker application.
- [services/aicarmine_broker/planner.py](../aicarmine_broker/planner.py)
  - Planner/controller facade and high-risk loop entry; owner packages live under services/aicarmine_broker/application/.
- [services/aicarmine_broker/repo_tools.py](../aicarmine_broker/repo_tools.py)
  - Compatibility facade for repo/tool helpers; concrete implementations live under services/aicarmine_broker/tools/.
- [services/aicarmine_broker/tool_registry.py](../aicarmine_broker/tool_registry.py)
  - Internal tool registry.
- [services/aicarmine_broker/tool_dispatch.py](../aicarmine_broker/tool_dispatch.py)
  - Compatibility facade for the explicit registry dispatcher in services/aicarmine_broker/application/tool_surface/dispatcher.py.
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

- [app.py](app.py)
  - Main 3571 FastAPI app, forwarding logic and OpenWebUI response shaping.
- [agentic_v9.py](agentic_v9.py)
  - Compatibility facade for agentic v9 helpers.
- [client.py](client.py)
  - Compatibility facade for client/helper functions.
- [compact.py](compact.py)
  - Compatibility facade for compaction helpers.
- [MODULE_REFERENCE.md](MODULE_REFERENCE.md)
  - Detailed module contract and public result shape.

## Source Of Public Evidence

3571 must treat the terminal 3572 result as the source for OpenWebUI evidence.
It must not depend on the native planner `messages` that were sent to 11434
during the internal loop. Those messages are only planner working context and
may be budgeted/windowed.

For terminal responses, 3571 must use the structured terminal context and
rehydrated tool artifacts to build `tool_context_for_30b`. The public payload
must preserve successful tool results inline:

- `repo_read`: real file content in `artifact.content` when available.
- `repo_propose_code_edit`: complete `artifact.unified_diff` or
  `artifact.structured_operations`.
- command and listing tools: concrete stdout/stderr, paths, entries or counts
  produced by the successful tool.

`skipped_history_items` in planner-native message transport is not a public
payload source and is not an acceptable reason to omit successful artifacts from
3571. If final OpenWebUI evidence is incomplete, verify the 3572 persistent
`history` and raw `tool-results` rehydration path before changing the public
schema.
