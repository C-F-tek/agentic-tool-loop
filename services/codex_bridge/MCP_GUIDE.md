# Codex Bridge MCP Guide

This guide is the operator-facing map for the MCP servers under
`services/codex_bridge/`. It documents what each server is for, which tools it
exposes and which paths are intentionally not allowed. It is not a replacement
for the agentic-loop contract: these are Codex-side MCP tools, not planner-native
3572 tools.

## Selection Order

Use the narrowest read-only MCP that can answer the question:

1. Repository orientation: `aicarmine_repo_state_*`, then RAG/search.
2. Semantic/code search: `aicarmine_rag_*` for owner discovery, then
   deterministic search and real file reads.
3. Job debugging: `aicarmine_job_artifact_*` for raw persisted evidence, then
   `aicarmine_job_view_*` only for rendered/operator presentation.
4. Regression history: `aicarmine_git_readonly_*`.
5. Project-local memory: `aicarmine_project_memory_search/get` first; write
   tools only with explicit confirmation and verified source metadata.
6. Agentic-loop runs from Codex: `aicarmine_agentic_loop_*` on the dedicated
   3579 client only, never through 3571/OpenWebUI.

Do not use a broad direct-dispatch tool when a dedicated MCP exists. RAG/MCP
output is orientation evidence: before patching, always read the real owner
file and verify the relevant diff/artifact/process.

## MCP Client JSON Compatibility

VS Code and similar MCP clients should configure these servers as stdio
processes. The stable shape is:

```json
{
  "type": "stdio",
  "command": "C:\\Users\\carmi\\AI\\venvs\\labtools\\Scripts\\python.exe",
  "args": ["-u", "C:\\Users\\carmi\\AI\\services\\codex_bridge\\rag_mcp_server.py"],
  "cwd": "C:\\Users\\carmi\\AI",
  "env": {
    "AICARMINE_CODEX_MCP_REPO_ROOT": "C:\\Users\\carmi\\AI",
    "AICARMINE_LAB_REPO": "C:\\Users\\carmi\\AI"
  }
}
```

Client-side server ids are display/config keys; tool names are the contract.
Keep ids consistent with the package name when possible, but do not infer tool
behavior from the id alone. Always verify via `tools/list` or the server health
tool after changing JSON.

Common environment fields:

- `AICARMINE_CODEX_MCP_REPO_ROOT`: selected repo root for Codex-side MCP tools.
- `AICARMINE_LAB_REPO`: process-local repo root visible to broker helper imports.
- `AICARMINE_USEFUL_TOOLS_ROOT`: optional helper-tool root for deterministic
  repo search/validation tools.
- `AICARMINE_REPO_MCP_MAX_TEXT_CHARS`: bounded response size for repo MCP output.
- `AICARMINE_RAG_REPO`, `AICARMINE_RAG_DB`,
  `AICARMINE_RAG_RERANK_URL`, `AICARMINE_RAG_RERANK_READY_URL`,
  `AICARMINE_RAG_RERANK_MODEL`: RAG-specific index and reranker settings.

Do not commit machine-local MCP JSON, hook state or probe reports unless they
are intentionally converted into a portable template. Local files under
`.codex/` can prove runtime shape, but they are not the source of truth for
server behavior.

## Root And Local Filesystem Rules

Repo MCP root selection is process-local. The shared helper checks, in order:

1. `AICARMINE_CODEX_MCP_REPO_ROOT`
2. `CODEX_WORKSPACE_ROOT`
3. `CODEX_PROJECT_ROOT`
4. `CODEX_CWD`
5. `WORKSPACE_ROOT`
6. `PROJECT_ROOT`
7. `INIT_CWD`
8. current working directory Git root
9. legacy `AICARMINE_LAB_REPO`
10. current working directory

After selection, the MCP process rewrites its own `AICARMINE_LAB_REPO` to the
selected root before importing broker helpers. This does not change any already
running OpenWebUI/3572 process.

Job artifact readers scan only allowlisted local roots:

- `AICARMINE_AGENT_JOB_ROOT`, when set;
- `qwen-agent-workspace/vulkan-broker/agent-jobs`;
- dedicated Codex broker workspaces under
  `state/codex_bridge/agentic_loop_client/port-*/workspace/agent-jobs`;
- `output/agent-jobs`, `output/agent_jobs`, `agent-jobs`, `agent_jobs`.

SQLite read-only tools resolve only allowlisted databases. Known aliases include
repo-local state such as the Codex RAG DB and job/planner DBs exposed by the
server health/list tools. Extra read roots must be passed through
`AICARMINE_SQLITE_READONLY_ALLOW_ROOTS`; user SQL remains bounded
`SELECT`/`WITH` only and user PRAGMA is rejected.

