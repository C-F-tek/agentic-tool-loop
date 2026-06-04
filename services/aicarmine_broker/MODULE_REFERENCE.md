<!-- AICARMINE_NON_NEGOTIABLE_CONTRACT_START -->
Regole operative non negoziabili:
1. Il contratto non va modificato se non richiesto da Carmine esplicitamente.
2. Il prodotto finale puo' essere arricchito come gia' viene fatto; non cambiare logica senza richiesta esplicita.
3. Non devi presupporre nulla: non e' il tuo compito.
<!-- AICARMINE_NON_NEGOTIABLE_CONTRACT_END -->
# aicarmine_broker Module Reference

Updated: 2026-06-01

`aicarmine_broker` is the 3572 runtime package. It owns the controlled
agentic loop, job persistence, internal tool dispatch, validator/finalization
contract and browser job views. It must stay independent from the OpenWebUI
public protocol except through the explicit 3571/3572 API boundary.

Read before edits:

- `C:\Users\carmi\AI\AGENTS.md`
- `C:\Users\carmi\AI\services\VALIDATOR_ONLY_AGENTIC_LOOP_CONTRACT.md`
- `C:\Users\carmi\AI\services\END_TO_END_AGENTIC_FLOW.md`
- `C:\Users\carmi\AI\services\SERVICES_MODULE_TECHNICAL_REFERENCE.md`

## Runtime Contract

- Process owner: 3572 broker/runtime.
- Uvicorn target: `aicarmine_vulkan_tool_broker:app`.
- Expected Python: `C:\Users\carmi\AI\venvs\labtools\Scripts\python.exe`.
- Main external model endpoints are configured through `config.py`.
- The controller validates planner decisions; Ollama `done_reason` is stored as
  turn metadata, not used as a job finalizer.
- Planner tool dispatch uses native Ollama `message.tool_calls` when
  `AICARMINE_AGENTIC_PLANNER_NATIVE_TOOLS` and
  `AICARMINE_AGENTIC_PLANNER_REQUIRE_NATIVE_TOOLS` are enabled. Text JSON
  `action=tool` is rejected in that mode; text JSON `final` and `block` remain
  valid non-tool decisions.
- Successful tool evidence must carry real result data. A path to a local JSON
  artifact is internal storage, not model-visible evidence.
- Before each 11434 planner turn, 3572 builds a measured prompt pack. The
  non-optional `required_working_set` carries real file/diff/result windows with
  text, coordinates, sizes and hashes. Optional history, memory and RAG live in
  `optional_context.intrinsic_context`; they are not planner-selectable tools
  and do not change the public surface.
- Planner context length is requested/capped/effective. `AICARMINE_AGENTIC_PLANNER_NUM_CTX`
  is the request, `AICARMINE_AGENTIC_PLANNER_NUM_CTX_CAP` is the guardrail, and
  `AGENTIC_PLANNER_NUM_CTX` is the effective value emitted in health/events.
- Diff/refactoring/code-product goals require the internal report-only
  `repo_propose_code_edit` tool after `repo_read` of the target. Apply/edit/fix
  goals remain separate and require `repo_apply_patch` only when source writes
  are actually requested.

## Module Map

