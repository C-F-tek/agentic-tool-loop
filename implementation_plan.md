# Implementation Plan - Python Code Refactoring: PEP 8 Compliance, Technical Debt Reduction, Import Optimization

## Overview

This plan addresses three interconnected objectives across the `services/` directory: improve code readability by enforcing PEP 8 style guidelines, reduce technical debt caused by scattered `# noqa` comment abuse, and maintain fast resource loading through strategic lazy loading. The refactoring targets approximately 28 `# noqa` annotations distributed across 12 source files, with the dominant issue being PLC0415 (local imports used to avoid circular dependencies).

The root cause analysis reveals two distinct patterns: (1) ~18 instances of lazy imports guarded by `# noqa: PLC0415` to silence "module import not at top-level" warnings, and (2) ~8 instances of `# noqa: F401` suppressing "imported but unused" warnings in a config compatibility module that intentionally re-exports symbols. Additionally, no Ruff lint configuration currently exists in `pyproject.toml`, meaning lint rules are applied inconsistently.

The approach combines architectural fixes (dependency injection for bidirectional import pairs), configuration improvements (global Ruff settings in `pyproject.toml`), and code organization (optional import blocks at top level). This hybrid strategy minimizes runtime impact while eliminating scattered inline comments.

## Types

```python
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

class ImportPattern(Enum):
    """Classify import anti-patterns for targeted remediation."""
    LAZY_IMPORT_CIRCULAR = "lazy_import_circular"      # Local import to break circular dep
    OPTIONAL_DEPENDENCY = "optional_dependency"         # try/except ImportError block
    WILDCARD_REEXPORT = "wildcard_reexport"             # from X import * with noqa F401,F403
    UNUSED_SYMBOL = "unused_symbol"                     # Imported but never referenced


@dataclass
class ImportRefactorRecord:
    """Track remediation progress for individual import issues."""
    file_path: str
    line_number: int
    pattern: ImportPattern
    original_code: str
    resolution: str  # "injected", "suppressed_global", "top_level_block", "removed"
    old_noqa: str
    new_approach: str


@dataclass
class RuffConfigProfile:
    """Ruff lint configuration profile for project-wide application."""
    ignore_codes: list[str] = field(default_factory=lambda: ["PLC0415"])
    per_file_ignores: dict[str, list[str]] = field(default_factory=dict)
    extend_per_file_ignores: dict[str, list[str]] = field(default_factory=dict)
    min_ruff_version: str = "0.4.0"


@dataclass
class DependencyInjectionPoint:
    """Identifies locations requiring dependency injection to resolve circular imports."""
    caller_file: str
    caller_function: str
    callee_module: str
    callee_symbol: str
    injection_method: str  # "parameter", "property", "setter", "factory"
```

## Files

