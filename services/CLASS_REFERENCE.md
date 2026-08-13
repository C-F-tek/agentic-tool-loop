# Class Reference

**Last updated:** 2026-08-13

## Overview

This document provides detailed descriptions of the key classes across the `services/` directory, their responsibilities, and their relationships.

---

## aicarmine_broker Classes

### Entry Point Classes

#### `AgentJobWorker` (application/job/worker.py)

**Purpose:** Background job execution orchestrator

**Fields:**
- `load_state`: Load job state from persistence
- `write_state`: Write job state to persistence
- `append_event`: Append event to job event log
- `agent_job_root`: Function returning job directory path
- `write_json`: JSON write utility
- `planner_runner`: Agentic planner execution function
- `agent_runner`: Legacy agent runner function
- `summary_from_result`: Terminal summary builder
- `agentic_planner_enabled`: Boolean flag for planner mode
- `agentic_fallback_oneshot`: Boolean flag for legacy fallback
- `terminal_finalizer`: Optional terminal finalization function
- `legacy_oneshot_timeout_seconds`: Timeout for legacy one-shot mode

**Methods:**
- `run(job_id)`: Execute a background job. Loads state, sets status to running, runs planner or legacy one-shot, handles failures.
- `_run_legacy_oneshot(job_id, state)`: Run legacy one-shot agent execution
- `_write_failure(job_id, state, exc)`: Write failure state and events

**Responsibilities:**
- Orchestrate single background job execution
- Coordinate between state management and planner/agent execution
- Handle both agentic planner mode and legacy one-shot fallback
- Write failure events when exceptions occur

---

#### `AgentJobLifecycle` (application/job/lifecycle.py)

**Purpose:** Job creation and lifecycle management

**Fields:**
- `init_agent_job_db`: Initialize job database
- `make_session_id`: Generate session/job IDs
- `agent_job_root`: Return job directory path
- `write_state`: Write job state
- `append_event`: Append job events
- `job_url`: Generate job URL
- `wait_for_terminal`: Wait for job completion
- `worker`: Background worker function
- `background_threads`: Thread registry
- `lock`: Job lock for concurrency control
- `agent_default_max_steps`: Default max steps per job
- `approval_mode`: Approval mode setting
- `return_wait_seconds`: Wait time for return mode
- `agentic_planner_enabled`: Planner enabled flag
- `planner_url`: Planner endpoint URL
- `planner_model`: Planner model name
- `selector_url`: Selector endpoint URL
- `selector_model`: Selector model name
- `thread_factory`: Thread factory function
- `now`: Time function
- `uuid_token`: UUID token generator

**Methods:**
- `start(payload, public_tool_name, original_args, task)`: Create and start a new agent job. Generates job ID, creates state, launches background worker thread.

**Responsibilities:**
- Create new agent jobs with proper state initialization
- Manage job ID generation and session management
- Launch background worker threads
- Handle return modes (wait, background, async)
- Coordinate with planner and selector endpoints

---

#### `AgentJobActionRouter` (application/job/action_router.py)

**Purpose:** Route job actions to appropriate handlers

**Responsibilities:**
- Route planner lab apply/compose actions
- Dispatch tool calls from planner lab UI
- Append events for planner lab operations

---

#### `SelectorRunner` (application/job/selector_runner.py)

**Purpose:** Run tool selector operations

**Responsibilities:**
- Execute tool selection logic
- Run internal tool selectors
- Handle selector fallback tools

---

### Application Layer Classes

#### Dispatcher (`application/dispatcher.py`)

**Purpose:** Main dispatch logic for incoming requests

**Key responsibilities:**
- Route incoming payloads to appropriate handlers
- Coordinate between planner and direct tool execution
- Manage evidence collection flow

---

#### Controller Memory (`application/controller/memory.py`)

**Purpose:** Controller-level memory management

**Key responsibilities:**
- Manage controller state across turns
- Track orientation decisions
- Maintain evidence history

---

### Code Product Classes

#### Public Outputs (`application/code_product/public_outputs.py`)

**Purpose:** Generate public-facing output from code products

