<!-- AICARMINE_NON_NEGOTIABLE_CONTRACT_START -->
Regole operative non negoziabili:
1. Il contratto non va modificato se non richiesto da Carmine esplicitamente.
2. Il prodotto finale puo' essere arricchito come gia' viene fatto; non cambiare logica senza richiesta esplicita.
3. Non devi presupporre nulla: non e' il tuo compito.
<!-- AICARMINE_NON_NEGOTIABLE_CONTRACT_END -->
# Module Technical Descriptions

Updated: 2026-06-15

This file is the detailed per-module technical reference for
`C:\Users\carmi\AI\services`. It complements the higher-level maps:

- `SERVICES_MODULE_TECHNICAL_REFERENCE.md`
- `RUNTIME_SCRIPT_REFERENCE.md`
- package-level `MODULE_REFERENCE.md` files

Generated/runtime areas are intentionally excluded: `.venv`, `openwebui-data`,
`BCKUP`, `__pycache__`, job workspaces and uploads.

## Reading Order For Future Changes

1. `C:\Users\carmi\AI\AGENTS.md`
2. `services/VALIDATOR_ONLY_AGENTIC_LOOP_CONTRACT.md`
3. `services/SERVICES_MODULE_TECHNICAL_REFERENCE.md`
4. `services/END_TO_END_AGENTIC_FLOW.md`
5. This file
6. Package `MODULE_REFERENCE.md` for the module being edited

## Top-Level Python Modules

### `aicarmine-executor-server.py`

FastAPI service for guarded command execution. It defines request models for
direct command execution and file-backed payload execution, validates bearer
auth when `AICARMINE_EXECUTOR_TOKEN` is set, resolves payload files under the
configured payload root and delegates actual command execution to
`aicarmine-run-safe-command.ps1`.

- Reads: `AI_ROOT`, `AICARMINE_SAFE_COMMAND_RUNNER`,
  `AICARMINE_EXECUTOR_TOKEN`, payload-root env.
- Exposes: `/health`, `/run`, `/payload_health`, `/run_payload_file`.
- Writes: none directly except through the delegated runner command.
- Risk: security boundary. Do not bypass auth, payload-root validation,
  timeout limits or runner delegation.
- Verify: call `/health`, then a harmless `/run` with explicit timeout and repo
  mode.

### `aicarmine-openwebui-serve.py`

OpenWebUI boot wrapper. It normalizes integer/float/bool environment values,
creates required boot secrets/defaults and starts the OpenWebUI application
inside the OpenWebUI venv.

- Reads: OpenWebUI data/cache/secret and keepalive env values.
- Exposes: OpenWebUI ASGI app through the launcher, not AI-Carmine tool routes.
- Writes: environment defaults during boot.
- Risk: must stay in the OpenWebUI venv. Do not start 3571/3572 services from
  this module.
- Verify: confirm process command line uses `venvs\openwebui`.

### `aicarmine_vulkan_bridge_server.py`

Compatibility uvicorn target for the 3571 public bridge. It imports
`vulkan_bridge.app:app` under the historical module name used by launchers and
process-match cleanup.

- Reads: implementation from `vulkan_bridge.app`.
- Exposes: the 3571 FastAPI app.
- Writes: none.
- Risk: import path stability. Do not move behavior here.
- Verify: launcher command line still contains this import target.

### `aicarmine_vulkan_tool_broker.py`

Compatibility uvicorn target for the 3572 broker/runtime. It imports
`aicarmine_broker.app:app` under the historical module name.

- Reads: implementation from `aicarmine_broker.app`.
- Exposes: the 3572 FastAPI app.
- Writes: none.
- Risk: import path stability. Do not move behavior here.
- Verify: launcher command line still contains this import target.

### `aicarmine_codex_mcp_server.py`

Historical wrapper for `codex_bridge.mcp_server`. It keeps existing command
paths working for Codex MCP startup.

- Reads: `codex_bridge.mcp_server`.
- Exposes: MCP stdio server when executed.
- Writes: only what the delegated module writes.
- Risk: should stay a thin wrapper.
- Verify: import/execute path resolves to the package module.

### `aicarmine_codex_ollama_responses_bridge.py`

Historical wrapper for `codex_bridge.ollama_responses_bridge`. It keeps old
startup paths for the Ollama/OpenAI Responses-compatible HTTP bridge.

- Reads: `codex_bridge.ollama_responses_bridge`.
- Exposes: delegated FastAPI app/CLI behavior.
- Writes: only delegated response-state storage.
- Risk: should stay a thin wrapper.
- Verify: import path resolves to the package module.

### `export_model.py`

Compatibility CLI wrapper for `model_export.cli`. It uses package execution so
older scripts can keep invoking the top-level file.

- Reads: `model_export.cli`.
- Exposes: export CLI.
- Writes: model/export outputs through delegated CLI.
- Risk: do not add export logic here; update `model_export/cli.py`.
- Verify: CLI help and intended exporter branch.

### `apply_openwebui_ps1_open_terminal.py`

Patch utility for OpenWebUI PowerShell scripts and zip packages. It detects old
Jupyter launch lines, inserts Open Terminal blocks and preserves encoding where
possible.

- Reads: root directories, `.ps1` text, optional zip archives.
- Writes: patched `.ps1` files or generated zip outputs.
- Risk: text patching is structure-sensitive. Verify diff before using patched
  launcher artifacts.
- Verify: run against a copy or inspect generated patch results.

## aicarmine_broker Modules

### `aicarmine_broker/__init__.py`

Package marker and compatibility import surface for the 3572 package.

- Reads: package app surface.
- Writes: none.
- Risk: import side effects can affect uvicorn startup.
- Verify: simple package import.

### `aicarmine_broker/app.py`

3572 FastAPI route layer. It registers the job dashboard, job JSON/event/final
artifact routes, health and `/vulkan/agent`. It delegates job creation to
`agent_entry`, state/event reads to `job_store` and HTML rendering to
`job_html`.

