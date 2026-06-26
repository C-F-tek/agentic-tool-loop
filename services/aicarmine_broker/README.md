# Broker Module — Architecture Overview

> **Purpose**: The broker module is the core orchestrator for the AI agent loop. It manages job lifecycle, planner decisions, tool execution, evidence building, and prompt construction.

---

## Quick Start

```powershell
# Start the broker (port 3571)
powershell -File services/start-agent.ps1

# Health check
curl http://localhost:3571/health
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    FastAPI App (app.py)                  │
│                    Port 3571                             │
├─────────────────────────────────────────────────────────┤
│              Planner (planner.py)                       │
│              └── Delegates to application/planner/       │
├─────────────────────────────────────────────────────────┤
│           Application Layer                              │
│  ├── planner/    — Decision building, loop control       │
│  ├── evidence/   — Evidence building & classification    │
│  ├── prompt/     — Prompt construction & management      │
│  ├── tool_surface/ — Tool dispatch & result handling     │
│  ├── public_payload/ — OpenWebUI payload formatting      │
│  ├── shared/     — Shared utilities                      │
│  ├── job/        — Job lifecycle management              │
│  ├── controller/ — Controller lane logic                 │
│  ├── code_product/ — Code product state                  │
│  └── memory/     — Memory conflict detection             │
├─────────────────────────────────────────────────────────┤
│           Infrastructure Layer                           │
│  ├── command_runner.py   — Shell command execution       │
│  ├── filesystem_repo.py  — File operations               │
│  ├── job_sqlite_store.py — SQLite persistence            │
│  └── ollama_planner_client.py — LLM client              │
├─────────────────────────────────────────────────────────┤
│           Tools Layer                                    │
│  ├── repo_read.py      — File reading                    │
│  ├── repo_search.py    — File search                     │
│  ├── repo_patch.py     — Patch application               │
│  └── git_surface.py    — Git operations                  │
├─────────────────────────────────────────────────────────┤
│           Domain Layer                                   │
│  ├── decisions.py  — Decision models                     │
│  ├── job.py        — Job state models                    │
│  └── tool.py       — Tool definition models              │
├─────────────────────────────────────────────────────────┤
│           Contracts Layer                                │
│  ├── dispatcher.py   — Dispatch protocol                 │
│  ├── tool.py         — Tool execution protocol           │
│  └── validator.py    — Validation protocol               │
├─────────────────────────────────────────────────────────┤
│           Configuration                                  │
│  ├── models.py       — BrokerConfig (frozen dataclass)   │
│  └── env_loader.py   — Environment variable parsing      │
└─────────────────────────────────────────────────────────┘
```

---

## Key Components

### Entry Points

| File | Role | Port/Path |
|------|------|-----------|
| `app.py` | FastAPI entry point | `/vulkan/agent` |
| `planner.py` | Main orchestrator | Thin wrapper |
| `planner_loop.py` | Loop execution | `run_agentic_planner_job()` |
| `job_store.py` | Job persistence | SQLite |

### Configuration

| File | Purpose |
|------|---------|
| `config/models.py` | `BrokerConfig` frozen dataclass |
| `config/env_loader.py` | Parse `AICARMINE_*` env vars |
| `config/compatibility.py` | `FINAL_QUALITY_ROUTE_TOOLS` |

### Domain Models

| File | Key Types |
|------|-----------|
| `domain/decisions.py` | `Decision`, `DecisionPath` |
| `domain/job.py` | `JobState`, lifecycle states |
| `domain/tool.py` | `ToolDefinition` |
| `domain/evidence.py` | `EvidenceRecord` |

---

## Documentation Index

| Document | Location |
|----------|----------|
| [Complete Services Index](../../docs/SERVICES_INDEX.md) | Full file-by-file documentation |
| [Python Refactoring Guide](../../docs/PYTHON_REFACTORING_GUIDE.md) | Anti-patterns and techniques |
| [Refactoring Status](../../docs/REFACTORING_STATUS_CURRENT.md) | Current refactoring state |
| [Module Technical Descriptions](../../services/MODULE_TECHNICAL_DESCRIPTIONS.md) | Detailed module descriptions |

---

*Generated from analysis of the C:\Users\carmi\AI workspace.*