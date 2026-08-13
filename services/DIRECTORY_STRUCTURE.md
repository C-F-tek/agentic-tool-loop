# Directory Structure Reference

**Last updated:** 2026-08-13

## Overview

This document describes the directory layout of the `services/` folder, explaining the purpose and contents of each subdirectory.

---

## Top-Level Services Directory

```
services/
├── __init__.py
├── aicarmine_broker/          # Main agentic loop broker service
├── aicarmine_broker.backup/   # Backup of previous broker version
├── aicarmine_broker.egg-info/ # Python package metadata
├── codex_bridge/              # MCP stdio integration layer
├── config/                    # Shared configuration
├── launch/                    # Service launch scripts
├── llm/                       # LLM model management
├── logs/                      # Runtime log files
├── model_export/              # Model export CLI tools
├── npu_phi_service/           # NPU diagnostic sidecar
├── openwebui-data/            # OpenWebUI configuration data
├── vulkan_bridge/             # OpenWebUI-facing bridge
├── __pycache__/               # Python bytecode cache
├── *.ps1                      # PowerShell launcher scripts
└── *.md                       # Documentation files
```

---

## aicarmine_broker/ — Main Broker Service

**Port:** 3572  
**Purpose:** Core agentic loop broker — owns job persistence, tool dispatch, planning, and evidence collection.

