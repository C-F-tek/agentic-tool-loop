# Refactoring Quick Reference Guide

Last updated: 2026-06-26T14:05:00+02:00

## Anti-Pattern Detection Checklist

Use this checklist when reviewing Python code for complexity issues.

### 1. Functions That Should Be Objects ✅

**Symptoms:**
- Function has >50 lines of code
- Function manages its own state via mutable defaults (`_cache=None`, `_step=0`)
- Function has multiple responsibilities (process, validate, persist, log)

**Fix:** Extract into a class with explicit state and single-responsibility methods

**Example:** `evidence_contract_builder.py` — Consolidated 12 import blocks into lazy imports inside function body

---

### 2. Objects That Should Be Functions ✅

**Symptoms:**
- Class has only one method (especially staticmethod)
- Class has no meaningful state
- Class is used as a namespace for related functions

**Fix:** Flatten to module-level functions with clear names

**Example:** Config loaders, path resolvers, validators

---

### 3. Triangular Code → Flat Code ✅

**Symptoms:**
- Nested `if/elif/else` chains with >3 levels
- Each branch does similar work but with different values
- Cyclomatic complexity >10 per function

**Fix:** Use guard clauses + early returns + flat decision tables

**Example:** `agentic_v2.py` — `_TOOL_PATH_KEYS` dict replaced 20+ elif branches
**Example:** `tool_context.py` — `_TOOL_ARTIFACT_KINDS` dict replaced 9 elif branches

---

### 4. Complex Dictionaries → Query Tools / Dataclasses ✅

**Symptoms:**
- Dictionary with >5 keys accessed via string literals
- Deep nesting: `dict.get("a", {}).get("b", {}).get("c")`
- Repeated type checking: `if isinstance(d.get("x"), dict) else {}`

**Fix:** Use query helpers (`_get()`) or dataclasses with typed fields

**Example:** `turn_surface_policy.py` — `_get_dict()` helper eliminated ~60 redundant type checks

---

### 5. Missing attrs/dataclasses ✅

**Symptoms:**
- Manual `__init__`, `__repr__`, `__eq__` methods
- Dictionary used as structured data
- Repeated boilerplate for simple data containers

**Fix:** Use `@dataclass(frozen=True)` for immutable, type-safe data classes

---

## Refactoring Patterns Cheat Sheet

### Pattern 1: Lazy Imports (Circular Dependency Fix)

```python
# ANTI-PATTERN: Module-level imports create circular deps
from .submodule_a import func_a  # Line 10
from .submodule_b import func_b  # Line 15
from .submodule_c import func_c  # Line 20
# ... 10+ more imports ...

# FIX: Single lazy import inside function body
def my_function(*args):
    from .submodule_a import func_a
    from .submodule_b import func_b
    from .submodule_c import func_c
    # ... use imports ...
```

**When to use:** When module imports create circular dependency risk
**Impact:** Eliminates circular deps, reduces module coupling

---

### Pattern 2: Flat Decision Table (Triangular Code Fix)

```python
# ANTI-PATTERN: Triangular if/elif chain
def classify_tool(tool: str) -> str:
    if tool == "repo_read":
        return "read"
    elif tool == "repo_search":
        return "search"
    elif tool == "repo_tree":
        return "tree"
    # ... 15+ more elif branches ...
    else:
        return "unknown"

# FIX: Flat decision table
_TOOL_CLASSIFICATION = {
    "repo_read": "read",
    "repo_search": "search",
    "repo_tree": "tree",
    # ... all mappings ...
}

def classify_tool(tool: str) -> str:
    """Classify a tool by its type."""
    return _TOOL_CLASSIFICATION.get(tool, "unknown")
```

**When to use:** When each elif branch handles different values for the same output type
**Impact:** O(1) lookup instead of O(n) conditionals, trivial to add new mappings

---

### Pattern 3: Query Helper for Nested Dicts

```python
# ANTI-PATTERN: Deep nested dict navigation
def get_planner_step(events):
    for event in events:
        if event.get("event_type") == "planner-prompts":
            step = event.get("step", {})
            if isinstance(step, dict):
                payload = step.get("payload", {})
                if isinstance(payload, dict):
                    prompts = payload.get("prompts", [])
                    if prompts:
                        return prompts
    return None

# FIX: Query helper for safe navigation
def _get(d, *keys, default=None):
    """Safely navigate nested dictionaries."""
    current = d
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key, default)
    return current

def get_planner_step(events):
    """Extract planner prompts from events using query helper."""
    for event in events:
        if _get(event, "event_type") == "planner-prompts":
            prompts = _get(event, "step", "payload", "prompts")
            if prompts:
                return prompts
    return None
```

**When to use:** When navigating deeply nested dictionaries with repeated `.get()` calls
**Impact:** Eliminates repetitive type checking, reduces LOC by 40-60%

---

### Pattern 4: Dependency Injection via Dict (Avoid Circular Imports)

```python
# ANTI-PATTERN: Hard-coded imports create tight coupling
def validate_decision(decision, history):
    from .agentic_v2 import decision_paths
    from .validator import check_validity
    # ... validation logic ...

# FIX: Inject dependencies via params dict
def validate_decision(decision, history, *, deps=None):
    deps = deps or {}
    decision_paths = deps.get("decision_paths") or _default_decision_paths
    check_validity = deps.get("check_validity") or _default_check_validity
    # ... validation logic ...
```

**When to use:** When functions need many dependencies that create circular import risk
**Impact:** Enables lazy loading, testable with mock dependencies

---

## Metrics Reference

| Metric | Threshold | Tool |
|--------|-----------|------|
| Function LOC | ≤ 50 | `wc -l`, PyCharm |
| Cyclomatic Complexity | ≤ 10 | `mccabe`, wily |
| Cognitive Complexity | ≤ 15 | `radin`, pylint |
| Nesting Depth | ≤ 3 | PyCharm inspection |
| Dict Keys | ≤ 8 | Manual review |
| Lines per File | ≤ 500 | `wc -l` |

---

## Quick Commands

```powershell
# Check complexity of a file
mccute -r 10 services/aicarmine_broker/application/planner/decision.py

# Run ruff linting
cd services; $env:PYTHONPATH = "C:\Users\carmi\AI\services"; ruff check application/planner/ --output-format=concise

# Count lines in files
Get-ChildItem -Recurse *.py | Select-Object FullName, @{Name="Lines";Expression={(Get-Content $_.FullName).Count}} | Sort Lines -Descending

# Find functions with high nesting
Select-String -Pattern "^\s{8,}" -Path services\aicarmine_broker\application\planner\*.py
```

---

## Recent Refactoring Sessions

### 2026-06-26: Clean Code Strategy Applied

| File | Anti-Pattern | Fix | Before | After | Change |
|------|-------------|-----|--------|-------|--------|
| `evidence_contract_builder.py` | 12 nested import blocks | Lazy imports | 409 | 387 | -22 |
| `agentic_v2.py` | Triangular if/elif (20+ branches) | Flat decision table | 236 | 251 | +15 clarity |
| `tool_context.py` | 9 elif branches | Lookup table | 569 | 554 | -15 |

**Verification:** Ruff lint 0 errors, all imports OK, broker running on port 3579

---

*This document is a quick reference. For detailed case studies, see `docs/PYTHON_REFACTORING_GUIDE.md` and `docs/REFACTORING_STATUS_CURRENT.md`.*