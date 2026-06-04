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
| `agent_entry.py` | Job entrypoint facade and start/status/result/cancel router. It creates queued job state, starts the thread and delegates background execution to `application/job/worker.py`. It is not the finalization authority; planner/controller validation decides terminal state. |
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
| `tool_dispatch.py` | Compatibility facade for internal tool dispatch. It builds a `DispatchRequest` and delegates to `application/tool_surface/dispatcher.py`; do not add if/elif dispatch logic here. |
| `tool_registry.py` | Canonical registry/schema for tools and capabilities. Prompt/tool metadata changes originate here, including the internal code-product schema. |
| `tool_selection.py` | Lightweight classifier for public request routing and initial internal tool choice. It may use generic request shape, but must not assume fixed project architecture. |

## application Subpackage

`application/` is no longer a flat script bucket. Real owners live under
capability superowner packages, and the former flat `application/*.py`
compatibility shims have been removed. New imports must target the owner
package directly, for example `application/planner/loop.py`,
`application/prompt/pack_builder.py` or `application/tool_surface/dispatcher.py`.

### Application Superowner Packages

| Package | Owner responsibility | Public API control |
| --- | --- | --- |
| `application/planner/` | Planner-turn and planner-loop ownership: decision normalization, one 11434 turn, multi-step job loop, validator and system prompt. | `__init__.py` exposes controlled public names such as `run_agentic_planner_job`, `planner_decision`, `validate_planner_decision_against_evidence` and `normalize_planner_decision`. |
| `application/prompt/` | Prompt construction, budget/headroom accounting, prompt windows, history-message transport and prompt value compaction. | `__init__.py` exposes only prompt-pack/budget/window primitives intended for consumers. |
| `application/evidence/` | Evidence contract, repo evidence extraction, path policy, required working set, core discovery and scope/user-claim constraints. | `__init__.py` exposes evidence builder and classifier/path primitives; validation still belongs to `application/planner/validator.py`. |
| `application/code_product/` | Report-only code-product build-state, history and public code-product text helpers. | `__init__.py` exposes code-product state/public-output helpers only. |
| `application/public_payload/` | OpenWebUI/30B terminal payload shaping, public history ledger, terminal answer, public tool context and sanitization. | `__init__.py` exposes public payload builders while preserving inline evidence and stripping local-only pointers. |
| `application/job/` | Job lifecycle, worker, action router, selector runner and compact job responses. | `__init__.py` exposes lifecycle/worker/router response services, not planner validation policy. |
| `application/controller/` | Controller guards, controller memory, deterministic preseed and diagnostics. | `__init__.py` exposes guard/memory/preseed/diagnostic helpers; controller code validates or records, it does not replace planner decisions. |
| `application/tool_surface/` | Tool surface, manifest, dispatch coordination and planner-facing tool-result compaction/digests. | `__init__.py` exposes dispatcher/surface/manifest primitives and keeps actual tool implementation in `tools/*`. |
| `application/shared/` | Low-level shared value/history/path helpers. | `__init__.py` exposes small pure helpers used by owner packages. |

Python privacy convention applies here: leading-underscore helpers inside owner
modules are implementation details. Mutating runtime state should happen only
through the owning service/package public API, not by reaching into flat aliases
or internal helper dictionaries.

