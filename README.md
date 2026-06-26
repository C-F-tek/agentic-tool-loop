# Agentic Tool Loop Runtime

Local agentic tool loop for OpenWebUI with validator-only controller gate, model-assisted guidance lanes, and inline evidence transport.

**Repository:** `agentic-tool-loop`  
**Branch:** main  
**Last verified:** 2026-06-26

---

## Architecture Overview

This project implements a controlled multi-step agentic loop that bridges OpenWebUI to an internal broker running a planner/validator loop over local Ollama instances. The system is split into three runtime surfaces:

| Surface | Port | Role |
|---------|------|------|
| **3571** — Public bridge | 3571 | OpenWebUI-facing wrapper. Exposes only `vulkan_helper`. Forwards work to 3572, shapes terminal payloads for the external model. |
| **3572** — Internal broker | 3572 | Agentic loop owner. Creates jobs, stores state/events, builds planner prompts, validates model decisions, dispatches tools, writes final artifacts. |
| **11434 / 11435** — Ollama endpoints | 11434 / 11435 | Planner (main) and repair/task (GPU0/Vulkan) model endpoints respectively. |

---

## Canonical Runtime Chain

```
OpenWebUI / external 30B
  -> 3571 vulkan_helper (public bridge)
  -> 3572 /vulkan/agent (internal broker)
  -> 3572 creates job + starts agent_job_worker
  -> 3572 requests controller_preplanner_rag_query_plan from 11434
     -> malformed JSON: 11434 repairs it
     -> unavailable/timeout: controller records typed gap, continues with deterministic preseed only
  -> 11434 planner turn (main model)
     -> 3572 builds measured prompt pack (required_working_set + optional_context)
     -> if prompt > compaction threshold: store large sections in job-local SQLite, inject recursive windows
     -> 3572 validates planner decision against evidence contract
     -> if final candidate for repo/semantic audit: call 11434 final-quality judge
        -> malformed judge JSON: repair/re-evaluate
        -> apply judge route through validator contract
     -> if validator rejection needs specialist guidance: call 11434 replan specialist
        -> malformed specialist JSON: repair
        -> store specialist route in controller guard/evidence contract
     -> if invalid planner decision and repair applies: call 11435 repair/normalize
        -> validate repaired decision
     -> if valid tool decision: dispatch_tool(tool, args)
     -> if valid final decision: finalize_agentic_job(completed)
     -> if terminal block/max/fail: finalize_agentic_job(non-completed terminal)
  -> 3572 returns compact terminal job response to 3571
  -> 3571 rehydrates terminal/final JSON when referenced
  -> 3571 sanitizes local pointers + builds tool_context_for_30b
  -> OpenWebUI receives payload_index_for_30b + priority_evidence_for_30b + pretty JSON tool_context_for_30b
```

---

## Component Details

### 3571 — Public Bridge (`services/vulkan_bridge/`)

- **Entry point:** `services/vulkan_bridge/app.py`
- **Public tool surface:** `vulkan_helper` only (via `OPENWEBUI_VISIBLE_TOOL_ALIASES`)
- **Forwarding:** `_handle_helper()` posts normalized agent payload to `AGENT_URL` (default `http://127.0.0.1:3572/vulkan/agent`)
- **Terminal wrapper:** `_agentic_v9_build_openwebui_response()` returns stable public shape for all terminal states (completed, blocked, max_steps, failed, cancelled)

**Key invariants:**
- OpenWebUI cannot open local paths (`C:\Users\...`, `reads/*.json`, `tool-results/*.json`, SQLite document IDs). Those are internal only.
- Public payload must not require local filesystem access. Real content is transported inline through `tool_context_for_30b.artifacts[*].artifact`.
- `priority_evidence_for_30b` is pointer-first and bounded: metadata, hashes, item locations, small summaries — never duplicate large content.
- Non-ok terminal jobs keep the same public shape as ok jobs; only status/warning metadata inside `openwebui_usage` and `payload_index_for_30b` changes.

### 3572 — Internal Broker (`services/aicarmine_broker/`)

- **Entry point:** `services/aicarmine_broker/app.py` → `agent_entry.agent()` → `agent_job_worker()` → `run_agentic_planner_job()`
- **Planner orchestrator:** `services/aicarmine_broker/planner.py` (3871 lines, compatibility entrypoint)
- **Job persistence:** `services/aicarmine_broker/job_store.py` (filesystem primary, SQLite secondary)
- **Tool registry:** `services/aicarmine_broker/tool_registry.py` (frozen dataclass pattern)
- **Tool dispatch:** `services/aicarmine_broker/application/tool_surface/dispatcher.py`

