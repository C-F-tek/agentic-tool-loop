# services

`services/` is the main runtime surface for the local OpenWebUI agentic tool
loop. It contains the public bridge, internal broker, launcher modules, model
export helpers, Codex bridge helpers, operational scripts and contract
documentation.

## Current Verified Runtime Highlights

As of 2026-06-15, the active 3572 loop uses these model-assisted lanes without
changing the validator-only contract:

- `controller_preplanner_rag_query_plan` runs before the first 11434 planner
  turn and may repair malformed JSON with the same planner model. If the model
  times out or is unavailable, that is recorded as typed diagnostics and the
  controller continues only with deterministic preseed evidence.
- `repo_analysis_final_answer_model_quality` is the final-quality judge for
  repository and semantic-audit finals. It can repair malformed judge JSON and
  can route a final back to `repo_read`, `repo_semantic_search` or a typed
  rejection; the controller still only validates and records the route.
- `planner_replan_specialist_for_validation` is called for selected validator
  rejections, including code-product/support-subturn loops. It can now repair
  malformed specialist JSON before returning the next required planner route.
- `vulkan_repair_invalid_planner_decision` on 11435 is limited to malformed
  planner emissions or invalid non-code-product tool proposals. It is not used
  to hide code-product contract failures such as missing complete diffs.
- `planner_core/json_io.py` guards the wait for HTTP response headers before
  streaming frames, so a stuck `urlopen()` produces visible timeout events
  instead of a silent zero-byte stream.

Public payload materialization is pointer-first: complete tool payloads live in
`tool_context_for_30b.artifacts[*].artifact`; priority evidence and payload
index sections point to those payloads instead of duplicating large content.

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
  - Planner/controller facade and high-risk loop entry; owner packages live under services/aicarmine_broker/application/.
- [services/aicarmine_broker/repo_tools.py](aicarmine_broker/repo_tools.py)
  - Compatibility facade for repo/tool helpers; concrete implementations live under services/aicarmine_broker/tools/.
- [services/aicarmine_broker/tool_registry.py](aicarmine_broker/tool_registry.py)
  - Internal tool registry.
- [services/aicarmine_broker/tool_dispatch.py](aicarmine_broker/tool_dispatch.py)
  - Compatibility facade for the explicit registry dispatcher in services/aicarmine_broker/application/tool_surface/dispatcher.py.
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
  - Optional Codex-facing MCP and Responses-compatible bridge helpers. These
    are host-side Codex integrations, not 3571 OpenWebUI tools and not 3572
    planner-native tools.
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

## Planner Context Vs 3571 Payload

The runtime has two different context surfaces:

- `3572 -> 11434` planner context: native tool-call `messages`, prompt windows
  and SQLite-backed prompt context are internal working context. They can be
  budgeted and windowed for the next planner decision. If this transport skips
  required history, the bug is inside planner routing/context construction.
- Native planner tool dispatch requires Ollama `message.tool_calls`; text JSON
  `action=tool` is invalid when native mode is required. Text JSON `final` and
  `block` remain valid non-tool decisions.
- `3572/3571 -> OpenWebUI` terminal payload: `tool_context_for_30b` is built
  from persistent job `history` and raw `tool-results` artifacts, then returned
  inline by 3571. It must remain complete for successful tool evidence and must
  not depend on how much prior history fit into the native planner messages.

Do not use local paths, SQLite ids, planner message windows or
`skipped_history_items` diagnostics as substitutes for the public payload. For
terminal OpenWebUI results, successful `repo_read` content and successful
`repo_propose_code_edit` diffs/operations must be present as concrete inline
artifacts in `tool_context_for_30b`.

## Codex MCP Boundary

Codex MCP servers under `codex_bridge/` are outside the OpenWebUI -> 3571 ->
3572 agentic chain. `mcp_server.py` exposes host-side Codex tools over stdio
without calling 3571, `/vulkan/agent` or the HTTP broker tool loop.
For broker-backed tool imports, the MCP process resolves its own Codex root
from `AICARMINE_CODEX_MCP_REPO_ROOT`, Codex workspace env or cwd, then rewrites
only that process' `AICARMINE_LAB_REPO` before import-time broker config is
read. The OpenWebUI/3572 lab shadow does not need to match the Codex repo root.
`rag_mcp_server.py` is a separate retrieval server backed by the Codex RAG
SQLite index and the local OVMS reranker. `repo_code_mcp_server.py` is a
separate incubator for candidate code-edit tools; it keeps proposal/diff-check
tools report-only and requires `allow_source_write=true` before exact source
patching. `ops_mcp_server.py` is a separate incubator for Codex-side MCP
inventory and read-only service-state inspection; it does not probe HTTP health
routes or call 3571/3572. None of these servers adds planner-native tool names
to the 3572 turn surface.

## Test/Smoke Guardrail

Test files, smoke scripts and macro runtime test surfaces are not part of the
active operating contract. Do not create, restore, run or document test/smoke
flows unless Carmine explicitly asks for them. Use concrete runtime evidence,
artifact reads, process/port/log inspection, payload inspection, compile/lint
or diff checks as targeted verification instead. If Carmine reports evidence
from a real run, that evidence is primary and must not be overruled by local
scripts.
