# Refactoring Prompt Template — How to Make the IA Work Strong on Refactoring

## Overview

This document provides ready-to-use prompts for triggering deep, forensic refactoring sessions using the AICarmine MCP toolchain. The prompts leverage the existing `aicarmine_refactor` skill, `repo_code_mcp_server`, and `repo_validate_mcp_server` for safe, evidence-first refactoring.

---

## Prompt 1: Complexity Audit & Target Selection

**Use when:** You want the IA to identify the most complex files and propose targeted refactoring.

```
TASK: Python Code Complexity Audit & Refactoring Plan

CONTEXT:
- Repository root: C:\Users\carmi\AI
- Focus area: services/aicarmine_broker/ (or specific subdirectory)
- Goal: Identify complexity anti-patterns and create a prioritized refactoring plan

INSTRUCTIONS:
1. Use aicarmine_code_dep_graph_health → code_build_dep_graph to understand module dependencies
2. Use aicarmine_repo_search_det → repo_search_ctags or repo_search_rg to find functions/classes with high cyclomatic complexity
3. Look for these complexity anti-patterns:
   - Functions that should be objects (procedural code blocks >50 lines)
   - Objects that should be functions (over-engineered simple operations)
   - Triangular code (nested conditionals, cascading if/elif/else)
   - Complex dictionary handling (should use attrs/dataclasses instead)
4. Report the top 5 most complex files with specific line ranges

PREFERRED TOOLS:
- aicarmine_code_dep_graph_health
- aicarmine_code_build_dep_graph
- aicarmine_repo_search_ctags
- aicarmine_repo_search_rg

OUTPUT FORMAT:
List each target file with:
- File path and line count
- Complexity score (estimated)
- Specific anti-patterns found
- Recommended refactoring action
```

---

## Prompt 2: Function-to-Class Refactoring

**Use when:** You have procedural functions that need to be converted to classes (State pattern, Strategy pattern, etc.).

```
TASK: Convert Procedural Functions to Classes

CONTEXT:
- Target file: services/aicarmine_broker/<specific_file>.py
- Pattern: Functions that should be objects (State/Strategy pattern)
- Goal: Replace procedural function calls with class-based state management

ANTI-PATTERN TO LOOK FOR:
```python
# Before: Procedural state machine
def handle_state_a(data): ...
def handle_state_b(data): ...
current_state = "a"

if current_state == "a":
    handle_state_a(data)
elif current_state == "b":
    handle_state_b(data)
```

# After: Class-based state machine
class StateMachine:
    def __init__(self):
        self._state = None
    
    def set_state(self, state):
        self._state = state
    
    def handle(self, data):
        if self._state == "a":
            return self._handle_state_a(data)
        elif self._state == "b":
            return self._handle_state_b(data)
```

INSTRUCTIONS:
1. Read the target file completely using repo_search_ctags for symbol overview
2. Identify all procedural functions that represent states/strategies
3. Propose a class-based structure using repo_code_propose_edit
4. Apply changes using repo_code_apply_patch (only when explicitly authorized)

PREFERRED TOOLS:
- aicarmine_repo_search_ctags (symbol overview)
- aicarmine_repo_code_propose_edit (structured_edit)
- aicarmine_repo_validate_ruff (lint verification)

CONSTRAINTS:
- Do not change external API signatures
- Maintain backward compatibility where possible
- Use scope="tracked" for git-tracked file operations only
```

---

## Prompt 3: Dataclass/Attrs Conversion

**Use when:** You have complex dictionaries or simple data containers that should use dataclasses.

```
TASK: Convert Complex Dictionaries to dataclasses

CONTEXT:
- Target file: services/aicarmine_broker/<specific_file>.py
- Pattern: Complex dictionary handling → attrs/dataclasses
- Goal: Replace dict-based data structures with typed dataclasses

