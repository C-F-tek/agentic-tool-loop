<!-- AICARMINE_NON_NEGOTIABLE_CONTRACT_START -->
Regole operative non negoziabili:
1. Il contratto non va modificato se non richiesto da Carmine esplicitamente.
2. Il prodotto finale puo' essere arricchito come gia' viene fatto; non cambiare logica senza richiesta esplicita.
3. Non devi presupporre nulla: non e' il tuo compito.
<!-- AICARMINE_NON_NEGOTIABLE_CONTRACT_END -->
# codex_bridge Module Reference

Updated: 2026-08-13

`codex_bridge` contains optional Codex-facing integration services. These are
not the OpenWebUI 3571 public bridge and are not planner-native 3572 tools.
Keep startup lightweight and avoid importing broker-heavy modules before a
tool call actually needs them. Most tools exposed by this package are host-side
Codex MCP tools; the explicit exception is
`agentic_loop_client_mcp_server.py`, which is a Codex MCP client that can start
or call a dedicated `aicarmine_broker.app` instance on a non-shared port.

For operator-facing tool selection and debug playbooks, read
`services/codex_bridge/MCP_GUIDE.md`. This reference stays focused on module
ownership and runtime constraints.

## Module Map

| Module | Technical description |
| --- | --- |
| `__init__.py` | Package marker for bridge implementations. |
| `mcp_server.py` | JSON-RPC/MCP server implementation for Codex. It reads and writes MCP frames, declares the direct `aicarmine_tools` surface and dispatches allowlisted tools in-process. It must not call 3571, `/vulkan/agent`, the 3572 agentic loop or an HTTP broker tool loop. Startup must stay lazy so MCP handshake does not trigger broker/repo initialization. Before importing broker tools, it normalizes this process' `AICARMINE_LAB_REPO` to the Codex-selected root so import-time broker config reads the right repo without changing the OpenWebUI/3572 lab shadow. |
| `repo_mcp_common.py` | Shared stdio/JSON-RPC helpers for the deterministic Codex repo MCP servers. It resolves the Codex-selected root, rewrites only the MCP process' `AICARMINE_LAB_REPO` before broker-tool imports and reports both the initial and effective root in health payloads. |
| `repo_state_mcp_server.py` | Dedicated deterministic repo-state MCP server exposing health, status and capability tools. It imports broker repo-status helpers only after `repo_mcp_common.py` has normalized the MCP process root. |
| `repo_search_det_mcp_server.py` | Dedicated deterministic repo-search MCP server exposing fd/rg/jq/ast-grep/tree-sitter/ctags helpers. It is tool-only and uses the Codex-selected root, not the OpenWebUI lab shadow. |
| `repo_validate_mcp_server.py` | Dedicated deterministic repo-validation MCP server exposing diffcheck, ruff, pyright, shellcheck and semgrep helpers. It is tool-only and does not call broker HTTP or the agentic loop. Pytest/test execution is not an active default workflow and must not be used unless Carmine explicitly asks. |
| `repo_code_change_set.py` | Content-addressed change-set owner for the incubating repo-code MCP. It applies bounded exact structured operations across up to 100 files, generates canonical LF unified diffs server-side, records repository/commit/preimage metadata under ignored `state/repo_code/change_sets/`, and resolves integrity-checked IDs. |
| `repo_code_mcp_server.py` | Incubating repo-code MCP server for candidate code-edit tools. It prefers multi-file `structured_edit`, retains unified-diff and exact legacy modes, propagates only verified change-set IDs after proposal, and requires `allow_source_write=true` for exact or atomic multi-file apply. |
| `ops_mcp_server.py` | Incubating Codex ops MCP server for local MCP inventory and service-state inspection. It reads Windows process/port/log state without HTTP probes and redacts command-line secrets before returning process rows. It does not own project test/smoke scripts. |
| `sqlite_readonly_mcp_server.py` | Dedicated read-only SQLite MCP server for Codex diagnostics. It lists allowlisted repo-local SQLite databases, reads schemas and runs bounded single-statement `SELECT`/`WITH` queries only. It opens databases with SQLite read-only mode, blocks write keywords, rejects user PRAGMA, enforces row/time/cell limits and never calls broker HTTP or the agentic loop. |
| `job_artifact_mcp_server.py` | Dedicated read-only job artifact MCP server. It reads persisted filesystem artifacts under allowlisted job roots such as `qwen-agent-workspace/vulkan-broker/agent-jobs`, normalizes `job.json`, `events.ndjson`, `final.json`, `tool-results/` and `planner-prompts/` payloads, and does not call 3571, 3572 or `vulkan_helper`. |
| `job_view_mcp_server.py` | Dedicated read-only job HTML view MCP server. It renders existing broker `job_html.py` and `job_planner_lab.py` views in-process, extracts outlines/links, validates bounded HTML and does not call broker HTTP, 3571, 3572, `vulkan_helper` or the agentic loop. |
| `git_readonly_mcp_server.py` | Dedicated read-only Git MCP server for regression diagnostics. It exposes bounded `git log`, `git show`, `git diff`, `git blame` and branch compare helpers using subprocess argument lists, path validation under the selected repo root and no write commands. |
| `project_memory_mcp_server.py` | Dedicated project-local persistent memory MCP server. It stores verified memory records in `state/project_memory/project_memory.sqlite3` through semantic tools only, requires explicit write confirmations, records source metadata, supports stale/superseded lifecycle states and never exposes free SQL, broker HTTP or agentic-loop calls. |
| `local_subagent_mcp_server.py` | Codex local subagent MCP facade over the dedicated 3579 agentic-loop client. It does not call Ollama directly and does not host a parallel local tool loop; bounded read-only work is delegated to the same broker planner/controller/validator path used by `agentic_loop_client_mcp_server.py`, with Codex MCP root handling process-local through `repo_mcp_common.py`. |
| `agentic_loop_client_mcp_server.py` | Explicit Codex MCP client for the canonical broker agentic loop. It can ensure a dedicated multi-instance `aicarmine_broker.app` process on `127.0.0.1:3579` by default, with `AICARMINE_LAB_REPO`, terminal cwd, workspace, job root, job DB and public base URL bound to the Codex-selected root and port. It can also ensure the repo-local OVMS/BGE reranker on `127.0.0.1:3550` using `services/ovms-reranker-npu.ps1`, then pass the reranker URLs into the dedicated broker environment. It requires confirmation tokens before starting a reranker, starting a broker, restarting a broker or calling `/vulkan/agent`, rejects shared ports such as 3571/3572/11434/11435, and returns compact Codex-safe job summaries instead of exposing raw oversized payloads by default. |
| `rag_index_repo.py` | Standalone index builder for the Codex RAG path. By default it indexes the Git candidate surface (`git ls-files --cached --others --exclude-standard`), so `.gitignore` owns project inclusion/exclusion. It writes a dedicated SQLite/FTS5 code chunk index under `state/codex_rag/`, supports full rebuilds and delta updates, and does not read OpenWebUI/Chroma state or call Ollama/OVMS. |
| `rag_mcp_server.py` | Dedicated MCP stdio server for Codex RAG. It exposes `aicarmine_rag_context`, `aicarmine_rag_index_status` and `aicarmine_rag_reindex`. Search reads the dedicated SQLite/FTS5 index lazily and optionally reranks candidates through the local OVMS `/v3/rerank` endpoint. Reindex writes only the RAG SQLite index and does not import OpenWebUI, broker dispatchers, or edit/validate tools. |
| `MCP_GUIDE.md` | Operator-facing MCP guide. It lists the exposed tools per server, selection order, prohibited paths and debug playbooks for RAG/search, job artifacts and the dedicated 3579 broker. Keep it in sync when adding or changing MCP tools. |
| `jsonrpc.py` | Compatibility exports from `mcp_server.py` for older import paths. No behavior should be added here. |
| `ollama_responses_bridge.py` | HTTP adapter that presents an OpenAI Responses-like surface over Ollama chat/native APIs. It can save/load response state, inject previous context and stream response events. Preserve native Ollama pass-through routes. |
| `responses_proxy.py` | Compatibility exports from `ollama_responses_bridge.py`. No behavior should be added here. |
| `storage.py` | Compatibility exports for storage helpers from `ollama_responses_bridge.py`. No behavior should be added here. |

