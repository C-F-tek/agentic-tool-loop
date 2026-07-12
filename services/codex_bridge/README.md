# services/codex_bridge

`services/codex_bridge/` contains optional Codex-facing bridge helpers. It is
not the public OpenWebUI 3571 bridge and not the 3572 planner runtime.
MCP tools exposed here are host-side Codex tools; they do not become
planner-native tools in the 3572 agentic loop.

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
- [services/aicarmine_broker/MODULE_REFERENCE.md](../aicarmine_broker/MODULE_REFERENCE.md)
  - Broker module reference.
- [services/vulkan_bridge/MODULE_REFERENCE.md](../vulkan_bridge/MODULE_REFERENCE.md)
  - Public bridge module reference.
- [services/codex_bridge/MODULE_REFERENCE.md](MODULE_REFERENCE.md)
  - Codex bridge module reference.
- [services/codex_bridge/MCP_GUIDE.md](MCP_GUIDE.md)
  - Operator-facing MCP server/tool matrix and debug playbooks.
- [services/launch/MODULE_REFERENCE.md](../launch/MODULE_REFERENCE.md)
  - Launch-script module reference.
- [services/model_export/MODULE_REFERENCE.md](../model_export/MODULE_REFERENCE.md)
  - Model export module reference.

Core code entry points:

- [services/vulkan_bridge/app.py](../vulkan_bridge/app.py)
  - Public OpenWebUI wrapper surface.
- [services/vulkan_bridge/agentic_v9.py](../vulkan_bridge/agentic_v9.py)
  - Agentic bridge integration surface.
- [services/aicarmine_broker/app.py](../aicarmine_broker/app.py)
  - Internal broker application.
- [services/aicarmine_broker/planner.py](../aicarmine_broker/planner.py)
  - Planner/controller facade and high-risk loop entry; owner packages live under services/aicarmine_broker/application/.
- [services/aicarmine_broker/repo_tools.py](../aicarmine_broker/repo_tools.py)
  - Compatibility facade for repo/tool helpers; concrete implementations live under services/aicarmine_broker/tools/.
- [services/aicarmine_broker/tool_registry.py](../aicarmine_broker/tool_registry.py)
  - Internal tool registry.
- [services/aicarmine_broker/tool_dispatch.py](../aicarmine_broker/tool_dispatch.py)
  - Compatibility facade for the explicit registry dispatcher in services/aicarmine_broker/application/tool_surface/dispatcher.py.
- [services/aicarmine_broker/job_store.py](../aicarmine_broker/job_store.py)
  - Job state and artifact persistence.
- [services/aicarmine_broker/public_wrapper.py](../aicarmine_broker/public_wrapper.py)
  - Public result packaging support.
- [services/aicarmine_broker/planner_intrinsic_context.py](../aicarmine_broker/planner_intrinsic_context.py)
  - Intrinsic planner context builder.
- [services/aicarmine_broker/code_edit_proposal_contract.py](../aicarmine_broker/code_edit_proposal_contract.py)
  - Report-only code edit proposal contract.
- [services/aicarmine_broker/memory_tools.py](../aicarmine_broker/memory_tools.py)
  - Runtime memory tool support.

## Current Folder Structure

- [mcp_server.py](mcp_server.py)
  - JSON-RPC/MCP server implementation for Codex integration. It exposes the
    direct `aicarmine_tools` surface without calling 3571, `/vulkan/agent` or
    the HTTP broker tool loop. If it imports broker tools, it first maps this
    process' `AICARMINE_LAB_REPO` to the Codex-selected repo root; this does
    not require the OpenWebUI/3572 lab shadow to use the same path.
- [repo_mcp_common.py](repo_mcp_common.py),
  [repo_state_mcp_server.py](repo_state_mcp_server.py),
  [repo_search_det_mcp_server.py](repo_search_det_mcp_server.py),
  [repo_validate_mcp_server.py](repo_validate_mcp_server.py)
  - Deterministic repo-state/search/validation MCP servers for Codex. They
    share the same process-local root normalization before importing broker
    repo helper modules.
- [repo_code_mcp_server.py](repo_code_mcp_server.py)
  - Incubating repo-code MCP server for candidate code edit tooling. It is
    separate from the stable state/search/validation MCPs, exposes proposal and
    diff-check helpers as report-only tools, and exposes exact `old_text` to
    `new_text` patching only with explicit `allow_source_write=true`.
- [ops_mcp_server.py](ops_mcp_server.py)
  - Incubating Codex ops MCP server for local MCP inventory and read-only
    service-state inspection. It uses static MCP target allowlists, reads
    process/port/log state without HTTP health probes, and does not call 3571,
    3572, `vulkan_helper` or the agentic loop.
- [local_subagent_mcp_server.py](local_subagent_mcp_server.py)
  - Local subagent MCP facade for Codex. It delegates bounded read-only work to
    the dedicated 3579 agentic-loop client, so execution still goes through the
    broker planner/controller/validator path. It does not call Ollama directly,
    does not use 3571/3572 and does not expose a parallel local tool loop.
- [rag_mcp_server.py](rag_mcp_server.py)
  - Dedicated Codex RAG MCP server backed by `state/codex_rag/` SQLite/FTS5 and
    the local OVMS reranker.
- [rag_index_repo.py](rag_index_repo.py)
  - Git-surface index builder for the Codex RAG SQLite index.
- [ollama_responses_bridge.py](ollama_responses_bridge.py)
  - OpenAI Responses-compatible adapter around Ollama.
- [jsonrpc.py](jsonrpc.py), [responses_proxy.py](responses_proxy.py), [storage.py](storage.py)
  - Compatibility facades for historical import paths.
- [MCP_GUIDE.md](MCP_GUIDE.md)
  - Practical map of MCP servers, exposed tools, selection order and debug
    playbooks.

## Current MCP Boundaries

The Codex MCP layer is an operator/tooling surface, not an alternate 3572
planner registry. RAG/search MCPs are for orientation and must be followed by
real file reads before patching. The local subagent facade delegates bounded
read-only work through the dedicated 3579 client; it must not call 3571, 3572,
OpenWebUI, `vulkan_helper` or Ollama directly.

Direct dispatch diagnostics should report requested/internal tool names,
effect classes and block reasons while keeping `allow_command=false` and the
existing confirmation policies. RAG reranking remains best-effort: timeout and
invalid-response metadata explain the fallback, while FTS candidates stay
available with `rerank_score=None`.

For practical tool selection, use [MCP_GUIDE.md](MCP_GUIDE.md). The short rule
is: prefer the narrow dedicated MCP first, use RAG for orientation, use raw job
artifacts as primary loop evidence and use direct `aicarmine_tools` dispatch
only when no dedicated MCP fits.

## Test/Smoke Guardrail

Codex bridge changes must not add, restore, run or document test/smoke flows
unless Carmine explicitly requests them. Prefer read-only MCP health/status,
RAG index status, artifact/job inspection, process/port/log evidence,
payload inspection, compile/lint or diff checks as targeted verification.
- [MODULE_REFERENCE.md](MODULE_REFERENCE.md)
  - Detailed module reference.