**Key responsibilities:**
- Build terminal summaries
- Format code product results
- Generate public payload structures

---

#### History (`application/code_product/history.py`)

**Purpose:** Query and manage job history

**Key responsibilities:**
- Retrieve historical job data
- Build step summaries
- Extract code product states

---

### Evidence Builder (`application/evidence/builder.py`)

**Purpose:** Build evidence collections for jobs

**Key responsibilities:**
- Collect runtime evidence
- Format evidence for terminal output
- Build evidence chains for diagnosis

---

### Memory Management Classes

#### Agent State (`application/memory/agent_state.py`)

**Purpose:** Manage agent state persistence

**Key responsibilities:**
- Load/save agent state
- Track agent session data
- Manage state transitions

---

#### Agent Memory Policy (`application/memory/agent_memory_policy.py`)

**Purpose:** Define memory policy rules

**Key responsibilities:**
- Determine what gets persisted
- Apply memory retention policies
- Manage memory routing decisions

---

#### Agent Memory Routing Policy (`application/memory/agent_memory_routing_policy.py`)

**Purpose:** Route memory operations based on context

**Key responsibilities:**
- Route memory reads/writes to appropriate stores
- Apply routing rules based on job context
- Manage persistent vs operational memory

---

### Planner Classes

#### Planning Loop (`application/planner/loop.py`)

**Purpose:** Execute the agentic planning loop

**Key responsibilities:**
- Run planning iterations
- Coordinate tool selection and execution
- Manage step-by-step planning flow

---

#### Turn Management (`application/planner/turn.py`)

**Purpose:** Manage planning turns

**Key responsibilities:**
- Track turn state
- Manage turn boundaries
- Handle turn completion

---

#### Decision Normalizer (`application/planner/decision_normalizer.py`)

**Purpose:** Normalize planner decisions

**Key responsibilities:**
- Standardize decision formats
- Validate decision structures
- Convert between decision representations

---

#### Validator (`application/planner/validator.py`)

**Purpose:** Validate planning operations

**Key responsibilities:**
- Validate planner configurations
- Check planning constraints
- Ensure planning validity

---

### Public Payload Classes

#### Evidence Materializer (`application/public_payload/evidence_materializer.py`)

**Purpose:** Convert internal evidence to public format

**Key responsibilities:**
- Transform evidence data structures
- Build public evidence payloads
- Format evidence for external consumption

---

#### Payload Index Resolver (`application/public_payload/payload_index_resolver.py`)

**Purpose:** Resolve payload indices

**Key responsibilities:**
- Map payload indices to data
- Resolve index references
- Build index structures

---

#### Lab Payloads (`application/public_payload/lab/`)

**Purpose:** Planner lab payload construction

**Key functions:**
- `build_planner_lab_apply_tool_call`: Build apply tool call
- `build_planner_lab_compose_request`: Build compose request
- `build_planner_payload_lab`: Build full lab payload
- `parse_planner_lab_compose_response`: Parse compose responses

---

### Command Execution Classes

#### Execution Policy (`application/command/execution_policy.py`)

**Purpose:** Define command execution policies

**Key responsibilities:**
- Validate commands against policy
- Determine execution safety
- Apply execution constraints

---

## codex_bridge MCP Server Classes

### Main MCP Servers

#### `McpServer` (mcp_server.py)

**Purpose:** Main MCP server entry point

**Responsibilities:**
- Initialize and manage MCP tool registry
- Handle JSON-RPC requests
- Route tool calls to appropriate handlers

---

#### `BrokerPlannerMcpServer` (broker_planner_mcp_server.py)

**Purpose:** Broker planner integration via MCP

**Responsibilities:**
- Expose planner operations as MCP tools
- Connect to broker 3572
- Handle planner job management

---

#### `AgenticLoopClientMcpServer` (agentic_loop_client_mcp_server.py)

**Purpose:** Agentic loop client interface

**Responsibilities:**
- Provide client interface to agentic loop
- Health checking for broker
- Job status and result retrieval

---

#### `LocalSubagentMcpServer` (local_subagent_mcp_server.py)

