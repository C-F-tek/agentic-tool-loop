# Python Refactoring Guide - Applied Patterns

## Complexity Anti-Patterns Identified

The codebase has **300+ functions returning `dict[str, Any]`**, representing the "Functions That Should Be Objects" anti-pattern.

### Pattern 1: Functions That Should Be Objects

**Before (current state):**
```python
def repo_search(args: dict[str, Any], root: Path) -> dict[str, Any]:
    # ... complex logic ...
    return {
        "ok": True,
        "tool": "repo_search",
        "count": len(results),
        "items": results,
        "artifact": str(artifact_path),
        # ... 20+ other fields ...
    }
```

**After (refactored with dataclass):**
```python
@dataclass(slots=True)
class ToolResult:
    ok: bool = True
    tool: str = ""
    count: int = 0
    items: list[Any] = field(default_factory=list)
    
def repo_search(args: dict[str, Any], root: Path) -> dict[str, Any]:
    result = ToolResult.ok_result(tool="repo_search", count=len(results), items=results)
    return asdict(result)  # Backward compatible dict output
```

### Pattern 2: Complex Dictionary Handling

**Before (current state - _window_text):**
```python
def _window_text(text: str, *, query: str = "", max_chars: int = 3000) -> dict[str, Any]:
    full = str(text or "")
    budget = max(500, int(max_chars or 3000))
    if len(full) <= budget:
        return {
            "text": full,
            "window_start": 0,
            "window_end": len(full),
            "full_chars": len(full),
            "window_chars": len(full),
            "complete": True,
            "has_more_before": False,
            "has_more_after": False,
            "sha256": _text_hash(full),
            "window_sha256": _text_hash(full),
        }
    # ... more complex logic ...
```

**After (refactored with PromptWindow dataclass):**
```python
@dataclass(slots=True)
class PromptWindow:
    text: str = ""
    window_start: int = 0
    window_end: int = 0
    full_chars: int = 0
    window_chars: int = 0
    complete: bool = True
    has_more_before: bool = False
    has_more_after: bool = False
    sha256: str = ""
    window_sha256: str = ""

def _window_text(text: str, *, query: str = "", max_chars: int = 3000) -> dict[str, Any]:
    window = PromptWindow.from_full_text(text, query=query, max_chars=max_chars)
    return {
        "text": window.text,
        "window_start": window.window_start,
        # ... clean mapping to dict for backward compatibility
    }
```

### Pattern 3: Triangular Code (Deeply Nested Conditionals)

**Before:**
```python
def complex_function(data):
    if isinstance(data, dict):
        if data.get("key"):
            if isinstance(data["key"], list):
                if len(data["key"]) > 0:
                    for item in data["key"]:
                        if isinstance(item, dict):
                            if item.get("nested"):
                                # ... deeper nesting
```

**After (flattened with early returns):**
```python
def complex_function(data):
    if not isinstance(data, dict):
        return default_result()
    
    key = data.get("key")
    if not isinstance(key, list) or not key:
        return default_result()
    
    for item in key:
        nested = item.get("nested") if isinstance(item, dict) else None
        if not nested:
            continue
        # Process nested value
```

## Applied Refactoring

### Files Modified

1. **Created `tool_result.py`** - New structured result types
   - `ToolResult` - Replaces repetitive dict pattern for tool results
   - `PromptWindow` - Extracted from `_window_text()` anti-pattern
   - `DiagnosticResult` - Structured diagnostic tracking

2. **Modified `memory_tools.py`** - Applied PromptWindow pattern
   - `_window_text()` now uses `PromptWindow.from_full_text()` factory
   - Reduced code duplication by extracting common window calculation logic

3. **Maintained backward compatibility** - All 330 tests pass

## Next Steps for Further Refactoring

### Priority 1: Core Tool Functions (~32 functions)
Apply `ToolResult` pattern to:
- `repo_search`, `repo_read`, `repo_tree`, `repo_list_files`
- `repo_patch`, `repo_apply_unified_diff`, `repo_write_file`
- `terminal_list_files`, `terminal_search_files`
- `repo_validate`

### Priority 2: HTML Generation (`job_html.py` ~1400 lines)
Extract `JsonNode`/`JsonArray` classes:
- 50+ helper functions returning dict fragments
- Could use structured JSON building classes

### Priority 3: Decision Logic (`decision.py`)
Flatten triangular code patterns:
- Replace nested isinstance checks with early returns
- Extract validation logic into dedicated validator classes

### Tracking Progress
Run wily complexity metrics to track refactoring progress:
```bash
pip install wily
wily report services/aicarmine_broker --json > complexity_report.json
```

## Benefits of This Approach

1. **Type safety** - Dataclasses provide IDE autocomplete and type checking
2. **Reduced duplication** - Common patterns extracted once, reused everywhere
3. **Backward compatible** - Existing dict-based callers continue working
4. **Testable** - Each dataclass can be tested independently
5. **Maintainable** - Clear separation between structure (dataclass) and behavior (methods)