ANTI-PATTERN TO LOOK FOR:
```python
# Before: Dictionary-based config
config = {
    "timeout": 30,
    "retry_count": 3,
    "backoff_factor": 0.5,
    "max_retries": 5,
}
config["timeout"] = 60  # Hard to track errors
```

# After: Dataclass-based config
from dataclasses import dataclass

@dataclass
class RetryConfig:
    timeout: int = 30
    retry_count: int = 3
    backoff_factor: float = 0.5
    max_retries: int = 5

config = RetryConfig()
config.timeout = 60  # Type-checked, IDE-friendly
```

INSTRUCTIONS:
1. Use aicarmine_repo_search_rg to find dictionary patterns with >3 keys
2. Identify all access patterns (dict["key"] = value)
3. Propose dataclass structure using repo_code_propose_edit
4. Update all access sites to use dot notation

PREFERRED TOOLS:
- aicarmine_repo_search_rg (find complex dicts)
- aicarmine_repo_code_propose_edit (structured_edit)
- aicarmine_repo_validate_pyright (type checking)

CONSTRAINTS:
- Preserve dict-like behavior if code expects dict input
- Add __init__ parameter defaults matching original dict values
```

---

## Prompt 4: Triangular Code Flattening

**Use when:** You have deeply nested conditionals (if/elif/else chains) that need flattening.

```
TASK: Flatten "Triangular" Code to Flat Code

CONTEXT:
- Target file: services/aicarmine_broker/<specific_file>.py
- Pattern: Cascading if/elif/else → early returns, guard clauses, strategy patterns
- Goal: Reduce nesting depth from 3+ levels to 1-2 levels

ANTI-PATTERN TO LOOK FOR:
```python
# Before: Triangular code
def process(data):
    if data is not None:
        if isinstance(data, dict):
            if "key" in data:
                if data["key"] is not None:
                    # Deep nesting!
                    result = handle(data["key"])
                    return result
            else:
                return default()
        else:
            return error()
    else:
        return default()

# After: Flat code with guard clauses
def process(data):
    if data is None:
        return default()
    if not isinstance(data, dict):
        raise TypeError("expected dict")
    if "key" not in data or data["key"] is None:
        return default()
    return handle(data["key"])
```

INSTRUCTIONS:
1. Use aicarmine_repo_search_rg to find functions with nesting depth >3
2. Identify each nested block and its condition
3. Propose guard clause refactoring using repo_code_propose_edit
4. Verify no logic changes using repo_validate_pyright

PREFERRED TOOLS:
- aicarmine_repo_search_rg (find deep nesting)
- aicarmine_repo_code_propose_edit (structured_edit)
- aicarmine_repo_validate_pyright (logic verification)

CONSTRAINTS:
- Preserve exact logic flow (no behavioral changes)
- Only reorder conditions for readability, not change semantics
```

---

## Prompt 5: Full Repository Refactoring Sweep

**Use when:** You want the IA to perform a comprehensive refactoring across the entire repository.

```
TASK: Comprehensive Python Code Refactoring Sweep

CONTEXT:
- Repository root: C:\Users\carmi\AI
- Scope: services/ directory (or specific subdirectory)
- Goal: Systematically identify and fix complexity anti-patterns

WORKFLOW:
1. Phase 1: Discovery
   - Use aicarmine_code_dep_graph_health → code_build_dep_graph
   - Use aicarmine_repo_search_ctags for all symbols
   - Identify files with >500 lines, functions with >50 lines

2. Phase 2: Target Selection
   - Rank files by complexity score
   - Select top 10 targets for refactoring
   - For each target, identify specific anti-patterns

3. Phase 3: Refactoring (one file at a time)
   - Read target file completely
   - Propose structured_edit changes
   - Validate with ruff/pyright
   - Apply only when explicitly authorized

ANTI-PATTERNS TO TARGET:
- Functions that should be objects
- Objects that should be functions
- Triangular code → flat code
- Complex dictionaries → dataclasses/attrs
- Duplicate utility functions → shared utilities
- Local imports → centralized import registry

CONSTRAINTS:
- Use repo_code_mcp_server for all source modifications
- Use repo_validate_mcp_server for all validation
- Do not modify tests unless explicitly requested
- Report line count of every modified file
- Preserve backward compatibility

PREFERRED TOOLS:
- aicarmine_code_dep_graph_health
- aicarmine_code_build_dep_graph
- aicarmine_repo_search_ctags
- aicarmine_repo_search_rg
- aicarmine_repo_code_propose_edit
- aicarmine_repo_validate_ruff
- aicarmine_repo_validate_pyright
```