```
aicarmine_broker/
├── __init__.py
├── app.py                     # FastAPI application factory & HTTP routes
├── agent_entry.py             # Agent entry point (background job lifecycle)
├── planner.py                 # Agentic loop planner execution
├── planner_intrinsic_context.py # Planner context utilities
├── public_wrapper.py          # Public-facing wrapper utilities
├── tool_contract.py           # Tool contract definitions
├── tool_dispatch.py           # Tool dispatch logic
├── tool_registry.py           # Tool registration
├── tool_schemas.py            # Tool schema definitions
├── tool_selection.py          # Tool selection logic
├── tool_drop.py               # Tool drop operations
├── repo_tools.py              # Repository tool wrappers
├── memory_tools.py            # Memory tool integration
├── job_html_assets.py         # Job HTML view assets
├── job_html.py                # Job HTML rendering
├── job_planner_lab.py         # Planner lab HTML views
├── job_store.py               # Job store utilities
├── code_edit_proposal_contract.py # Code edit proposal contract
├── flow.svg                   # Flow diagram image
├── README.md                  # Service documentation
├── MODULE_REFERENCE.md        # Module reference
├── JOB_VIEW_OPTIMIZATION_NOTES.md # Job view optimization notes
│
├── config/                    # Configuration layer
│   ├── __init__.py
│   └── models.py              # Configuration data models
│
├── contracts/                 # Interface contracts layer
│   ├── dispatcher.py          # Dispatcher interface
│   ├── job_repository.py      # Job repository interface
│   ├── tool.py                # Tool interface
│   ├── prompt_store.py        # Prompt store interface
│   └── validator.py           # Validator interface
│
├── domain/                    # Domain models layer
│   ├── __init__.py
│   ├── models.py              # Core domain models
│   ├── config.py              # Configuration domain models
│   ├── tool.py                # Tool domain models
│   ├── decisions.py           # Decision domain models
│   ├── evidence.py            # Evidence domain models
│   └── tests/
│       └── test_models.py     # Domain model tests
│
├── infrastructure/             # Infrastructure layer
│   ├── job_store_repository.py  # Job store repository implementation
│   ├── job_sqlite_store.py      # SQLite job store
│   ├── executable_resolver.py   # Executable path resolution
│   └── command_runner.py        # Command execution
│
├── application/               # Application services layer
│   ├── __init__.py
│   ├── dispatcher.py          # Main dispatch logic
│   ├── test_ab_flow.py        # AB flow tests
│   │
│   ├── command/               # Command execution services
│   │   └── execution_policy.py  # Execution policy
│   │
│   ├── controller/            # Control flow services
│   │   ├── memory.py          # Controller memory management
│   │   ├── tests/
│   │   │   ├── test_guards.py     # Guard tests
│   │   │   ├── test_memory.py     # Memory tests
│   │   │   ├── test_orientation_lane.py # Orientation lane tests
│   │   │   ├── test_preseed.py    # Preseed tests
│   │   │   └── test_rag_preseed.py    # RAG preseed tests
│   │
│   ├── code_product/          # Code product services
│   │   ├── public_outputs.py  # Public output generation
│   │   ├── history.py         # History queries
│   │   ├── tests/
│   │   │   ├── test_history.py      # History tests
│   │   │   ├── test_public_outputs.py # Public output tests
│   │   │   ├── test_state.py          # State tests
│   │   │   └── test_required_working_set.py # Working set tests
│   │
│   ├── evidence/              # Evidence collection services
│   │   ├── builder.py         # Evidence builder
│   │   ├── tests/
│   │   │   ├── test_builder.py      # Builder tests
│   │   │   ├── test_coverage_scorer.py # Coverage scorer tests
│   │   │   ├── test_execution_digest.py # Execution digest tests
│   │   │   ├── test_goal_classifier.py # Goal classifier tests
│   │   │   └── test_final_quality.py   # Final quality tests
│   │
│   ├── job/                   # Job management services
│   │   ├── worker.py          # Background job worker
│   │   ├── action_router.py   # Action routing
│   │   ├── selector_runner.py # Selector execution
│   │   └── lifecycle.py       # Job lifecycle management
│   │
│   ├── memory/                # Agent memory services
│   │   ├── agent_state.py     # Agent state management
│   │   ├── agent_memory_policy.py    # Memory policy
│   │   ├── agent_memory_routing_policy.py # Memory routing
│   │   └── tests/
│   │       └── test_agent_state.py  # Agent state tests
│   │
│   ├── planner/               # Planner services
│   │   ├── loop.py            # Planning loop
│   │   ├── turn.py            # Turn management
│   │   ├── decision_normalizer.py # Decision normalization
│   │   ├── validator.py       # Planning validation
│   │   └── tests/
│   │       └── test_loop_helpers.py # Loop helper tests
│   │
│   ├── public_payload/        # Public payload services
│   │   ├── evidence_materializer.py # Evidence materialization
│   │   ├── payload_index_resolver.py # Index resolution
│   │   ├── terminal_sanitizer.py  # Terminal sanitization
│   │   ├── lab/               # Planner lab payloads
│   │   │   └── tests/
│   │   │       └── test_lab_init.py # Lab init tests
│   │   └── tests/
│   │       ├── test_evidence_materializer.py # Evidence tests
│   │       └── test_payload_index_resolver.py # Index tests
│   │
│   ├── shared/                # Shared utilities
│   │   └── history_queries.py # History query utilities
│   │
│   └── tests/
│       └── test_dispatcher.py # Dispatcher tests
│
├── security/                  # Security layer
│   ├── __init__.py
│   ├── injection_audit.py     # Injection audit
│   └── sanitization.py        # Input sanitization
│
├── tests/                     # Broker-level tests
│   └── test_planner.py        # Planner tests
│
└── tools/                     # Tool operations layer
    ├── deterministic_common.py  # Deterministic search utilities
    ├── repo_command.py          # Git command wrapper
    ├── repo_deterministic.py    # Deterministic file operations
    ├── repo_patch.py            # Patch application
    ├── repo_read.py             # File reading
    ├── repo_code_product.py     # Code product operations
    ├── repo_list_files.py       # File listing
    ├── repo_search.py           # File search
    ├── repo_semantic_search.py  # Semantic search
    ├── repo_status.py           # Repository status
    ├── repo_tree.py             # Repository tree
    ├── repo_validate.py         # Repository validation
    ├── git_surface.py           # Git surface operations
    ├── powershell_runner.py     # PowerShell execution
    ├── terminal.py              # Terminal operations
    ├── command_safety.py        # Command safety checks
    └── repo_probe_profiles.py   # Probe profile management
```

