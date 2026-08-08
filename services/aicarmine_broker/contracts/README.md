# Contracts Module — Protocol Interfaces

> **Purpose**: Abstract protocol interfaces (Python protocols/interfaces) that define contracts between layers. No implementations — pure type definitions for dependency inversion.

---

## Files

| File | Purpose | Key Types |
|------|---------|-----------|
| `__init__.py` | Package init | — |
| `command_runner.py` | Command runner contract | `CommandRunnerProtocol` |
| `dispatcher.py` | Dispatcher contract | `DispatcherProtocol` |
| `job_repository.py` | Job repository contract | `JobRepositoryProtocol` |
| `planner_client.py` | Planner client contract | `PlannerClientProtocol` |
| `prompt_store.py` | Prompt store contract | `PromptStoreProtocol` |
| `repo_filesystem.py` | Repo filesystem contract | `RepoFilesystemProtocol` |
| `tool.py` | Tool contract | `ToolProtocol` |
| `validator.py` | Validator contract | `ValidatorProtocol` |

---

## Protocol Hierarchy

```
Contracts (protocols)
    ↓ implemented by
Infrastructure (implementations)
    ↓ used by
Application (business logic)
```

---

## Key Protocols

### Command Runner (`command_runner.py`)

| Method | Purpose |
|--------|---------|
| `run_command(cmd, timeout)` | Execute shell command with timeout |

### Dispatcher (`dispatcher.py`)

| Method | Purpose |
|--------|---------|
| `dispatch(tool_call)` | Dispatch tool call to appropriate handler |

### Job Repository (`job_repository.py`)

| Method | Purpose |
|--------|---------|
| `save(job)` | Save job to persistence |
| `load(job_id)` | Load job from persistence |
| `delete(job_id)` | Delete job from persistence |

### Planner Client (`planner_client.py`)

| Method | Purpose |
|--------|---------|
| `generate_response(messages, max_tokens)` | Generate LLM response |

### Tool (`tool.py`)

| Method | Purpose |
|--------|---------|
| `execute(args)` | Execute tool with arguments |

---

## Documentation Index

| Document | Location |
|----------|----------|
| [Complete Services Index](../../docs/SERVICES_INDEX.md) | Full file-by-file documentation |
| [Python Refactoring Guide](../../docs/PYTHON_REFACTORING_GUIDE.md) | Protocol/interface patterns |

---

*Generated from analysis of the C:\Users\carmi\AI workspace.*