| Module | Technical description |
| --- | --- |
| `__init__.py` | Package import compatibility. It imports the app package surface so historical uvicorn/import targets keep working. Keep import side effects minimal. |
| `app.py` | FastAPI application factory and route registration for the 3572 broker. It exposes health, job index, job JSON, job events, final artifacts and `/vulkan/agent`. It should only route requests and delegate lifecycle to `agent_entry` and persistence to `job_store`. |
| `agent_entry.py` | Job entrypoint and background worker orchestration. It creates queued job state, starts the worker, invokes `run_agentic_planner_job`, and returns public job metadata. It is not the finalization authority; planner/controller validation decides terminal state. |
| `config.py` | Central environment parser for planner URLs/models, timeouts, max steps, result limits, optional tool lists and Ollama options. This is the first file to inspect when runtime behavior differs between shells or launchers. |
| `dispatcher.py` | Compatibility facade that re-exports dispatch and job helpers for older import paths. Do not add new behavior here; correct the owning module instead. |
| `helper.py` | Composite helper logic for public-style requests and repository evidence summaries. It can gather repo context and useful next calls, but it must not replace real tool results with local artifact paths. |
| `job_html.py` | HTML renderer for human job dashboards and the IA Live Control View. It formats existing job state, events, prompt captures, planner streams and same-job tool artifacts only. It must not change planner state, evidence, or validation. |
| `job_store.py` | Persistence layer for jobs: SQLite metadata, state JSON, NDJSON events, final JSON/MD, compact terminal responses and polling helpers. It is the source of truth for browser/job views after the worker writes state. |
| `memory_tools.py` | Scratchpad and SQLite-backed memory tools exposed to planner/runtime. `planner_scratchpad_write kind=answer_chunk` also stores complete answer sections in a job-local SQLite composer that the terminal wrapper can reassemble. Use for recall/composition, not for proving repo evidence. |
| `planner.py` | Main controlled agentic loop. It builds planner prompts, records turns, calls Ollama, validates decisions, separates code-product from apply intent, executes internal tools, handles repair routing, writes events/state and finalizes jobs. Highest-risk file in this package. |
| `planner_intrinsic_context.py` | Internal pre-turn context builder for the planner. It reads controller memory and optional `rag.sqlite`/FTS5 chunks in read-only mode, bounds/deduplicates them, adds repo-map/failure-pattern/tool-purpose context and exposes `budget_report.num_ctx_effective`. It is not registered as a tool. |
| `public_wrapper.py` | Deterministic public response helpers and selector failure formatting. Keep pure and deterministic. |
| `repo_tools.py` | Compatibility facade for deterministic repo/tool helpers. It re-exports tool implementations from `tools/` and keeps historical imports such as `compact`, `safe_rel_path` and `terminal_environment_contract` stable. Do not add new tool behavior here; update the owning `tools/*` module. |
| `code_edit_proposal_contract.py` | Local stable contract builder for `repo_propose_code_edit`. It creates complete report-only `code_edit_proposal` payloads for `unified_diff`, `structured_edit` and `no_op`, validates diffs/operations/rationale, and attaches optional AST evidence. |
| `tool_contract.py` | Shared tool contract: parse tool calls, normalize public/internal names, sanitize args, detect bad paths and extract user text. Keep pure so planner, selector and dispatcher agree. |
| `tool_dispatch.py` | Dispatch table that maps normalized internal tool names to concrete implementations, including `repo_propose_code_edit`. Keep explicit; no hidden planner choices here. |
| `tool_registry.py` | Canonical registry/schema for tools and capabilities. Prompt/tool metadata changes originate here, including the internal code-product schema. |
| `tool_selection.py` | Lightweight classifier for public request routing and initial internal tool choice. It may use generic request shape, but must not assume fixed project architecture. |

## application Subpackage

| Module | Technical description |
| --- | --- |
| `application/__init__.py` | Package marker for deterministic application-level helpers used by the planner/controller. |
| `application/code_product_state.py` | Deterministic code-product build-state parser/section helper, ready-payload extractor, inline proposal payload validator and exact old/new text parser. It does not read job history or execute tools. |
| `application/decision_normalizer.py` | Normalizes planner JSON/native output into controller decisions without executing tools. |
| `application/goal_classifier.py` | Pure goal text and deliverable classifier helpers for analysis/code-product/apply intent, input-envelope detection and final-summary code-product checks. Repo-specific scope evidence stays in `planner.py`. |
| `application/path_tokens.py` | Shared repo-relative token normalizer used by planner/cache helpers. It preserves dot-directories while removing only literal `./` prefixes. |
| `application/public_history_ledger.py` | Builds the public history ledger transported to 3571/OpenWebUI without leaking internal transport metadata. |
| `application/tool_dispatcher.py` | Dispatch coordination helper for normalized tool decisions. |
| `application/window_signatures.py` | Pure signature/range helpers for repo_read and planner_scratchpad_read windows. Used to prevent repeated identical reads without embedding history policy. |

## planner_core Subpackage

| Module | Technical description |
| --- | --- |
| `planner_core/__init__.py` | Package marker for planner support modules. |
| `planner_core/cache.py` | Per-job cache helpers for repeated read-only tools and repair outcomes. It may reuse successful equivalent evidence but must not convert failed/missing evidence into success. |
| `planner_core/json_io.py` | Ollama HTTP and streaming JSON I/O utilities plus strict JSON object parsing. This module observes model turn completion and streams, but controller validation remains in `planner.py`. |

## Data Flow

1. 3571 posts a job request to 3572 `/vulkan/agent`.
2. `app.py` routes to `agent_entry.agent`.
3. `agent_entry.py` creates job state through `job_store.py` and starts the
   planner worker.
