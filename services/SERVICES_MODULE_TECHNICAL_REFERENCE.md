<!-- AICARMINE_NON_NEGOTIABLE_CONTRACT_START -->
Regole operative non negoziabili:
1. Il contratto non va modificato se non richiesto da Carmine esplicitamente.
2. Il prodotto finale puo' essere arricchito come gia' viene fatto; non cambiare logica senza richiesta esplicita.
3. Non devi presupporre nulla: non e' il tuo compito.
<!-- AICARMINE_NON_NEGOTIABLE_CONTRACT_END -->
# Services Module Technical Reference

Updated: 2026-06-02

This document is a source map for `C:\Users\carmi\AI\services`. It documents
the modules that are part of the runtime or developer tooling. It intentionally
excludes generated/runtime data such as `.venv`, `openwebui-data`, `BCKUP`,
`__pycache__`, job workspaces, uploads and model caches.

Before changing runtime behavior, also read:

- `C:\Users\carmi\AI\AGENTS.md`
- `C:\Users\carmi\AI\services\VALIDATOR_ONLY_AGENTIC_LOOP_CONTRACT.md`
- `C:\Users\carmi\AI\services\END_TO_END_AGENTIC_FLOW.md`

Detailed local references:

- `C:\Users\carmi\AI\services\aicarmine_broker\MODULE_REFERENCE.md`
- `C:\Users\carmi\AI\services\vulkan_bridge\MODULE_REFERENCE.md`
- `C:\Users\carmi\AI\services\codex_bridge\MODULE_REFERENCE.md`
- `C:\Users\carmi\AI\services\model_export\MODULE_REFERENCE.md`
- `C:\Users\carmi\AI\services\launch\MODULE_REFERENCE.md`
- `C:\Users\carmi\AI\services\RUNTIME_SCRIPT_REFERENCE.md`
- `C:\Users\carmi\AI\services\MODULE_TECHNICAL_DESCRIPTIONS.md`
- `C:\Users\carmi\AI\services\END_TO_END_AGENTIC_FLOW.md`

## Runtime Boundaries

| Boundary | Primary modules | Port/process | Expected venv | Technical role |
| --- | --- | --- | --- | --- |
| OpenWebUI public UI | `launch/openwebui_runtime.ps1`, `aicarmine-openwebui-serve.py` | OpenWebUI foreground, usually `127.0.0.1:8080` | `venvs/openwebui` | Starts OpenWebUI with AI-Carmine env, WebSocket keepalive env and tool OpenAPI registration. |
| Public tool bridge | `vulkan_bridge/app.py`, `aicarmine_vulkan_bridge_server.py` | `127.0.0.1:3571` | `venvs/labtools` | Exposes the OpenWebUI-facing `vulkan_helper` surface and forwards agent jobs to 3572. |
| Agent broker/runtime | `aicarmine_broker/app.py`, `aicarmine_vulkan_tool_broker.py` | `127.0.0.1:3572` | `venvs/labtools` | Owns job lifecycle, planner loop, internal tool dispatch and job dashboards. |
| Planner model API | external Ollama via env in `config.py` and launcher | `127.0.0.1:11434` | external Ollama | Main controlled planner endpoint. The controller validates decisions; Ollama `done_reason` is turn metadata, not the job finalizer. |
| Task/repair model API | `ollama-task-vulkan.ps1` plus env | `127.0.0.1:11435` | external Ollama task instance | Secondary Ollama/Vulkan endpoint for the GPU0 Intel task lane, used for selector/repair/normalization flows, not the public 3571 tool. |
| Safe command executor | `aicarmine-executor-server.py`, `aicarmine-executor-server.ps1`, `aicarmine-run-safe-command.ps1` | `127.0.0.1:3560` when launched | `venvs/labtools` unless overridden | Executes approved shell commands through the guarded PowerShell runner. |
| Codex MCP/Responses bridges | `codex_bridge/*`, top-level compatibility wrappers | MCP stdio or HTTP proxy | service-dependent | Optional integration layer for Codex and Ollama/OpenAI-compatible response flows. |
| Model export tooling | `model_export/*`, `export_model.py` | CLI | export/OpenVINO env | Converts or exports supported model families and updates serving config. |