- Reads: job state, event logs, final JSON/MD through `job_store`.
- Exposes: 3572 HTTP routes consumed by 3571 and browser dashboards.
- Writes: only through delegated job lifecycle calls.
- Risk: route shape is part of the 3571/3572 protocol.
- Verify: `/health`, `/jobs.json`, specific `/jobs/{id}/json` for a known job.

### `aicarmine_broker/agent_entry.py`

Agent job entrypoint and worker lifecycle. It normalizes public request payloads,
creates job IDs/state, starts background worker execution and calls
`run_agentic_planner_job`.

- Reads: public tool name, original args, selected task, config.
- Writes: queued/started/finished state and events through `job_store`.
- Risk: should not short-circuit planner/controller finalization.
- Verify: new job transitions from queued to running to terminal status.

### `aicarmine_broker/config/`

Central runtime configuration package. `models.py` parses booleans, integers,
floats, multiple env aliases, planner/tool lists and Ollama options into
`BrokerConfig`; `compatibility.py` exposes the legacy constants imported as
`aicarmine_broker.config`.

- Reads: `AICARMINE_*` env and model/runtime env values.
- Exposes: constants and helper functions used by planner, dispatcher and
  launcher-facing services, including planner `num_ctx`, intrinsic-context
  budgets, prompt compaction ratio, optional `AICARMINE_PLANNER_RAG_DB` and
  external RAG reranker settings.
- Writes: none.
- Risk: env defaults affect live behavior only after process restart unless
  code reads env dynamically.
- Verify: inspect running process env, not only user env or file values.

### Removed: `aicarmine_broker/dispatcher.py`

The old compatibility facade was removed after the broker app and tests moved
to real owners. HTTP routing imports `agent_entry` directly, while validated
tool dispatch remains in `tool_dispatch.py` and
`application/tool_surface/dispatcher.py`.

- Reads: none.
- Writes: none.
- Risk: reintroducing this file creates duplicate import paths.
- Verify: no imports of `aicarmine_broker.dispatcher` remain.

### `aicarmine_broker/helper.py`

Composite helper and evidence assembly support. It derives helper text, search
queries, changed files, review docs, verified problem evidence, patch targets,
next calls and helper summaries. It also implements `vulkan_helper` on the 3572
side.

- Reads: repo status/search/read outputs and docs in the target repo.
- Writes: no direct source writes unless delegated to tools.
- Risk: summary must not replace successful tool evidence required by 3571.
- Verify: helper output includes useful evidence and does not expose local JSON
  artifact paths as content.

### `aicarmine_broker/job_html.py`

Human-facing HTML renderer for an agent job page.

- Reads: job state and event data.
- Writes: none.
- Risk: display-only. Do not put state transitions here.
- Verify: browser job page renders after job terminal state.

### `aicarmine_broker/job_store.py`

Persistence layer for agent jobs. It creates job IDs, writes/reads JSON state,
maintains SQLite metadata, appends NDJSON events, computes compact digests and
waits for terminal job state.

- Reads: job DB, state JSON, events NDJSON, final files.
- Writes: job DB, state JSON, event logs, final response artifacts.
- Risk: schema/state fields are consumed by 3571 and dashboards.
- Verify: state JSON, events NDJSON and DB row agree for the same job ID.

### `aicarmine_broker/application/public_payload/evidence_materializer.py`

Broker-side public evidence materializer for OpenWebUI terminal payloads. It
selects concrete inline artifacts already present in `tool_context_for_30b`,
promotes complete repo reads and code-edit proposals into
`priority_evidence_for_30b`, builds non-duplicating `payload_index_for_30b`
pointers and emits `materialization_report owner=3572_broker`.

- Reads: inline `tool_context_for_30b` dictionaries produced by broker public
  payload builders.
- Writes: no files; returns JSON-serializable public payload sections.
- Risk: must not read local paths, duplicate large payload into the index, alter
  validator/finalization gates or hide missing inline evidence.
- Verify: inspect inline public payload fields and materialization reports.

### `aicarmine_broker/application/public_payload/payload_index_resolver.py`

Pure resolver for broker public payload-index field paths. It verifies whether
`payload_index_for_30b` references resolve to present and non-empty inline JSON
fields, including paths inside `tool_context_for_30b.artifacts[*].artifact`.

- Reads: in-memory public payload dictionaries only.
- Writes: none.
- Risk: resolver drift from the bridge resolver can create contradictory lint
  reports. Keep path grammar aligned.
- Verify: inspect materializer reports and bridge payload-index resolution
  against concrete payloads.

### `aicarmine_broker/memory_tools.py`

 Planner scratchpad and SQLite memory tools. It supports scratchpad read/write,
runtime memory write/search/cleanup, planner memory surface generation, the
job-local answer composer and SQLite-backed prompt-context windows used only by
the planner prompt pack.

- Reads: scratchpad JSON, memory SQLite DBs and job-local
  `planner_composer.sqlite` prompt-context documents.
- Writes: scratchpad JSON, memory SQLite rows, answer chunks and full
  prompt-context documents with small real text windows.
- Risk: memory is context, not proof for finalization gates. Prompt windows are
  for 11434 planner context only and must not replace full successful tool
  payloads in `tool_context_for_30b`.
- Verify: memory search returns rows without polluting tool evidence;
  `planner_scratchpad_read(kind=prompt_context_window, document_id, offset)`
  returns real text windows with offsets and hashes.

### `aicarmine_broker/planner.py`

Main controlled planner loop. It normalizes planner decisions, compacts tool
results for model context, builds intrinsic pre-turn context, builds history
ledgers, records Ollama turns, expands
successful tool artifacts, validates finalization, calls final-quality and
replan guidance lanes, handles repair, dispatches tools and writes terminal job
state. It also separates code-product intent from apply intent:
diff/refactoring/code-product goals require a successful
`repo_propose_code_edit` proposal, while apply/edit/fix/write goals still
require `repo_apply_patch`. Its planner prompt pack measures the exact
serialized prompt and, above the configured compaction threshold, moves large
file/diff/history/result sections into job-local SQLite prompt documents and
injects only small real windows that the planner can read recursively.

Planner-adjacent model lanes are explicit:

