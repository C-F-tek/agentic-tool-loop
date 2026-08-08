# Domain Module — Domain Models

> **Purpose**: Pure domain models: decision types, job states, tool definitions, evidence records, configuration values, error types, and result models. No infrastructure dependencies.

---

## Files

| File | Purpose | Key Types |
|------|---------|-----------|
| `__init__.py` | Package init | — |
| `config.py` | Domain config types | Value objects for configuration |
| `decisions.py` | Decision domain model | `Decision`, `DecisionPath` |
| `errors.py` | Domain error types | Custom exception hierarchy |
| `evidence.py` | Evidence domain model | `EvidenceRecord`, evidence types |
| `job.py` | Job domain model | `JobState`, job lifecycle states |
| `models.py` | Shared domain models | Common value objects |
| `results.py` | Result domain model | `ToolResultDomain`, result types |
| `tool.py` | Tool domain model | `ToolDefinition`, tool metadata |

---

## Key Types

### Decisions (`decisions.py`)

| Type | Purpose |
|------|---------|
| `Decision` | Represents a planner decision with path, justification, and metadata |
| `DecisionPath` | Enum of possible decision paths (execute, repair, replan, terminate) |

### Job (`job.py`)

| Type | Purpose |
|------|---------|
| `JobState` | Current state in job lifecycle (pending, running, completed, failed, terminated) |

### Evidence (`evidence.py`)

| Type | Purpose |
|------|---------|
| `EvidenceRecord` | Evidence data with source, content, and confidence |

### Tool (`tool.py`)

| Type | Purpose |
|------|---------|
| `ToolDefinition` | Tool metadata: name, description, parameters, schema |

---

## Documentation Index

| Document | Location |
|----------|----------|
| [Complete Services Index](../../docs/SERVICES_INDEX.md) | Full file-by-file documentation |
| [Python Refactoring Guide](../../docs/PYTHON_REFACTORING_GUIDE.md) | Domain model patterns |

---

*Generated from analysis of the C:\Users\carmi\AI workspace.*