## Runtime Notes

- MCP traffic is stdio JSON-RPC; raw stdout/stderr framing matters.
- `mcp_server.py` direct-dispatches the allowlisted Codex MCP tools without
  calling 3571, `/vulkan/agent`, or an HTTP broker tool loop. Imports of broker
  registry/dispatcher helpers must remain lazy and function-scoped.
- Direct MCP dispatch must stay auditable without opening extra capabilities:
  blocked responses and logs should include `requested_tool`, `internal_tool`,
  `effect_classes` and `block_reason`, while command execution remains disabled
  unless a dedicated confirmed tool owns it.
- Codex root selection is process-local. `AICARMINE_CODEX_MCP_REPO_ROOT`,
  Codex workspace env and the MCP cwd take precedence over any inherited
  broker `AICARMINE_LAB_REPO`; once resolved, the MCP process rewrites its own
  `AICARMINE_LAB_REPO` before broker imports. Do not require the OpenWebUI lab
  shadow to equal the Codex repo root.
- Codex MCP tools do not become planner-native tool names. The planner tool
  surface is still owned by `aicarmine_broker` turn policy and native Ollama
  `message.tool_calls`. The agentic-loop client is a caller of the broker HTTP
  API on a dedicated port, not a tool injected into the planner surface.
- The Responses bridge is protocol-sensitive. Do not mix it with the 3571
  OpenWebUI tool contract.