| Action | Path | Description |
|--------|------|-------------|
| **Modify** | `services/pyproject.toml` | Add `[tool.ruff]` and `[tool.ruff.lint]` sections with global ignore for PLC0415, per-file ignores for wildcard re-exports, and minimum version bump to `ruff>=0.4.0`. |
| **Create** | `services/aicarmine_broker/import_refs.py` | Centralized import registry providing lazy-loaded access to cross-module symbols. Replaces scattered local imports with a single controlled indirection layer. |
| **Modify** | `services/aicarmine_broker/application/planner/loop.py` | Replace 2 local imports (lines 763-764) with DI via `deps` dictionary or import from `import_refs`. Remove `# noqa: PLC0415` comments. |
| **Modify** | `services/aicarmine_broker/application/planner/loop_controller.py` | Replace 4 local imports (lines 14, 20, 30, 36) with DI or `import_refs`. Remove bare `noqa` and `# noqa: PLC0415` comments. |
| **Modify** | `services/aicarmine_broker/planner.py` | Replace 3 local imports (lines 10, 14, 18) with DI or `import_refs`. Remove `# noqa: PLC0415` comments. |
| **Modify** | `services/aicarmine_broker/helper.py` | Replace 2 local imports (lines 103, 399) with top-level conditional import or DI. Remove `# noqa: PLC0415` comments. |
| **Modify** | `services/aicarmine_broker/planner_core/cache.py` | Replace 1 local import (line 10) with DI or `import_refs`. Remove `# noqa: PLC0415` comment. |
| **Modify** | `services/aicarmine_broker/job_store.py` | Replace 1 local import with DI or `import_refs`. Remove `# noqa: PLC0415` comment. |
| **Modify** | `services/codex_bridge/mcp_server.py` | Replace 2 local imports (lines 10, 14) with DI or `import_refs`. Remove `# noqa: PLC0415` comments. |
| **Modify** | `services/codex_bridge/job_view_mcp_server.py` | Replace 1 local import with DI or `import_refs`. Remove `# noqa: PLC0415` comment. |
| **Modify** | `services/vulkan_bridge/app.py` | Replace 1 local import with DI or `import_refs`. Remove `# noqa: PLC0415` comment. |
| **Modify** | `services/vulkan_bridge/app_refactored.py` | Replace 1 local import with DI or `import_refs`. Remove `# noqa: PLC0415` comment. |
| **Modify** | `services/aicarmine_broker/config/compatibility.py` | Remove all `# noqa: F401` comments (6 instances). Symbols are intentionally re-exported; add `__all__` declaration instead. |
| **Modify** | `services/aicarmine_broker/config/__init__.py` | Remove `# noqa: F401,F403` from wildcard import. Add explicit `__all__` list to satisfy both rules. |

## Functions

| Change Type | Name | File | Signature / Details |
|-------------|------|------|---------------------|
| **New** | `_build_import_registry()` | `services/aicarmine_broker/import_refs.py` | Returns `dict[str, Any]` mapping symbol names to lazy-loaders. Provides centralized indirection replacing scattered local imports. |
| **New** | `_resolve_lazy(module_path: str, symbol_names: list[str])` | `services/aicarmine_broker/import_refs.py` | Cached loader using `importlib.import_module`. Memoizes results to preserve startup performance. |
| **Modified** | `vulkan_helper(args, root)` | `services/aicarmine_broker/helper.py` | Lines 399-400: Replace `from .repo_tools import LAB_REPO` and `from .job_store import write_json, now` with calls to `_build_import_registry()`. |
| **Modified** | `review_docs(task, root)` | `services/aicarmine_broker/helper.py` | Line 103: Replace local `LAB_REPO` import with registry lookup. |
| **Modified** | `run_agentic_planner_job(...)` | `services/aicarmine_broker/application/planner/loop.py` | Lines 763-764: Replace `dispatch_tool`, `normalize_tool_name`, `sanitize_tool_args` local imports with DI via `deps` or registry. |
| **Modified** | Various loop methods | `services/aicarmine_broker/application/planner/loop_controller.py` | Lines 14, 20, 30, 36: Replace 4 local imports with DI or registry lookups. Methods affected: `execute_step()`, `handle_decision()`, `continue_loop()`, `finalize_turn()`. |
| **Modified** | `_normalize_tool_name(value)` | `services/aicarmine_broker/planner.py` | Line 10: Replace local `normalize_tool_name` import with registry. |
| **Modified** | `guard_readonly_modes(tool, mode, ...)` | `services/aicarmine_broker/planner.py` | Lines 14, 18: Replace `TOOL_ALIASES` and `dangerous_command` local imports with registry/DI. |
| **Modified** | Cache methods | `services/aicarmine_broker/planner_core/cache.py` | Line 10: Replace `normalize_tool_name`, `sanitize_tool_args` local imports with registry. |
| **Modified** | `compatibility.py exports` | `services/aicarmine_broker/config/compatibility.py` | Remove all `# noqa: F401` comments. Add `__all__ = [...]` listing exported symbols explicitly. |