## End-To-End Agentic Chain

The runtime chain verified in code is:

```text
OpenWebUI
  -> 3571 /vulkan_helper
  -> 3572 /vulkan/agent
  -> 3572 agent job worker
  -> 11434 planner turn
  -> 3572 validator
      -> valid tool: 3572 dispatch_tool(...)
      -> invalid/dirty planner emission: optional 11435 repair, then validation again
      -> semantic tool-contract failure: controller_guard, no hidden substitute
      -> valid final: finalize_agentic_job(...)
  -> 3572 compact terminal job response
  -> 3571 terminal wrapper
  -> OpenWebUI payload_index_for_30b + priority_evidence_for_30b + tool_context_for_30b
```

Detailed proof and diagnostic steps are in
`C:\Users\carmi\AI\services\END_TO_END_AGENTIC_FLOW.md`.

Critical protocol notes:

- 3571 is a public helper facade. It must not expose 3572 internal routes as
  OpenWebUI tools.
- 3572 owns the internal agentic loop and validator/finalization contract.
- In OpenWebUI output, `artifact` means the real result produced by a successful
  tool, not a local JSON path.
- OpenWebUI cannot read `C:\Users\...` paths. Tool results needed by the 30B
  must be transported inline in `tool_context_for_30b`.
- For diff/refactoring/code-product goals, `repo_propose_code_edit` is the
  internal report-only tool surface. Its complete diff or structured operations
  are evidence, not metadata, and must stay inline in `tool_context_for_30b`.
- Planner calls use a measured prompt pack. Required file/diff/result evidence
  is represented as real windows with coordinates and hashes. Above the prompt
  compaction threshold, large sections are stored in job-local SQLite and the
  planner receives recursive `planner_prompt_context_window.v1` windows.
  Optional memory/RAG/history context can be omitted only after real
  SQLite-windowing and serialized prompt counting. `num_ctx` is
  requested/capped/effective, not assumed. Current documented defaults are
  `num_ctx_requested=12288`, `num_ctx_cap=12288`,
  `prompt_char_budget=48000`, with compaction beginning at 50% of that budget.
  The 50% compaction threshold is a soft trigger for SQLite windowing, not a
  hard no-headroom blocker; the hard generation headroom budget is the prompt
  char budget minus the reserved generation margin.
- If required prompt context still has unread real text, the next planner action
  must be `planner_scratchpad_read(kind=prompt_context_window, ...)`; the
  controller rejects other actions as `prompt_context_continuation_required`
  without sending them to GPU0/11435 repair.
- 3572 also exposes an internal IA Live Control View at
  `/jobs/{job_id}/ia-view` and `/jobs/{job_id}/ia-view.json`. This is an
  operator dashboard only: it is read-only, hidden from 3571/OpenWebUI OpenAPI,
  and shows the exact planner prompt capture, compact tool result fed back to
  planner history, raw rehydrated tool payload, validator guard and terminal
  `tool_context_for_30b`.
- Do not hide broken protocol behavior with fallback wrappers. Prove which
  process, venv, port, env var and file version is active before patching.

## Public 3571 Result Shape

For terminal jobs returned to OpenWebUI:

- primary metadata: `ok`, `job_ok`, `service`, `mode`, `tool_name`,
  `tool_result_for`, `called_by_30b`, `required_top_level_keys`.
- `payload_index_for_30b`: first navigation surface for concrete payload fields.
- `priority_evidence_for_30b`: high-priority inline concrete payloads and
  compact analysis evidence.
- `openwebui_usage`: runtime instructions for reading the indexed fields.
- `tool_context_for_30b`: pretty-printed JSON string containing only useful
  successful-tool evidence and declared limits.