- The RAG MCP is deliberately separate from `mcp_server.py` to keep Codex tool
  selection small and avoid loading repo/edit/validation tools for retrieval
  only sessions. Its index source is Git plus `.gitignore`, not a Python
  directory blacklist.
- `repo_code_mcp_server.py` is an incubator, not a promotion into the stable
  state/search/validation MCPs. New code-edit tools should live there first
  with explicit write flags and concrete runtime evidence before being moved
  into a semantic MCP server. Callers should send bounded structured edits;
  the server generates and persists the canonical unified diff once, then its
  ID is propagated through validation, apply-check and apply. Inline unified
  diffs remain a compatibility mode for clients that already own a valid diff.
- `ops_mcp_server.py` is an incubator for Codex-side operational checks only.
  Its service-state tools must not call `/health`, 3571, 3572,
  `vulkan_helper` or the agentic loop. MCP inventory probes are allowlisted
  stdio initialize/list/optional-health probes and are separate from deleted
  project test/smoke scripts.
- `sqlite_readonly_mcp_server.py`, `job_artifact_mcp_server.py`,
  `job_view_mcp_server.py` and `git_readonly_mcp_server.py` are observability MCPs. They are host-side
  Codex tools only; they do not become planner tools and must remain read-only.
  SQLite user queries must stay `SELECT`/`WITH` only, job artifacts must stay
  filesystem reads, job views must stay local renderer reads without HTTP, and
  Git commands must stay diagnostic read commands.
- `project_memory_mcp_server.py` is the one Codex-side persistent memory MCP in
  this folder. It is write-capable by design, but writes are restricted to a
  repo-local SQLite database, require `confirm_write`, `confirm_stale` or
  `confirm_supersede`, and must carry source metadata. It must not reuse RAG,
  job or planner SQLite databases as a memory store.
- `local_subagent_mcp_server.py` is Codex-side only and is only a facade over
  the dedicated agentic-loop client. It must not call Ollama directly, use
  11434/11435, host a parallel local tool loop, call 3571/3572, OpenWebUI,
  `vulkan_helper`, service launchers or any source-write tool. It does not
  inherit Codex app `/subagents`; execution goes through the 3579 broker
  planner/controller/validator path and artifact surface.