## Confirmation And Write Gates

Most MCP servers are read-only. The few tools that can start processes, call the
dedicated broker or write project-local state require explicit arguments:

| Tool family | Gate argument | Required value | Effect |
| --- | --- | --- | --- |
| `aicarmine_agentic_loop_run` | `confirm_agentic_loop` | `aicarmine_agentic_loop_run` | Calls the dedicated 3579 broker `/vulkan/agent`. |
| `aicarmine_agentic_loop_status` | `confirm_agentic_loop` | `aicarmine_agentic_loop_status` | Reads status from the dedicated 3579 broker. |
| `aicarmine_agentic_loop_result` | `confirm_agentic_loop` | `aicarmine_agentic_loop_result` | Reads a compact result from the dedicated 3579 broker. |
| `aicarmine_agentic_loop_ensure_broker` | `confirm_ensure_broker` | `aicarmine_agentic_loop_ensure_broker` | Starts a new dedicated broker only when the configured port is free. |
| `aicarmine_agentic_loop_ensure_broker` with `restart=true` | `confirm_restart_broker` | `aicarmine_agentic_loop_restart_broker` | Restarts only the dedicated broker process tree. |
| `aicarmine_agentic_loop_ensure_reranker` | `confirm_ensure_reranker` | `aicarmine_agentic_loop_ensure_reranker` | Starts the repo-local OVMS/BGE reranker only when the configured port is free. |
| `aicarmine_project_memory_upsert_verified` | `confirm_write` | `project_memory_upsert_verified` | Writes verified memory to the repo-local memory DB. |
| `aicarmine_project_memory_mark_stale` | `confirm_stale` | `project_memory_mark_stale` | Marks memory records stale by verified source. |
| `aicarmine_project_memory_supersede` | `confirm_supersede` | `project_memory_supersede` | Supersedes existing memory through the memory DB. |
| `aicarmine_repo_code_apply_patch` | `allow_source_write` | `true` | Applies exact `old_text` -> `new_text` replacement only. |

The direct `mcp_server.py` facade may list legacy write-like tool names, but
its Codex direct-dispatch policy keeps command execution disabled and reports
effect classes/block reasons. Prefer the dedicated MCP above whenever one
exists.

## Server Matrix