- `result`: preserved unchanged when already produced by the current flow.
- No continuation protocol, no tool-call examples, no raw events, no transport
  diagnostics, no blocked/prose narrative as primary answer, no local artifact
  paths as content.

The evidence JSON should preserve real successful tool output:

- `repo_read`: `repo_path`, `line_count`, `truncated`, and full `content`.
- `repo_tree`: `repo_path`, `count`, `entries_total`, `truncated`, and
  `entries`.
- `repo_list_files`: `repo_path`, `count`, `total_matches`, `limit`,
  `truncated`, and `paths`.
- `repo_propose_code_edit`: `kind=code_edit_proposal`, `target_file`,
  `edit_kind`, `rationale`, full `unified_diff` or full
  `structured_operations` or valid `no_op`, `validation_commands`, `errors`,
  `warnings`, `source_writes_performed=false`,
  `patch_application_performed=false`, `manual_review_required=true`, plus AST
  evidence when produced.
- command/terminal tools: `returncode`, `stdout`, `stderr` and tails when the
  tool produced them.

## Top-Level Python Entrypoints

| Module | Responsibility | State and dependencies | Change risk |
| --- | --- | --- | --- |
| `aicarmine_vulkan_bridge_server.py` | Compatibility uvicorn target for `vulkan_bridge.app:app`. | Imports the 3571 FastAPI app. | Keep import path stable for launcher shortcuts and process matching. |
| `aicarmine_vulkan_tool_broker.py` | Compatibility uvicorn target for `aicarmine_broker.app:app`. | Imports the 3572 FastAPI app. | Keep import path stable for launcher shortcuts and process matching. |
| `aicarmine-executor-server.py` | FastAPI executor service with `/health`, `/run`, `/payload_health`, `/run_payload_file`. | Calls `aicarmine-run-safe-command.ps1`; reads `AICARMINE_EXECUTOR_TOKEN`, `AICARMINE_SAFE_COMMAND_RUNNER`, payload root env. | Security-sensitive: do not bypass auth, payload-root checks or runner guardrails. |
| `aicarmine-openwebui-serve.py` | Wrapper that prepares OpenWebUI boot env and runs the OpenWebUI ASGI app. | Uses OpenWebUI data/cache env and generated secret defaults. | Keep this in the OpenWebUI venv only; do not start broker/bridge services from here. |
| `aicarmine_codex_mcp_server.py` | Compatibility wrapper for `codex_bridge.mcp_server`. | Delegates to package module. | Keep as thin wrapper for historical command paths. |
| `aicarmine_codex_ollama_responses_bridge.py` | Compatibility wrapper for `codex_bridge.ollama_responses_bridge`. | Delegates to package module. | Keep as thin wrapper for historical command paths. |
| `export_model.py` | Compatibility CLI wrapper for `model_export.cli`. | Uses `runpy` to run package CLI. | Keep stable for old shortcuts/scripts. |
| `apply_openwebui_ps1_open_terminal.py` | Patches OpenWebUI PowerShell launch artifacts so Open Terminal replaces Jupyter where configured. | Reads/writes launcher text and zip contents. | Patch logic is text-sensitive; verify generated launcher before and after. |
| `requirements-agentic-optional.txt` | Optional Python dependency list for agentic/runtime features that are not part of the base interpreter. | Consumed manually or by setup scripts when preparing service venvs. | Dependency changes can alter import/runtime behavior; verify the exact venv being updated. |

## `aicarmine_broker` Package

This package is the 3572 runtime. It owns job creation, internal tool dispatch,
planner history, validation, finalization and job dashboards.

