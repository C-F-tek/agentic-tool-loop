# services/aicarmine_broker/planner_core

`services/aicarmine_broker/planner_core/` contains support modules for planner
cache handling and strict Ollama JSON transport. It supports the 3572 planner
loop but does not own planner policy or finalization.

## Initial Reading Index

Start from these documents before changing runtime behavior:

- [AGENTS.md](../../../AGENTS.md)
  - Workspace operating rules and non-negotiable runtime contract notes.
- [services/VALIDATOR_ONLY_AGENTIC_LOOP_CONTRACT.md](../../VALIDATOR_ONLY_AGENTIC_LOOP_CONTRACT.md)
  - Core validator/controller contract for the agentic loop.
- [services/END_TO_END_AGENTIC_FLOW.md](../../END_TO_END_AGENTIC_FLOW.md)
  - End-to-end flow between OpenWebUI, 3571, 3572, planner, tools, and final payload.
- [services/SERVICES_MODULE_TECHNICAL_REFERENCE.md](../../SERVICES_MODULE_TECHNICAL_REFERENCE.md)
  - Service-level technical map and module references.
- [services/MODULE_TECHNICAL_DESCRIPTIONS.md](../../MODULE_TECHNICAL_DESCRIPTIONS.md)
  - File-by-file technical descriptions for the `services/` tree.
- [services/CODEX_OPENWEBUI_PAYLOAD_LIMITATION.md](../../CODEX_OPENWEBUI_PAYLOAD_LIMITATION.md)
  - Operational limit for Codex when inspecting large OpenWebUI payloads.
- [services/aicarmine_broker/MODULE_REFERENCE.md](../MODULE_REFERENCE.md)
  - Broker module reference.
- [services/vulkan_bridge/MODULE_REFERENCE.md](../../vulkan_bridge/MODULE_REFERENCE.md)
  - Public bridge module reference.
- [services/codex_bridge/MODULE_REFERENCE.md](../../codex_bridge/MODULE_REFERENCE.md)
  - Codex bridge module reference.
- [services/codex_bridge/MCP_GUIDE.md](../../codex_bridge/MCP_GUIDE.md)
  - Codex MCP server/tool map, client JSON compatibility, confirmation gates
    and debug playbooks.
- [services/launch/MODULE_REFERENCE.md](../../launch/MODULE_REFERENCE.md)
  - Launch-script module reference.
- [services/model_export/MODULE_REFERENCE.md](../../model_export/MODULE_REFERENCE.md)
  - Model export module reference.

Core code entry points:

- [services/vulkan_bridge/app.py](../../vulkan_bridge/app.py)
  - Public OpenWebUI wrapper surface.
- [services/vulkan_bridge/agentic_v9.py](../../vulkan_bridge/agentic_v9.py)
  - Agentic bridge integration surface.
- [services/aicarmine_broker/app.py](../app.py)
  - Internal broker application.
- [services/aicarmine_broker/planner.py](../planner.py)
  - Planner/controller facade and high-risk loop entry; owner packages live under services/aicarmine_broker/application/.
- [services/aicarmine_broker/repo_tools.py](../repo_tools.py)
  - Compatibility facade for repo/tool helpers; concrete implementations live under services/aicarmine_broker/tools/.
- [services/aicarmine_broker/tool_registry.py](../tool_registry.py)
  - Internal tool registry.
- [services/aicarmine_broker/tool_dispatch.py](../tool_dispatch.py)
  - Compatibility facade for the explicit registry dispatcher in services/aicarmine_broker/application/tool_surface/dispatcher.py.
- [services/aicarmine_broker/job_store.py](../job_store.py)
  - Job state and artifact persistence.
- [services/aicarmine_broker/public_wrapper.py](../public_wrapper.py)
  - Public result packaging support.
- [services/aicarmine_broker/planner_intrinsic_context.py](../planner_intrinsic_context.py)
  - Intrinsic planner context builder.
- [services/aicarmine_broker/code_edit_proposal_contract.py](../code_edit_proposal_contract.py)
  - Report-only code edit proposal contract.
- [services/aicarmine_broker/memory_tools.py](../memory_tools.py)
  - Runtime memory tool support.

## Current Folder Structure

- [cache.py](cache.py)
  - Per-job cache helpers for read-only tool results and repair outcomes.
- [json_io.py](json_io.py)
  - Ollama HTTP streaming, response-header wait guarding, stream capture and
    strict planner JSON parsing.
- [__init__.py](__init__.py)
  - Package marker.

## Native Tool Calling Boundary

`planner_core/json_io.py` handles HTTP streaming and strict JSON parsing, but it
does not decide whether a planner tool call is valid. In the current planner
protocol:

- native Ollama `message.tool_calls` is the required transport for tool
  dispatch when native mode is enabled;
- strict JSON text parsing remains valid for `final` and `block` decisions;
- JSON text `action=tool` must not be treated as a dispatchable tool call in
  native-required mode;
- per-job cache helpers may reuse successful read-only tool results, but do not
  create new planner decisions and do not replace validator checks.

Any change in this subpackage must preserve that boundary: transport/parsing
support belongs here; planner policy, validator gates, native provenance checks
and finalization remain owned by `planner.py`.

## Streaming Header Wait Guard

`post_json_stream_to_file()` owns both phases of planner streaming:

- awaiting HTTP response headers from Ollama;
- reading streamed token lines after headers arrive.

A zero-byte `step-*.txt` with `planner_stream_started` but no token progress
means the loop is blocked before streaming lines exist, during the header wait
phase. The expected behavior is to emit `planner_stream_waiting` while waiting
and return a typed `PlannerStreamHeaderTimeout` with
`timeout_phase=awaiting_response_headers` if Ollama does not return headers in
time. Readline deadlines alone are insufficient for this failure mode.