- `agentic_loop_client_mcp_server.py` is the only Codex MCP in this folder
  allowed to start or call the agentic broker. It must use a dedicated
  non-shared port, default `3579`, and must not call the shared OpenWebUI
  bridge on 3571 or a shared 3572 broker. `ensure_broker` starts only when the
  configured port is free and `confirm_ensure_broker` is supplied. It must not
  reload or restart a broker already listening on 3579; `reload`, `restart` and
  `confirm_restart_broker` are rejected because uvicorn reload/restart can
  terminate in-process job workers before terminal state is written. Loading
  new code is a manual operator stop/start followed by PID/log/port
  verification. `run`, `status` and `result` call `/vulkan/agent` only when the matching
  `confirm_agentic_loop` token is supplied. Dedicated instances must set
  `AICARMINE_LAB_REPO`, `AICARMINE_REAL_REPO`, `OPEN_TERMINAL_CWD`,
  `AICARMINE_OPEN_TERMINAL_WORKDIR`, `AICARMINE_VULKAN_WORKSPACE`,
  `AICARMINE_AGENT_JOB_ROOT`, `AICARMINE_AGENT_JOB_DB` and
  `AICARMINE_AGENT_PUBLIC_BASE_URL` for the selected Codex root and port.
- The same agentic-loop client may ensure the local BGE reranker on
  `127.0.0.1:3550` through `aicarmine_agentic_loop_ensure_reranker` or the
  `ensure_reranker` flag on broker/run calls. Startup is allowed only for the
  repo-local `services/ovms-reranker-npu.ps1` provider script, only when the
  configured port is free and only when `confirm_ensure_reranker` is supplied.
  It must not reuse 11435/GPU0 task Ollama for rerank work.
- `job_artifact_mcp_server.py` also scans dedicated Codex broker workspaces
  under `state/codex_bridge/agentic_loop_client/port-*/workspace/agent-jobs`
  so jobs launched through the 3579 client remain inspectable without HTTP.
- Normal RAG indexing should run as delta. Full mode is for schema changes or
  cleanup after a previously noisy index build.
- Memory/RAG read paths are best-effort per section. A corrupt or locked memory
  DB, reranker timeout or invalid reranker response should produce bounded
  diagnostics and preserve any valid read-only data already available.
- The RAG MCP reranker path uses an FTS candidate pool default of `80`, a
  reranker input default of `12`, `AICARMINE_RAG_RERANK_DOC_CHARS` default
  `2500` and `AICARMINE_RAG_RERANK_TIMEOUT_SECONDS` default `30.0`, so the
  shared BGE reranker can improve precision without turning every search into
  a large blocking request.
- RAG reranker timeouts are reported with requested/effective timeout metadata.
  When reranking is unavailable or returns no usable scores, FTS results remain
  valid orientation evidence with `rerank_score=None`.
- If Codex bridge behavior appears stale, verify which wrapper path launched it:
  `aicarmine_codex_mcp_server.py`, `aicarmine_codex_ollama_responses_bridge.py`
  or a package module directly.

## Safe Edit Checklist

1. Verify whether the caller is MCP stdio, HTTP Responses proxy or a historical
   wrapper.
2. Keep compatibility modules as facades.
3. Do not import 3572 broker modules during MCP handshake unless proven safe.
4. For HTTP adapter changes, capture a request/response sample before patching.
5. For RAG MCP changes, verify the SQLite index schema and OVMS rerank endpoint
   independently before adding it to Codex configuration.
6. For repo-code MCP changes, prove report-only tools do not write source and
   prove write-capable tools require an explicit opt-in argument.
7. For ops MCP changes, prove process command lines are redacted and log reads
   stay inside the selected repo root.
8. For agentic-loop client changes, prove reranker startup stays explicit,
   local-only, repo-script-only and separate from OpenWebUI/3571/3572.
