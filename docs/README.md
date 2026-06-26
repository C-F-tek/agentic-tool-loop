# Documentation — Complete Index

> **Purpose**: Master index of all Markdown documentation for the C:\Users\carmi\AI workspace. Provides surface-IA-friendly navigation across all modules, scripts, and services.

---

## Quick Navigation

| Document | Purpose |
|----------|---------|
| [SERVICES_INDEX.md](SERVICES_INDEX.md) | Complete file-by-file documentation index |
| [PYTHON_REFACTORING_GUIDE.md](PYTHON_REFACTORING_GUIDE.md) | Refactoring techniques, anti-patterns, case studies |
| [REFACTORING_STATUS_CURRENT.md](REFACTORING_STATUS_CURRENT.md) | Current refactoring state and verification results |
| [REFACTORING_PROMPT_TEMPLATE.md](REFACTORING_PROMPT_TEMPLATE.md) | Template for AI-assisted refactoring prompts |
| [REFACTORING_QUICK_REFERENCE.md](REFACTORING_QUICK_REFERENCE.md) | Quick reference for refactoring techniques |

---

## Module Documentation

### Broker Module (`services/aicarmine_broker/`)

| Document | Location |
|----------|----------|
| [Broker README](../services/aicarmine_broker/README.md) | Architecture overview, entry points |
| [Config README](../services/aicarmine_broker/config/README.md) | BrokerConfig, env_loader, compatibility |
| [Tools README](../services/aicarmine_broker/tools/README.md) | Repository tool implementations |
| [Infrastructure README](../services/aicarmine_broker/infrastructure/README.md) | Command execution, storage, JSON I/O |
| [Application README](../services/aicarmine_broker/application/README.md) | Planner, evidence, prompt, tool surface |
| [Domain README](../services/aicarmine_broker/domain/README.md) | Domain models: decisions, job, tool |
| [Contracts README](../services/aicarmine_broker/contracts/README.md) | Protocol interfaces |

### Vulkan Bridge (`services/vulkan_bridge/`)

| Document | Location |
|----------|----------|
| [Vulkan Bridge README](../services/vulkan_bridge/README.md) | GPU-accelerated service overview |

### Codex Bridge (`services/codex_bridge/`)

| Document | Location |
|----------|----------|
| [Codex Bridge README](../services/codex_bridge/README.md) | External provider integration |

### Codex Ollama Bridge Applied (`codex_ollama_bridge_applied/`)

| Document | Location |
|----------|----------|
| [Applied README](../codex_ollama_bridge_applied/README.md) | Full Codex + Ollama integration |

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
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                    Other Services                            │
│                    services/vulkan_bridge/                   │
│                    services/codex_bridge/                    │
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