| Module | Responsibility | State and dependencies | Change risk |
| --- | --- | --- | --- |
| `aicarmine_broker/__init__.py` | Package marker and app import compatibility. | Imports `.app`. | Keep import side effects minimal. |
| `aicarmine_broker/app.py` | FastAPI app factory and routes for health, dashboards, job JSON, job events and `/vulkan/agent`. | Uses `agent_entry`, `job_store`, `job_html`. | Route shape is consumed by 3571 and browser dashboards. |
| `aicarmine_broker/agent_entry.py` | Public agent entrypoint and background job lifecycle. | Creates queued jobs, starts worker threads, calls planner, selects public/internal tools. | Do not make this decide final answers; finalization belongs in planner/controller flow. |
| `aicarmine_broker/config.py` | Central env parsing and runtime options. | Reads `AICARMINE_*`, Ollama URLs/models, timeouts, max steps, result limits. | Env changes affect both 3571/3572 behavior; prove active process env before changing defaults. |
| `aicarmine_broker/dispatcher.py` | Compatibility facade for old imports. | Re-exports app/job/dispatch helpers. | Keep thin; do not add new behavior here. |
| `aicarmine_broker/helper.py` | Composite `vulkan_helper` implementation and evidence assembly helpers. | Calls repo tools, derives useful next calls, builds helper summaries. | Must not replace internal planner evidence with local artifact paths. |
| `aicarmine_broker/job_html.py` | HTML renderer for job dashboard pages and the 3572-only IA Live Control View. | Reads job state/events, planner prompt captures, stream files and same-job tool artifacts for display. | Display-only; avoid changing job semantics here. |
| `aicarmine_broker/job_store.py` | Job persistence: SQLite metadata, JSON state, NDJSON events, final result files, compact terminal responses. | Writes under agent job workspace and broker DB. | State schema and compact responses are consumed by 3571, dashboards and tests. |
| `aicarmine_broker/memory_tools.py` | Scratchpad and SQLite-backed planner memory tools. | Reads/writes broker memory tables and scratchpad files. | Keep memory distinct from proof/evidence used by finalization gates. |
| `aicarmine_broker/planner.py` | Controlled planner loop, prompt/history construction, intrinsic-context injection, preseed evidence, validation, repair routing, code-product/apply intent split, tool execution and finalization. | Talks to Ollama 11434/11435, dispatches internal tools, writes job state/events. | Highest-risk module. Do not change max step, model, ctx, launcher or validator flow without direct evidence. |
| `aicarmine_broker/planner_intrinsic_context.py` | Internal optional-context builder. It bounds controller memory, reads optional `rag.sqlite`/FTS5 chunks in read-only mode, summarizes repo evidence, failure patterns, tool purposes and `num_ctx` requested/cap/effective. | Reads planner memory surface and optional SQLite RAG DB. Writes nothing and is not a tool surface. | Keep it controller-injected only; do not register RAG/chunks as planner tools or import lab runtime modules. |
| `aicarmine_broker/public_wrapper.py` | Deterministic public wrapper helpers for public answers and selector failures. | Pure formatting/normalization helpers. | Keep deterministic; no hidden tool calls. |
| `aicarmine_broker/repo_tools.py` | Deterministic filesystem, search, read, report-only code edit proposal, patch, validation, terminal and command tools for lab/main repos. | Reads/writes repo files only through explicit write/apply tool paths and approval rules; shells via guarded commands. | Security-sensitive and evidence-sensitive. Tool results must contain real output, not only artifact paths. |
| `aicarmine_broker/code_edit_proposal_contract.py` | Local stable contract builder for report-only code products. It validates `unified_diff`, `structured_edit` and `no_op`, generates diffs from `old_text/new_text`, and attaches AST evidence through deterministic tooling. | Reads target files and optional AST/diff dependencies from the active venv/CLI. Writes no source files. | Diff/code-product payload must stay complete; dependency failures are typed errors, not heuristic fallbacks. |
| `aicarmine_broker/tool_contract.py` | Tool schema normalization: names, aliases, args, bad-path detection, text extraction. | Pure contract helpers. | Public/internal name changes can break planner and OpenWebUI routing. |
| `aicarmine_broker/tool_dispatch.py` | Dispatch table from normalized tool calls to repo/memory/helper functions, including `repo_propose_code_edit`. | Calls deterministic tools. | Keep dispatch explicit; do not insert hidden planner decisions. |
| `aicarmine_broker/tool_registry.py` | Canonical tool registry and OpenAPI-like schema data, including the internal `repo_propose_code_edit` schema and aliases. | Pure data and schema helpers. | Tool schema changes affect planner prompts and public tool metadata. |
| `aicarmine_broker/tool_selection.py` | Public request classifier and fallback internal tool selector. | Reads user goal text; chooses initial public/internal tool path. | Avoid hard-coded repo structure assumptions except documented generic rules. |

