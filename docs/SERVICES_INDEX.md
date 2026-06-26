# Services Module — Complete Documentation Index

> **Purpose**: This document provides a complete surface-level index of all Python scripts in the `services/` directory, organized by module and subsystem. Each entry includes purpose, key functions/classes, and cross-references to detailed documentation.

---

## Table of Contents

1. [Broker Module (`aicarmine_broker/`)](#1-broker-module-aicarmine_broker)
2. [Vulkan Bridge (`vulkan_bridge/`)](#2-vulkan-bridge-vulkan_bridge)
3. [Codex Bridge (`codex_bridge/`)](#3-codex-bridge-codex_bridge)
4. [Root-Level Scripts](#4-root-level-scripts)
5. [Codex Ollama Bridge Applied](#5-codex_ollama_bridge_applied)

---

## 1. Broker Module (`aicarmine_broker/`)

The broker module is the core orchestrator for the AI agent loop. It manages job lifecycle, planner decisions, tool execution, evidence building, and prompt construction.

### 1.1 Entry Points

| File | Purpose | Key Functions/Classes |
|------|---------|----------------------|
| `app.py` | FastAPI entry point | `create_app()`, lifespan context manager |
| `planner.py` | Main orchestrator (thin wrapper) | Delegates to `application/planner/*.py` |
| `planner_loop.py` | Loop execution entry | `run_agentic_planner_job()` |
| `job_store.py` | Job persistence layer | `JobStore`, SQLite operations |
| `job_planner_lab.py` | Lab-specific planner config | `LabPlannerConfig` |
| `import_refs.py` | Import registry | Module import mappings |

### 1.2 Configuration (`config/`)

| File | Purpose | Key Functions/Classes |
|------|---------|----------------------|
| `__init__.py` | Config package init | Re-exports from submodules |
| `models.py` | BrokerConfig dataclass (frozen=True) | `BrokerConfig` with all config fields |
| `env_loader.py` | Environment variable parsing | Parse `AICARMINE_*` env vars |
| `compatibility.py` | Legacy constants | `FINAL_QUALITY_ROUTE_TOOLS` re-export |
| `entry_points_config.py` | Entry point configuration | Entry point mappings |

### 1.3 Domain Layer (`domain/`)

| File | Purpose | Key Functions/Classes |
|------|---------|----------------------|
| `__init__.py` | Domain package init | — |
| `config.py` | Domain config types | Value objects for configuration |
| `decisions.py` | Decision domain model | `Decision`, `DecisionPath` |
| `errors.py` | Domain error types | Custom exception hierarchy |
| `evidence.py` | Evidence domain model | `EvidenceRecord`, evidence types |
| `job.py` | Job domain model | `JobState`, job lifecycle states |
| `models.py` | Shared domain models | Common value objects |
| `results.py` | Result domain model | `ToolResultDomain`, result types |
| `tool.py` | Tool domain model | `ToolDefinition`, tool metadata |

### 1.4 Contracts (`contracts/`)

| File | Purpose | Key Functions/Classes |
|------|---------|----------------------|
| `__init__.py` | Contracts package init | — |
| `command_runner.py` | Command runner contract | Protocol/interface |
| `dispatcher.py` | Dispatcher contract | Tool dispatch protocol |
| `job_repository.py` | Job repository contract | CRUD operations interface |
| `planner_client.py` | Planner client contract | LLM client protocol |
| `prompt_store.py` | Prompt store contract | Prompt persistence interface |
| `repo_filesystem.py` | Repo filesystem contract | File operations interface |
| `tool.py` | Tool contract | Tool execution protocol |
| `validator.py` | Validator contract | Validation protocol |

### 1.5 Application Layer (`application/`)

#### 1.5.1 Planner (`application/planner/`)

Core planner logic: decision building, loop control, validation, lane routing.

| File | Purpose | Key Functions/Classes |
|------|---------|----------------------|
| `agentic_v2.py` | Agentic v2 decision paths | `_TOOL_PATH_KEYS`, flat decision table |
| `code_product_state.py` | Code product state management | State transitions |
| `contract_validator.py` | Contract validation | Validates tool contracts |
| `decision.py` | Decision building (720 lines) | Decision construction logic |
| `decision_normalizer.py` | Decision normalization | Normalizes decision formats |
| `evidence_contract_builder.py` | Evidence contract construction | Lazy imports, single import block |
| `final_quality_validator.py` | Final quality checks | Quality gate validation |
| `goal_classifier.py` | Goal classification | Classifies agent goals |
| `guard_evaluator.py` | Guard evaluation | Evaluates safety guards |
| `judge_lane.py` | Judge lane terminal diagnosis | Diagnoses terminal issues |
| `lane_authority.py` | Lane authority management | Lane permission checks |
| `lane_catalog.py` | Lane catalog | Lane registry |
| `loop.py` | Agentic loop orchestration | Loop control flow |
| `loop_controller.py` | Loop controller | Manages loop iterations |
| `planner_cuda_rewrite.py` | CUDA rewrite helpers | CUDA environment rewrites |
| `planner_decision.py` | Planner decision implementation | `_planner_decision_impl()` |
| `planner_helpers.py` | Helper utilities | Common planner helpers |
| `planner_loop.py` | Run agentic planner job | Main loop execution function |
| `planner_prompt.py` | Prompt construction | Builds system/user prompts |
| `planner_repair.py` | Vulkan repair logic | Repair/replan strategies |
| `planner_replan_specialist.py` | Replan specialist logic | Replan decision making |
| `planner_validation.py` | Planner validation | Validates planner output |
| `prompt_budget.py` | Budget management | Context budget tracking |
| `required_progress.py` | Required progress tracking | Progress measurement |
| `route_validator.py` | Route validation | Validates lane routing |
| `state.py` | Planner state | Planner state machine |
| `status.py` | Status management | Status code handling |
| `system_prompt.py` | System prompt building | Constructs system prompts |
| `terminal_output.py` | Terminal output formatting | Formats terminal output |
| `turn.py` | Turn management | Turn lifecycle |
| `validation_rejections.py` | Validation rejection handling | Rejection reasons |
| `validator.py` | Validator orchestration | Main validator coordinator |
| `validator_utils.py` | Validator utilities | Helper functions for validators |
| `vulkan_repair.py` | Vulkan repair helpers | Repair utility functions |

##### Sub-modules (`application/planner/modules/`)

| File | Purpose | Key Functions/Classes |
|------|---------|----------------------|
| `__init__.py` | Modules package init | — |
| `replan_specialist.py` | Replan specialist (duplicate) | Replan logic |

##### Validator sub-directory (`application/planner/validator/`)

| File | Purpose | Key Functions/Classes |
|------|---------|----------------------|
| `__init__.py` | Validator package init | — |
| `_discover_entry_points.py` | Entry point discovery | Dynamic validator loading |
| `action_validators.py` | Action validators | Validates actions |
| `contract_utils.py` | Contract utilities | Contract helper functions |
| `final_quality_route.py` | Final quality route | Quality route validation |
| `path_utilis.py` | Path utilities | Path manipulation helpers |
| `rewrite_latch.py` | Rewrite latch | Rewrite state management |
| `validate_decision.py` | Decision validation | Validates individual decisions |

#### 1.5.2 Evidence (`application/evidence/`)

Evidence building and classification for agent decision-making.

| File | Purpose | Key Functions/Classes |
|------|---------|----------------------|
| `__init__.py` | Evidence package init | — |
| `audit_guidance.py` | Audit guidance | Audit trail building |
| `builder.py` | Evidence builder orchestration | Main evidence builder |
| `core_discovery.py` | Core discovery candidates | Candidate selection |
| `coverage_scorer.py` | Coverage scoring | Test coverage metrics |
| `entry_point_analyzer.py` | Entry point analysis | Analyzes entry points |
| `entry_point_info.py` | Entry point info | Entry point metadata |
| `execution_digest.py` | Execution evidence digest | Digests execution results |
| `final_quality.py` | Final quality validation | Quality gate checks |
| `goal_classifier.py` | Goal classification | Classifies goals |
| `goal_scope.py` | Goal scope extraction | Extracts goal scope |
| `initial_orientation.py` | Initial orientation surface | Orientation discovery |
| `repo_history.py` | Repository history tracking | Git history analysis |
| `repo_path_policy.py` | Repo path policy | Path policy rules |
| `required_working_set.py` | Required working set | Working set requirements |
| `scope_conflict_resolution.py` | Scope conflict resolution | Resolves scope conflicts |
| `user_scope_claims.py` | User scope claims | User-provided scope |

#### 1.5.3 Tool Surface (`application/tool_surface/`)

Tool dispatch, manifest building, result compaction, and turn surface policy.

| File | Purpose | Key Functions/Classes |
|------|---------|----------------------|
| `__init__.py` | Tool surface package init | — |
| `action_proof_ledger.py` | Action proof ledger | Tracks action proofs |
| `batch_contract.py` | Batch contract management | Batch operations |
| `candidate_action_gate.py` | Candidate action gating | Gates candidate actions |
| `candidate_actions.py` | Candidate action selection | Selects candidate tools |
| `dispatcher.py` | Tool dispatch | Dispatches tool calls |
| `manifest_builder.py` | Manifest building | Builds tool manifests |
| `required_tool_call.py` | Required tool call tracking | Tracks required calls |
| `result_compaction.py` | Result compaction | Compacts results |
| `result_digest.py` | Result digest formatting | Formats result digests |
| `tool_dispatch.py` | Tool dispatch (detailed) | Detailed dispatch logic |
| `turn_surface_policy.py` | Turn surface policy | Policy for turn surfaces |

#### 1.5.4 Prompt (`application/prompt/`)

Prompt construction, context windows, history management, and budget tracking.

| File | Purpose | Key Functions/Classes |
|------|---------|----------------------|
| `__init__.py` | Prompt package init | — |
| `available_tools.py` | Available tools listing | Lists available tools |
| `budget.py` | Budget management | Context budget tracking |
| `context_windows.py` | Context window management | Window size management |
| `evidence_contract.py` | Evidence contract building | Builds evidence contracts |
| `evidence_contract_window.py` | Evidence contract windowing | Windows evidence contracts |
| `history_contract.py` | History contract management | Manages history contracts |
| `history_messages.py` | History message formatting | Formats history messages |
| `intrinsic_context.py` | Intrinsic context building | Builds intrinsic context |
| `pack_builder.py` | Pack builder | Packs messages together |
| `text_windows.py` | Text window management | Text window handling |
| `tool_contract.py` | Tool contract (prompt) | Prompt-level tool contracts |
| `values.py` | Value management | Value handling utilities |
| `window_signatures.py` | Window signatures | Window signature generation |

#### 1.5.5 Public Payload (`application/public_payload/`)

Payload formatting for OpenWebUI, terminal results, and evidence materialization.

| File | Purpose | Key Functions/Classes |
|------|---------|----------------------|
| `__init__.py` | Public payload package init | — |
| `evidence_materializer.py` | Evidence materialization | Materializes evidence payloads |
| `field_names.py` | Field name constants | Constants for field names |
| `final_state_result.py` | Final state result formatting | Formats final results |
| `history_ledger.py` | History ledger | Ledger for history |
| `openwebui_terminal_answer.py` | Terminal answer formatting | OpenWebUI terminal answers |
| `payload_index_resolver.py` | Payload index resolution | Resolves payload indices |
| `terminal_context_rows.py` | Terminal context rows | Terminal context formatting |
| `terminal_result.py` | Terminal result formatting | Formats terminal results |
| `terminal_sanitizer.py` | Terminal sanitization | Sanitizes terminal output |
| `tool_context.py` | Tool context formatting | Flat decision table, lookup dispatch |

##### Sub-directory (`application/public_payload/lab/`)

| File | Purpose | Key Functions/Classes |
|------|---------|----------------------|
| `__init__.py` | Lab package init | — |
| `openwebui_tool_context.py` | OpenWebUI tool context | Tool context for OpenWebUI |

#### 1.5.6 Shared (`application/shared/`)

Shared utilities: JSON handling, history queries, memory tools, path tokens, diagnostics.

| File | Purpose | Key Functions/Classes |
|------|---------|----------------------|
| `__init__.py` | Shared package init | — |
| `clean_values.py` | Value cleaning | Cleans string values |
| `diagnostics.py` | Diagnostics utilities | Diagnostic helpers |
| `evidence_builder.py` | Evidence builder (shared) | Shared evidence building |
| `evidence_contract_summary.py` | Evidence contract summary | Summarizes contracts |
| `helper.py` | Helper utilities | Common helper functions |
| `history_ledger.py` | History ledger (shared) | Shared history ledger |
| `history_queries.py` | History query utilities | Query history data |
| `job_html.py` | HTML job page generation | Generates HTML pages |
| `json_node.py` | JSON node handling | JSON tree navigation |
| `memory_tools.py` | Memory tool integration | Memory MCP integration |
| `path_tokens.py` | Path token management | Path token handling |
| `payload_metadata.py` | Payload metadata | Metadata extraction |
| `tool_result.py` | Tool result formatting | Dataclass slots fix, `ToolResult`, `PromptWindow` |
| `validation_utils.py` | Validation utilities | Validation helpers |

#### 1.5.7 Job (`application/job/`)

Job lifecycle management: action routing, status/response, terminal output.

| File | Purpose | Key Functions/Classes |
|------|---------|----------------------|
| `__init__.py` | Job package init | — |
| `action_router.py` | Action routing to lifecycle states | `_ACTION_ROUTE_MAP` lookup dispatch |
| `lifecycle.py` | Job lifecycle states | State definitions |
| `response_values.py` | Response value formatting | Formats response values |
| `selector_runner.py` | Selector runner | Runs tool selectors |
| `status_response.py` | Status response formatting | Formats status responses |
| `terminal_response.py` | Terminal response formatting | Formats terminal responses |
| `wait_response.py` | Wait response handling | Handles wait responses |
| `worker.py` | Worker management | Manages job workers |

#### 1.5.8 Controller (`application/controller/`)

Controller lane logic: guards, memory persistence, orientation routing, preseed plans.

| File | Purpose | Key Functions/Classes |
|------|---------|----------------------|
| `__init__.py` | Controller package init | — |
| `diagnostics.py` | Runtime diagnostics | Runtime debug info |
| `guards.py` | Controller guard validation | Validates controller guards |
| `memory.py` | Memory lesson persistence | Persists memory lessons |
| `orientation_lane.py` | Orientation lane routing | Routes to orientation |
| `preseed.py` | Preseed plan generation | Generates preseed plans |
| `rag_preseed.py` | RAG preseed queries | Queries RAG for preseed |

#### 1.5.9 Code Product (`application/code_product/`)

Code product state management: history tracking, public outputs, working set requirements.

| File | Purpose | Key Functions/Classes |
|------|---------|----------------------|
| `__init__.py` | Code product package init | — |
| `history.py` | Code product history tracking | Tracks code changes |
| `public_outputs.py` | Public output formatting | Formats public outputs |
| `required_working_set.py` | Working set requirements | Defines working set needs |
| `state.py` | Code product state machine | State machine for code products |

#### 1.5.10 Memory (`application/memory/`)

Memory conflict detection and resolution.

| File | Purpose | Key Functions/Classes |
|------|---------|----------------------|
| `__init__.py` | Memory package init | — |
| `conflict_detector.py` | Memory conflict detection | Detects conflicts |

#### 1.5.11 NPU Phi (`application/npu_phi/`)

NPU phi service integration for GPU acceleration.

| File | Purpose | Key Functions/Classes |
|------|---------|----------------------|
| `__init__.py` | NPU phi package init | — |
| `client.py` | NPU phi client | Client for NPU service |
| `policy.py` | NPU phi policy | Policy configuration |

#### 1.5.12 Replay (`application/replay/`)

Loop replay functionality for debugging and testing.

| File | Purpose | Key Functions/Classes |
|------|---------|----------------------|
| `__init__.py` | Replay package init | — |
| `loop_replay.py` | Loop replay logic | Replays agent loops |

#### 1.5.13 Runtime Debug (`application/runtime_debug/`)

Runtime debug packet management.

| File | Purpose | Key Functions/Classes |
|------|---------|----------------------|
| `__init__.py` | Runtime debug package init | — |
| `debug_packet.py` | Debug packet management | Manages debug packets |

#### 1.5.14 Search (`application/search/`)

Search quality metrics and evaluation.

| File | Purpose | Key Functions/Classes |
|------|---------|----------------------|
| `__init__.py` | Search package init | — |
| `search_quality.py` | Search quality metrics | Quality scoring |

#### 1.5.15 Command (`application/command/`)

Command execution policy and control.

| File | Purpose | Key Functions/Classes |
|------|---------|----------------------|
| `__init__.py` | Command package init | — |
| `execution_policy.py` | Execution policy | Command execution rules |

### 1.6 Infrastructure (`infrastructure/`)

Infrastructure layer: command execution, repository access, job storage, JSON I/O.

| File | Purpose | Key Functions/Classes |
|------|---------|----------------------|
| `__init__.py` | Infrastructure package init | — |
| `command_runner.py` | Command execution | Runs shell commands |
| `executable_resolver.py` | Executable resolution | Resolves executables |
| `filesystem_repo.py` | Filesystem repository access | File operations |
| `job_sqlite_store.py` | SQLite job storage | SQLite persistence |
| `job_store_repository.py` | Job store repository | Repository pattern for jobs |
| `json_files.py` | JSON file I/O | JSON read/write operations |
| `ollama_planner_client.py` | Ollama planner client | LLM client wrapper |
| `repo_tools.py` | Repository tool integration | Integrates repo tools |
| `result_compaction.py` | Result compaction (infra) | Infrastructure compaction |
| `time_provider.py` | Time provider | Time utilities |

### 1.7 Tools (`tools/`)

Tool implementations: git operations, PowerShell runner, repository commands, search, patching.

| File | Purpose | Key Functions/Classes |
|------|---------|----------------------|
| `__init__.py` | Tools package init | — |
| `command_safety.py` | Command safety checks | Validates command safety |
| `deterministic_common.py` | Deterministic common utilities | Shared deterministic helpers |
| `git_surface.py` | Git surface operations | Git operations wrapper |
| `powershell_runner.py` | PowerShell runner | Runs PowerShell commands |
| `repo_code_product.py` | Code product operations | Code product manipulation |
| `repo_command.py` | Repository commands | Generic repo commands |
| `repo_deterministic.py` | Deterministic repo operations | Deterministic operations |
| `repo_list_files.py` | File listing | Lists directory files |
| `repo_patch.py` | Patch application | Applies unified diffs |
| `repo_read.py` | File reading | Reads repository files |
| `repo_search.py` | Search operations | Searches repository files |
| `repo_semantic_search.py` | Semantic search | RAG-based semantic search |
| `repo_status.py` | Status reporting | Reports repo status |
| `repo_tree.py` | Tree operations | Directory tree traversal |
| `repo_validate.py` | Validation operations | Validates repository state |
| `terminal.py` | Terminal operations | Terminal I/O handling |

### 1.8 Planner Core (`planner_core/`)

Planner core utilities: JSON I/O, caching, RAG cache management.

| File | Purpose | Key Functions/Classes |
|------|---------|----------------------|
| `__init__.py` | Planner core package init | — |
| `cache.py` | Decision caching | Caches planner decisions |
| `json_io.py` | JSON I/O helpers | JSON serialization helpers |
| `rag_cache_manager.py` | RAG cache manager | Manages RAG cache |
| `README.md` | Planner core documentation | Architecture overview |

### 1.9 Top-Level Files

| File | Purpose | Key Functions/Classes |
|------|---------|----------------------|
| `__init__.py` | Broker package init | — |
| `agent_entry.py` | Agent entry point | Entry for agent invocation |
| `app.py` | FastAPI entry point | Creates FastAPI app |
| `code_edit_proposal_contract.py` | Code edit proposal contract | Proposal validation |
| `import_refs.py` | Import registry | Module import mappings |
| `job_html.py` | Job HTML generation | Generates job HTML pages |
| `job_html_assets.py` | Job HTML assets | Asset management |
| `job_planner_lab.py` | Lab-specific planner | Lab planner configuration |
| `job_store.py` | Job persistence | Job store implementation |
| `planner.py` | Main orchestrator (thin wrapper) | Delegates to application layer |
| `planner_loop.py` | Loop execution entry | Main loop function |
| `tool_contract.py` | Tool contract definitions | Tool contract protocol |
| `tool_registry.py` | Tool registry (frozen dataclass pattern) | Registry with frozen dataclasses |
| `tool_schemas.py` | Tool schema definitions | Schema for tool inputs |
| `tool_selection.py` | Tool selection logic | Selects appropriate tools |

---

## 2. Vulkan Bridge (`vulkan_bridge/`)

Vulkan bridge service: handles GPU-accelerated operations via Vulkan.

| File | Purpose | Key Functions/Classes |
|------|---------|----------------------|
| `__init__.py` | Vulkan bridge package init | — |
| `agentic_v9.py` | Agentic v9 logic (13 lines, already minimal) | Minimal entry point |
| `agentic_v2.py` | Agentic v2 logic | V2 agentic operations |
| `app.py` | Vulkan app entry point | FastAPI app for Vulkan |

---

## 3. Codex Bridge (`codex_bridge/`)

Codex bridge services: connects to external Codex providers.

> See `codex_ollama_bridge_applied/codex_ollama_bridge/` for detailed documentation.

---

## 4. Root-Level Scripts

| File | Purpose | Key Functions/Classes |
|------|---------|----------------------|
| `audit_mcp_allowlist.py` | Audit MCP allowlist | Validates allowlist entries |
| `check_existing_profiles.py` | Check existing profiles | Profile verification |
| `debug_profiles.py` | Debug profiles | Profile debugging |
| `find_deps_config.py` | Find dependency config | Dependency resolution |
| `probe_mcp_raw.py` | Probe MCP raw | Raw MCP probing |
| `probe_r4r.py` | Probe R4R | R4R probing |
| `test_mcp_client.py` | Test MCP client | Client testing |
| `verify_changes.py` | Verify changes | Change verification |

---

## 5. Codex Ollama Bridge Applied (`codex_ollama_bridge_applied/`)

Applied changes for Codex + Ollama integration.

### 5.1 Core Files

| File | Purpose | Key Functions/Classes |
|------|---------|----------------------|
| `aicarmine_vulkan_bridge_server.py` | Vulkan bridge server | Server implementation |
| `aicarmine_vulkan_tool_broker.py` | Vulkan tool broker | Tool broker logic |
| `export_model.py` | Model export | Exports Ollama models |

### 5.2 Codex Bridge (`codex_ollama_bridge/codex_ollama_bridge/`)

| File | Purpose | Key Functions/Classes |
|------|---------|----------------------|
| `aicarmine_codex_mcp_server.py` | Codex MCP server | MCP server implementation |
| `aicarmine_codex_ollama_responses_bridge.py` | Responses bridge | Bridges responses |

### 5.3 Useful Tools (`useful_tools/`)

Extensive utility library for context management, memory, RAG, and agent operations.

| Directory | Purpose |
|-----------|---------|
| `chunks/` | Code and evidence chunking utilities |
| `context/` | Agent context management |
| `memory/` | Agent memory operations |

---

## Documentation Quick Reference

### Refactoring & Technical Guides

| Document | Description |
|----------|-------------|
| `PYTHON_REFACTORING_GUIDE.md` | Comprehensive refactoring guide with anti-patterns and case studies |
| `REFACTORING_STATUS_CURRENT.md` | Current state of refactoring work and verification results |
| `REFACTORING_PROMPT_TEMPLATE.md` | Template for AI-assisted refactoring prompts |
| `REFACTORING_QUICK_REFERENCE.md` | Quick reference for refactoring techniques |
| `launcher_contract.md` | Launcher service contract (ports 3571, 3572) |
| `runtime_env_contract.md` | Runtime environment contract |
| `START_HERE_RUNTIME.md` | Getting started with runtime |
| `VENVS_MANAGEMENT.md` | Virtual environment management |

### Module README Files (New — Complete Surface Documentation)

#### Broker Module (`services/aicarmine_broker/`)

| Document | Location |
|----------|----------|
| Broker Overview | [README](../services/aicarmine_broker/README.md) |
| Config | [README](../services/aicarmine_broker/config/README.md) |
| Tools | [README](../services/aicarmine_broker/tools/README.md) |
| Infrastructure | [README](../services/aicarmine_broker/infrastructure/README.md) |
| Application Layer | [README](../services/aicarmine_broker/application/README.md) |
| Domain | [README](../services/aicarmine_broker/domain/README.md) |
| Contracts | [README](../services/aicarmine_broker/contracts/README.md) |
| Planner Modules | [README](../services/aicarmine_broker/application/planner/modules/README.md) |
| Planner Validator | [README](../services/aicarmine_broker/application/planner/validator/README.md) |
| Public Payload Lab | [README](../services/aicarmine_broker/application/public_payload/lab/README.md) |
| Planner Core | [README](../services/aicarmine_broker/planner_core/README.md) |

#### Application Sub-Modules

| Document | Location |
|----------|----------|
| Evidence | [README](../services/aicarmine_broker/application/evidence/README.md) |
| Tool Surface | [README](../services/aicarmine_broker/application/tool_surface/README.md) |
| Prompt | [README](../services/aicarmine_broker/application/prompt/README.md) |
| Controller | [README](../services/aicarmine_broker/application/controller/README.md) |
| Code Product | [README](../services/aicarmine_broker/application/code_product/README.md) |
| Job | [README](../services/aicarmine_broker/application/job/README.md) |
| Memory | [README](../services/aicarmine_broker/application/memory/README.md) |
| NPU Phi | [README](../services/aicarmine_broker/application/npu_phi/README.md) |
| Replay | [README](../services/aicarmine_broker/application/replay/README.md) |
| Runtime Debug | [README](../services/aicarmine_broker/application/runtime_debug/README.md) |
| Search | [README](../services/aicarmine_broker/application/search/README.md) |
| Command | [README](../services/aicarmine_broker/application/command/README.md) |

#### Other Services

| Document | Location |
|----------|----------|
| Vulkan Bridge | [README](../services/vulkan_bridge/README.md) |
| Codex Bridge | [README](../services/codex_bridge/README.md) |
| Launch Scripts | [README](../services/launch/README.md) |
| Model Export | [README](../services/model_export/README.md) |
| NPU Phi Service | [README](../services/npu_phi_service/README.md) |
| Tests | [README](../services/tests/README.md) |
| Codex Ollama Applied | [README](../codex_ollama_bridge_applied/README.md) |
| Codex Ollama Bridge | [README](../codex_ollama_bridge_applied/codex_ollama_bridge/README.md) |

---

*Generated from analysis of the C:\Users\carmi\AI workspace.*