---

## codex_bridge/ — MCP Integration Layer

**Transport:** stdio  
**Purpose:** Exposes MCP tools to Cline for repository operations, job inspection, RAG, and more.

```
codex_bridge/
├── __init__.py
├── mcp_server.py                    # Main MCP server entry
├── json_gzip_util.py               # JSON gzip utilities
├── jsonrpc.py                      # JSON-RPC handling
├── storage.py                      # Storage utilities
├── repo_mcp_common.py              # Common repo MCP utilities
├── repo_code_change_set.py         # Code change set handling
├── flow.svg                        # Flow diagram
├── README.md                       # Service documentation
├── MODULE_REFERENCE.md             # Module reference
├── REPO_MCP_CONTRACT.md            # Repo MCP contract
├── MCP_GUIDE.md                    # MCP usage guide
│
├── agentic_loop_client_mcp_server.py  # Agentic loop client
├── api_documentation_mcp_server.py    # API documentation quality
├── broker_planner_mcp_server.py       # Broker planner integration
├── code_architect_mcp_server.py       # Code architecture analysis
├── context_compressor_mcp_server.py   # Context compression
├── git_readonly_mcp_server.py         # Read-only Git operations
├── job_artifact_mcp_server.py         # Job artifact access
├── job_view_mcp_server.py             # Job HTML view rendering
├── local_subagent_mcp_server.py       # Local subagent facade
├── mcp_batch_proxy_server.py          # Batch MCP proxy
├── network_monitor_mcp_server.py      # Network monitoring
├── ollama_mcp_server.py               # Ollama integration
├── ollama_responses_bridge.py         # Ollama response bridge
├── ollama_subagent_mcp_server.py      # Ollama subagent
├── ops_mcp_server.py                  # Operations monitoring
├── ovms_mcp_server.py                 # OVMS MCP
├── performance_profiling_mcp_server.py # Performance profiling
├── planner_components_mcp_server.py   # Planner components
├── project_memory_mcp_server.py       # Project memory
├── rag_mcp_server.py                  # RAG index operations
├── rag_index_repo.py                  # RAG index utilities
├── refactor_mcp_server.py             # Code refactoring
├── repo_code_mcp_server.py            # Repo code operations
├── repo_search_det_mcp_server.py      # Deterministic search
├── repo_state_mcp_server.py           # Repository state
├── repo_validate_mcp_server.py        # Repository validation
├── responses_proxy.py                 # Responses proxy
├── sqlite_readonly_mcp_server.py      # Read-only SQLite
├── symbol_rag_mcp_server.py           # Symbol RAG
├── test_coverage_mcp_server.py        # Test coverage analysis
├── test_repo_code_mcp_serialization.py # Serialization tests
│
├── mcp_proxy/                         # MCP proxy components
└── tests/                              # MCP server tests
    ├── test_core_mcp.py               # Core MCP tests
    ├── test_mcp_server_core.py        # Server core tests
    └── test_mcp_servers.py            # General MCP tests
```

---

## vulkan_bridge/ — OpenWebUI Bridge

**Port:** 3571  
**Purpose:** Public-facing bridge that forwards requests to the broker.

```
vulkan_bridge/
├── __init__.py
├── app.py              # Main application (legacy)
├── app_refactored.py    # Refactored application
├── agentic_v9.py        # Agentic v9 implementation
├── client.py            # HTTP client
├── compact.py           # Compact representation
├── config.py            # Configuration
├── openapi_builder.py    # OpenAPI schema builder
├── flow.svg             # Flow diagram
├── README.md            # Service documentation
├── MODULE_REFERENCE.md   # Module reference
│
└── application/         # Application layer
```

---

## launch/ — Service Launch Scripts

**Purpose:** PowerShell scripts for launching and managing services.