### `aicarmine_broker/planner_core`

| Module | Responsibility | State and dependencies | Change risk |
| --- | --- | --- | --- |
| `planner_core/__init__.py` | Subpackage marker. | No runtime behavior expected. | Keep import-light. |
| `planner_core/cache.py` | Per-job read-only tool cache and repair cache helpers used by planner. | Operates on in-memory/job history payloads. | Caches must not invent evidence or turn failed tools into successful ones. |
| `planner_core/json_io.py` | Ollama JSON transport, stream capture and strict planner JSON parsing. | HTTP calls to Ollama; writes stream files when requested. | Do not treat Ollama `done_reason` as controller finalization. It is turn metadata. |

## `vulkan_bridge` Package

This package is the 3571 OpenWebUI-facing bridge. Its job is to expose one
public helper surface, forward work to 3572 and return useful terminal evidence
to the model.

| Module | Responsibility | State and dependencies | Change risk |
| --- | --- | --- | --- |
| `vulkan_bridge/__init__.py` | Package marker. | No runtime behavior expected. | Keep import-light. |
| `vulkan_bridge/app.py` | FastAPI 3571 service: `/health`, OpenWebUI-visible `/vulkan_helper`, legacy compatibility alias routes hidden from the generated OpenWebUI OpenAPI, 3572 forwarding, wait/result handling and OpenWebUI payload shaping. It preserves complete `repo_propose_code_edit` payloads in `tool_context_for_30b`. | Talks to 3572 and may unload planner model after handoff depending on env. | Highest-risk 3571 file. Do not expose continuation/call protocol in terminal results or degrade code-product payloads to previews/paths. |
| `vulkan_bridge/agentic_v9.py` | Compatibility re-export for v9 OpenWebUI shaping helpers. | Imports selected helpers from `.app`. | Keep as facade unless app logic is intentionally split. |
| `vulkan_bridge/client.py` | Compatibility HTTP client/helper exports from `.app`. | Imports selected app helpers. | Keep thin; real client behavior currently lives in `app.py`. |
| `vulkan_bridge/compact.py` | Compatibility compaction exports from `.app`. | Imports selected app helpers. | Keep thin; compaction changes belong in app or extracted module. |

## `codex_bridge` Package

| Module | Responsibility | State and dependencies | Change risk |
| --- | --- | --- | --- |
| `codex_bridge/__init__.py` | Package marker for Codex bridge implementations. | No runtime behavior expected. | Keep import-light. |
| `codex_bridge/mcp_server.py` | JSON-RPC/MCP server for Codex integration; lazy broker startup and broker tool calls. | Uses stdio JSON-RPC and HTTP calls to broker when tools are invoked. | Handshake must stay lightweight; do not import heavy broker/repo modules before initialization. |
| `codex_bridge/jsonrpc.py` | Compatibility exports from `mcp_server`. | Import facade. | Keep stable for old import paths. |
| `codex_bridge/ollama_responses_bridge.py` | OpenAI Responses-compatible HTTP adapter around Ollama/chat flows. | Stores/reloads response state and can inject previous context. | Protocol-sensitive; preserve native Ollama pass-through behavior. |
| `codex_bridge/responses_proxy.py` | Compatibility exports from `ollama_responses_bridge`. | Import facade. | Keep stable for old import paths. |
| `codex_bridge/storage.py` | Storage compatibility exports from `ollama_responses_bridge`. | Import facade. | Keep stable for old import paths. |