**Key invariants:**
- The planner decides; the controller validates. The controller does not replace planner reasoning with hidden hard-coded tool sequences or hidden auto-final behavior.
- `done_reason` from Ollama closes a model turn — it does not complete the job by itself. A job reaches `completed` only after the planner emits a valid final decision and the 3572 validator accepts it.
- Filesystem job state (`job.json`, `events.ndjson`) is the operational source of truth. SQLite is a secondary dashboard/index cache.

### 11434 — Main Planner Endpoint

- **URL:** `http://127.0.0.1:11434/api/chat` (from `PLANNER_URL`)
- **Model:** Read from planner env variables or defaults in `services/aicarmine_broker/config/models.py`
- **Payload:** `history`, `turn_memory`, `evidence_contract`, tool schemas, response protocol instructions
- **Transport:** Stream with dual guards — response-header wait and stream-read timeout recording

**Model-assisted guidance lanes (all pass through validator before execution):**
1. **Preplanner RAG query plan** — Before first planner turn: classifies goal semantically, proposes RAG query paths. Malformed JSON repaired by same planner model. Timeout → deterministic preseed only.
2. **Final-quality judge** — For repo/semantic-audit final candidates: accepts, rejects, or returns `continue_required` with `required_next_tool_call`.
3. **Planner replan specialist** — After selected validator rejections: translates rejection into `required_next_progress` and `required_next_tool_call`.

### 11435 — Repair/Task Endpoint (GPU0/Vulkan)

- **URL:** `http://127.0.0.1:11435/api/chat` (from `OLLAMA_TASK_URL`)
- **Purpose:** Selector/repair/normalization paths for malformed planner emissions or invalid non-code-product proposals
- **Boundary:** Does NOT decide job completion. Semantic code-product contract failures (missing rationale, missing complete diff, target not read) remain validator guard feedback — not routed to 11435 repair.

---

## Validator-Only Gate

Every planner decision is checked by `validate_planner_decision_against_evidence()` before dispatch.

**Main checks:**
- Non-existent paths in `repo_read`, `repo_apply_patch`, `repo_write_file`
- `repo_read` on invented basenames not from prior evidence
- `repo_list_files` with `limit` below user request
- `repo_list_files` or `repo_read` outside requested scope
- Repeated identical tool call with same arguments without progress
- `final` before reading truly required files
- `repo_read ok=True` with zero real content

**Controller guard response:** When a decision is invalid, the controller inserts a `controller_guard` event with violations, evidence contract, and rejected decision — then calls the planner again. It does not execute an alternative tool sequence.

---

## Model-Assisted Guidance Lanes

| Lane | Endpoint | Purpose | Repair on malformed JSON |
|------|----------|---------|-------------------------|
| **Preplanner** | 11434 | Classify goal semantically, propose RAG query paths | Same planner model repairs |
| **Final-quality judge** | 11434 | Evaluate final candidates for repo/semantic audit | Same planner model repairs |
| **Planner replan specialist** | 11434 | Translate validator rejection into next required progress | Same planner model repairs |
| **Repair/normalize** | 11435 | Fix malformed planner emissions or invalid tool proposals | GPU0/Vulkan task model |

**Rule:** All guidance lanes produce input to the validator/controller guard — they never auto-dispatch tool calls. A new valid planner output is always required (except for an already-accepted final).

---

## Code Product Lane

For goals requesting diff, unified diff, concrete refactoring, patch proposal, or code product:

**Contract:**
- Target must be read with `repo_read` before proposal
- Planner must call `repo_propose_code_edit` (report-only, no source writes)
- Valid payload requires: `kind=code_edit_proposal`, `target_file`, `edit_kind`, `rationale`, `validation_commands`, complete `unified_diff` or `structured_operations`
- Flags: `source_writes_performed=false`, `patch_application_performed=false`, `manual_review_required=true`

**Violations (typed, not routed to 11435 repair):**
- `missing_code_product_candidate` — goal without valid `repo_propose_code_edit`
- `code_product_payload_not_complete` — preview/summary/artifact path only
- `invalid_code_product_candidate` — diff without markers or unparsable
- `code_product_target_not_read` — target not read via `repo_read` first