4. `planner.py` builds a measured prompt pack and calls the main planner at
   `PLANNER_URL` (default 11434). The planner payload includes
   `required_working_set`, `optional_context.intrinsic_context` and
   `prompt_budget_report` before the planner chooses a tool/final/block action.
5. `planner.py` validates each planner decision. Invalid/dirty emissions may
   use the task/repair endpoint `OLLAMA_TASK_URL` (default 11435), but repaired
   decisions still pass validation before execution. Semantic code-product
   contract failures remain controller guards; they are not sent to GPU0/11435
   as repair candidates.
6. Valid tool decisions call `tool_dispatch.dispatch_tool`.
7. `tool_dispatch.py` calls `repo_tools.py` compatibility exports, concrete
   `tools/*` modules, `memory_tools.py` or helper implementations.
8. Tool results, events, turn memory and final state are written through
   `job_store.py`.
9. 3571 reads terminal job state and transports successful real tool results to
   OpenWebUI.

## Native Tool Calling Rules

The planner protocol has two valid output shapes:

- Tool dispatch: native Ollama `message.tool_calls` only when native mode is
  required. The normalized decision carries `native_tool_call=true` and keeps
  the raw native call for history/audit.
- Non-tool terminal decisions: strict JSON text for `final`, `block`,
  `completed`, `needs_user` or equivalent terminal actions.

Invalid shapes:

- text JSON `{"action":"tool", ...}` in native-required mode;
- native tool call whose name is not present in the current turn tool surface
  (`native_tool_not_in_turn_surface`);
- native batch containing write/command/non-cacheable tools;
- native batch exceeding `AICARMINE_AGENTIC_PLANNER_NATIVE_MAX_PARALLEL_READONLY`;
- repair output that tries to turn invalid text into hidden tool execution
  without native provenance and validator approval.

Native messages are not durable evidence. Every dispatched tool still writes a
raw artifact and appends persistent job `history`; finalization and 3571
payload reconstruction use that history, not the budgeted planner messages.

The turn surface is dynamic. Analysis turns normally expose repo inspection
tools plus deterministic discovery/search/symbol support. Code-product turns
add AST/diff/proposal tools such as `repo_ast_grep_search`,
`repo_tree_sitter_parse`, `repo_unidiff_validate`, `repo_git_apply_check` and
`repo_propose_code_edit`. Apply/write turns add guarded apply and validation
tools. `planner_scratchpad_read` is exposed only for an exact required
continuation window.

## Evidence Rules

- `repo_read ok=True` counts as meaningful content only if full `content` is
  available from the same successful tool result or its own internal artifact.
- `content_preview`, a repo path, a count or a local artifact path is not enough
  for verified finalization.
- `repo_tree` useful evidence is `entries`.
- `repo_list_files` useful evidence is `paths`.
- `repo_propose_code_edit ok=True` useful evidence is the inline
  `code_edit_proposal` payload: `target_file`, `edit_kind`, `rationale`, full
  `unified_diff` or full `structured_operations` or valid `no_op`,
  `validation_commands`, `errors`, `warnings`, report-only flags and AST
  evidence when produced.
- For code-product goals, a local `artifact` path, preview, summary or
  `content_preview` cannot satisfy finalization. The target must have been read
  first with `repo_read`.
- For code-product goals, `planner_evidence_contract.finalization_contract`
  must keep `final_allowed=false` while a valid `repo_propose_code_edit ok=True`
  is missing, even if generic repo/file evidence is otherwise sufficient.
- terminal tools useful evidence is `returncode`, `stdout`, `stderr` and tails
  when produced.
- deterministic adapter useful evidence is their structured inline payload:
  file paths/matches for `repo_fd_files` and `repo_rg_search`, parsed JSON for
  `repo_jq_query`, AST anchors/symbols for `repo_tree_sitter_parse` and
  `repo_ctags_symbols`, diff validation for `repo_unidiff_validate` and
  `repo_git_apply_check`, diagnostics for `repo_ruff_check`,
  `repo_pyright_check`, `repo_pytest_run`, `repo_shellcheck` and
  `repo_semgrep_scan`, and explicit-consent benchmark results for
  `repo_hyperfine_benchmark`.
- Failed, rejected, blocked, guard and diagnostic entries are job history, not
  successful evidence for OpenWebUI.

## Intrinsic Context

`planner_intrinsic_context.py` implements the local RAG/memory substrate for the
planner. It does not import lab modules and does not create a new planner tool.

- Default RAG DB: `AICARMINE_PLANNER_RAG_DB`, falling back to
  `REAL_REPO/output/ai_runtime_memory/rag/rag.sqlite`.
