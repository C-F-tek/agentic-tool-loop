# Job — Job Lifecycle Management

> **Purpose**: Job lifecycle management: action routing to lifecycle states, status/response formatting, terminal output, and worker management.

---

## Files

| File | Purpose | Key Types/Functions |
|------|---------|----------------------|
| `__init__.py` | Package init | — |
| `action_router.py` | Action routing to lifecycle states | `_ACTION_ROUTE_MAP` lookup dispatch |
| `lifecycle.py` | Job lifecycle states | State definitions |
| `response_values.py` | Response value formatting | Formats response values |
| `selector_runner.py` | Selector runner | Runs tool selectors |
| `status_response.py` | Status response formatting | Formats status responses |
| `terminal_response.py` | Terminal response formatting | Formats terminal responses |
| `wait_response.py` | Wait response handling | Handles wait responses |
| `worker.py` | Worker management | Manages job workers |

---

## Documentation Index

| Document | Location |
|----------|----------|
| [Application README](../../README.md) | Application layer overview |
| [Complete Services Index](../../../docs/SERVICES_INDEX.md) | Full file-by-file documentation |

---

*Generated from analysis of the C:\Users\carmi\AI workspace.*