## `model_export` Package

| Module | Responsibility | State and dependencies | Change risk |
| --- | --- | --- | --- |
| `model_export/__init__.py` | Package marker for export implementation. | No runtime behavior expected. | Keep import-light. |
| `model_export/cli.py` | Full model export CLI: text generation, embeddings, rerank, text-to-speech, speech-to-text, image generation, tokenizer export, serving config updates. | Uses OpenVINO/model export dependencies and filesystem model/config outputs. | Long CLI with many model-family branches; verify target exporter path before editing. |
| `model_export/config.py` | Compatibility surface for export config helpers. | Currently delegates to CLI-owned parser/template setup. | Keep stable for old imports. |
| `model_export/exporters.py` | Lazy compatibility exports for historical exporter function names. | Imports functions from `cli` on demand. | Keep lazy to avoid import-time dependency cost. |

## Launcher Modules

Launcher modules are operationally sensitive because venv and process order
determine whether 3571, 3572, Ollama and OpenWebUI are connected correctly.

| Module | Responsibility | State and dependencies | Change risk |
| --- | --- | --- | --- |
| `launch/openwebui_runtime.ps1` | Main runtime launcher. Sets env, validates venvs, starts/stops managed services, registers tool URLs, starts OpenWebUI foreground. | Writes user/process env, starts 11435 task Ollama, 3572, 3571, executor, Open Terminal, mirror watchdog and OpenWebUI depending on config. | Highest-risk launcher. Preserve venv boundaries and launch sequence; do not change model/ctx/max-step defaults while debugging unrelated protocol issues. |
| `launch/env.ps1` | Shared env helpers; cleans Python env and sets/clears user env values. | Mutates process/user env. | Env writes can persist across sessions; verify active env before and after. |
| `launch/http.ps1` | Shared HTTP endpoint polling helpers. | HTTP only. | Display/check helper only; should not start services. |
| `launch/ollama.ps1` | Shared Ollama endpoint/task helpers. | Talks to Ollama ports and may manage task instance. | Keep 11434 main and 11435 task roles distinct. |
| `launch/process.ps1` | Shared port/process ownership helpers. | Reads process tables and can stop processes when called by runtime. | Never kill unrelated processes without verified command line/port ownership. |

## Root PowerShell Operational Scripts

| Module | Responsibility | State and dependencies | Change risk |
| --- | --- | --- | --- |
| `openwebui.ps1` | Compatibility wrapper that invokes `launch/openwebui_runtime.ps1`. | Stable shortcut path. | Keep thin; runtime logic belongs in `launch/openwebui_runtime.ps1`. |
| `aicarmine-vulkan-tool-broker.ps1` | Standalone launcher for the Vulkan helper stack: starts/checks 3572 broker/runtime and then runs the 3571 public bridge. | Uses `AICARMINE_LABTOOLS_PYTHON` or labtools default. | Venv-sensitive; mismatched Python can break FastAPI imports or tool behavior on either port. |
| `aicarmine-executor-server.ps1` | Launches executor FastAPI service. | Uses `AICARMINE_EXECUTOR_PYTHON` or labtools default. | Venv-sensitive and security-sensitive. |
| `aicarmine-run-safe-command.ps1` | Guarded command runner for executor/tool commands. | Executes shell commands under approved repo modes and timeout. | Security boundary; do not weaken validation/consent checks. |
| `aicarmine-jupyter-codeinterpreter.ps1` | Starts legacy Jupyter/code-interpreter service when configured. | Uses codeinterpreter venv and token/workdir env. | Legacy/Open Terminal replacement area; avoid re-enabling accidentally. |
| `ollama-task-vulkan.ps1` | Starts or checks a task Ollama instance for GPU0 Intel Vulkan/task model use. | Requires `ollama.exe`; uses task model/env, `models-task`, `OLLAMA_VULKAN` and `GGML_VK_VISIBLE_DEVICES`. | Keep separate from main planner 11434 and verify Intel Vulkan device selection. |
| `openvino-env.ps1` | Sets OpenVINO/cache/HuggingFace environment variables. | Mutates process env. | Source before OpenVINO diagnostics/providers only. |
| `ovms-reranker-npu.ps1` | Starts OVMS reranker serving with NPU/OpenVINO env. | Uses OVMS env vars and executable paths. | Provider-specific; do not mix with OpenWebUI Python venv. |
| `test-openvino.ps1` | Minimal OpenVINO environment diagnostic. | Sources `openvino-env.ps1`; runs configured OpenVINO Python. | Diagnostic only. |
| `check-dev-toolchain.ps1` | Checks main/lab repo toolchain assumptions. | Reads project paths and tool availability. | Diagnostic only unless explicitly extended. |
| `sync-lab-from-main.ps1` | Synchronizes lab worktree from main project path. | Reads/writes lab/main repo trees. | High data risk; verify paths before running or editing. |
| `watch-lab-mirror.ps1` | Periodic mirror/watchdog around lab sync. | Long-running watcher process. | Ensure it cannot overwrite unexpected repos. |