- preplanner RAG query-plan wiring calls `application/controller/rag_preseed.py`
  before the first turn and keeps timeout/unavailability non-blocking;
- final-quality judge wiring calls
  `application/evidence/final_quality.py` request builders for repo and
  semantic-audit finals, then routes any `continue_required` result through the
  validator contract;
- planner replan specialist wiring handles selected validator rejections and
  repairs malformed specialist JSON before updating the next required route;
- Vulkan/GPU0 repair on 11435 is limited to malformed planner emissions or
  invalid non-code-product tool proposals and must not mask code-product
  contract failures.

- Reads: config, job history, tool registry/dispatch, Ollama responses,
  successful tool artifacts.
- Writes: job state, event stream, final JSON/MD, planner stream files.
- Risk: highest-risk file. Do not change model, ctx, max steps, launcher or
  validator flow without direct evidence. Do not route semantic
  `repo_propose_code_edit` contract failures to GPU0/11435 repair. Prompt
  compaction must remain internal to 11434 planner calls and must not degrade
  OpenWebUI `tool_context_for_30b`. Do not patch this module from intuition:
  confirm the owner, active process and runtime artifact first.
- Verify: real job events show planner step, decision, tool result, turn memory
  and terminal status in expected order; code-product jobs show
  `repo_read -> repo_propose_code_edit -> final`, with no `repo_apply_patch`
  unless the goal asked to apply. Prompt events expose requested/capped/effective
  `num_ctx`, exact prompt chars, compact mode and required working-set chars.

### `aicarmine_broker/planner_intrinsic_context.py`

Internal pre-turn context builder for the 11434 planner payload. It consumes the
controller-injected memory surface and optional `rag.sqlite`/FTS5 chunks, can
rerank those chunks through the configured external RAG reranker using the same
bounded parser/payload shape as the Codex RAG MCP path, then returns bounded
`schema=planner_intrinsic_context.v1` context with goal classification,
retrieved memory, retrieved RAG chunks, repo-map summary, failure patterns, tool
purpose manifest and budget report.

- Reads: planner memory surface and optional `AICARMINE_PLANNER_RAG_DB`
  (`rag_chunks` plus `rag_chunks_fts`) in SQLite read-only mode; optional
  `RAG_EXTERNAL_RERANKER_URL` when `RAG_RERANKING_ENGINE=external`.
- Rerank bounds: FTS candidate pool default `80`, reranker input default `12`,
  document cap `2500` chars and default timeout `30.0` seconds. Metadata
  separates `candidate_count` from reranker `input_count`.
- Writes: none.
- Risk: must not become a planner-selectable tool, must not import lab runtime
  modules and must not hide missing DB/schema or unavailable reranker with
  heuristic content.
- Verify: payload includes `intrinsic_context`, `budget_report.num_ctx_effective`
  and typed RAG/rerank status; `PLANNER_INTERNAL_TOOLS` has no
  RAG/chunk/intrinsic tool additions.

### `aicarmine_broker/application/controller/rag_preseed.py`

Controller-owned preseed and preplanner query-plan module. It performs
deterministic initial repo orientation and, when useful, asks the 11434 planner
model for a bounded RAG query/path plan before the first planner turn. It
validates semantic intent, repairs malformed query-plan JSON through the same
planner model and records typed non-blocking fallback metadata when the backend
times out or is unavailable.

- Reads: goal text, repo/preseed surfaces, injected planner model response and
  optional reranker/index diagnostics.
- Writes: no source files; returns JSON-serializable preseed/query-plan
  payloads to the loop.
- Risk: must not become a hidden deterministic planner or auto-finalizer.
  Timeout/unavailable query planning can only reduce semantic preplanner
  guidance to deterministic preseed; it cannot authorize invented paths or
  broad uncontrolled repo reads.
- Verify: events include `controller_preplanner_rag_query_plan_result` with
  `status=ready` or typed unavailable/invalid diagnostics and the job still
  proceeds through normal planner turns.

### `aicarmine_broker/application/evidence/final_quality.py`

Evidence-owned final-quality checks and model judge request builder. It
combines deterministic red flags with a structured model request for
repo-analysis and semantic-audit finals. The actual 11434 call and malformed
JSON repair are wired by `planner.py`; this module owns the bounded request
shape, role guidance and route vocabulary.

- Reads: final answer text, evidence contract, goal/audit guidance.
- Writes: none.
- Risk: judge output is guidance for validator routing, not a controller
  finalizer. It can request `repo_read`, `repo_semantic_search` or a typed
  rejection, but the planner must still produce the next accepted action.
- Verify: validator evidence contract contains
  `repo_analysis_final_quality` for repo/semantic-audit finals and violations
  include final-quality route reasons when the judge rejects.

### `aicarmine_broker/application/evidence/required_working_set.py`

Required working-set builder for planner prompt content. It collects concrete
file, diff and tool-result windows needed for the next planner decision,
rehydrates same-job repo-read/code-product artifacts through injected helpers
and stores oversized windows through injected prompt-window storage.

- Reads: planner history, evidence contract, file memory and injected artifact
  rehydration callbacks.
- Writes: no files directly; prompt-window storage is injected by the caller.
- Risk: must never replace required text/diff evidence with path-only metadata.
  It can bound item counts/window chars for the planner prompt, but public
  OpenWebUI payload completeness is handled elsewhere.
- Verify: working-set entries include concrete text/diff windows with offsets,
  chars and hashes, not only `artifact` paths.

### `aicarmine_broker/application/prompt/pack_builder.py`

Measured prompt-pack builder for one 11434 planner turn. It combines the
required working set, optional intrinsic context, history messages, available
tool windows and budget reports. It performs hard-budget compaction by moving
large sections into job-local SQLite prompt windows and exposing real bounded
windows to the planner.

- Reads: runtime prompt config, required working set, optional context and
  history.
- Writes: prompt-window documents through injected storage only.
- Risk: compaction is only for planner input. It must not remove successful
  tool payloads from `tool_context_for_30b` or make local SQLite ids part of
  the public evidence contract.
- Verify: planner prompt captures show `prompt_budget_report`,
  `required_working_set`, optional-context omission/window diagnostics and
  recursive `planner_prompt_context_window.v1` references when needed.

