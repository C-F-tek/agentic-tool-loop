# Infrastructure Module — Infrastructure Layer

> **Purpose**: Low-level infrastructure: command execution, repository access, job storage, JSON I/O, LLM client wrapper, time utilities.

---

## Files

| File | Purpose | Key Functions/Classes |
|------|---------|----------------------|
| `__init__.py` | Package init | — |
| `command_runner.py` | Shell command execution | Runs shell commands with timeout |
| `executable_resolver.py` | Executable resolution | Resolves executable paths |
| `filesystem_repo.py` | Filesystem repository access | File operations on repo |
| `job_sqlite_store.py` | SQLite job storage | SQLite persistence layer |
| `job_store_repository.py` | Job store repository | Repository pattern for jobs |
| `json_files.py` | JSON file I/O | JSON read/write operations |
| `ollama_planner_client.py` | Ollama planner client | LLM client wrapper |
| `repo_tools.py` | Repository tool integration | Integrates repo tools |
| `result_compaction.py` | Result compaction (infra) | Infrastructure compaction |
| `time_provider.py` | Time provider | Time utilities |

---

## Layer Responsibilities

### Command Execution
- `command_runner.py` — Shell command execution with timeout and safety checks

### File System
- `filesystem_repo.py` — File read/write/list operations on repository
- `json_files.py` — JSON serialization/deserialization

### Persistence
- `job_sqlite_store.py` — SQLite-based job persistence
- `job_store_repository.py` — Repository pattern abstraction over job storage

### External Services
- `ollama_planner_client.py` — Ollama LLM client wrapper for planner decisions

### Utilities
- `executable_resolver.py` — Resolve executable paths from PATH or virtualenv
- `repo_tools.py` — Integrate repository tools with infrastructure
- `result_compaction.py` — Compact results for storage
- `time_provider.py` — Time utilities for timestamps and durations

---

## Documentation Index

| Document | Location |
|----------|----------|
| [Complete Services Index](../../docs/SERVICES_INDEX.md) | Full file-by-file documentation |
| [Python Refactoring Guide](../../docs/PYTHON_REFACTORING_GUIDE.md) | Infrastructure patterns |

---

*Generated from analysis of the C:\Users\carmi\AI workspace.*