- Access mode: SQLite read-only URI (`mode=ro`) during planner turns.
- Expected schema: `rag_chunks` plus `rag_chunks_fts`; missing DB/schema is a
  typed gap (`rag_sqlite_missing` or `rag_sqlite_schema_missing`).
- Output schema: `planner_intrinsic_context.v1` with `goal_classification`,
  `retrieved_memory`, `retrieved_rag_chunks`, `repo_map_summary`,
  `failure_patterns`, `tool_purpose_manifest` and `budget_report`.
- Optional rerank: if `RAG_RERANKING_ENGINE=external` and
  `RAG_EXTERNAL_RERANKER_URL` is set, retrieved chunks are posted to the
  external reranker as an internal ranking step. The result appears under
  `retrieved_rag_chunks.rerank`; if the service is down, status is
  `unavailable` and `ranking_source=fts_only_rerank_unavailable`.
- Tool policy: memory/RAG/chunks are injected first; `runtime_sqlite_memory_*`
  and `planner_scratchpad_*` are only for selective gaps after the intrinsic
  context is visible.

## Prompt Pack Budget

`planner.py` does not rely on rough context estimates. It serializes and counts
the actual prompt payload before posting to 11434.

- `required_working_set` must contain real consumable windows/chunks, not
  placeholder metadata. File windows include `text`, `window_start`,
  `window_end`, `full_chars`, `window_chars`, `complete` and hashes.
- When the measured prompt exceeds
  `AICARMINE_AGENTIC_PLANNER_PROMPT_COMPACT_RATIO` of the prompt budget
  (default 50%), large required and optional sections are stored in the
  job-local SQLite composer and represented as
  `planner_prompt_context_window.v1` text windows with `document_id`, offsets
  `has_more_before/has_more_after` and hashes.
- If the turn tool manifest itself becomes the budget pressure point,
  `available_tools` is represented as `planner_available_tools_window.v1`: a
  bounded tool-name index plus a real SQLite text window containing the complete
  compact manifest. This is prompt compaction, not a public schema change.
- The compaction ratio is a soft windowing trigger. It must not be reused as
  the hard generation-headroom limit. The hard limit is the prompt char budget
  minus the reserved generation margin, so a prompt below that hard limit can
  still call 11434 after windowing.
- If a SQLite-backed prompt window has `has_more_after=true`, the planner can read
  the next real window through `planner_scratchpad_read` using
  `kind=prompt_context_window`, `document_id`, `offset` and `max_chars`.
- Short diffs stay inline for planner context. Large diffs are SQLite-backed
  windows for the planner, while successful `repo_propose_code_edit` tool
  results remain complete in `tool_context_for_30b`.
- `optional_context` may be omitted section-by-section only after real SQLite
  windowing and only when the real `system + user payload` count still exceeds
  `AICARMINE_AGENTIC_PLANNER_PROMPT_CHAR_BUDGET`.
- `prompt_budget_report.total_prompt_chars` is a fixed-point count that includes
  the report itself. Jobs/events expose prompt budget and `num_ctx`
  requested/cap/effective values.
- If the required working set cannot be represented as real windows/chunks
  inside the budget after optional context is removed, the controller blocks
  with a typed prompt-pack error instead of sending truncated substance.

## IA Live Control View

The broker exposes operator-only dashboard routes:

- `/jobs/{job_id}/ia-view`
- `/jobs/{job_id}/ia-view.json`

These routes are read-only and hidden from the 3571/OpenWebUI public schema.
They show what 11434 received and what the controller fed back to the next
planner turn: saved planner prompt payload, `required_working_set`,
`optional_context.intrinsic_context`, `evidence_contract`, planner decision,
compact tool result, raw tool result rehydrated from the same job workspace,
validator guard and terminal `tool_context_for_30b`.

The view includes explicit audit flags for preview-only, metadata-only and
artifact-only payload violations. It is a diagnostic/control surface, not a
source of planner evidence and not a fallback.

## Safe Edit Checklist

Before changing this package:

1. Identify which process imports the module: 3572 worker, 3572 route, 3571
   bridge, Codex bridge or CLI.
2. Confirm active env values from the running process when the bug is runtime
   dependent.
3. Confirm whether state is written to SQLite, state JSON, event NDJSON, final
   JSON/MD or only HTTP response.
4. For planner changes, inspect a real job JSON and event stream before patching.
5. Re-run at least `python -m compileall -q services\aicarmine_broker`.
