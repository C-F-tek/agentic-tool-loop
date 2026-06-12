<!-- AICARMINE_NON_NEGOTIABLE_CONTRACT_START -->
Regole operative non negoziabili:
1. Il contratto non va modificato se non richiesto da Carmine esplicitamente.
2. Il prodotto finale puo' essere arricchito come gia' viene fatto; non cambiare logica senza richiesta esplicita.
3. Non devi presupporre nulla: non e' il tuo compito.
<!-- AICARMINE_NON_NEGOTIABLE_CONTRACT_END -->
# codex_bridge Module Reference

Updated: 2026-06-12

`codex_bridge` contains optional Codex-facing integration services. These are
not the OpenWebUI 3571 public bridge and are not the 3572 planner runtime. Keep
their startup lightweight and avoid importing broker-heavy modules before a
tool call actually needs them. Tools exposed by this package are host-side
Codex MCP tools; they are not planner-native 3572 tools and must not be
documented as part of the agentic loop tool surface.

## Module Map

| Module | Technical description |
| --- | --- |
| `__init__.py` | Package marker for bridge implementations. |
| `mcp_server.py` | JSON-RPC/MCP server implementation for Codex. It reads and writes MCP frames, declares the direct `aicarmine_tools` surface and dispatches allowlisted tools in-process. It must not call 3571, `/vulkan/agent`, the 3572 agentic loop or an HTTP broker tool loop. Startup must stay lazy so MCP handshake does not trigger broker/repo initialization. Before importing broker tools, it normalizes this process' `AICARMINE_LAB_REPO` to the Codex-selected root so import-time broker config reads the right repo without changing the OpenWebUI/3572 lab shadow. |
| `repo_mcp_common.py` | Shared stdio/JSON-RPC helpers for the deterministic Codex repo MCP servers. It resolves the Codex-selected root, rewrites only the MCP process' `AICARMINE_LAB_REPO` before broker-tool imports and reports both the initial and effective root in health payloads. |
| `repo_state_mcp_server.py` | Dedicated deterministic repo-state MCP server exposing health, status and capability tools. It imports broker repo-status helpers only after `repo_mcp_common.py` has normalized the MCP process root. |
| `repo_search_det_mcp_server.py` | Dedicated deterministic repo-search MCP server exposing fd/rg/jq/ast-grep/tree-sitter/ctags helpers. It is tool-only and uses the Codex-selected root, not the OpenWebUI lab shadow. |
| `repo_validate_mcp_server.py` | Dedicated deterministic repo-validation MCP server exposing diffcheck, ruff, pyright, pytest, shellcheck and semgrep helpers. It is tool-only and does not call broker HTTP or the agentic loop. |
| `repo_code_mcp_server.py` | Incubating repo-code MCP server for candidate code-edit tools. It stays separate from the stable repo MCPs, exposes proposal/diff-check helpers as report-only tools and exposes exact `old_text` to `new_text` source patching only when `allow_source_write=true` is supplied. |
| `ops_mcp_server.py` | Incubating Codex ops MCP server for local MCP smoke tests and service-state inspection. It uses static allowlists for child MCP smoke checks, reads Windows process/port/log state without HTTP probes and redacts command-line secrets before returning process rows. |
| `rag_index_repo.py` | Standalone index builder for the Codex RAG path. By default it indexes the Git candidate surface (`git ls-files --cached --others --exclude-standard`), so `.gitignore` owns project inclusion/exclusion. It writes a dedicated SQLite/FTS5 code chunk index under `state/codex_rag/`, supports full rebuilds and delta updates, and does not read OpenWebUI/Chroma state or call Ollama/OVMS. |
| `rag_mcp_server.py` | Dedicated MCP stdio server for Codex RAG. It exposes `aicarmine_rag_context`, `aicarmine_rag_index_status` and `aicarmine_rag_reindex`. Search reads the dedicated SQLite/FTS5 index lazily and optionally reranks candidates through the local OVMS `/v3/rerank` endpoint. Reindex writes only the RAG SQLite index and does not import OpenWebUI, broker dispatchers, or edit/validate tools. |
| `jsonrpc.py` | Compatibility exports from `mcp_server.py` for older import paths. No behavior should be added here. |
| `ollama_responses_bridge.py` | HTTP adapter that presents an OpenAI Responses-like surface over Ollama chat/native APIs. It can save/load response state, inject previous context and stream response events. Preserve native Ollama pass-through routes. |
| `responses_proxy.py` | Compatibility exports from `ollama_responses_bridge.py`. No behavior should be added here. |
| `storage.py` | Compatibility exports for storage helpers from `ollama_responses_bridge.py`. No behavior should be added here. |

## Runtime Notes

- MCP traffic is stdio JSON-RPC; raw stdout/stderr framing matters.
- `mcp_server.py` direct-dispatches the allowlisted Codex MCP tools without
  calling 3571, `/vulkan/agent`, or an HTTP broker tool loop. Imports of broker
  registry/dispatcher helpers must remain lazy and function-scoped.
- Codex root selection is process-local. `AICARMINE_CODEX_MCP_REPO_ROOT`,
  Codex workspace env and the MCP cwd take precedence over any inherited
  broker `AICARMINE_LAB_REPO`; once resolved, the MCP process rewrites its own
  `AICARMINE_LAB_REPO` before broker imports. Do not require the OpenWebUI lab
  shadow to equal the Codex repo root.
- Codex MCP tools do not become 3572 planner tool names. The planner tool
  surface is still owned by `aicarmine_broker` turn policy and native Ollama
  `message.tool_calls`.
- The Responses bridge is protocol-sensitive. Do not mix it with the 3571
  OpenWebUI tool contract.
- The RAG MCP is deliberately separate from `mcp_server.py` to keep Codex tool
  selection small and avoid loading repo/edit/validation tools for retrieval
  only sessions. Its index source is Git plus `.gitignore`, not a Python
  directory blacklist.
- `repo_code_mcp_server.py` is an incubator, not a promotion into the stable
  state/search/validation MCPs. New code-edit tools should live there first
  with explicit write flags and concrete tests before being moved into a
  semantic MCP server.
- `ops_mcp_server.py` is an incubator for Codex-side operational checks only.
  Its MCP smoke runner must stay allowlist-only, and its service-state tools
  must not call `/health`, 3571, 3572, `vulkan_helper` or the agentic loop.
- Normal RAG indexing should run as delta. Full mode is for schema changes or
  cleanup after a previously noisy index build.
- The RAG MCP reranker path uses an FTS candidate pool default of `80`, a
  reranker input default of `12`, `AICARMINE_RAG_RERANK_DOC_CHARS` default
  `2500` and `AICARMINE_RAG_RERANK_TIMEOUT_SECONDS` default `30.0`, so the
  shared BGE reranker can improve precision without turning every search into
  a large blocking request.
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
7. For ops MCP changes, prove smoke targets are static, process command lines
   are redacted and log reads stay inside the selected repo root.