### `aicarmine_broker/public_wrapper.py`

Deterministic public wrapper helpers for result summaries and selector failure
messages.

- Reads: tool result payloads.
- Writes: none.
- Risk: should remain pure and deterministic.
- Verify: same input produces same wrapper text.

### `aicarmine_broker/repo_tools.py`

Compatibility facade for deterministic repo and terminal operations. Concrete
tool behavior now lives under `aicarmine_broker/tools/`: repo
tree/list/search/read, report-only code edit proposals, patch/write/validate,
command classification, compile target resolution, terminal path normalization
and readonly command repair.

- Reads: lab/main repo filesystem, process env, command outputs.
- Writes: delegated tools may write repo files only through explicit
  write/patch paths; command tools may write only through guarded/classified
  shell operations. `repo_propose_code_edit` writes only its audit JSON under
  `tool-results` and never writes/applies source changes.
- Risk: filesystem and shell security boundary. Results must include real
  useful output, not only artifact metadata. Code-product results must include
  the full diff/operations inline.
- Verify: facade imports delegate to the owning `tools/*` module; path stays
  under intended repo, and tool result has expected `content`, `entries`,
  `paths`, `stdout`, `stderr` or complete `unified_diff`.

### `aicarmine_broker/code_edit_proposal_contract.py`

Local stable report-only contract for code product proposals. It builds
`kind=code_edit_proposal` payloads for `unified_diff`, `structured_edit` and
`no_op`, generates complete unified diffs from exact `old_text/new_text` with
`difflib`, validates diff structure with `unidiff` when required, and records
optional AST evidence from Tree-sitter, Python AST anchors and `ast-grep`.

- Reads: target source file, optional `unidiff`, `tree-sitter`,
  `tree-sitter-python` and `ast-grep` runtime dependencies.
- Writes: no source files; returns payload to `repo_tools.py`, which writes an
  audit copy under `tool-results`.
- Risk: this is the contract boundary for diff/refactoring goals. Missing
  dependencies or parse failures must be typed errors, not heuristic fallback
  validation.
- Verify: inspect concrete proposal payloads for complete diffs, typed
  preview/path-only rejection, broken-diff rejection, no-op rationale and AST
  evidence when available.

### `aicarmine_broker/tool_contract.py`

Shared tool-call contract. It parses planner/native tool calls, normalizes tool
names and aliases, extracts public args/text, detects bad paths and sanitizes
internal tool arguments.

- Reads: planner/public payload dictionaries.
- Writes: none.
- Risk: changes can break both planner and dispatcher interpretation.
- Verify: known alias payloads normalize to expected internal tool/args.

### `aicarmine_broker/tool_dispatch.py`

Compatibility facade for the explicit registry dispatcher in
`application/tool_surface/dispatcher.py`.

- Reads: normalized name/args, repo root, command permission flag.
- Writes: through delegated dispatcher/tool only.
- Risk: do not add hidden planner decisions or fallback behavior here.
  `repo_propose_code_edit` must dispatch only to the report-only tool, not to
  apply/write paths.
- Verify: the facade builds a dispatch request and delegates; registered tool
  names are owned by the application dispatcher/registry.

### `aicarmine_broker/tool_registry.py`

Canonical internal tool schema and capability map. It defines schema metadata,
registry hash and advertised capability structure.

- Reads: static schema definitions.
- Writes: none.
- Risk: schema changes alter planner prompts and public metadata. The
  `repo_propose_code_edit` schema must require `target_file`, `edit_kind` and
  `rationale`, and must keep full diff/structured operation fields in the tool
  payload.
- Verify: registry hash/schema changes are intentional and the 3571 public
  OpenAPI surface still exposes only `vulkan_helper`.

### `aicarmine_broker/tool_selection.py`

Initial public request classifier and fallback internal tool selector. It
detects generic repo analysis and composite-review needs, and requests selector
model/tool choice when configured.

- Reads: public tool name, task text, original args, selector response.
- Writes: none.
- Risk: avoid hard-coded repo architecture assumptions. Generic selection must
  derive from request shape, not local project names.
- Verify: file-specific requests stay file-specific; generic repo analysis
  routes to agentic flow.

## aicarmine_broker/planner_core Modules

### `aicarmine_broker/planner_core/__init__.py`

Subpackage marker for planner support modules.

- Reads/writes: none.
- Risk: import side effects.
- Verify: package import only.

### `aicarmine_broker/planner_core/cache.py`

Cache helpers for read-only tool results and Vulkan repair outcomes inside a
job. It computes cache keys, detects repeated tool calls and can reuse matching
successful results.

- Reads: planner history and current call payload.
- Writes: in-memory/history-derived cache entries.
- Risk: cache must not turn failed or missing evidence into successful
  evidence.
- Verify: repeated identical read-only calls reuse only valid prior success.

### `aicarmine_broker/planner_core/json_io.py`

Ollama HTTP JSON and streaming helper module. It posts JSON, streams planner
responses to files, detects malformed/repetitive streams and parses strict JSON
objects. The streaming path guards both phases separately: waiting for HTTP
response headers and reading stream frames. If `urlopen()` never returns
headers, the job emits typed `planner_stream_waiting` /
`planner_stream_header_timeout` diagnostics instead of leaving a silent
zero-byte stream.

- Reads: Ollama stream frames and response payloads.
- Writes: optional planner stream files.
- Risk: stream `done`/`done_reason` is turn metadata. Controller validation in
  `planner.py` decides job state. Do not rely only on a readline deadline; the
  response-header wait must also be bounded and visible.
- Verify: valid streamed JSON is captured and parsed without truncating the
  final frame; a simulated header wait timeout produces typed diagnostics.

## vulkan_bridge Modules

### `vulkan_bridge/__init__.py`

Package marker for 3571 bridge modules.

- Reads/writes: none.
- Risk: import side effects.
- Verify: package import only.

### `vulkan_bridge/app.py`