**Purpose:** Local subagent facade

**Responsibilities:**
- Run bounded read-only subagent tasks
- Provide safe subagent execution environment
- Enforce no-loop guarantees

---

#### `RepoCodeMcpServer` (repo_code_mcp_server.py)

**Purpose:** Repository code operations via MCP

**Responsibilities:**
- Expose repo code operations
- Handle code edit proposals
- Manage change sets

---

#### `RepoSearchDetMcpServer` (repo_search_det_mcp_server.py)

**Purpose:** Deterministic repository search

**Responsibilities:**
- Run fd-based file discovery
- Execute ripgrep searches
- Run ast-grep searches
- Provide jq queries against JSON

---

#### `RepoValidateMcpServer` (repo_validate_mcp_server.py)

**Purpose:** Repository validation via MCP

**Responsibilities:**
- Run diff checks
- Execute ruff/pyright/shellcheck/semgrep
- Run pytest with bounded args
- Execute probe profiles

---

#### `RepoStateMcpServer` (repo_state_mcp_server.py)

**Purpose:** Repository state inspection

**Responsibilities:**
- Report git status
- Report repo capabilities
- Provide read-only state information

---

#### `RagMcpServer` (rag_mcp_server.py)

**Purpose:** RAG index operations

**Responsibilities:**
- Search RAG index
- Build/rebuild RAG index
- Report index status

---

#### `ProjectMemoryMcpServer` (project_memory_mcp_server.py)

**Purpose:** Project memory management

**Responsibilities:**
- Search project memory records
- Read individual memory records
- Upsert verified memory records
- Mark records stale
- Supersede old records

---

#### `JobArtifactMcpServer` (job_artifact_mcp_server.py)

**Purpose:** Job artifact access

**Responsibilities:**
- List persisted agent jobs
- Read job summaries
- Read job events
- Read final results
- Access tool-result artifacts

---

#### `JobViewMcpServer` (job_view_mcp_server.py)

**Purpose:** Job HTML view rendering

**Responsibilities:**
- Render job HTML views
- Render section fragments
- Extract links and outlines
- Validate rendered HTML

---

#### `SqliteReadonlyMcpServer` (sqlite_readonly_mcp_server.py)

**Purpose:** Read-only SQLite access

**Responsibilities:**
- List allowlisted databases
- Read database schemas
- Execute bounded SELECT queries

---

#### `GitReadonlyMcpServer` (git_readonly_mcp_server.py)

**Purpose:** Read-only Git operations

**Responsibilities:**
- Read commit logs
- Show commit details
- Run diffs
- Run blame
- Compare branches

---

#### `OpsMcpServer` (ops_mcp_server.py)

**Purpose:** Operations monitoring

**Responsibilities:**
- Report MCP health
- Inventory MCP servers
- Probe server connectivity
- Monitor service state
- Snapshot system state

---

#### `NetworkMonitorMcpServer` (network_monitor_mcp_server.py)

**Purpose:** Network monitoring

**Responsibilities:**
- List network interfaces
- Start/stop packet capture
- List threats
- Manage firewall rules

---

#### `SymbolRagMcpServer` (symbol_rag_mcp_server.py)

**Purpose:** Symbol RAG operations

**Responsibilities:**
- Build symbol RAG index
- Search symbol index
- Report index status

---

#### `ContextCompressorMcpServer` (context_compressor_mcp_server.py)

**Purpose:** Context window compression

**Responsibilities:**
- Summarize large files
- Build table of contents
- Calculate context budgets
- Compress modules

---

#### `TestCoverageMcpServer` (test_coverage_mcp_server.py)

**Purpose:** Test coverage analysis

**Responsibilities:**
- Analyze file-level coverage
- Analyze module coverage
- Identify uncovered regions
- Generate coverage reports

---

#### `ApiDocumentationMcpServer` (api_documentation_mcp_server.py)

**Purpose:** API documentation quality

**Responsibilities:**
- Generate function signature docs
- Generate class documentation
- Generate module documentation
- Calculate documentation quality scores

---

