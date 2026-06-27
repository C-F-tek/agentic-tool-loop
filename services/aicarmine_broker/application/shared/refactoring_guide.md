# Python Refactoring Guide — Applied Patterns & Best Practices

## Table of Contents

1. [Complexity Anti-Patterns](#complexity-anti-patterns)
2. [Pattern 1: Functions That Should Be Objects](#pattern-1-functions-that-should-be-objects)
3. [Pattern 2: Objects That Should Be Functions](#pattern-2-objects-that-should-be-functions)
4. [Pattern 3: Triangular Code (Deeply Nested Conditionals)](#pattern-3-triangular-code-deeply-nested-conditionals)
5. [Pattern 4: Complex Dictionary Handling](#pattern-4-complex-dictionary-handling)
6. [Pattern 5: attrs and dataclasses for Boilerplate Reduction](#pattern-5-attrs-and-dataclasses-for-boilerplate-reduction)
7. [Refactoring Workflow](#refactoring-workflow)
8. [Evidence-First Diagnosis](#evidence-first-diagnosis)
9. [Constraints & Guardrails](#constraints--guardrails)
10. [MCP Servers for Refactoring](#mcp-servers-for-refactoring)
11. [Environment Information](#environment-information)
12. [Appendix: Quick Command Reference](#appendix-quick-command-reference)

---

## Complexity Anti-Patterns

The codebase has **300+ functions returning `dict[str, Any]`**, representing the "Functions That Should Be Objects" anti-pattern. This guide documents identified patterns and their corrections.

### Detection Tools

Run Wily complexity metrics to track refactoring progress:

```bash
pip install wily
wily report services/aicarmine_broker --json > complexity_report.json
wily rank --metric cyclomatic --limit 50
ast_complexity_report  # via MCP (aicarmine_wily server)
ast_top_functions(limit=20, min_complexity=10)  # via MCP (aicarmine_wily server)
```

**Current Environment:** Python 3.11.9 | Git branch: `Local-AI-coding-work-base`

**Verification:** Run `wily_health` via MCP to confirm availability before use.

---

## Pattern 1: Functions That Should Be Objects

**Symptom:** Long functions with many conditional branches that manage their own state via parameters. These functions typically return dicts with 10+ fields.

### Before (Current State)

```python
def repo_search(args: dict[str, Any], root: Path) -> dict[str, Any]:
    """Search repository files."""
    results = []
    ok = True
    tool = "repo_search"
    count = 0
    artifact = ""
    
    try:
        for f in os.listdir(root):
            if f.endswith(".py"):
                results.append(f)
                count += 1
    except Exception as e:
        ok = False
        artifact = str(e)
    
    return {
        "ok": ok,
        "tool": tool,
        "count": count,
        "items": results,
        "artifact": artifact,
        "search_root": str(root),
        "pattern": args.get("pattern", ""),
        "max_results": args.get("max_results", 100),
        "elapsed_ms": 0,
        "cache_key": "",
        "cached": False,
        "error": None if ok else str(artifact),
        "metadata": {},
    }
```

**Problems:**
- 14 fields in return dict — hard to maintain, easy to forget updating
- No type safety — IDE cannot autocomplete field access
- State managed via local variables scattered throughout function body
- Return dict construction duplicated across error/success paths

### After (Refactored with dataclass)

```python
@dataclass(slots=True)
class ToolResult:
    """Structured result for tool operations."""
    ok: bool = True
    tool: str = ""
    count: int = 0
    items: list[Any] = field(default_factory=list)
    artifact: str = ""
    search_root: str = ""
    pattern: str = ""
    max_results: int = 100
    elapsed_ms: int = 0
    cache_key: str = ""
    cached: bool = False
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def ok_result(cls, *, tool: str, count: int = 0, **kwargs) -> "ToolResult":
        """Factory for successful results."""
        return cls(ok=True, tool=tool, count=count, error=None, **kwargs)
    
    @classmethod
    def error_result(cls, *, tool: str, error: str, **kwargs) -> "ToolResult":
        """Factory for error results."""
        return cls(ok=False, tool=tool, error=error, **kwargs)

def repo_search(args: dict[str, Any], root: Path) -> dict[str, Any]:
    """Search repository files."""
    result = ToolResult.ok_result(
        tool="repo_search",
        search_root=str(root),
        pattern=args.get("pattern", ""),
        max_results=args.get("max_results", 100),
    )
    try:
        for f in os.listdir(root):
            if f.endswith(".py"):
                result.items.append(f)
                result.count += 1
    except Exception as e:
        return ToolResult.error_result(tool="repo_search", error=str(e)).__dict__
    
    return asdict(result)  # Backward compatible dict output
```

**Benefits:**
- **Type safety** — Dataclasses provide IDE autocomplete and type checking
- **Reduced duplication** — Common patterns extracted once, reused everywhere
- **Backward compatible** — Existing dict-based callers continue working via `asdict()`
- **Testable** — Each dataclass can be tested independently
- **Clear separation** — Structure (dataclass) vs. behavior (methods)

### Guidelines

| Condition | Action |
|-----------|--------|
| Function returns dict with 10+ fields | Extract to `@dataclass(slots=True)` |
| Function has >5 conditional branches | Consider extracting logic into a class or method |
| Multiple error paths return different dict shapes | Use `.ok_result()` / `.error_result()` factory methods |
| Dict keys are accessed by position (`d["key"]`) | Convert to attribute access (`result.key`) |

---

## Pattern 2: Objects That Should Be Functions

**Symptom:** Classes with single-method protocols or simple data containers that could be `dataclass` or `namedtuple`.

### Before (Over-Engineered)

```python
class PromptWindowBuilder:
    """Builds prompt window configurations."""
    
    def __init__(self, text: str, query: str = "", max_chars: int = 3000):
        self.text = text
        self.query = query
        self.max_chars = max_chars
    
    def get_window_start(self) -> int:
        return 0
    
    def get_window_end(self) -> int:
        return len(self.text)
    
    def is_complete(self) -> bool:
        return len(self.text) <= self.max_chars
    
    def build(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "window_start": self.get_window_start(),
            "window_end": self.get_window_end(),
            "complete": self.is_complete(),
        }
```

**Problems:**
- Single meaningful method (`build`) buried in class protocol
- Getter methods (`get_window_start`, `is_complete`) add noise
- Instantiation requires two steps: `__init__` then `.build()`

### After (Simplified Function)

```python
@dataclass(slots=True)
class PromptWindow:
    """Represents a window into prompt text."""
    text: str = ""
    window_start: int = 0
    window_end: int = 0
    complete: bool = True

def _window_text(text: str, *, query: str = "", max_chars: int = 3000) -> dict[str, Any]:
    """Extract a window from prompt text."""
    full = str(text or "")
    budget = max(500, int(max_chars or 3000))
    
    if len(full) <= budget:
        return PromptWindow(
            text=full,
            window_start=0,
            window_end=len(full),
            complete=True,
        ).__dict__
    
    # ... window extraction logic ...
    
    return window.__dict__
```

### Guidelines

| Condition | Action |
|-----------|--------|
| Class only has `__init__` and property accessors | Use `@dataclass(slots=True)` |
| Class has only one meaningful method | Inline it into a function |
| Class wraps a single value or tuple | Use `namedtuple` or `dataclass` |
| Class has no side effects in methods | Convert to pure functions |

---

## Pattern 3: Triangular Code (Deeply Nested Conditionals)

**Symptom:** Deeply nested if/else chains creating triangular code shapes. This is the most common anti-pattern in the codebase.

### Before (Triangular)

```python
def process_decision(decision: dict[str, Any]) -> dict[str, Any]:
    """Process a planner decision."""
    if isinstance(decision, dict):
        action = decision.get("action")
        if action:
            if isinstance(action, str):
                if action.lower() in ("tool", "execute"):
                    tool = decision.get("tool")
                    if tool:
                        if isinstance(tool, str):
                            if len(tool) > 0:
                                args = decision.get("arguments")
                                if args:
                                    if isinstance(args, dict):
                                        # ... 6+ levels deep ...
                                        return {
                                            "ok": True,
                                            "tool": tool,
                                            "args": args,
                                            "processed": True,
                                        }
                                    else:
                                        return {"ok": False, "error": "invalid_args"}
                                else:
                                    return {"ok": False, "error": "no_args"}
                            else:
                                return {"ok": False, "error": "empty_tool"}
                        else:
                            return {"ok": False, "error": "tool_not_str"}
                    else:
                        return {"ok": False, "error": "no_tool"}
                else:
                    return {"ok": False, "error": "unknown_action"}
            else:
                return {"ok": False, "error": "action_not_str"}
        else:
            return {"ok": False, "error": "no_action"}
    else:
        return {"ok": False, "error": "not_dict"}
```

**Problems:**
- 10+ levels of nesting — impossible to read without scrolling
- Every error path returns a different dict shape
- No early exit — all validation happens inside nested blocks
- Cyclomatic complexity: ~25 (should be <10)

### After (Flattened with Guard Clauses)

```python
def process_decision(decision: dict[str, Any]) -> dict[str, Any]:
    """Process a planner decision."""
    if not isinstance(decision, dict):
        return {"ok": False, "error": "not_dict"}
    
    action = decision.get("action")
    if not isinstance(action, str):
        return {"ok": False, "error": "action_not_str"}
    
    if action.lower() not in ("tool", "execute"):
        return {"ok": False, "error": "unknown_action"}
    
    tool = decision.get("tool")
    if not isinstance(tool, str) or not tool:
        return {"ok": False, "error": "invalid_tool"}
    
    args = decision.get("arguments")
    if not isinstance(args, dict):
        return {"ok": False, "error": "invalid_args"}
    
    return {
        "ok": True,
        "tool": tool,
        "args": args,
        "processed": True,
    }
```

**Benefits:**
- **Flat structure** — All validation at top level, no nesting
- **Cyclomatic complexity** reduced from ~25 to ~5
- **Early returns** make each condition self-documenting
- **Readability** — Can understand function in one pass

### Advanced: Guard Clause Pattern with Extracted Validation

```python
def _validate_dict(value: Any) -> bool:
    return isinstance(value, dict)

def _validate_string(value: Any) -> bool:
    return isinstance(value, str) and len(value) > 0

def process_decision(decision: dict[str, Any]) -> dict[str, Any]:
    """Process a planner decision."""
    if not _validate_dict(decision):
        return {"ok": False, "error": "not_dict"}
    
    action = decision.get("action")
    if not _validate_string(action):
        return {"ok": False, "error": "invalid_action"}
    
    if action.lower() not in ("tool", "execute"):
        return {"ok": False, "error": "unknown_action"}
    
    tool = decision.get("tool")
    if not _validate_string(tool):
        return {"ok": False, "error": "invalid_tool"}
    
    args = decision.get("arguments")
    if not _validate_dict(args):
        return {"ok": False, "error": "invalid_args"}
    
    return {"ok": True, "tool": tool, "args": args, "processed": True}
```

### Guidelines

| Pattern | Fix |
|---------|-----|
| `if x: if y: if z:` | Extract to early returns |
| Nested `try/except` inside `if` | Use guard clauses before try block |
| `else` blocks that just return | Convert to early return at top |
| Cyclomatic complexity >10 | Extract validation functions |

---

## Pattern 4: Complex Dictionary Handling

**Symptom:** Manual dict key checks that could use `.get()` or `.setdefault()`. Repeated key access patterns. Using `try/except KeyError` where `.get()` would suffice.

### Before (Manual Checks)

```python
def get_config_value(config: dict, key: str, default: Any = None) -> Any:
    """Get a value from config dict."""
    if key in config:
        value = config[key]
        if isinstance(value, dict):
            nested_key = key + "_nested"
            if nested_key in config:
                return config[nested_key]
            else:
                return value.get("default", default)
        else:
            return value
    else:
        return default
```

**Problems:**
- `key in config` then `config[key]` — double lookup
- Nested manual checks for each level
- No reuse of access pattern

### After (Using .get() and .setdefault())

```python
def get_config_value(config: dict, key: str, default: Any = None) -> Any:
    """Get a value from config dict."""
    value = config.get(key)
    if isinstance(value, dict):
        nested = config.get(key + "_nested")
        return nested if nested is not None else value.get("default", default)
    return value if value is not None else default
```

### Advanced: Safe Dict Access Helper

```python
def safe_get(mapping: Mapping[str, Any], *keys: str, default: Any = None) -> Any:
    """Safely navigate nested dict keys.
    
    Args:
        mapping: The dict to traverse.
        *keys: Sequential keys to access.
        default: Value to return if any key is missing.
    
    Example:
        safe_get(data, "user", "profile", "name", default="Unknown")
        # Equivalent to: data["user"]["profile"]["name"] or default
    """
    current = mapping
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
        if current is None:
            return default
    return current

# Usage:
name = safe_get(config, "planner", "decision", "tool", default="")
```

### Guidelines

| Pattern | Fix |
|---------|-----|
| `if k in d: v = d[k]` | Use `v = d.get(k)` |
| `try: v = d[k] except KeyError: v = default` | Use `v = d.get(k, default)` |
| Repeated `d.get("key")` calls | Extract to local variable or use `safe_get()` |
| `if key not in d: d[key] = []` | Use `d.setdefault(key, []).append(val)` |

---

## Pattern 5: attrs and dataclasses for Boilerplate Reduction

**Symptom:** Repetitive `__init__`, `__eq__`, `__repr__` methods. Simple data containers with many lines of boilerplate.

### Before (Manual Boilerplate)

```python
class ToolResult:
    def __init__(self, ok: bool, tool: str, count: int, items: list):
        self.ok = ok
        self.tool = tool
        self.count = count
        self.items = items
    
    def __eq__(self, other):
        if not isinstance(other, ToolResult):
            return False
        return (self.ok == other.ok and 
                self.tool == other.tool and
                self.count == other.count and
                self.items == other.items)
    
    def __repr__(self):
        return f"ToolResult(ok={self.ok}, tool={self.tool!r}, count={self.count})"
    
    def to_dict(self):
        return {
            "ok": self.ok,
            "tool": self.tool,
            "count": self.count,
            "items": self.items,
        }
```

**Problems:**
- 20+ lines for simple data container
- `__eq__` must be updated when fields change
- `__repr__` duplicates field names
- `to_dict()` manually lists all fields

### After (dataclass)

```python
@dataclass(slots=True)
class ToolResult:
    ok: bool = True
    tool: str = ""
    count: int = 0
    items: list[Any] = field(default_factory=list)
    
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
```

**Benefits:**
- **Auto-generated** `__init__`, `__eq__`, `__repr__`, `__hash__`
- **slots=True** reduces memory footprint (no `__dict__`)
- **field(default_factory=list)** handles mutable defaults correctly
- **asdict()** recursively converts nested dataclasses to dicts

### Guidelines

| Scenario | Tool |
|----------|------|
| Simple data container | `@dataclass(slots=True)` |
| Immutable data | `@dataclass(frozen=True)` |
| Nested data structures | `@dataclass` with `asdict()` |
| Custom validation in `__init__` | Use `__post_init__()` |
| Cross-field validation | Override `__eq__` or use `attrs` |

---

## Refactoring Workflow

### Phase 1: Complexity Audit

1. Run `wily_health` to verify Wily availability
2. Run `ast_complexity_report` for full workspace complexity overview
3. Run `ast_top_functions(limit=20, min_complexity=10)` to identify top complex functions
4. For each high-complexity file, run `ast_file_metrics(path="file.py")` for per-file breakdown

### Phase 2: Impact Analysis

1. Run `estimate_breakage_risk(file_path="file.py")` to understand impact
2. Run `find_callers(target_module="module")` to understand dependencies
3. Run `find_dependents(module="module")` to understand what this code depends on

### Phase 3: Refactoring Plan

1. Use `propose_edit` to build report-only proposal for changes
2. Review the diff carefully
3. Verify no unintended side effects

### Phase 4: Apply Changes

1. Use `apply_patch` with `allow_source_write=true` to apply changes
2. Run `ruff` on affected files to verify no new lint errors
3. Run `pyright` on affected files to verify type safety

### Phase 5: Verification

1. Re-run `ast_complexity_report` to verify complexity decreased
2. Run `ast_top_functions` to verify previously complex functions are now simpler
3. Check Git diff to verify only intended changes were made
4. Run full test suite to confirm no regressions

---

## Evidence-First Diagnosis

A valid diagnosis requires this chain:

```
symptom → evidence → confirmed cause → minimal fix → verification
```

### Steps

1. **Symptom** — Observed behavior only (e.g., "function has cyclomatic complexity of 85")
2. **Hypotheses** — Material explanations to test (e.g., "too many nested if/else", "missing dataclass")
3. **Evidence** — Concrete source, runtime, or tool evidence (e.g., "Wily reports 85 branches in function X")
4. **Confirmed cause** — The demonstrated causal mechanism (e.g., "function has 12 levels of nesting")
5. **Minimal fix** — The smallest contract-preserving correction (e.g., "extract 3 validation functions, flatten to early returns")
6. **Verification** — Original symptom check + targeted checks (e.g., "complexity reduced to 12, all tests pass")
7. **Residual risk** — Conditions that remain unverified (e.g., "performance impact unknown")

### Rules

- Prefer demonstrated runtime or source evidence over plausible explanations
- Do not stop at the first plausible cause — give each material hypothesis a discriminating check
- When evidence contradicts the diagnosis, stop and rebuild the causal chain
- Do not invent files, APIs, symbols, tools, processes, commits, payloads, states, or results
- Distinguish facts, inferences, hypotheses, and unknowns
- Stop broad investigation when the causal line is confirmed
- Do not repeat an identical tool call unless the underlying state changed

---

## Constraints & Guardrails

### Before Modifying Code

1. Identify the owner implementation
2. Verify which file is actually loaded
3. Check readers, writers, launchers, caches, overwrite paths
4. Use the smallest reversible correction in the existing owner component
5. Do not create wrappers, compatibility layers, or workarounds when the owner can be corrected directly

### After Modifying Code

1. Inspect the resulting diff
2. Run the narrowest relevant verification
3. Verify the original symptom when possible
4. Report the resulting line count of every modified source file

### Prohibited Actions (Without Explicit Authorization)

- Destructive deletion
- Force-push or history rewrite
- Merge to a protected or primary branch
- Production deployment
- Repository visibility changes
- Permission changes
- Secret or credential changes
- Billing changes

### Refactoring-Specific Constraints

- Use `scope=tracked` for project-wide renames (excludes external packages)
- Prefer `dry_run=true` first, then `dry_run=false` to apply changes
- Never write project memory unless explicitly authorized
- Never create persistent tests unless explicitly requested
- Never reformat unrelated code or perform broad refactors unless explicitly requested
- Report line count of every modified source file after changes

---

## MCP Servers for Refactoring

### Available Servers (Verified)

| Server | Status | Purpose | Key Tools |
|--------|--------|---------|-----------|
| `aicarmine_wily` | ✅ Active | Code complexity analysis | `ast_complexity_report`, `ast_file_metrics`, `ast_top_functions`, `wily_health`, `wily_rank`, `wily_report` |
| `aicarmine_code_dep_graph` | ✅ Active | Dependency analysis | `build_dep_graph`, `find_callers`, `find_dependents`, `estimate_breakage_risk`, `detect_circular_deps` |
| `aicarmine_repo_search_det` | ✅ Active | Code search | `repo_search_rg`, `repo_search_fd`, `repo_search_ast_grep`, `repo_search_ctags` |
| `aicarmine_repo_validate` | ✅ Active | Linting/type checking | `ruff`, `pyright`, `shellcheck`, `semgrep` |
| `aicarmine_git_readonly` | ✅ Active | Git operations | `diff`, `blame`, `show`, `log`, `branch_compare` |
| `aicarmine_rag` | ✅ Active | Semantic code search | `context`, `index_status`, `health`, `reindex` |

### Available Servers (Verified)

| Server | Status | Purpose | Key Tools |
|--------|--------|---------|-----------|
| `aicarmine_wily` | ✅ Active | Code complexity analysis | `ast_complexity_report`, `ast_file_metrics`, `ast_top_functions`, `wily_health`, `wily_rank`, `wily_report` |
| `aicarmine_code_dep_graph` | ✅ Active | Dependency analysis | `build_dep_graph`, `find_callers`, `find_dependents`, `estimate_breakage_risk`, `detect_circular_deps` |
| `aicarmine_repo_search_det` | ✅ Active | Code search | `repo_search_rg`, `repo_search_fd`, `repo_search_ast_grep`, `repo_search_ctags` |
| `aicarmine_repo_validate` | ✅ Active | Linting/type checking | `ruff`, `pyright`, `shellcheck`, `semgrep` |
| `aicarmine_git_readonly` | ✅ Active | Git operations | `diff`, `blame`, `show`, `log`, `branch_compare` |
| `aicarmine_rag` | ✅ Active | Semantic code search | `context`, `index_status`, `health`, `reindex` |
| `aicarmine_refactor` | ✅ Active | Symbol renaming, extraction | `refactor_rename_symbol`, `refactor_rename_symbol_rope`, `refactor_add_parameter`, `refactor_extract_function`, `refactor_rename_project`, `refactor_rename_project_bowler`, `git_list_tracked_files`, `refactor_health` |

**Note:** `aicarmine_refactor` was added to `.clinerules/cline_mcp_settings.json` with all 8 tools configured and auto-approved.

### Pre-call Protocol

Before using any MCP tool for the first time:

1. Call the server's `*_health` tool to verify availability
2. Use the full prefixed name (e.g., `aicarmine_wily.ast_complexity_report`, NOT just `ast_complexity_report`)
3. Never guess tool names — always check via `*_health` response

```python
# Correct MCP tool call format
use_mcp_tool(
    server_name="aicarmine_wily",
    tool_name="wily_health",
    arguments={}
)
```

---

## Quick Reference Commands

### "Show me the most complex code"
```bash
ast_complexity_report → ast_top_functions(limit=20, min_complexity=10)
```

### "Refactor this specific file"
```bash
ast_file_metrics(path="file.py") → propose_edit → apply_patch
```

### "Find all functions with complexity > 50"
```bash
ast_top_functions(limit=100, min_complexity=50)
```

### "Check impact before refactoring"
```bash
estimate_breakage_risk(file_path="file.py") → find_callers(target_module="module")
```

### "Run full test suite"
```bash
cd services/aicarmine_broker && python -m pytest tests/ -v --tb=short
```

### "Run ruff linting"
```bash
cd services/aicarmine_broker && python -m ruff check application/planner/ --output-format=concise