---

## Prompt Pack And Compaction

Before each 11434 planner call, 3572 builds a measured prompt pack:

| Section | Content |
|---------|---------|
| **required_working_set** | Real file/diff/result windows needed for next decision. Must have real text, coordinates, full size, hash. |
| **optional_context** | History digest, memory, RAG/chunks, intrinsic context, tool-purpose manifest, budget report |
| **prompt_budget_report** | Real serialized prompt count and budget data |

**Compaction rules:**
- Threshold: `AICARMINE_AGENTIC_PLANNER_PROMPT_COMPACT_RATIO` (default 0.5)
- When exceeded: large sections stored in job-local SQLite, planner receives real recursive windows with `document_id`, `offset`, `has_more_before`, `has_more_after`, `sha256`
- Compaction applies only to planner prompt — terminal `tool_context_for_30b` still transports full inline payloads
- If prompt still over budget after compaction: typed block instead of truncated prompt

---

## Public OpenWebUI Payload Contract

Stable shape across all terminal states:

```json
{
  "ok": true,
  "service": "vulkan_agent",
  "mode": "agent_job_final_waited_compact",
  "required_top_level_keys": ["ok","service","mode","required_top_level_keys","payload_index_for_30b","priority_evidence_for_30b","openwebui_usage","tool_context_for_30b"],
  "payload_index_for_30b": {
    "internal_job_status": {"completed": true, "status": "completed"},
    "concrete_results": [{
      "primary_location": "tool_context_for_30b.artifacts[*].artifact"
    }]
  },
  "priority_evidence_for_30b": {
    "schema": "openwebui.priority_evidence_for_30b.v1",
    "items": [{
      "kind": "code_edit_proposal",
      "target_file": "...",
      "edit_kind": "unified_diff",
      "payload_is_complete": true,
      "content_not_duplicated_here": true
    }]
  },
  "openwebui_usage": {
    "payload_index_field": "payload_index_for_30b",
    "priority_evidence_field": "priority_evidence_for_30b.items",
    "full_tool_evidence_field": "tool_context_for_30b.artifacts[*].artifact"
  },
  "tool_context_for_30b": "{\n  \"artifacts\": [...],\n  \"limits\": [...]\n}"
}
```

**`tool_context_for_30b`** is a pretty-printed JSON string containing real successful tool payloads inline. Local paths, SQLite document IDs, and artifact pointers are never substitutes for visible content.

---

## Internal Tool Surface

Planner selects tools through the 3572 registry only. Key families:

| Family | Tools | Scope |
|--------|-------|-------|
| **Repository inspection** | `repo_status`, `repo_tree`, `repo_search`, `repo_list_files`, `repo_read` | Read-only analysis |
| **Code product (report-only)** | `repo_propose_code_edit` | Diff/refactoring proposals — no source writes |
| **Write/apply (guarded)** | `repo_apply_patch`, `repo_write_file` | Explicit consent required |
| **Validation** | `repo_validate`, `repo_ruff_check`, `repo_pyright_check`, `repo_shellcheck`, `repo_semgrep_scan` | Deterministic adapters |
| **Terminal** | `terminal_run_command_wait`, `terminal_search_files`, `terminal_list_files` | Command execution |
| **Planner memory** | `planner_scratchpad_read`, `planner_scratchpad_write` | Scratchpad storage |
| **Runtime memory** | `runtime_sqlite_memory_search`, `runtime_sqlite_memory_write`, `runtime_sqlite_memory_cleanup` | Selective follow-up only |

**Write-guarded tools:** `repo_apply_patch`, `repo_write_file`, `repo_command`, `terminal_run_command_wait`, `runtime_sqlite_memory_cleanup` — require explicit consent.

---

## MCP Server Inventory

The workspace includes 24+ MCP servers for external tool access:

