# Services Flow Structure

**Last updated:** 2026-08-13

## Overview

This document describes the architectural flow structure across all services in the `services/` directory. It maps how components communicate, what ports they listen on, and how data flows through the system.

## Service Ports and Roles

| Service | Port(s) | Role |
|---------|---------|------|
| aicarmine_broker | 3572 | Main agentic loop broker - owns job persistence, tool dispatch, planner |
| vulkan_bridge | 3571 | OpenWebUI-facing public bridge |
| codex_bridge | stdio | MCP stdio integration layer - exposes MCP tools to Cline |
| ollama | 11434 | Local LLM provider (Ollama runtime) |
| ovms_reranker | 3550 | ONNX Runtime model server + BGE reranker |
| openwebui | 8080 | Web UI frontend |

## Flow Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
│  Cline/     │     │  Codex       │     │  aicarmine      │
│  OpenWebUI  │─────│  Bridge      │─────│  Broker (3572)  │
│  (port 8080)│     │  (stdio)     │     │                 │
└─────────────┘     └──────────────┘     └─────────────────┘
                                          │
                                          ├─→ tool_dispatch.py (tool execution)
                                          ├─→ planner.py (agentic loop planning)
                                          ├─→ agent_entry.py (agent entry point)
                                          └─→ app.py (FastAPI HTTP endpoints)
                                              
┌─────────────────────────────────────────────────────────────┐
│                     Vulkan Bridge (3571)                    │
│                     app_refactored.py                       │
└─────────────────────────────────────────────────────────────┘
          │
          ├─→ Forward requests to broker 3572
          └─→ OpenWebUI public-facing surface
```

## aicarmine_broker Internal Flow

### Entry Points

1. **`app.py`** - FastAPI application factory
   - Creates `FastAPI` app instance
   - Registers HTTP routes for job management, planner lab, health
   - Exposes `/health`, `/vulkan/agent`, `/jobs/index`, `/planner-lab`
   - Custom OpenAPI schema with `x-aicarmine-*` metadata

2. **`agent_entry.py`** - Agent entry point
   - `agent(payload)` function - main agent invocation
   - Called by `app.py` at `/vulkan/agent` endpoint
   - Dispatches to planner or direct tool execution

3. **`planner.py`** - Agentic loop planner
   - Manages planning steps
   - Coordinates tool selection and execution
   - Handles evidence gathering and decision making

### Application Layer (`application/`)

```
application/
├── dispatcher.py         - Main dispatch logic
├── controller/            - Control flow components
│   ├── memory.py          - Controller memory management
│   ├── tests/test_*.py    - Controller tests
├── code_product/          - Code product management
│   ├── public_outputs.py  - Public output generation
│   ├── history.py         - History queries
│   ├── tests/test_*.py    - Code product tests
├── evidence/              - Evidence collection
│   ├── builder.py         - Evidence builder
│   ├── tests/test_*.py    - Evidence tests
├── job/                   - Job management
│   ├── worker.py          - Job worker
│   ├── action_router.py   - Action routing
│   ├── selector_runner.py - Selector execution
├── memory/                - Agent memory
│   ├── agent_state.py     - Agent state management
│   ├── agent_memory_policy.py    - Memory policy
│   ├── agent_memory_routing_policy.py - Memory routing
├── planner/               - Planner components
│   ├── loop.py            - Planning loop
│   ├── turn.py            - Turn management
│   ├── decision_normalizer.py - Decision normalization
│   ├── validator.py       - Validation
├── public_payload/        - Public payload handling
│   ├── lab/               - Planner lab payloads
└── command/               - Command execution
    ├── execution_policy.py - Execution policy