## Classes

| Change Type | Name | File | Modifications |
|-------------|------|------|---------------|
| **New** | `ImportRegistry` | `services/aicarmine_broker/import_refs.py` | Singleton-like cached registry. Thread-safe via `threading.Lock`. Provides `_resolve_lazy()` method. Zero overhead when not accessed. |
| **Modified** | `BrokerConfig` | `services/aicarmine_broker/config/models.py` | Add `IMPORT_REGISTRY_ENABLED: bool = True` field to control lazy-loading behavior globally. |

## Dependencies

| Change | Detail |
|--------|--------|
| **Bump** | `ruff>=0.4.0` in `pyproject.toml` dependencies (currently `ruff>=0.1.0`). Ensures support for `[tool.ruff.lint.per-file-ignores]` syntax. |
| **None** | No new external packages required. All changes use stdlib (`importlib`, `threading`, `typing`) and existing project structure. |
| **Internal** | New module `services/aicarmine_broker/import_refs.py` (~80 lines) provides centralized lazy import indirection. |

## Testing

Validation strategy relies on existing test infrastructure and deterministic verification:

1. **Run existing pytest suite**: Execute `pytest services/ -v --tb=short` to verify no regression in functional behavior after import restructuring.
2. **Verify Ruff compliance**: Run `ruff check services/ --output-format=json` and confirm zero violations related to PLC0415 and F401.
3. **Verify import correctness**: Confirm all modified files can be imported successfully: `python -c "from services.aicarmine_broker import helper, planner, job_store"` etc.
4. **Performance smoke test**: Verify lazy-loading overhead is negligible by timing first-call vs subsequent-calls in `import_refs.py` registry. Expect <5ms difference due to caching.
5. **Wildcard export validation**: Confirm `from services.aicarmine_broker.config.compatibility import *` still exports all expected symbols by checking `__all__` contents.

## Implementation Order

1. **Step 1**: Add `[tool.ruff]` configuration to `pyproject.toml` — bump ruff version, set global `ignore = ["PLC0415"]`, add per-file ignores for `config/__init__.py` and `config/compatibility.py`. This is non-destructive and establishes the baseline lint policy.

2. **Step 2**: Create `services/aicarmine_broker/import_refs.py` — implement `ImportRegistry` class with cached lazy loading via `importlib.import_module`. Provide `_resolve_lazy(module_path, symbol_names)` method. (~80 lines, new file)

3. **Step 3**: Update `services/aicarmine_broker/config/compatibility.py` — remove all `# noqa: F401` comments (6 instances), add `__all__` declaration listing exported symbols explicitly.

4. **Step 4**: Update `services/aicarmine_broker/config/__init__.py` — remove `# noqa: F401,F403` from wildcard import, replace with explicit `__all__` list.

5. **Step 5**: Update `services/aicarmine_broker/application/planner/loop.py` — replace 2 local imports with registry/DI, remove `# noqa: PLC0415` comments.

6. **Step 6**: Update `services/aicarmine_broker/application/planner/loop_controller.py` — replace 4 local imports with registry/DI, remove bare `noqa` and `# noqa: PLC0415` comments.

7. **Step 7**: Update `services/aicarmine_broker/planner.py` — replace 3 local imports with registry/DI, remove `# noqa: PLC0415` comments.

8. **Step 8**: Update `services/aicarmine_broker/helper.py` — replace 2 local imports with registry/DI, remove `# noqa: PLC0415` comments.

9. **Step 9**: Update remaining files (`cache.py`, `job_store.py`, `mcp_server.py`, `job_view_mcp_server.py`, `app.py`, `app_refactored.py`) — replace local imports with registry/DI, remove `# noqa: PLC0415` comments.

10. **Step 10**: Run full verification — `ruff check services/`, `pytest services/ -v --tb=short`, manual import smoke tests. Report diff stats and line counts.