| Category | Servers | Tools | Purpose |
|----------|---------|-------|---------|
| **Core repository** | `repo_state`, `repo_search_det`, `repo_validate`, `repo_code` | 25 | Health, search, validate, propose/edit |
| **Data & query** | `rag`, `sqlite_readonly`, `project_memory`, `index_bridge` | 19 | RAG search, SQLite queries, memory management |
| **Job & artifacts** | `job_artifact`, `job_view`, `git_readonly` | 23 | Events, final state, tool results, Git history |
| **Operations** | `codex_ops`, `repo_symbol_index`, `test_discovery`, `code_dep_graph` | 29 | MCP inventory, symbols, tests, dependency analysis |
| **Refactoring** | `refactor` | 8 | libcst/rope/bowler-based code transformations |
| **Agent clients** | `local_subagent`, `agentic_loop_client`, `ollama_subagent` | 10 | Subagent execution, GPU Ollama access |
| **Formatting/linting** | `prettier`, `biome`, `ruff`, `eslint`, `black` | — | Cline built-in wrappers |

See `AGENTS.md` section "Available MCP Servers" and `services/MCP_OPERATIONAL_SUMMARY.md` for complete tool lists.

---

## Active Repository Root

The active repository for planner repo tools is `AICARMINE_LAB_REPO`. A job can analyze a lab worktree (e.g., `C:\Users\carmi\AI\lab-worktrees\blender-audio-project-lab`) even when the Codex thread cwd differs.

**Contract invariants:**
- All repo tools resolve paths against `AICARMINE_LAB_REPO`
- `candidate_next_actions` and `validator_admissible_repo_read_paths` derived from same root
- Open Terminal cwd expected to mirror `AICARMINE_LAB_REPO` via `OPEN_TERMINAL_CWD` / `AICARMINE_OPEN_TERMINAL_WORKDIR`

---

## IA Live Control View

3572 exposes an operator-only read-only dashboard:

- **HTML:** `GET /jobs/{job_id}/ia-view`
- **JSON:** `GET /jobs/{job_id}/ia-view.json`

Shows what the planner saw per turn: prompt payload, required working set, intrinsic context, evidence contract, compact tool result, raw rehydrated tool result, validator guard, and terminal `tool_context_for_30b`. Audits payload transport violations (preview-only, metadata-only, artifact-path-only regressions).

---

## Virtual Environments

| Name | Purpose | Primary Tools | Python Path |
|------|---------|---------------|-------------|
| **labtools** | Internal broker, planner, validator, dispatcher | `repo_*`, `planner_*`, `validator_*` | `venvs/labtools/Scripts/python.exe` |
| **codeinterpreter** | Jupyter execution, code analysis | `jupyter_execute`, `code_interpreter` | `venvs/codeinterpreter/Scripts/python.exe` |
| **executor** | Command execution, safe runner | `terminal_run_command_wait`, `repo_command` | `venvs/executor/Scripts/python.exe` |
| **openwebui** | UI dashboard, public API surface | `vulkan_helper`, `openwebui` | `venvs/openwebui/Scripts/python.exe` |
| **openvino** | CPU inference, reranking | `rerank`, `embedding`, `npu` | `venvs/openvino/Scripts/python.exe` |

Activation: `. .\activate-venv.ps1 -tool <tool_name>` or `. .\activate-venv.ps1 -auto`

---

## Key Files Reference

### Entry Points
| File | Role |
|------|------|
| `services/vulkan_bridge/app.py` | Public OpenWebUI bridge surface |
| `services/vulkan_bridge/agentic_v9.py` | Agentic bridge integration (13 lines) |
| `services/aicarmine_broker/app.py` | Internal broker FastAPI entry point |
| `services/aicarmine_broker/planner.py` | Planner/controller facade and high-risk loop entry |
| `services/aicarmine_broker/agent_entry.py` | `/vulkan/agent` route → job worker |

### Application Layer
| File | Role |
|------|------|
| `application/planner/validator.py` | Validator orchestration |
| `application/planner/loop.py` | Agentic loop orchestration |
| `application/planner/agentic_v2.py` | Flat decision table routing |
| `application/planner/evidence_contract_builder.py` | Evidence contract construction |
| `application/planner/goal_classifier.py` | Goal classification |
| `application/evidence/final_quality.py` | Final quality validation |
| `application/code_product/state.py` | Code product state machine |

### Tools Layer
| File | Role |
|------|------|
| `tools/repo_read.py` | File reading |
| `tools/repo_search.py` | Search operations |
| `tools/repo_tree.py` | Tree operations |
| `tools/repo_list_files.py` | File listing |
| `tools/repo_code_product.py` | Code product operations |
| `tools/terminal.py` | Terminal command execution |