Main 3571 FastAPI bridge. It defines public request models, public helper
routes, compatibility alias routes, forwarding to 3572, OpenWebUI wait/timeout
behavior, planner model handoff/unload logic, OpenAPI shaping and terminal
result compaction. The Python app still defines legacy/alias POST routes such
as `/helper_for_all` and `/repo_read`, but `_native_helper_openapi()` filters
the OpenWebUI-visible OpenAPI surface to `/vulkan_helper` only. It also keeps
successful `repo_propose_code_edit` payloads complete in `tool_context_for_30b`
instead of replacing the diff with previews, summaries or local paths.

- Reads: env, public request payloads, 3572 responses/job final payloads,
  successful tool result artifacts when expanding same-tool evidence.
- Writes: HTTP responses only; may request model unload according to handoff
  config.
- Risk: highest-risk 3571 file. Public payload must not include 3572 internal
  call protocol, continuation examples, debug blocks or local artifact paths.
- Verify: `POST /vulkan_helper` terminal response exposes
  `payload_index_for_30b`, `priority_evidence_for_30b`, `openwebui_usage` and a
  pretty JSON string `tool_context_for_30b` with real successful tool outputs;
  for code products, `artifact.unified_diff` or `artifact.structured_operations`
  is complete.

### `vulkan_bridge/agentic_v9.py`

Compatibility re-export for v9 result-shaping helpers currently implemented in
`app.py`.

- Reads: selected functions from `vulkan_bridge.app`.
- Writes: none.
- Risk: do not duplicate implementation.
- Verify: imports resolve after app refactors.

### `vulkan_bridge/client.py`

Compatibility facade for client/helper functions from `app.py`.

- Reads: selected app helpers.
- Writes: none.
- Risk: should remain thin unless a deliberate client extraction happens.
- Verify: old imports still work.

### `vulkan_bridge/compact.py`

Compatibility facade for compaction helpers from `app.py`.

- Reads: selected app helpers.
- Writes: none.
- Risk: compaction behavior should have one owning implementation.
- Verify: old imports still call current compactor.

## codex_bridge Modules

### `codex_bridge/__init__.py`

Package marker for Codex bridge implementations.

- Reads/writes: none.
- Risk: import side effects.
- Verify: package import only.

### `codex_bridge/mcp_server.py`

Codex MCP JSON-RPC server. It handles framing, direct MCP tool call dispatch,
memory reports and health behavior for the host-side Codex
integration.

- Reads: stdio frames, env paths, repository files through allowlisted tool
  handlers and optional memory DBs.
- Writes: stdio frames; write-capable MCP tools write only through their
  explicit tool handlers, not by calling the 3572 agentic loop.
- Risk: handshake must stay lightweight. Do not call 3571, `/vulkan/agent`,
  or an HTTP broker tool loop, and do not import heavy broker/repo code before
  a tool call actually needs it. When a broker tool import is required, resolve
  the Codex-selected root first and rewrite only this MCP process'
  `AICARMINE_LAB_REPO`; do not require the OpenWebUI/3572 lab shadow to match.
- Verify: MCP initialize/list/call flows with exact JSON-RPC framing.

### `codex_bridge/repo_mcp_common.py`

Shared helper module for deterministic Codex repo MCP servers. It owns stdio
JSON-RPC framing, schema validation, health payloads and
Codex-root selection.

- Reads: env, cwd and Git root markers for root resolution.
- Writes: stdio frames and this MCP process' env values
  `AICARMINE_CODEX_MCP_REPO_ROOT` and `AICARMINE_LAB_REPO` before broker-tool
  imports.
- Risk: an inherited broker/OpenWebUI lab shadow must not override the Codex
  selected repo root.
- Verify: health payload reports `repo_root`, `codex_mcp_repo_root` and the
  effective `aicarmine_lab_repo` as the same Codex root.

### `codex_bridge/repo_state_mcp_server.py`

Deterministic Codex MCP server for repo state, status and capability tools.

- Reads: MCP stdio frames and broker repo-status helper modules after
  `repo_mcp_common` root synchronization.
- Writes: MCP stdio frames only.
- Risk: must remain read-only, no HTTP broker, no agentic loop.
- Verify: `aicarmine_repo_state_health` and `aicarmine_repo_state_status`.

### `codex_bridge/repo_search_det_mcp_server.py`

Deterministic Codex MCP server for local repo search helpers.

- Reads: MCP stdio frames and broker deterministic search helper modules after
  `repo_mcp_common` root synchronization.
- Writes: MCP stdio frames only.
- Risk: do not add write/composite/agentic-loop behavior.
- Verify: `aicarmine_repo_search_det_health` and a bounded
  `aicarmine_repo_search_rg` call.

### `codex_bridge/repo_validate_mcp_server.py`

Deterministic Codex MCP server for validation tools.

- Reads: MCP stdio frames and broker validation helper modules after
  `repo_mcp_common` root synchronization.
- Writes: MCP stdio frames; validation commands may write their own tool
  artifacts but must not edit project source.
- Risk: validation-only; no broker HTTP, no 3571, no 3572 agentic loop.
- Verify: `aicarmine_repo_validate_health` and targeted validation tools.

### `codex_bridge/repo_code_mcp_server.py`

Incubating Codex MCP server for candidate code edit tools before they are
promoted into a semantic stable MCP surface.

- Reads: MCP stdio frames and broker code-proposal/deterministic patch helper
  modules after `repo_mcp_common` root synchronization.
- Writes: MCP stdio frames; `aicarmine_repo_code_apply_patch` may edit source
  only for exact `old_text` to `new_text` replacement when
  `allow_source_write=true` is supplied, and writes broker backup/tool-result
  artifacts for that operation.
- Risk: must remain isolated from the stable state/search/validation MCPs; do
  not add generic command execution or whole-file write tools here.
- Verify: `aicarmine_repo_code_health`, report-only write flags and explicit
  source-write opt-in evidence.

### `codex_bridge/ops_mcp_server.py`

Incubating Codex MCP server for operational checks that should stay outside
the OpenWebUI/3571/3572 agentic path.

- Reads: MCP stdio frames, Windows TCP listener/process state and bounded
  tails from repo-local log files.