| Server | Primary tools | Use for | Must not do |
| --- | --- | --- | --- |
| `repo_state_mcp_server.py` | `aicarmine_repo_state_health`, `aicarmine_repo_state_status`, `aicarmine_repo_state_capabilities` | Repo root, branch, status, available repo capabilities. | Mutate Git, launch services or call broker HTTP. |
| `repo_search_det_mcp_server.py` | `aicarmine_repo_search_fd`, `aicarmine_repo_search_rg`, `aicarmine_repo_search_jq`, `aicarmine_repo_search_ast_grep`, `aicarmine_repo_search_tree_sitter_parse`, `aicarmine_repo_search_ctags` | Deterministic file/text/AST/symbol discovery. | Replace real file reads before patching. |
| `rag_mcp_server.py` | `aicarmine_rag_context`, `aicarmine_rag_index_status`, `aicarmine_rag_reindex` | Semantic owner discovery and index freshness. | Treat reranker failure as absence of code; FTS fallback remains valid orientation. |
| `repo_validate_mcp_server.py` | `aicarmine_repo_validate_diffcheck`, `aicarmine_repo_validate_ruff`, `aicarmine_repo_validate_pyright`, `aicarmine_repo_validate_shellcheck`, `aicarmine_repo_validate_semgrep` | Targeted validation after a change. | Run pytest/test flows unless explicitly requested. |
| `git_readonly_mcp_server.py` | `aicarmine_git_readonly_log`, `aicarmine_git_readonly_show`, `aicarmine_git_readonly_diff`, `aicarmine_git_readonly_blame`, `aicarmine_git_readonly_branch_compare` | Regression comparison and commit evidence. | Fetch, checkout, reset, commit, push or any Git write. |
| `sqlite_readonly_mcp_server.py` | `aicarmine_sqlite_readonly_list_databases`, `aicarmine_sqlite_readonly_schema`, `aicarmine_sqlite_readonly_query` | Read-only DB inspection for RAG/job/planner diagnostics. | PRAGMA/write SQL/free path access. Queries stay bounded `SELECT`/`WITH`. |
| `job_artifact_mcp_server.py` | `aicarmine_job_artifact_list_jobs`, `aicarmine_job_artifact_summary`, `aicarmine_job_artifact_events`, `aicarmine_job_artifact_final`, `aicarmine_job_artifact_tool_results`, `aicarmine_job_artifact_subturns`, `aicarmine_job_artifact_planner_payload`, `aicarmine_job_artifact_rejections` | Raw persisted job evidence. This is primary for loop debugging. | Call 3571/3572/OpenWebUI or infer from HTML alone. |
| `job_view_mcp_server.py` | `aicarmine_job_view_list_views`, `aicarmine_job_view_render`, `aicarmine_job_view_render_section`, `aicarmine_job_view_ia_payload`, `aicarmine_job_view_outline`, `aicarmine_job_view_links`, `aicarmine_job_view_validate_html` | Local-rendered operator views for existing jobs. | Treat HTML as primary evidence when raw artifacts are available. |
| `project_memory_mcp_server.py` | `aicarmine_project_memory_search`, `aicarmine_project_memory_get`, `aicarmine_project_memory_upsert_verified`, `aicarmine_project_memory_mark_stale`, `aicarmine_project_memory_supersede`, `aicarmine_project_memory_audit_sources` | Persistent project-local memory with source metadata. | Write silently, store unverified assumptions or reuse RAG/job/planner DBs. |
| `local_subagent_mcp_server.py` | `aicarmine_local_subagent_health`, `aicarmine_local_subagent_capabilities`, `aicarmine_local_subagent_run_readonly` | Bounded read-only subagent analysis through the dedicated 3579 loop. | Call Ollama directly, use 11434/11435, call 3571/3572 or write source. |
| `agentic_loop_client_mcp_server.py` | `aicarmine_agentic_loop_health`, `aicarmine_agentic_loop_capabilities`, `aicarmine_agentic_loop_ensure_reranker`, `aicarmine_agentic_loop_ensure_broker`, `aicarmine_agentic_loop_run`, `aicarmine_agentic_loop_status`, `aicarmine_agentic_loop_result` | Dedicated Codex agentic-loop jobs on non-shared 3579. | Reuse shared 3571/3572, start/restart without confirmation, hide oversized payloads as if fully read. |
| `repo_code_mcp_server.py` | `aicarmine_repo_code_propose_edit`, `aicarmine_repo_code_unidiff_validate`, `aicarmine_repo_code_git_apply_check`, `aicarmine_repo_code_apply_patch` | Incubating report-only code proposal checks; exact patching only when explicitly confirmed. | Promote into stable tools or write source without `allow_source_write=true`. |
| `ops_mcp_server.py` | `aicarmine_mcp_inventory_*`, `aicarmine_service_state_*` | Read-only local MCP/process/port/log inventory. | HTTP smoke against services, broker calls or unredacted command output. |
| `mcp_server.py` | Direct `aicarmine_tools` facade including repo/status/search/memory helpers | Compatibility/direct dispatch when no dedicated MCP fits. | Bypass dedicated MCPs, enable command execution, call 3571 or broker HTTP loop. |

## Debug Playbooks

### RAG or Search Looks Wrong

1. Run `aicarmine_rag_index_status` and record `repo_root`, `db`, current commit
   and stale status.
2. Run `aicarmine_rag_context` with bounded `candidate_limit` and inspect
   `candidate_count`, `returned`, reranker status and warnings.
3. If reranker is unavailable, continue with FTS candidates; do not treat that
   as an empty repo.
4. Confirm owner files with deterministic search or direct file reads before
   patching.

### Agentic Job Stalls Or Finals Look Wrong

1. Use `aicarmine_job_artifact_summary` and `aicarmine_job_artifact_events`.
2. If a support turn or scratchpad loop is suspected, read
   `aicarmine_job_artifact_subturns`.
3. Read `aicarmine_job_artifact_planner_payload` for the exact prompt/payload
   surface and `aicarmine_job_artifact_rejections` for validator feedback.
4. Use `aicarmine_job_view_*` only after raw artifacts establish the state.

### Dedicated 3579 Broker Reload

`aicarmine_agentic_loop_ensure_broker(reload=true)` applies reload behavior only
when it starts a new dedicated broker process. If a 3579 broker is already
listening, verify `reload_applied`, PID/log and port state before assuming new
code is loaded. Use `restart=true` only with `confirm_restart_broker` and only
for the dedicated 3579 process tree.

## Documentation Maintenance

When adding or changing an MCP server:

- update this guide with the server purpose, exposed tools and prohibited paths;
- update `MODULE_REFERENCE.md` for module ownership and runtime constraints;
- keep `README.md` short and point readers here for the operational map;
- run compile/diff validation and RAG delta reindex after the documentation
  change.
