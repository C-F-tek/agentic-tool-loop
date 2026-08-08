# Documentation — Complete Index

> **Purpose**: Master index of all Markdown documentation for the C:\Users\carmi\AI workspace. Provides surface-IA-friendly navigation across all modules, scripts, and services.

---

## Quick Navigation

| Document | Purpose |
|----------|---------|
| [SERVICES_INDEX.md](SERVICES_INDEX.md) | Complete file-by-file documentation index with cross-links to all READMEs |
| [PYTHON_REFACTORING_GUIDE.md](PYTHON_REFACTORING_GUIDE.md) | Refactoring techniques, anti-patterns, case studies |
| [REFACTORING_STATUS_CURRENT.md](REFACTORING_STATUS_CURRENT.md) | Current refactoring state and verification results |
| [REFACTORING_PROMPT_TEMPLATE.md](REFACTORING_PROMPT_TEMPLATE.md) | Template for AI-assisted refactoring prompts |
| [REFACTORING_QUICK_REFERENCE.md](REFACTORING_QUICK_REFERENCE.md) | Quick reference for refactoring techniques |

---

## Module Documentation — Complete Surface Index

### Broker Module (`services/aicarmine_broker/`)

| Document | Location |
|----------|----------|
| [Broker Overview](../services/aicarmine_broker/README.md) | Architecture overview, entry points |
| [Config](../services/aicarmine_broker/config/README.md) | BrokerConfig, env_loader, compatibility |
| [Tools](../services/aicarmine_broker/tools/README.md) | Repository tool implementations (17 files) |
| [Infrastructure](../services/aicarmine_broker/infrastructure/README.md) | Command execution, storage, JSON I/O |
| [Application Layer](../services/aicarmine_broker/application/README.md) | 15 application sub-modules |
| [Domain](../services/aicarmine_broker/domain/README.md) | Domain models: decisions, job, tool |
| [Contracts](../services/aicarmine_broker/contracts/README.md) | Protocol interfaces |

#### Application Sub-Modules

| Document | Location |
|----------|----------|
| [Evidence](../services/aicarmine_broker/application/evidence/README.md) | Evidence building & classification (9 files) |
| [Tool Surface](../services/aicarmine_broker/application/tool_surface/README.md) | Tool dispatch & result handling (11 files) |
| [Prompt](../services/aicarmine_broker/application/prompt/README.md) | Prompt construction & management (11 files) |
| [Controller](../services/aicarmine_broker/application/controller/README.md) | Controller lane logic (7 files) |
| [Code Product](../services/aicarmine_broker/application/code_product/README.md) | Code product state (4 files) |
| [Job](../services/aicarmine_broker/application/job/README.md) | Job lifecycle (8 files) |
| [Memory](../services/aicarmine_broker/application/memory/README.md) | Memory conflict detection |
| [NPU Phi](../services/aicarmine_broker/application/npu_phi/README.md) | NPU phi service integration |
| [Replay](../services/aicarmine_broker/application/replay/README.md) | Loop replay functionality |
| [Runtime Debug](../services/aicarmine_broker/application/runtime_debug/README.md) | Debug packet management |
| [Search](../services/aicarmine_broker/application/search/README.md) | Search quality metrics |
| [Command](../services/aicarmine_broker/application/command/README.md) | Command execution policy |

#### Planner Sub-Modules

| Document | Location |
|----------|----------|
| [Planner Modules](../services/aicarmine_broker/application/planner/modules/README.md) | Replan specialist |
| [Planner Validator](../services/aicarmine_broker/application/planner/validator/README.md) | Validation sub-package (8 files) |
| [Public Payload Lab](../services/aicarmine_broker/application/public_payload/lab/README.md) | Lab-specific payloads |
| [Planner Core](../services/aicarmine_broker/planner_core/README.md) | JSON I/O, caching, RAG cache |

### Vulkan Bridge (`services/vulkan_bridge/`)

| Document | Location |
|----------|----------|
| [Vulkan Bridge](../services/vulkan_bridge/README.md) | GPU-accelerated service overview |

### Codex Bridge (`services/codex_bridge/`)

| Document | Location |
|----------|----------|
| [Codex Bridge](../services/codex_bridge/README.md) | External provider integration |

### Other Services

| Document | Location |
|----------|----------|
| [Launch Scripts](../services/launch/README.md) | PowerShell startup automation (3 scripts) |
| [Model Export](../services/model_export/README.md) | Model export utilities |
| [NPU Phi Service](../services/npu_phi_service/README.md) | NPU phi service launcher |
| [Tests](../services/tests/README.md) | Test suite |

### Codex Ollama Bridge Applied (`codex_ollama_bridge_applied/`)

| Document | Location |
|----------|----------|
| [Applied Overview](../codex_ollama_bridge_applied/README.md) | Full Codex + Ollama integration |
| [Core Bridge](../codex_ollama_bridge_applied/codex_ollama_bridge/README.md) | MCP server + response bridge |

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Documentation Surface                     │
│                    docs/ (master index)                      │
├─────────────────────────────────────────────────────────────┤
│  SERVICES_INDEX.md          — Complete file-by-file index   │
│  PYTHON_REFACTORING_GUIDE.md — Anti-patterns & techniques    │
│  REFACTORING_STATUS_CURRENT.md — Current state              │
│  REFACTORING_PROMPT_TEMPLATE.md — AI prompt template         │
│  REFACTORING_QUICK_REFERENCE.md — Quick reference            │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                    Broker Module                             │
│                    services/aicarmine_broker/                │
├─────────────────────────────────────────────────────────────┤
│  README.md       — Architecture overview                     │
│  config/README.md    — Configuration management              │
│  tools/README.md     — Repository tool implementations       │
│  infrastructure/README.md — Low-level infrastructure         │
│  application/README.md — Business logic modules              │
│  domain/README.md      — Domain models                       │
│  contracts/README.md   — Protocol interfaces                 │
│  └── application/evidence/README.md    — Evidence building  │
│  └── application/tool_surface/README.md — Tool dispatch     │
│  └── application/prompt/README.md      — Prompt construction│
│  └── application/controller/README.md  — Controller lane    │
│  └── application/code_product/README.md — Code product state│
│  └── application/job/README.md        — Job lifecycle       │
│  └── application/memory/README.md     — Memory conflict     │
│  └── application/npu_phi/README.md    — NPU phi service     │
│  └── application/replay/README.md     — Loop replay         │
│  └── application/runtime_debug/README.md — Debug packets    │
│  └── application/search/README.md     — Search quality      │
│  └── application/command/README.md    — Command policy      │
│  └── application/planner/modules/README.md — Replan spec    │
│  └── application/planner/validator/README.md — Validation   │
│  └── application/public_payload/lab/README.md — Lab payload │
│  └── planner_core/README.md           — JSON I/O, caching   │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                    Other Services                            │
│                    services/vulkan_bridge/                   │
│                    services/codex_bridge/                    │
│                    services/launch/                          │
│                    services/model_export/                    │
│                    services/npu_phi_service/                 │
│                    services/tests/                           │
│                    codex_ollama_bridge_applied/              │
└─────────────────────────────────────────────────────────────┘
```

---

## Documentation Standards

Each README.md follows this structure:

1. **Header** — Purpose statement (blockquote)
2. **Files table** — File, purpose, key types/functions
3. **Architecture diagram** — ASCII art showing module structure
4. **Key components** — Entry points, ports, paths
5. **Documentation index** — Cross-links to related docs

---

*Generated from analysis of the C:\Users\carmi\AI workspace.*