### Configuration
| File | Role |
|------|------|
| `config/compatibility.py` | Legacy constants, URL defaults, tool aliases |
| `config/models.py` | Model configuration defaults |
| `config/env_loader.py` | Environment variable parsing |

---

## Diagnostic Checklist

When the flow breaks, prove the failed edge:

1. OpenWebUI sees only `/vulkan_helper` from `3571/openapi.json`.
2. 3571 `/health` reports `agent_url` as `http://127.0.0.1:3572/vulkan/agent`.
3. 3572 `/health` reports expected `planner_url`, `planner_model`, `ollama_task_url`, `ollama_task_model`.
4. A 3572 job has events for `agentic_loop_started`, `planner_request_started`, `planner_decision`, and either `tool_result` or validator rejection.
5. If final exists, `final.json` contains planner final data and structured context.
6. 3571 `POST /vulkan_helper {"action":"result","job_id":"..."}` returns `payload_index_for_30b`, `priority_evidence_for_30b.items[*]`, `openwebui_usage`, and `tool_context_for_30b.artifacts[*].artifact` inline.

---

## Operational Stop Proof

To stop runaway/stuck jobs:

1. Inspect port ownership for `3571`, `3572`, `11434`, `11435`.
2. Match each PID to command line (`aicarmine-vulkan-tool-broker.ps1`, `uvicorn --port 3571`, `ollama-task-vulkan.ps1`, `ollama.exe serve`).
3. To stop GPU0/task repair only: stop `ollama-task-vulkan.ps1` tree and child `ollama.exe` on `11435`.
4. To stop new bridge-launched jobs: stop `aicarmine-vulkan-tool-broker.ps1`/3571 tree. `11434` can remain alive.
5. Verify after stop that `11435` and `3571` are absent from listening ports.

---

## Documentation Index

### Start Here
1. [AGENTS.md](AGENTS.md) — Workspace operating rules
2. [docs/START_HERE_RUNTIME.md](docs/START_HERE_RUNTIME.md) — Guided first-read map
3. [services/VALIDATOR_ONLY_AGENTIC_LOOP_CONTRACT.md](services/VALIDATOR_ONLY_AGENTIC_LOOP_CONTRACT.md) — Core validator/controller contract
4. [services/END_TO_END_AGENTIC_FLOW.md](services/END_TO_END_AGENTIC_FLOW.md) — End-to-end flow with owner matrix
5. [services/MODULE_TECHNICAL_DESCRIPTIONS.md](services/MODULE_TECHNICAL_DESCRIPTIONS.md) — File-by-file technical descriptions
6. [docs/runtime_env_contract.md](docs/runtime_env_contract.md) — Runtime process/env contract
7. [docs/launcher_contract.md](docs/launcher_contract.md) — Launcher responsibilities

### MCP & Operations
8. [services/MCP_OPERATIONAL_SUMMARY.md](services/MCP_OPERATIONAL_SUMMARY.md) — Complete tool inventory, health status, known issues
9. [docs/VENVS_MANAGEMENT.md](docs/VENVS_MANAGEMENT.md) — Virtual environment management

### Refactoring Documentation
10. [docs/REFACTORING_STATUS_CURRENT.md](docs/REFACTORING_STATUS_CURRENT.md) — Refactoring status and module structure
11. [docs/PYTHON_REFACTORING_GUIDE.md](docs/PYTHON_REFACTORING_GUIDE.md) — Python refactoring patterns and case studies
12. [docs/REFACTORING_PROMPT_TEMPLATE.md](docs/REFACTORING_PROMPT_TEMPLATE.md) — Prompt template for refactoring tasks
13. [docs/REFACTORING_QUICK_REFERENCE.md](docs/REFACTORING_QUICK_REFERENCE.md) — Anti-pattern detection checklist, patterns cheat sheet

### Code Flow Diagrams
- [flow.svg](flow.svg) — Root runtime flow
- [services/flow.svg](services/flow.svg) — Services flow
- [services/aicarmine_broker/flow.svg](services/aicarmine_broker/flow.svg) — 3572 broker flow
- [services/vulkan_bridge/flow.svg](services/vulkan_bridge/flow.svg) — 3571 bridge flow

---

## Git Policy

Committed: source code, scripts, contracts, documentation, directory descriptors.  
Excluded: OpenWebUI data, agent job artifacts, virtual environments, model binaries, SQLite databases, generated knowledge stores, logs, payload captures, external lab worktree contents.