- Writes: MCP stdio frames only.
- Risk: must not become a generic command runner, must not call HTTP health
  routes, 3571, 3572, `vulkan_helper` or the agentic loop, and must redact
  command-line secrets before returning process rows.
- Verify: `aicarmine_codex_ops_health` and
  `aicarmine_service_state_snapshot`.

### `codex_bridge/sqlite_readonly_mcp_server.py`

Dedicated read-only SQLite MCP server for Codex-side diagnostics.

- Reads: MCP stdio frames and allowlisted repo-local SQLite databases.
- Writes: MCP stdio frames only.
- Risk: must remain single-statement `SELECT`/`WITH` only; no user PRAGMA,
  write keywords, unbounded rows or path reads outside the allowlist.
- Verify: `aicarmine_sqlite_readonly_health` and
  `aicarmine_sqlite_readonly_list_databases`.

### `codex_bridge/job_artifact_mcp_server.py`

Dedicated read-only MCP server for persisted agent job artifacts.

- Reads: MCP stdio frames and files under allowlisted job roots, including
  `job.json`, `events.ndjson`, `final.json`, `tool-results/` and
  `planner-prompts/`.
- Writes: MCP stdio frames only.
- Risk: must not call 3571, 3572, `vulkan_helper`, broker HTTP routes or the
  agentic loop; local artifact paths are diagnostics, not OpenWebUI evidence.
- Verify: `aicarmine_job_artifact_health` and
  `aicarmine_job_artifact_list_jobs`.

### `codex_bridge/job_view_mcp_server.py`

Dedicated read-only MCP server for persisted agent job HTML views.

- Reads: MCP stdio frames, existing broker job renderer modules, and files
  under the selected agent job root through those renderer functions.
- Writes: MCP stdio frames only.
- Risk: must not call broker HTTP routes, 3571, 3572, `vulkan_helper`, start
  services or mutate job state. Rendered HTML and outlines are diagnostics,
  not a replacement for raw job artifacts when validating model-visible
  payloads.
- Verify: `aicarmine_job_view_health`, `aicarmine_job_view_list_views` and
  `aicarmine_job_view_render`.

### `codex_bridge/git_readonly_mcp_server.py`

Dedicated read-only Git MCP server for regression diagnostics.

- Reads: MCP stdio frames and Git metadata/diffs from the selected repo root.
- Writes: MCP stdio frames only.
- Risk: must not fetch, checkout, reset, commit, push or mutate local/remote
  state; file path arguments must resolve under the selected repo root.
- Verify: `aicarmine_git_readonly_health` and
  `aicarmine_git_readonly_log`.

### `codex_bridge/project_memory_mcp_server.py`

Dedicated project-local persistent memory MCP server.

- Reads: MCP stdio frames and `state/project_memory/project_memory.sqlite3`
  when present.
- Writes: MCP stdio frames and semantic memory records in the repo-local
  project memory SQLite DB. Write tools require explicit confirmation strings:
  `project_memory_upsert_verified`, `project_memory_mark_stale` or
  `project_memory_supersede`.
- Risk: must not become generic SQL, global memory, chat transcript storage,
  broker HTTP, 3571/3572 access or an agentic-loop substitute. Stored records
  must carry scope, key, value, source metadata, repo root, branch, commit,
  timestamps, status and confidence.
- Verify: `aicarmine_project_memory_health`,
  `aicarmine_project_memory_search` and source audit.

### `codex_bridge/local_subagent_mcp_server.py`

Codex local subagent MCP facade over the dedicated 3579 agentic-loop client.
It does not implement a direct Ollama/chat loop and does not host a parallel
local tool surface; `aicarmine_local_subagent_run_readonly` delegates bounded
read-only work to `agentic_loop_client_mcp_server.py`, so the broker
planner/controller/validator path remains the enforcement boundary.

- Reads: MCP stdio frames, selected Codex MCP repo root and, only through the
  delegated 3579 client path, dedicated broker job status/result payloads.
- Writes: MCP stdio frames only. Any job artifacts are produced by the
  dedicated broker client path, not by this facade directly.
- Risk: must not call Ollama 11434/11435 directly, use shared 3571/3572,
  OpenWebUI, `vulkan_helper`, service launchers or source-write tools. It also
  must not inherit Codex app `/subagents`; execution goes through the explicit
  MCP client and its confirmation tokens.
- Verify: `aicarmine_local_subagent_health`,
  `aicarmine_local_subagent_capabilities` and the delegated-tool metadata from
  `aicarmine_local_subagent_run_readonly` when a confirmed run is requested.

### `codex_bridge/rag_index_repo.py`

Standalone index builder for the Codex RAG MCP path. It scans the Git candidate
surface and writes SQLite/FTS5 chunks that `rag_mcp_server.py` can read.

- Reads: `git ls-files --cached --others --exclude-standard`, file contents
  under the selected repo and `.gitignore` exclusions through Git.
- Writes: `state/codex_rag/code_rag.sqlite3` and related SQLite files.
- Risk: keep it independent from OpenWebUI/Chroma, broker job state and the
  3572 planner loop.
- Verify: `aicarmine_rag_index_status` reports the expected repo root, tables
  and Git candidate surface after full or delta indexing.

### `codex_bridge/rag_mcp_server.py`

Dedicated Codex RAG MCP stdio server. It exposes `aicarmine_rag_context`,
`aicarmine_rag_index_status` and `aicarmine_rag_reindex`; search reads the
Codex SQLite/FTS5 index and can rerank through the local OVMS `/v3/rerank`
endpoint.

- Reads: MCP stdio frames, `state/codex_rag/code_rag.sqlite3`, Git candidate
  metadata for status, and optional OVMS reranker readiness/results.
- Writes: MCP stdio frames and, for reindex only, the Codex RAG SQLite index.
- Risk: must not import broker dispatchers, edit/validate tools, OpenWebUI,
  3571 or 3572 agentic-loop paths. It is a Codex-host retrieval tool, not a
  planner-native tool.
- Verify: RAG search shows `candidate_count=80`, rerank `input_count=12`,
  `doc_chars=2500`, timeout `30.0` and `rerank.status=ready` when OVMS is up.

