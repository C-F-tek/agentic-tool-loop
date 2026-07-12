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
- [services/codex_bridge/MCP_GUIDE.md](../codex_bridge/MCP_GUIDE.md)
  - Codex MCP server/tool map, client JSON compatibility, confirmation gates
    and debug playbooks.
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
  - Planner/controller facade and high-risk loop entry; owner packages live under services/aicarmine_broker/application/.
- [services/aicarmine_broker/repo_tools.py](repo_tools.py)
  - Compatibility facade for repo/tool helpers; concrete implementations live under services/aicarmine_broker/tools/.
- [services/aicarmine_broker/tool_registry.py](tool_registry.py)
  - Internal tool registry.
- [services/aicarmine_broker/tool_dispatch.py](tool_dispatch.py)
  - Compatibility facade for the explicit registry dispatcher in services/aicarmine_broker/application/tool_surface/dispatcher.py.
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
- [job_planner_lab.py](job_planner_lab.py)
  - Operator-only chat plus step-summary lab for inspecting the actual
    OpenWebUI-bound payload, extracting code-product candidates and handing
    exact old/new text patches to `repo_apply_patch` with explicit confirmation.
    It is also the payload-calibration view for redundant narrative fields:
    `evidence_guide_for_30b` is the single global guide, while
    `tool_context_for_30b` must stay structured evidence/context rather than a
    duplicate answer/message/summary/content surface.
- [memory_tools.py](memory_tools.py)
  - Scratchpad, SQLite memory and prompt-window support.

## Current Planner Guidance Lanes

The 3572 loop remains planner-led and validator-gated. Specialist model calls
are guidance lanes, not controller replacements:

- Preplanner/RAG query planning may propose search/read orientation before the
  planner turn. If its JSON is malformed, the owner path is model JSON repair
  or bounded fallback metadata, not a hard stop that replaces the planner.
- Final-quality/judge evaluation is the semantic check for attempted finals.
  It should accept, reject or redirect the planner after a final request; the
  controller must not synthesize a final answer on its own.
- Replan/repair specialists are used after validator feedback or malformed
  planner emissions. They return strict JSON decisions or diagnostics that are
  fed back into the normal loop.
- Vulkan/GPU0 repair is limited to explicit malformed planner emissions. It is
  not a semantic patch generator and not a hidden controller fallback.

When debugging these lanes, verify the job events and owner artifacts first:
preplanner events, final-quality/judge results, validator rejection summaries,
repair attempts and the next planner payload. A missing specialist call is a
flow bug only after the triggering condition is confirmed in the persisted job.

## Persistent History Vs Planner Messages

`aicarmine_broker` owns the internal 3572 loop and must keep two records
separate:

- Planner messages: when native tool calling is enabled, prior tool calls and
  tool results can be transported to 11434 through Ollama `messages`. This is a
  budgeted working-context surface for the next planner decision. It may use
  SQLite windows and can report `skipped_history_items`; skipped items mean the
  planner may lack working history for that turn.
- Persistent job history: every executed internal tool result must be written
  to a raw `tool-results/*.json` artifact and appended to the in-memory/job
  `history`. This is the authoritative record used by finalization.

The final OpenWebUI payload must be reconstructible from persistent job
history, not from native planner messages. A native tool-call turn that omits
an item from `messages` must not delete, replace or weaken the persistent
`history` entry. For code-product work, each successful
`repo_propose_code_edit` must keep its complete `unified_diff` or
`structured_operations` available through the history/artifact rehydration path,
even when many files are involved.

If a regression is suspected, test the two surfaces separately: inspect the
planner prompt capture for native message loss, then inspect final
`tool_context_for_30b.artifacts` for complete public reconstruction.

## Public Payload Materialization

The canonical complete public payload is
`tool_context_for_30b.artifacts[*].artifact`. `priority_evidence_for_30b`,
`payload_index_for_30b` and `evidence_guide_for_30b` are navigation and guide
surfaces over that canonical artifact set; they must not reintroduce large
duplicate `content`, `unified_diff` or `structured_operations` copies.

For completed and non-completed terminal states, preserve successful concrete
tool artifacts in the persistent history and expose pointers/metadata that
resolve back to `tool_context_for_30b`. Local job paths, raw `reads/*.json`,
SQLite document ids and previews are operator diagnostics, not model-usable
evidence.