Directory descriptors are committed where useful so the project tree remains understandable without importing private or generated data.

### Full Project Structure - (DONT DELETE) 

```
C:\Users\carmi\AI\
├── AGENTS.md                       # Global agent instructions
├── .clinerules/                    # Cline rules directory
│   └── 00-aicarmine-mcp-first.md   # MCP routing rule
├── docs/                           # Documentation
│   ├── REFACTORING_STATUS_CURRENT.md  # ✅ Updated — this document
│   ├── PYTHON_REFACTORING_GUIDE.md
│   ├── REFACTORING_PROMPT_TEMPLATE.md
│   ├── launcher_contract.md
│   ├── runtime_env_contract.md
│   ├── START_HERE_RUNTIME.md
│   └── VENVS_MANAGEMENT.md
├── services/                       # Main services directory
│   ├── __init__.py
│   ├── aicarmine_codex_mcp_server.py
│   ├── aicarmine_codex_ollama_responses_bridge.py
│   ├── aicarmine_vulkan_bridge_server.py
│   ├── aicarmine_vulkan_tool_broker.py
│   ├── MCP_OPERATIONAL_SUMMARY.md
│   ├── MODULE_TECHNICAL_DESCRIPTIONS.md
│   ├── pyproject.toml
│   ├── README.md
│   ├── requirements-agentic-optional.txt
│   ├── run-agent.ps1
│   ├── RUNTIME_SCRIPT_REFERENCE.md
│   ├── SERVICES_MODULE_TECHNICAL_REFERENCE.md
│   ├── set_mcp_env_vars.ps1
│   ├── start-agent.ps1
│   ├── sync-lab-from-main.ps1
│   ├── watch-lab-mirror.ps1
│   ├── aicarmine_broker/           # ✅ Broker module — refactored files here
│   │   ├── __init__.py
│   │   ├── app.py                  # FastAPI entry point (no changes)
│   │   ├── planner.py              # Main orchestrator (3871 lines, no changes)
│   │   ├── planner_loop.py         # Loop execution
│   │   ├── job_store.py            # Job persistence
│   │   ├── job_planner_lab.py      # Lab-specific planner
│   │   ├── tool_contract.py        # Tool contract definitions
│   │   ├── tool_registry.py        # Tool registry (frozen dataclass pattern)
│   │   ├── tool_schemas.py         # Tool schema definitions
│   │   ├── tool_selection.py       # Tool selection logic
│   │   ├── import_refs.py          # Import registry
│   │   ├── config/                 # Configuration
│   │   │   ├── __init__.py
│   │   │   ├── compatibility.py    # Legacy constants (FINAL_QUALITY_ROUTE_TOOLS)
│   │   │   ├── env_loader.py       # Environment variable parsing
│   │   │   └── models.py           # BrokerConfig dataclass (frozen=True)
│   │   ├── application/            # Application layer
│   │   │   ├── planner/            # ✅ Refactored files here
│   │   │   │   ├── evidence_contract_builder.py  # ✅ Refactored — lazy imports
│   │   │   │   ├── agentic_v2.py               # ✅ Refactored — flat decision table
│   │   │   │   ├── decision.py             # Decision building (720 lines, no changes)
│   │   │   │   ├── decision_normalizer.py  # Decision normalization
│   │   │   │   ├── contract_validator.py   # Contract validation
│   │   │   │   ├── planner_loop.py         # Loop execution
│   │   │   │   ├── planner_prompt.py       # Prompt construction
│   │   │   │   ├── planner_helpers.py      # Helper utilities
│   │   │   │   ├── planner_cuda_rewrite.py # CUDA rewrite helpers
│   │   │   │   ├── planner_repair.py       # Vulkan repair logic
│   │   │   │   ├── planner_replan_specialist.py  # Replan specialist
│   │   │   │   ├── planner_validation.py   # Planner validation
│   │   │   │   ├── prompt_budget.py        # Budget management
│   │   │   │   ├── vulkan_repair.py        # Vulkan repair helpers
│   │   │   │   ├── validator.py            # Validator orchestration
│   │   │   │   ├── validator_utils.py      # Validator utilities
│   │   │   │   ├── loop.py                 # Agentic loop orchestration
│   │   │   │   ├── loop_controller.py      # Loop controller
│   │   │   │   ├── judge_lane.py           # Judge lane terminal diagnosis
│   │   │   │   ├── final_quality_validator.py  # Final quality validation
│   │   │   │   ├── code_product_state.py   # Code product state management
│   │   │   │   ├── terminal_output.py      # Terminal output formatting
│   │   │   │   ├── goal_classifier.py      # Goal classification
│   │   │   │   └── modules/                # Planner sub-modules
│   │   │   │       └── replan_specialist.py  # Replan specialist (duplicate)
│   │   │   ├── evidence/             # Evidence building and classification
│   │   │   │   ├── builder.py          # Evidence builder orchestration
│   │   │   │   ├── core_discovery.py   # Core discovery candidate selection
│   │   │   │   ├── execution_digest.py # Execution evidence digest
│   │   │   │   ├── final_quality.py    # Final quality validation
│   │   │   │   ├── goal_classifier.py  # Goal classification
│   │   │   │   ├── goal_scope.py       # Goal scope extraction
│   │   │   │   ├── initial_orientation.py  # Initial orientation surface
│   │   │   │   └── repo_history.py     # Repository history tracking
│   │   │   ├── public_payload/         # ✅ Refactored file here
│   │   │   │   ├── tool_context.py     # ✅ Refactored — flat decision table
│   │   │   │   ├── terminal_result.py  # Terminal result formatting
│   │   │   │   ├── terminal_sanitizer.py  # Terminal sanitization
│   │   │   │   ├── public_wrapper.py   # Public wrapper
│   │   │   │   ├── evidence_materializer.py    # Evidence materialization
│   │   │   │   ├── final_state_result.py       # Final state result formatting
│   │   │   │   ├── history_ledger.py           # History ledger
│   │   │   │   ├── openwebui_terminal_answer.py  # Terminal answer formatting
│   │   │   │   ├── payload_index_resolver.py   # Payload index resolution
│   │   │   │   ├── tool_context.py             # Tool context formatting
│   │   │   │   └── field_names.py              # Field name constants
│   │   │   ├── shared/                 # Shared utilities
│   │   │   │   ├── clean_values.py     # Value cleaning
│   │   │   │   ├── diagnostics.py      # Diagnostics utilities
│   │   │   │   ├── evidence_contract_summary.py  # Evidence contract summary
│   │   │   │   ├── helper.py           # Helper utilities
│   │   │   │   ├── history_ledger.py   # History ledger
│   │   │   │   ├── history_queries.py  # History query utilities
│   │   │   │   ├── job_html.py         # HTML job page generation
│   │   │   │   ├── json_node.py        # JSON node handling
│   │   │   │   ├── memory_tools.py     # Memory tool integration
│   │   │   │   ├── payload_metadata.py # Payload metadata
│   │   │   │   ├── path_tokens.py      # Path token management
│   │   │   │   └── tool_result.py      # Tool result formatting (dataclass slots fix)
│   │   │   ├── tool_surface/           # Tool surface management
│   │   │   │   ├── action_proof_ledger.py  # Action proof ledger
│   │   │   │   ├── batch_contract.py       # Batch contract management
│   │   │   │   ├── candidate_action_gate.py    # Candidate action gating
│   │   │   │   ├── candidate_actions.py    # Candidate action selection
│   │   │   │   ├── dispatcher.py           # Tool dispatch
│   │   │   │   ├── manifest_builder.py     # Manifest building
│   │   │   │   ├── result_compaction.py    # Result compaction
│   │   │   │   ├── result_digest.py        # Result digest formatting
│   │   │   │   ├── required_tool_call.py   # Required tool call tracking
│   │   │   │   └── turn_surface_policy.py  # Turn surface policy
│   │   │   ├── prompt/                 # Prompt construction and management
│   │   │   │   ├── available_tools.py      # Available tools listing
│   │   │   │   ├── budget.py               # Budget management
│   │   │   │   ├── context_windows.py      # Context window management
│   │   │   │   ├── evidence_contract.py    # Evidence contract building
│   │   │   │   ├── evidence_contract_window.py  # Evidence contract windowing
│   │   │   │   ├── history_contract.py     # History contract management
│   │   │   │   ├── history_messages.py     # History message formatting
│   │   │   │   ├── intrinsic_context.py    # Intrinsic context building
│   │   │   │   ├── pack_builder.py         # Pack builder
│   │   │   │   ├── text_windows.py         # Text window management
│   │   │   │   └── values.py               # Value management
│   │   │   ├── controller/             # Controller lane logic
│   │   │   │   ├── guards.py           # Controller guard validation
│   │   │   │   ├── memory.py           # Memory lesson persistence
│   │   │   │   ├── orientation_lane.py # Orientation lane routing
│   │   │   │   ├── preseed.py          # Preseed plan generation
│   │   │   │   ├── rag_preseed.py      # RAG preseed queries
│   │   │   │   └── diagnostics.py      # Runtime diagnostics
│   │   │   ├── code_product/           # Code product state management
│   │   │   │   ├── history.py          # Code product history tracking
│   │   │   │   ├── public_outputs.py   # Public output formatting
│   │   │   │   ├── required_working_set.py # Working set requirements
│   │   │   │   └── state.py            # Code product state machine
│   │   │   ├── job/                    # Job lifecycle management
│   │   │   │   ├── action_router.py    # Action routing to lifecycle states
│   │   │   │   ├── status_response.py  # Status response formatting
│   │   │   │   └── terminal_response.py    # Terminal response formatting
│   │   │   ├── memory/                 # Memory conflict detection
│   │   │   ├── npu_phi/                # NPU phi service integration
│   │   │   ├── replay/                 # Loop replay functionality
│   │   │   └── runtime_debug/          # Runtime debug packet management
│   │   ├── infrastructure/             # Infrastructure layer
│   │   │   ├── command_runner.py       # Command execution
│   │   │   ├── executable_resolver.py  # Executable resolution
│   │   │   ├── filesystem_repo.py      # Filesystem repository access
│   │   │   ├── job_sqlite_store.py     # SQLite job storage
│   │   │   ├── job_store_repository.py # Job store repository
│   │   │   ├── json_files.py           # JSON file I/O
│   │   │   ├── ollama_planner_client.py    # Ollama planner client
│   │   │   ├── repo_tools.py           # Repository tool integration
│   │   │   └── result_compaction.py    # Result compaction
│   │   ├── tools/                      # Tool implementations
│   │   │   ├── command_safety.py       # Command safety checks
│   │   │   ├── deterministic_common.py # Deterministic common utilities
│   │   │   ├── git_surface.py          # Git surface operations
│   │   │   ├── powershell_runner.py    # PowerShell runner
│   │   │   ├── repo_code_product.py    # Code product operations
│   │   │   ├── repo_command.py         # Repository commands
│   │   │   ├── repo_list_files.py      # File listing
│   │   │   ├── repo_patch.py           # Patch application
│   │   │   ├── repo_read.py            # File reading
│   │   │   ├── repo_search.py          # Search operations
│   │   │   ├── repo_semantic_search.py # Semantic search
│   │   │   ├── repo_status.py          # Status reporting
│   │   │   ├── repo_tree.py            # Tree operations
│   │   │   └── repo_validate.py        # Validation operations
│   │   └── planner_core/               # Planner core utilities
│   │       ├── json_io.py              # JSON I/O helpers
│   │       └── cache.py                # Decision caching
│   ├── vulkan_bridge/                  # Vulkan bridge service
│   │   ├── __init__.py
│   │   ├── agentic_v9.py           # ✅ Only 13 lines — already minimal (no changes)
│   │   ├── app.py                  # Vulkan app entry point
│   │   ├── agentic_v2.py           # Agentic v2 logic
│   │   └── ...                       # Other vulkan files
│   ├── codex_bridge/                 # Codex bridge services
│   ├── launch/                       # Launch scripts
│   ├── model_export/                 # Model export utilities
│   ├── npu_phi_service/              # NPU phi service
│   └── tests/                        # Test suite
├── codex_ollama_bridge_applied/      # Applied codex bridge changes
│   ├── AGENTS.md
│   ├── aicarmine_vulkan_bridge_server.py
│   ├── aicarmine_vulkan_tool_broker.py
│   └── ...                           # Other bridge files
├── tools/                            # Standalone tools
│   ├── mechanical_payload_surface_cut.py
│   ├── mechanical_runtime_prune.py
│   └── mechanical_services_dedupe.py
├── indexAI/                          # Index data
├── modelfiles/                       # Ollama model files
├── css/                              # CSS assets
├── git-apply-check-smoke-*/          # Smoke test directories
└── *.ps1, *.py, *.json               # Root-level scripts and configs