### `codex_bridge/jsonrpc.py`

Compatibility export module for `mcp_server.py`.

- Reads: `mcp_server`.
- Writes: none.
- Risk: should not own behavior.
- Verify: historical imports resolve.

### `codex_bridge/ollama_responses_bridge.py`

OpenAI Responses-compatible HTTP adapter around Ollama. It stores response
state, injects previous context, proxies `/v1/*` and native `/api/*` routes and
can generate fallback response objects from chat completions.

- Reads: HTTP request bodies, Ollama responses, state DB.
- Writes: response state DB.
- Risk: protocol-sensitive. Keep native Ollama pass-through distinct from
  Responses transformation.
- Verify: `/health`, `/api/version`, `/v1/responses` sample request.

### `codex_bridge/responses_proxy.py`

Compatibility export module for `ollama_responses_bridge.py`.

- Reads: bridge module.
- Writes: none.
- Risk: should not own behavior.
- Verify: historical imports resolve.

### `codex_bridge/storage.py`

Compatibility export module for response storage helpers.

- Reads: bridge module.
- Writes: none directly.
- Risk: should not own behavior.
- Verify: historical imports resolve.

## model_export Modules

### `model_export/__init__.py`

Package marker for model export tooling.

- Reads/writes: none.
- Risk: import side effects.
- Verify: package import only.

### `model_export/cli.py`

Main model export CLI. It defines common args and exporter branches for text
generation, embeddings, rerank, tokenizer, text-to-speech, speech-to-text and
image generation, plus serving config updates.

- Reads: source model paths/IDs, task parameters, config file path.
- Writes: exported model folders, tokenizer files, OpenVINO runtime metadata,
  serving config entries.
- Risk: model-family branches have different dependencies and side effects.
- Verify: CLI help, dry path inspection, target exporter branch.

### `model_export/config.py`

Compatibility surface for config helpers still owned by `cli.py`.

- Reads: `cli.py`.
- Writes: none.
- Risk: should not own behavior.
- Verify: old imports resolve.

### `model_export/exporters.py`

Lazy compatibility exports for historical exporter function names. It imports
actual exporter functions from `cli.py` only when requested.

- Reads: `cli.py` on attribute access.
- Writes: none.
- Risk: keep lazy to avoid import-time heavy dependencies.
- Verify: each exported historical name resolves.

## launch Modules

### `launch/openwebui_runtime.ps1`

Main runtime launcher. It sets user/process env, validates venv isolation,
starts or checks task Ollama, 3572, 3571, executor, Open Terminal, lab mirror
watchdog and foreground OpenWebUI, then performs guided shutdown.

- Reads: user env, process env, port ownership, endpoint health, venv paths.
- Writes: user env, process env, starts/stops managed processes.
- Risk: highest-risk launcher. Preserve venv boundaries and launch order.
- Verify: process command lines and health for 3572, 3571, executor and
  OpenWebUI after launch.

### `launch/env.ps1`

Shared environment helper module. It clears Python contamination, writes user
env values, clears user env values, sets defaults and creates WebUI secrets.

- Reads: process/user env.
- Writes: process/user env, secret values.
- Risk: user env persists beyond current shell.
- Verify: before/after env values and process inherited env.

### `launch/http.ps1`

Shared HTTP endpoint helper module.

- Reads: HTTP endpoint responses.
- Writes: none.
- Risk: should not start or stop services.
- Verify: health endpoint status only.

### `launch/ollama.ps1`

Shared Ollama helper module. It checks endpoints, starts endpoint scripts when
needed and ensures required models are present.

- Reads: Ollama HTTP endpoints, model names.
- Writes: may start task endpoint script or pull/check model depending on call.
- Risk: keep 11434 planner and 11435 task roles distinct.
- Verify: endpoint URL and model name before action.

### `launch/process.ps1`

Shared process/port helper module. It detects port owners, stops port owners
when asked and starts OpenVINO provider if enabled.

- Reads: process table, net TCP connections, env.
- Writes: can stop processes or start provider process.
- Risk: process control. Verify command line and port ownership before stopping
  anything.
- Verify: `Get-PortOwner` output matches intended service.

## Root PowerShell Modules

### `openwebui.ps1`

Compatibility wrapper for `launch/openwebui_runtime.ps1`.

- Reads: launcher path.
- Writes: through delegated launcher.
- Risk: should stay thin.
- Verify: wrapper invokes current runtime script.

### `aicarmine-vulkan-tool-broker.ps1`

Standalone launcher for the local Vulkan helper stack. It starts the 3572
broker/runtime with labtools Python, checks the task Ollama endpoint, then
starts the 3571 public bridge foreground from the same labtools Python.

- Reads: `AICARMINE_LABTOOLS_PYTHON`, repo/model/env defaults, port health.
- Writes: process env, starts uvicorn processes for 3572 and 3571.
- Risk: venv and port ownership for both bridge and broker.
- Verify: launched Python prefix is labtools and both port 3572 and 3571 health
  endpoints are correct.

### `aicarmine-executor-server.ps1`

Standalone launcher for the executor FastAPI service.

- Reads: `AICARMINE_EXECUTOR_PYTHON`, runner path and repo env.
- Writes: process env, starts uvicorn process.
- Risk: venv and command security.
- Verify: port 3560 `/health` reports the intended runner.

### `aicarmine-run-safe-command.ps1`

Guarded PowerShell command runner. It enforces timeout, repo mode, repo path and
consent-oriented safety checks, then runs commands and can stop process trees.

- Reads: command string, repo mode/path, timeout, env.
- Writes: command side effects only after validation.
- Risk: command execution security boundary.
- Verify: benign command in lab mode and rejected dangerous command.

### `aicarmine-jupyter-codeinterpreter.ps1`

Legacy Jupyter/code-interpreter launcher.

- Reads: codeinterpreter Python, token/workdir env.
- Writes: token file/process startup.
- Risk: legacy path can conflict with Open Terminal replacement.
- Verify: only enabled intentionally.

### `ollama-task-vulkan.ps1`

Task Ollama launcher/check script for the secondary task/repair model port.