## Documentation Files

| File | Purpose |
| --- | --- |
| `VALIDATOR_ONLY_AGENTIC_LOOP_CONTRACT.md` | Operational contract for 3571/3572 agentic loop, validator, finalization and OpenWebUI evidence transport. |
| `END_TO_END_AGENTIC_FLOW.md` | Code-backed end-to-end flow: OpenWebUI -> 3571 -> 3572 -> 11434/11435 -> dispatcher -> validated terminal result -> 3571 wrapper. |
| `AGENTIC_LOOP_PATCH_NOTES.md` | Patch notes and technical memory for current agentic loop changes. |
| `AGENTIC_LOOP_V5_OPERATIONAL_MEMORY_NOTES.md` | Operational notes for planner turn memory, done reasons and tool-result transport. |
| `SERVICES_MODULE_TECHNICAL_REFERENCE.md` | This module-level source reference. |
| `MODULE_TECHNICAL_DESCRIPTIONS.md` | Detailed per-file technical descriptions: purpose, inputs, outputs, side effects, risks and verification notes. |
| `RUNTIME_SCRIPT_REFERENCE.md` | Detailed reference for top-level Python and PowerShell service scripts. |
| `aicarmine_broker/MODULE_REFERENCE.md` | Detailed module reference for the 3572 broker/runtime package. |
| `vulkan_bridge/MODULE_REFERENCE.md` | Detailed module reference for the 3571 OpenWebUI-facing bridge package. |
| `codex_bridge/MODULE_REFERENCE.md` | Detailed module reference for Codex MCP/Responses bridge modules. |
| `model_export/MODULE_REFERENCE.md` | Detailed module reference for model export modules. |
| `launch/MODULE_REFERENCE.md` | Detailed module reference for launcher helpers and runtime order. |

## Editor Tooling

| File | Purpose |
| --- | --- |
| `.vscode/settings.json` | Workspace-local editor setting for the VS Code Ollama extension model selection. This is tooling metadata, not a runtime service config. Do not use it as evidence for the model loaded by 3571/3572 or launcher processes. |

## Generated Or Non-Source Areas

Do not treat these as source modules for refactor planning:

- `services/.venv`
- `services/openwebui-data`
- `services/BCKUP`
- `services/__pycache__`
- `services/**/__pycache__`
- job workspaces under `C:\Users\carmi\AI\qwen-agent-workspace`

These paths can contain evidence for a running job, but they are not the source
implementation to edit. If job artifacts are needed for a protocol bug, use
them only to prove what a successful tool produced and which source module
failed to transport it.