---

## Prompt 6: Import Registry Creation (Phase 1 Step 2)

**Use when:** You want to create the centralized import registry to fix PLC0415 violations.

```
TASK: Create Centralized Import Registry

CONTEXT:
- File to create: services/aicarmine_broker/import_refs.py
- Goal: Replace local imports with lazy-loading registry
- Pattern: ~80 lines, thread-safe via threading.Lock

REQUIREMENTS:
1. Create ImportRegistry class with:
   - _cache: dict[str, Any] for cached imports
   - _lock: threading.Lock for thread safety
   - _resolve_lazy(module_path: str, symbol_names: list[str]) → dict

2. Provide module-level convenience functions:
   - get_helper() → returns cached 'helper' module
   - get_planner() → returns cached 'planner' module
   - (etc., one per lazy-imported module)

3. Each convenience function should:
   - Call _resolve_lazy internally
   - Cache result on first call
   - Return cached result on subsequent calls

4. Add to AGENTS.md: "Use ImportRegistry for lazy imports"

PREFERRED TOOLS:
- aicarmine_repo_code_propose_edit (create new file)
- aicarmine_repo_validate_pyright (verify syntax)

CONSTRAINTS:
- File must be <1200 lines (Cline rule)
- Use only stdlib (no external packages)
- Thread-safe via threading.Lock
```

---

## Prompt 7: Ruff Configuration Setup (Phase 1 Step 1)

**Use when:** You want to set up proper ruff configuration to eliminate PLC0415 violations.

```
TASK: Configure Ruff for Lazy Import Tolerance

CONTEXT:
- File: services/pyproject.toml
- Goal: Add [tool.ruff] section that ignores PLC0415 globally and per-file

1. Update ruff version in requirements or pyproject.toml to >=0.4.0

PREFERRED TOOLS:
- aicarmine_repo_code_propose_edit (modify pyproject.toml)
- aicarmine_repo_validate_ruff (verify configuration)

CONSTRAINTS:
- Do not change line-length from 120
- Only add ignore rules for lazy imports and wildcard exports
- Preserve existing ruff configuration
```

---

## Quick Reference: Prompt Selection Guide

| Situation | Use Prompt | Estimated Effort |
|-----------|-----------|-----------------|
| Find complex files first | #1: Complexity Audit | 30 min |
| Convert functions to classes | #2: Function-to-Class | 1 hour |
| Replace dicts with dataclasses | #3: Dataclass Conversion | 30 min |
| Flatten nested conditionals | #4: Triangular Code | 1 hour |
| Full sweep refactoring | #5: Comprehensive Sweep | 4-6 hours |
| Create import registry | #6: Import Registry | 1 hour |
| Setup ruff config | #7: Ruff Configuration | 30 min |

---

## Tips for Best Results

1. **Be specific about scope:** Always specify the exact file path or directory when possible
2. **Mention constraints:** Include "do not change external API signatures" and "preserve backward compatibility"
3. **Use MCP tools explicitly:** Reference the preferred tools in your prompt
4. **Request structured output:** Ask for file paths, line counts, and diff previews
5. **Validate before applying:** Always run `ruff check` or `pyright` before approving changes
6. **One file at a time:** Refactor one file completely before moving to the next
7. **Track progress:** Use the implementation_plan.md checklist to track completed phases