- Reads: `ollama.exe`, task model/env and `models-task`.
- Writes: starts or checks a separate `ollama.exe serve` process on 11435 for
  the GPU0 Intel task lane through Vulkan.
- Risk: do not confuse with main planner Ollama on 11434 and do not debug it
  as labtools/openwebui Python. GPU0 here means the Intel role; the Vulkan
  index comes from resolved device selection and `GGML_VK_VISIBLE_DEVICES`, not
  from NVIDIA/Windows numbering assumptions.
- Verify: endpoint, process command line, `OLLAMA_HOST=127.0.0.1:11435`,
  `OLLAMA_MODELS`, Vulkan env, Intel device selection and model on 11435.

### `openvino-env.ps1`

OpenVINO/cache environment setup script.

- Reads: static configured AI root/cache paths.
- Writes: process env for OpenVINO/HuggingFace/cache.
- Risk: provider-specific env must not contaminate unrelated venv debugging.
- Verify: source only in OpenVINO diagnostics/provider shell.

### `ovms-reranker-npu.ps1`

OpenVINO Model Server reranker/NPU startup helper.

- Reads: OVMS executable/root/setup env.
- Writes: starts OVMS process.
- Risk: uses provider-specific runtime and embedded Python assumptions.
- Verify: OVMS env and provider endpoint.

### `npu-phi-service.ps1`

PowerShell entrypoint for the Phi-3.5 OpenVINO/NPU diagnostic sidecar.

- Reads: `NPU_PHI_*`, `AI_ROOT`, `services/openvino-env.ps1`, local model IR
  files under `npu-models/Phi-3.5-mini-instruct-int4-cw-ov`.
- Writes: process env for the sidecar, local cache/spool directories.
- Exposes: `python -m npu_phi_service` on `127.0.0.1:3551` when enabled by
  the launcher.
- Risk: must use `venvs/openvino`, not `labtools` or `openwebui`; must not
  reuse the 3550 reranker port.
- Verify: PowerShell parse, `NPU_PHI_PYTHON_EXE`, model XML/BIN existence and
  `/healthz`/`/readyz` before any warmup/generation.

### `check-dev-toolchain.ps1`

Developer diagnostic for main/lab repo and tool availability.

- Reads: configured main/lab repo paths and local toolchain.
- Writes: diagnostic output only.
- Risk: diagnostic only unless extended.
- Verify: reported paths match intended repos.

### `sync-lab-from-main.ps1`

Synchronizes lab worktree from main project path, including git-oriented helper
operations.

- Reads: main repo, lab repo, git state.
- Writes: lab repo contents and possibly git index state.
- Risk: high data risk. Verify source/destination before running.
- Verify: dry inspection of main/lab paths and expected changed file list.

### `watch-lab-mirror.ps1`

Periodic lab mirror watchdog around sync behavior.

- Reads: lab mirror env and interval.
- Writes: invokes sync behavior over time.
- Risk: long-running process can repeatedly overwrite unexpected destination if
  paths are wrong.
- Verify: interval, source and destination before starting.

## Root Documentation And Config Files

### `requirements-agentic-optional.txt`

Optional dependency list for agentic/runtime extras.

- Reads: by installer/pip commands.
- Writes: target venv when installed.
- Risk: installing into wrong venv changes runtime behavior.
- Verify: active Python path before install.

### `.vscode/settings.json`

Editor-local VS Code Ollama extension model setting.

- Reads: VS Code extension only.
- Writes: editor config.
- Risk: not runtime evidence for 3571/3572 model selection.
- Verify: do not use this to diagnose launcher/model env.

### `VALIDATOR_ONLY_AGENTIC_LOOP_CONTRACT.md`

Contract documentation for planner/controller validation, finalization and
OpenWebUI evidence transport.

- Reads: by maintainers/agents.
- Writes: documentation only.
- Risk: must stay aligned with actual code.
- Verify: compare claims against real job JSON/events.

### `END_TO_END_AGENTIC_FLOW.md`

Code-backed runtime chain documentation for OpenWebUI -> 3571 -> 3572 ->
11434/11435 -> dispatcher -> validated terminal response -> 3571 wrapper.

- Reads: by maintainers/agents.
- Writes: documentation only.
- Risk: must stay aligned with route, launcher and planner code.
- Verify: compare each edge against `vulkan_bridge/app.py`,
  `aicarmine_broker/app.py`, `agent_entry.py`, `planner.py`,
  `tool_dispatch.py` and `job_store.py`.

### `SERVICES_MODULE_TECHNICAL_REFERENCE.md`

Central source map for all `services` modules and runtime boundaries.

- Reads: by maintainers/agents.
- Writes: documentation only.
- Risk: must stay in sync when files are added/removed.
- Verify: compare against `rg --files`.

### `RUNTIME_SCRIPT_REFERENCE.md`

Detailed reference for top-level service scripts.

- Reads: by maintainers/agents.
- Writes: documentation only.
- Risk: must stay aligned with launcher/script behavior.
- Verify: compare against root script inventory.

### `../docs/START_HERE_RUNTIME.md`

Guided first-read runtime map for maintainers and agents.

- Reads: by maintainers/agents before choosing a deeper contract or reference.
- Writes: documentation only.
- Risk: must stay short and must not duplicate or override the technical
  contracts.
- Verify: every linked owner document exists and role descriptions match the
  package references.

### Package `MODULE_REFERENCE.md` files

Package-local technical references exist for:

- `aicarmine_broker/MODULE_REFERENCE.md`
- `vulkan_bridge/MODULE_REFERENCE.md`
- `codex_bridge/MODULE_REFERENCE.md`
- `codex_bridge/MCP_GUIDE.md`
- `model_export/MODULE_REFERENCE.md`
- `npu_phi_service/MODULE_REFERENCE.md`
- `launch/MODULE_REFERENCE.md`

They document runtime contracts, module responsibilities, data flow and safe
edit checklists near the modules they describe. `codex_bridge/MCP_GUIDE.md`
is the operator-facing MCP map for server selection, client JSON compatibility,
confirmation gates and read-only/debug playbooks.