```

### Domain Layer (`domain/`)

```
domain/
├── models.py              - Core domain models
├── config.py              - Configuration models
├── tool.py                - Tool domain models
├── decisions.py           - Decision models
├── evidence.py            - Evidence models
└── tests/test_models.py   - Domain tests
```

### Contracts Layer (`contracts/`)

```
contracts/
├── dispatcher.py          - Dispatcher contract
├── job_repository.py      - Job repository interface
├── tool.py                - Tool contract
├── prompt_store.py        - Prompt store contract
└── validator.py           - Validator contract
```

### Infrastructure Layer (`infrastructure/`)

```
infrastructure/
├── job_store_repository.py    - Job store repository implementation
├── job_sqlite_store.py        - SQLite job store
├── executable_resolver.py     - Executable path resolution
└── command_runner.py          - Command execution
```

### Tools Layer (`tools/`)

```
tools/
├── deterministic_common.py  - Deterministic search utilities
├── repo_command.py          - Git command wrapper
├── repo_deterministic.py    - Deterministic file operations
├── repo_patch.py            - Patch application
├── repo_read.py             - File reading
├── repo_code_product.py     - Code product operations
├── repo_list_files.py       - File listing
├── repo_search.py           - File search
├── repo_semantic_search.py  - Semantic search
├── repo_status.py           - Repository status
├── repo_tree.py             - Repository tree
├── repo_validate.py         - Repository validation
├── git_surface.py           - Git surface operations
├── powershell_runner.py     - PowerShell execution
├── terminal.py              - Terminal operations
├── command_safety.py        - Command safety checks
└── repo_probe_profiles.py   - Probe profile management
```

### Config Layer (`config/`)

```
config/
└── models.py              - Configuration models
```

### Security Layer (`security/`)

```
security/
├── __init__.py            - Security module init
├── injection_audit.py     - Injection audit
└── someoization.py        - Input someoization
```

## codex_bridge Internal Flow

### MCP Server Components

```
codex_bridge/
├── mcp_server.py                    - Main MCP server entry
├── json_gzip_util.py               - JSON gzip utilities
├── jsonrpc.py                      - JSON-RPC handling
├── storage.py                      - Storage utilities
├── repo_mcp_common.py              - Common repo MCP utilities
├── repo_code_change_set.py         - Code change set handling
├── planner_components_mcp_server.py - Planner components MCP
├── broker_planner_mcp_server.py    - Broker planner MCP
├── agentic_loop_client_mcp_server.py - Agentic loop client
├── local_subagent_mcp_server.py    - Local subagent facade
├── ollama_mcp_server.py            - Ollama integration
├── ollama_responses_bridge.py      - Ollama response bridge
├── ollama_subagent_mcp_server.py   - Ollama subagent
├── ops_mcp_server.py               - Operations MCP
├── ovms_mcp_server.py              - OVMS MCP
├── network_monitor_mcp_server.py   - Network monitoring
├── symbol_rag_mcp_server.py        - Symbol RAG
├── rag_mcp_server.py               - RAG server
├── rag_index_repo.py               - RAG index operations
├── project_memory_mcp_server.py    - Project memory
├── sqlite_readonly_mcp_server.py   - SQLite read-only
├── git_readonly_mcp_server.py      - Git read-only
├── job_artifact_mcp_server.py      - Job artifacts
├── job_view_mcp_server.py          - Job views
├── refactor_mcp_server.py          - Refactoring tools
├── code_architect_mcp_server.py    - Code architecture
├── context_compressor_mcp_server.py - Context compression
├── test_coverage_mcp_server.py     - Test coverage
├── api_documentation_mcp_server.py - API documentation
├── performance_profiling_mcp_server.py - Performance profiling
├── repo_code_mcp_server.py         - Repo code operations
├── repo_search_det_mcp_server.py   - Deterministic search
├── repo_state_mcp_server.py        - Repo state
├── repo_validate_mcp_server.py     - Repo validation
├── mcp_batch_proxy_server.py       - Batch MCP proxy
├── responses_proxy.py              - Responses proxy
└── mcp_proxy/                      - MCP proxy components
```

## vulkan_bridge Internal Flow

```
vulkan_bridge/
├── app.py              - Main application (legacy)
├── app_refactored.py    - Refactored application
├── agentic_v9.py        - Agentic v9 implementation
├── client.py            - HTTP client
├── compact.py           - Compact representation
├── config.py            - Configuration
├── openapi_builder.py    - OpenAPI schema builder
└── application/         - Application layer
```

## launch Layer

```
launch/
├── contracts/           - Service launch contracts
├── models-ovms-rerank/  - OVMS reranker model files
├── ovms-runtime/        - OVMS runtime configuration
├── download_ovms.ps1    - OVMS download script
├── env.ps1              - Environment setup
├── http.ps1             - HTTP utilities
├── ollama.ps1           - Ollama launcher
├── openwebui_runtime.ps1 - OpenWebUI runtime
├── process.ps1          - Process management
├── setup_ovms_reranker.ps1 - OVMS reranker setup
└── export_model.py      - Model export CLI
```

## Data Flow Summary

1. **External Request** → OpenWebUI (8080) or Cline
2. **OpenWebUI Bridge** → vulkan_bridge (3571)
3. **Vulkan Bridge** → aicarmine_broker (3572) via `/vulkan/agent`
4. **Broker** → planner.py → agent_entry.py → tool_dispatch.py
5. **Tool Execution** → tools/ layer → repository operations
6. **Job Persistence** → infrastructure/job_store_repository.py → SQLite
7. **MCP Tools** → codex_bridge → stdio transport → Cline

## Key Integration Points

- **Port 3572**: Primary broker endpoint for agentic loop jobs
- **Port 3571**: Vulkan bridge for OpenWebUI public access
- **Port 11434**: Ollama LLM provider
- **Port 3550**: OVMS reranker model server
- **Port 8080**: OpenWebUI frontend
- **stdio**: Codex bridge MCP transport for Cline integration