```
launch/
├── contracts/              # Service launch contracts
├── models-ovms-rerank/     # OVMS reranker model files
│   └── BAAI/bge-reranker-v2-m3/
│       ├── graph.pbtxt     # Model graph definition
│       └── config.json     # Model configuration
├── ovms-runtime/           # OVMS runtime configuration
├── download_ovms.ps1       # OVMS download script
├── env.ps1                 # Environment setup
├── http.ps1                # HTTP utilities
├── MCP_SERVERS_ANALYSIS.md  # MCP servers analysis
├── MODULE_REFERENCE.md      # Module reference
├── ollama.ps1              # Ollama launcher
├── openwebui_runtime.ps1   # OpenWebUI runtime
├── OVMS_RERANKER_MANUAL_INSTALL.md # Installation guide
├── process.ps1             # Process management
├── README.md               # Documentation
├── setup_ovms_reranker.ps1 # OVMS reranker setup
└── export_model.py         # Model export CLI
```

---

## model_export/ — Model Export Tools

**Purpose:** CLI tools for exporting models to OpenVINO format.

```
model_export/
├── __init__.py
├── export.py              # Main export CLI
├── MODULE_REFERENCE.md     # Module reference
└── ...
```

---

## npu_phi_service/ — NPU Diagnostic Sidecar

**Purpose:** OpenVINO diagnostic service for NPU/GPU monitoring.

```
npu_phi_service/
├── __init__.py
├── service.py             # Main service entry
├── MODULE_REFERENCE.md     # Module reference
└── ...
```

---

## config/ — Shared Configuration

**Purpose:** Shared configuration across services.

```
config/
└── __init__.py
```

---

## llm/ — LLM Model Management

**Purpose:** Local LLM model storage and management.

```
llm/
└── ... (model files and configurations)
```

---

## logs/ — Runtime Logs

**Purpose:** Runtime log file storage.

```
logs/
└── ... (log files)
```

---

## openwebui-data/ — OpenWebUI Data

**Purpose:** OpenWebUI configuration and data storage.

```
openwebui-data/
└── ... (configuration files)
```

---

## aicarmine_broker.backup/ — Broker Backup

**Purpose:** Backup of previous broker version for rollback.

```
aicarmine_broker.backup/
└── ... (previous version files)
```

---

## Directory-Level Architecture Summary

```
services/
│
├── aicarmine_broker/    ← Core service (port 3572)
│   ├── app.py           → HTTP entry point
│   ├── agent_entry.py   → Agent entry point
│   ├── planner.py       → Agentic planning
│   ├── application/     → Application services (layered)
│   ├── domain/          → Domain models
│   ├── contracts/       → Interface contracts
│   ├── infrastructure/  → Infrastructure implementations
│   ├── tools/           → Tool operations
│   ├── security/        → Security utilities
│   └── config/          → Configuration
│
├── codex_bridge/        ← MCP stdio layer
│   ├── mcp_server.py    → Main MCP entry
│   ├── *_mcp_server.py  → Individual MCP servers
│   └── tests/           → MCP tests
│
├── vulkan_bridge/       ← OpenWebUI bridge (port 3571)
│   ├── app.py           → Bridge application
│   └── application/     → Application layer
│
├── launch/              ← Service launchers
│   ├── *.ps1           → PowerShell scripts
│   └── contracts/      → Launch contracts
│
├── model_export/        ← Model export CLI
├── npu_phi_service/     ← NPU diagnostic
├── config/              ← Shared configuration
├── llm/                 ← LLM models
├── logs/                ← Runtime logs
└── openwebui-data/      ← OpenWebUI data
```

---

## Key Architectural Patterns

1. **Layered Architecture** (aicarmine_broker): domain → contracts → infrastructure → application → entry points
2. **MCP Server Modularity** (codex_bridge): Each capability is a separate MCP server
3. **Dataclass Dependency Injection** (application/job/*): Frozen dataclasses with callable fields
4. **PowerShell Launch Scripts** (launch): Windows-native service management
5. **Separation of Concerns**: Each directory has a single focused responsibility