#### `PerformanceProfilingMcpServer` (performance_profiling_mcp_server.py)

**Purpose:** Performance profiling

**Responsibilities:**
- Analyze algorithmic complexity
- Identify memory hotspots
- Analyze execution patterns
- Generate benchmark suggestions

---

#### `RefactorMcpServer` (refactor_mcp_server.py)

**Purpose:** Code refactoring tools

**Responsibilities:**
- Add function parameters
- Extract functions
- Rename symbols
- Rename projects

---

#### `CodeArchitectMcpServer` (code_architect_mcp_server.py)

**Purpose:** Architecture analysis

**Responsibilities:**
- Build dependency graphs
- Analyze architecture patterns
- Calculate coupling/cohension metrics
- Detect design patterns
- Suggest module boundaries
- Analyze cyclomatic complexity

---

#### `McpBatchProxyServer` (mcp_batch_proxy_server.py)

**Purpose:** Batch MCP execution proxy

**Responsibilities:**
- Execute batches of MCP tool calls
- Provide batch health checking
- List available batch servers

---

## vulkan_bridge Classes

### Main Application Classes

#### `VulkanApp` (app.py / app_refactored.py)

**Purpose:** Vulkan bridge application

**Responsibilities:**
- Handle OpenWebUI-facing requests
- Forward to broker 3572
- Manage API schema generation

---

#### `AgenticV9` (agentic_v9.py)

**Purpose:** Agentic v9 implementation

**Responsibilities:**
- Implement v9 agentic patterns
- Handle modern agent flow

---

#### `HttpClient` (client.py)

**Purpose:** HTTP client for bridge communication

**Responsibilities:**
- Make HTTP requests to broker
- Handle response parsing
- Manage connection lifecycle

---

#### `OpenApiBuilder` (openapi_builder.py)

**Purpose:** OpenAPI schema generation

**Responsibilities:**
- Build OpenAPI schemas for vulkan_bridge
- Generate API documentation

---

## launch Layer Scripts

The launch layer consists primarily of PowerShell scripts rather than Python classes. Key scripts:

- `download_ovms.ps1`: Download OVMS model server
- `env.ps1`: Environment setup
- `http.ps1`: HTTP utilities
- `ollama.ps1`: Ollama launcher
- `openwebui_runtime.ps1`: OpenWebUI runtime setup
- `process.ps1`: Process management
- `setup_ovms_reranker.ps1`: OVMS reranker setup
- `export_model.py`: Model export CLI tool

---

## Class Relationships

```
AgentJobLifecycle (creates jobs)
    │
    └─→ launches AgentJobWorker (runs jobs)
            │
            ├─→ runs planner.py (agentic planning)
            │
            └─→ runs agent() from agent_entry.py (legacy mode)
                    │
                    └─→ dispatches via tool_dispatch.py
                            │
                            └─→ calls tools/ layer operations

AgentJobActionRouter (routes actions)
    │
    └─→ uses SelectorRunner (selector operations)

Vulkan Bridge (app.py)
    │
    └─→ HttpClient → Broker 3572 (/vulkan/agent)
            │
            └─→ AgentJobLifecycle → AgentJobWorker

Codex Bridge MCP Servers
    │
    ├─→ JobArtifactMcpServer → job_store_repository
    │
    ├─→ JobViewMcpServer → job_html assets
    │
    ├─→ RepoCodeMcpServer → broker tools/ layer
    │
    └─→ RepoValidateMcpServer → broker tools/ layer
```

## Key Design Patterns

1. **Dataclass-based dependency injection**: `AgentJobWorker`, `AgentJobLifecycle`, and other application classes use `@dataclass(frozen=True)` with callable fields for testability.

2. **Factory pattern**: `build_job_worker()`, `build_job_lifecycle()`, `build_selector_runner()` create configured instances.

3. **Callable type aliases**: `LoadState`, `WriteState`, `PlannerRunner`, etc. provide typed function signatures.

4. **Layered architecture**: domain → contracts → infrastructure → application → entry points.

5. **MCP server modularity**: Each codex_bridge MCP server exposes a single focused capability surface.