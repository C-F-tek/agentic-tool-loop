# Start Here Runtime Guide

This is the first-read guide for the local Agentic Tool Loop repository. It is
intentionally short: use it to decide which technical document or MCP tool to
open next, not as a replacement for the contracts.

## One-Minute Map

| Surface | Role | Primary owner | First document |
| --- | --- | --- | --- |
| OpenWebUI public tool | User-facing `vulkan_helper` endpoint on 3571. | `services/vulkan_bridge/app.py` | `services/vulkan_bridge/MODULE_REFERENCE.md` |
| Internal broker loop | Job lifecycle, planner/controller/validator and internal tools on 3572. | `services/aicarmine_broker/` | `services/aicarmine_broker/MODULE_REFERENCE.md` |
| Planner model lane | Main planner/preplanner/final-quality/replan specialist calls on 11434. | `services/aicarmine_broker/planner.py` and `application/*` owners | `services/END_TO_END_AGENTIC_FLOW.md` |
| Repair/task model lane | Bounded selector/repair support on 11435. | `services/aicarmine_broker/tool_selection.py`, `services/ollama-task-vulkan.ps1` | `services/END_TO_END_AGENTIC_FLOW.md` |
| Codex MCP tools | Host-side read/debug/edit-assist tools, outside 3571/3572 tool surfaces. | `services/codex_bridge/` | `services/codex_bridge/MCP_GUIDE.md` |
| Dedicated Codex broker | Optional Codex-only broker client, default 3579, gated by confirmation tokens. | `services/codex_bridge/agentic_loop_client_mcp_server.py` | `services/codex_bridge/MCP_GUIDE.md` |
| Codex RAG | SQLite/FTS repo retrieval for owner discovery and index freshness. | `services/codex_bridge/rag_mcp_server.py` | `services/codex_bridge/MCP_GUIDE.md` |
| Launch/runtime env | PowerShell launch order, venvs, ports and process env. | `services/launch/` | `docs/launcher_contract.md` |

## Read In This Order

1. `AGENTS.md`
   - Workspace rules, anti-assumption policy and non-negotiable contracts.
2. `docs/START_HERE_RUNTIME.md`
   - This guide.
3. `services/END_TO_END_AGENTIC_FLOW.md`
   - Runtime chain and boundaries: OpenWebUI -> 3571 -> 3572 -> model lanes.
4. `services/codex_bridge/MCP_GUIDE.md`
   - Which MCP to use for repo state, RAG, jobs, Git, SQLite and 3579.
5. Package reference for the area being edited:
   - `services/aicarmine_broker/MODULE_REFERENCE.md`
   - `services/vulkan_bridge/MODULE_REFERENCE.md`
   - `services/codex_bridge/MODULE_REFERENCE.md`
   - `services/launch/MODULE_REFERENCE.md`
   - `services/model_export/MODULE_REFERENCE.md`
   - `services/npu_phi_service/MODULE_REFERENCE.md`
6. `services/MODULE_TECHNICAL_DESCRIPTIONS.md`
   - File-by-file owner map when the package reference is not specific enough.

## If You Need To Debug

| Symptom | First evidence | Preferred tool/doc | Do not start with |
| --- | --- | --- | --- |
| Job stalled or final looks wrong | Persisted job artifacts and events. | `aicarmine_job_artifact_*`, then `services/END_TO_END_AGENTIC_FLOW.md` | HTML view alone, model guesswork or service restart. |
| Planner chose an invalid action | Planner payload, validator rejection and evidence contract. | `aicarmine_job_artifact_planner_payload`, `aicarmine_job_artifact_rejections` | Patching `planner.py` before reading the rejection. |
| RAG/search looks empty | RAG index status, candidate count and reranker status. | `aicarmine_rag_index_status`, `aicarmine_rag_context` | Treating reranker failure as missing code. |
| Repo/file owner unclear | RAG for orientation, then real file reads. | `aicarmine_rag_context`, deterministic search, direct file read | Patching from RAG snippets only. |
| MCP tool behavior unclear | Server health/capabilities and guide matrix. | `services/codex_bridge/MCP_GUIDE.md` | Assuming tool behavior from server id alone. |
| Runtime/root mismatch | Process env, job payload root and launcher docs. | `docs/runtime_env_contract.md`, `docs/launcher_contract.md` | Inferring from Codex cwd only. |
| Public OpenWebUI payload too large/confusing | Final payload and concrete `tool_context_for_30b` artifacts. | `services/CODEX_OPENWEBUI_PAYLOAD_LIMITATION.md` | Local artifact paths as proof of model-visible evidence. |

## Source Of Truth Rules

- Runtime contracts beat historical notes.
- Code owners beat README summaries.
- Job artifacts beat rendered HTML views.
- MCP/RAG output is orientation until the real owner file is read.
- `tool_context_for_30b.artifacts[*].artifact` is the canonical public payload
  location for complete successful tool evidence.
- Codex MCP tools are not planner-native 3572 tools and do not alter the
  OpenWebUI public tool surface.

## What Not To Do On First Read

- Do not change ports, models, launcher order, max steps or validator gates to
  explain a symptom before reading the relevant job/process evidence.
- Do not call 3571/3572/HTTP services when persisted artifacts or read-only MCPs
  can answer the question.
- Do not use local paths, SQLite ids or preview fields as substitutes for
  payloads visible to OpenWebUI.
- Do not treat generated knowledge packs, local `.codex/` state, venvs, caches
  or job outputs as source documentation.

## Deep References

- Runtime flow: `services/END_TO_END_AGENTIC_FLOW.md`
- Validator contract: `services/VALIDATOR_ONLY_AGENTIC_LOOP_CONTRACT.md`
- Public payload limits: `services/CODEX_OPENWEBUI_PAYLOAD_LIMITATION.md`
- Inline evidence contract: `services/OPENWEBUI_INLINE_EVIDENCE_CONTRACT.md`
- Service map: `services/SERVICES_MODULE_TECHNICAL_REFERENCE.md`
- Per-file map: `services/MODULE_TECHNICAL_DESCRIPTIONS.md`
- MCP guide: `services/codex_bridge/MCP_GUIDE.md`
- MCP contract: `services/codex_bridge/REPO_MCP_CONTRACT.md`
- Runtime env: `docs/runtime_env_contract.md`
- Launcher contract: `docs/launcher_contract.md`