| Module | Technical description |
| --- | --- |
| `application/__init__.py` | Package marker for deterministic application-level helpers used by the planner/controller. |
| `application/controller/diagnostics.py` | Deterministic terminal diagnostics builder for planner/tool/guard/memory counters. It receives evidence-contract and retry callbacks so it does not own validation policy. |
| `application/prompt/available_tools.py` | Prompt window helper for available-tool manifests. It summarizes tool names and stores the complete manifest through an injected prompt-window writer. |
| `application/tool_surface/candidate_actions.py` | Candidate next-action accessors/dedupe helpers used by turn-surface policy. It normalizes tool names, recognizes code-product build-state read/write actions and preserves exact required continuation tool calls across prompt compaction. |
| `application/shared/clean_values.py` | Small shared value-cleaning helpers used by application payload shapers. |
| `application/controller/guards.py` | Controller guard counting, rejection signature and recoverable planner-block helpers. It contains loop-integrity checks without dispatching tools or finalizing jobs. |
| `application/controller/memory.py` | Controller-owned SQLite memory text and write helpers for job lessons and loop turns. It records searchable internal memory without changing planner decisions or OpenWebUI payload policy. |
| `application/controller/preseed.py` | Initial repository-orientation preseed planner. It builds the same read-only repo_tree/repo_list_files/repo_read plan dictionaries from real root/list surfaces without dispatching tools or finalizing jobs. |
| `application/evidence/core_discovery.py` | Builds core-discovery read candidates and status from intrinsic RAG chunks or current repo evidence using injected repo path/scope/readability checks. |
| `application/code_product/state.py` | Deterministic code-product build-state parser/section helper, ready-payload extractor, inline proposal payload validator and exact old/new text parser. It does not read job history or execute tools. |
| `application/code_product/history.py` | Code-product build-state history and action helper. It detects duplicate scratchpad writes, extracts ready/window-only state from planner history, builds exact read/write/propose actions, handles duplicate window replan contract shaping and receives artifact/content rehydration callbacks from the planner. |
| `application/code_product/public_outputs.py` | Public code-product and partial-product text helpers for 30B/OpenWebUI. It formats accepted report-only proposals and rejected/partial code-product candidates without changing validator acceptance. |
| `application/planner/decision_normalizer.py` | Normalizes planner JSON/native output into controller decisions without executing tools. |
| `application/evidence/builder.py` | Owner for the planner evidence contract and finalization gate data. It computes verified reads, code-product requirements, candidate next actions and turn-surface policy without dispatching tools or calling models. |
| `application/prompt/evidence_contract.py` | Prompt-facing evidence contract compaction and hard-budget summary helpers. It keeps the planner-visible keys bounded without storing windows or changing validation policy. |
| `application/evidence/execution_digest.py` | Builds OpenWebUI follow-up evidence text and bounded repo-read content views from executed tool history. It rehydrates same-job repo_read artifacts but does not decide planner actions. |
| `application/public_payload/final_state_result.py` | Pure final-state result compaction helper. It builds terminal digest fields with an injected history ledger builder and does not finalize jobs. |
| `application/evidence/goal_classifier.py` | Pure goal text and deliverable classifier helpers for analysis/code-product/apply intent, input-envelope detection and final-summary code-product checks. Repo-specific scope evidence stays in `planner.py`. |
| `application/evidence/goal_scope.py` | Goal path/scope extraction helper. It resolves requested file limits, existing repo files and explicit directory scopes using planner-injected repo root/path-safety callbacks instead of importing runtime state. |
| `application/shared/history_queries.py` | Small query helpers over planner history, including normalized tool-result extraction, tool-presence checks and code-edit proposal success/failure extraction. |
| `application/shared/history_ledger.py` | Planner history ledger shaping, including Ollama turn extraction and preservation of code-product/window payloads. |
| `application/prompt/history_messages.py` | Planner history message shaping for Ollama/native turns. It removes transport noise, preserves bounded prompt windows and stores oversized history payloads through injected window storage. |
| `application/prompt/history_contract.py` | Prompt-facing history tail compaction helper. It receives a ledger builder callback and only clips the bounded planner history payload. |
| `application/evidence/initial_orientation.py` | Builds the read-only initial orientation surface from controller preseed history rows. It summarizes root tree, docs read, listed areas and concrete files without deciding planner actions. |
| `application/prompt/intrinsic_context.py` | Prompt compaction helper for intrinsic planner context, including bounded RAG and memory item surfaces. It does not retrieve or write memory. |
| `application/prompt/pack_builder.py` | Owner for measured planner prompt payload construction, including prompt budget reports, hard-budget windowing and required continuation surface preservation. It builds the payload but does not call Ollama, validate decisions or dispatch tools. |
| `application/public_payload/openwebui_terminal_answer.py` | Builds the terminal `answer_for_30b` text and `next_action_for_30b` instruction for OpenWebUI using injected code-product/evidence/partial-product text builders. |
| `application/public_payload/openwebui_tool_context.py` | Builds the structured terminal `tool_context_for_30b` payload from injected planner/job/output helpers, preserving the public OpenWebUI payload contract without owning validation policy. |
| `application/job/action_router.py` | Public broker payload router. It normalizes start/status/result/cancel actions, handles cancel state transitions and delegates non-job requests to the selector runner. |
| `application/job/lifecycle.py` | Agent job lifecycle service. It creates queued job state, starts/reuses the background worker thread and returns start/wait responses through injected persistence, thread registry and wait helpers. |
| `application/job/response_values.py` | Pure public job-response value helpers: text/JSON compaction and event digest shaping used by `job_store.py` compatibility exports. |
| `application/job/status_response.py` | Pure compact status response builder for running/queued jobs. `job_store.py` provides state/events and this module shapes the OpenWebUI-facing status payload. |
| `application/job/terminal_response.py` | Pure compact terminal job-response builder. `job_store.py` still owns loading state/final JSON/events, then delegates payload construction here. |
| `application/job/wait_response.py` | Pure wait-timeout response builder. Polling stays in `job_store.py`; this module adds timeout metadata, continuation guidance and event digest. |
| `application/job/worker.py` | Background job worker application service. It owns running/failure state transitions, planner handoff and disabled-planner legacy one-shot execution through injected persistence/planner/agent dependencies. |
| `application/shared/path_tokens.py` | Shared repo-relative token normalizer used by planner/cache helpers. It preserves dot-directories while removing only literal `./` prefixes. |
| `application/planner/status.py` | Pure planner status helpers for done-token detection and bounded artifact summaries. It does not call Ollama, dispatch tools or finalize jobs. |
| `application/planner/loop.py` | Owner for the multi-step agentic planner job loop. It coordinates preseed reads, per-step decisions, validation guards, tool execution, repair routing and terminal handoff through injected dependencies while preserving the rule that the planner decides and the controller validates. |
| `application/planner/turn.py` | Owner for one measured 11434 planner turn: prompt payload assembly, native/history transport, planner request capture, stream response handling and decision normalization. It does not validate decisions, dispatch tools or finalize jobs. |
| `application/planner/system_prompt.py` | Planner system-prompt contract for native and non-native tool modes. It owns the static planner instructions without calling models, validating decisions or dispatching tools. |
| `application/prompt/budget.py` | Prompt compaction/headroom/window-size calculations and serialized prompt budget reports derived from runtime config. It does not build prompts or decide planner actions. |
| `application/prompt/context_windows.py` | Prompt-context window compaction and bounded planner_scratchpad_read result helpers. It preserves text plus tracking hashes/offsets for recursive SQLite windows. |
| `application/prompt/values.py` | Prompt clipping/value compaction and stable text hashing helpers. It converts large diff/structured-operation fields into bounded metadata for planner prompt use only. |
| `application/public_payload/history_ledger.py` | Builds the public history ledger transported to 3571/OpenWebUI without leaking internal transport metadata. |
| `application/public_payload/terminal_sanitizer.py` | Pure terminal payload sanitizer for OpenWebUI-visible result sections. It removes local path/pointer fields while preserving real content and diff text fields. |
| `application/public_payload/terminal_result.py` | Builds the public terminal result and history ledger for 30B/OpenWebUI using injected repo-read content rehydration. It preserves diff/code-product payloads inline while removing local-only pointers. |
| `application/public_payload/tool_context.py` | OpenWebUI-visible terminal tool-context shaping. It rehydrates successful tool payloads inline, strips local paths and keeps code-product diffs visible without exposing internal scratchpad build state. |
| `application/evidence/required_working_set.py` | Builds the planner required working set for target repo reads and report-only code-product payloads. It uses injected text-window storage and content rehydration helpers so no local path substitutes replace real prompt content. |
| `application/evidence/repo_history.py` | Extracts repo-read memory, repo-list evidence, failed list paths and core area candidates from planner history using injected artifact rehydration and repo path safety callbacks. |
| `application/evidence/repo_path_policy.py` | Repository path policy and read-candidate ranking helper. It owns repo-local existence checks, doc/code/readable classification, scope containment and dynamic read candidate ordering using injected repo root/path safety. |
| `application/evidence/scope_conflict_resolution.py` | Resolves user-declared scope conflicts for code-product validation by requiring verified target reads, complete proposal payloads, rationale terms and anchors from file memory. |
| `application/job/selector_runner.py` | Non-job selector/dispatch path for public broker calls. It owns selector fallback, composite-review forcing, dispatcher artifact writing and deterministic public-wrapper invocation through injected adapters. |
| `application/prompt/text_windows.py` | Text and diff window primitives with offsets, completeness flags and hashes for prompt/SQLite window composition. |
| `application/public_payload/terminal_context_rows.py` | Pure terminal-context row builders for decision, validation-rejection and executed-tool sections plus stable aliases to `tool_context_for_30b`. |
| `application/tool_surface/manifest_builder.py` | Planner tool manifest compaction and Ollama native tool schema builder. It keeps provider schema slim and leaves long internal contracts in the planner payload. |
| `application/prompt/tool_contract.py` | Planner prompt contract helper for available-tool payloads and native/legacy tool-shape examples. It does not dispatch tools or alter provider schemas. |
| `application/tool_surface/result_compaction.py` | Planner-facing tool-result compaction policy. It preserves code-product diffs and prompt-context window tracking while bounding ordinary tool payloads. |
| `application/tool_surface/result_digest.py` | Planner-facing last-tool-result digest helper. It preserves code-product payloads and bounded prompt-context window metadata. |
| `application/tool_surface/turn_surface_policy.py` | Dynamic planner turn tool-surface policy. It filters candidate actions and provider tool names according to required progress without executing fallback steps. |
| `application/tool_surface/dispatcher.py` | Dispatch coordination helper for normalized tool decisions. |
| `application/evidence/user_scope_claims.py` | Extracts user-declared scope claims, such as `_shared` not being core, as evidence constraints with injected repo-existence checks instead of hard-coded controller behavior. |
| `application/planner/validator.py` | Owner for planner-decision validation against the current evidence contract. It rejects invalid native/text tool calls, repeated reads, missing required windows and code-product contract violations without dispatching tools or finalizing jobs. |
| `application/planner/validation_rejections.py` | Validation rejection signature and prompt compaction helpers, including invalid code-product repeat detection. |
| `application/prompt/window_signatures.py` | Pure signature/range helpers for repo_read and planner_scratchpad_read windows. Used to prevent repeated identical reads without embedding history policy. |

## infrastructure Subpackage

| Module | Technical description |
| --- | --- |
| `infrastructure/json_files.py` | JSON file adapter with atomic writes and same-tool artifact rehydration. Artifact loading is internal evidence reconstruction, not public payload substitution. |
| `infrastructure/job_sqlite_store.py` | SQLite primitive adapter for job index rows and event rows. `job_store.py` still writes filesystem state/events and delegates DB schema/upsert/list/event insert here. |
| `infrastructure/result_compaction.py` | Generic text/result compaction primitive shared by compatibility facades and planner-facing compaction code. |

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
