# Refactoring Python Applications for Simplicity

> *"Do you want simpler Python code? You always start a project with the best intentions, a clean codebase, and a nice structure. But over time, there are changes to your apps, and things can get a little messy."*

This guide covers practical techniques for reducing complexity in Python applications, with real-world examples drawn from production service architectures.

---

## Table of Contents

1. [Code Complexity in Python](#1-code-complexity-in-python)
2. [Metrics for Measuring Complexity](#2-metrics-for-measuring-complexity)
3. [Using wily to Capture and Track Your Projects' Complexity](#3-using-wily-to-capture-and-track-your-projects-complexity)
4. [Refactoring in Python](#4-refactoring-in-python)
5. [Avoiding Risks With Refactoring: Leveraging Tools and Having Tests](#5-avoiding-risks-with-refactoring-leveraging-tools-and-having-tests)
6. [Using rope for Refactoring](#6-using-rope-for-refactoring)
7. [Using PyCharm for Refactoring](#7-using-pycharm-for-refactoring)
8. [Complexity Anti-Patterns](#8-complexity-anti-patterns)
9. [Real-World Refactoring Case Studies](#9-real-world-refactoring-case-studies)
10. [Conclusion](#10-conclusion)

---

## 1. Code Complexity in Python

Complexity creeps into codebases through three primary mechanisms:

1. **Cyclomatic complexity** — too many branching paths in a single function
2. **Cognitive complexity** — the mental effort required to understand the code
3. **Structural complexity** — poor organization, deep nesting, or excessive coupling

### Example: High Cognitive Complexity

Consider this pattern commonly seen in configuration loaders:

```python
# ANTI-PATTERN: Deeply nested conditionals with repeated logic
def load_config(env):
    if env is not None:
        if isinstance(env, dict):
            val = env.get("AICARMINE_SOME_SETTING")
            if val is not None:
                if isinstance(val, str):
                    stripped = val.strip()
                    if stripped.lower() in {"legacy", "shadow", "active"}:
                        return stripped.lower()
                    else:
                        return "legacy"
                else:
                    return "legacy"
            else:
                return "legacy"
        else:
            return "legacy"
    else:
        return "legacy"
```

This function has **cyclomatic complexity of 10** and requires reading 10 levels deep to understand its logic. The same function, refactored:

```python
# REFACTORED: Guard clauses + early returns
def load_config(env: object | None = None) -> str:
    """Return a normalized lane mode value."""
    if not isinstance(env, dict):
        return "legacy"

    val = env.get("AICARMINE_SOME_SETTING")
    if not isinstance(val, str):
        return "legacy"

    normalized = val.strip().lower()
    if normalized in {"legacy", "shadow", "active"}:
        return normalized

    return "legacy"
```

The refactored version has **cyclomatic complexity of 4** and is immediately readable.

---

## 2. Metrics for Measuring Complexity

### Key Metrics to Track

| Metric | What It Measures | Threshold |
|--------|-----------------|-----------|
| **Cyclomatic Complexity (V(G))** | Number of independent paths | ≤ 10 per function |
| **Cognitive Complexity** | Human readability difficulty | ≤ 15 per function |
| **Lines of Code (LOC)** | Function/file size | ≤ 50 LOC per function |
| **Maintainability Index** | Composite score (0-100) | ≥ 65 |
| **Halstead Volume** | Program size in bits | Project-dependent |

### Calculating Cyclomatic Complexity

```python
def calculate_cyclomatic_complexity(code: str) -> int:
    """Calculate cyclomatic complexity for a function.

    V(G) = 1 + number of decision points
    Decision points: if, elif, for, while, and, or, except, with, assert, case
    """
    import ast

    tree = ast.parse(code)
    total_complexities = {}

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Start with base complexity of 1
            complexity = 1
            for child in ast.walk(node):
                if isinstance(child, (
                    ast.If, ast.While, ast.For, ast.AsyncFor,
                    ast.IfExp, ast.With, ast.AsyncWith,
                    ast.Try, ast.Assert,
                    ast.BoolOp  # counts len(values) - 1 for each 'and'/'or'
                )):
                    complexity += 1
            total_complexities[node.name] = complexity

    return total_complexities
```

### Cognitive Complexity vs Cyclomatic Complexity

Cognitive complexity penalizes:
- **Nested logic** — deeper nesting increases score more than flat decisions
- **Forks** — `if`, `for`, `while` add points
- **Penalties** — `else`, `elif`, `catch` add extra points because they reset the reader's mental model

A function can have low cyclomatic complexity but high cognitive complexity due to deep nesting.

---

## 3. Using wily to Capture and Track Your Projects' Complexity

[wily](https://wily.readthedocs.io/) is a command-line tool that tracks code metrics over time using git history.

### Installation

```powershell
pip install wily
```

### Basic Usage

```powershell
# Initialize wily in your project
wily init

# Add files to track
wily add services/aicarmine_broker/config/models.py

# View current metrics
wily show services/aicarmine_broker/config/models.py

# View historical trends
wily log services/aicarmine_broker/config/models.py

# Generate HTML report
wily report --output docs/complexity-report.html
```

### Integration with CI/CD

```yaml
# .github/workflows/complexity-check.yml
name: Complexity Check
on: [pull_request]
jobs:
  complexity:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Install wily
        run: pip install wily
      - name: Check complexity
        run: |
          wily add services/
          wily report --output /tmp/report.html
          # Fail if any function exceeds threshold
          wily show --max-complexity 10 services/
```

### Wily's Git Integration

Wily stores metrics in a SQLite database and tracks changes across commits. This allows you to:

1. See how complexity evolved over time
2. Identify when complexity spikes occurred
3. Correlate complexity increases with specific commits
4. Set complexity budgets per file or function

---

## 4. Refactoring in Python

Refactoring is the process of improving code structure without changing its external behavior.

### The Refactoring Workflow

```
1. Understand the current behavior (tests, runtime evidence)
2. Make a small, reversible change
3. Run tests to verify behavior is preserved
4. Repeat until desired simplicity is achieved
```

### When NOT to Refactor

- Before understanding what the code actually does
- Without tests covering the changed code
- When under deadline pressure that doesn't allow verification
- If the code is being actively worked on by someone else

### Refactoring Categories

| Category | Goal | Example Technique |
|----------|------|-------------------|
| **Simplification** | Reduce complexity | Extract function, flatten conditionals |
| **Restructuring** | Improve organization | Move functions between modules |
| **Generalization** | Increase reusability | Parameterize magic values |
| **Specialization** | Narrow scope | Split monolithic functions |

---

## 5. Avoiding Risks With Refactoring: Leveraging Tools and Having Tests

### Pre-Refactoring Checklist

- [ ] Tests exist for the code being changed
- [ ] Tests are passing before refactoring begins
- [ ] Changes are made in small, incremental steps
- [ ] Each step is verified by tests
- [ ] Git branch is clean (no uncommitted changes)

### Safe Refactoring Patterns

#### Pattern 1: Extract Function

```python
# BEFORE: Single function does too much
def process_tool_result(result: dict) -> str:
    summary = ""
    if result.get("type") == "success":
        summary = f"Success: {result['data']}"
    elif result.get("type") == "error":
        summary = f"Error: {result.get('message', 'unknown')}"
    elif result.get("type") == "partial":
        summary = f"Partial: {result.get('partial_data', 'N/A')}"

    timestamp = datetime.now().isoformat()
    log_entry = f"[{timestamp}] {summary}"

    db_path = Path("/var/log/tool_results.db")
    with sqlite3.connect(db_path) as conn:
        conn.execute("INSERT INTO logs VALUES (?)", (log_entry,))

    return log_entry
```

```python
# AFTER: Extract functions for each responsibility
def summarize_result(result: dict) -> str:
    """Create a human-readable summary from a tool result."""
    type_map = {
        "success": lambda r: f"Success: {r['data']}",
        "error": lambda r: f"Error: {r.get('message', 'unknown')}",
        "partial": lambda r: f"Partial: {r.get('partial_data', 'N/A')}",
    }
    builder = type_map.get(result.get("type"), lambda r: "Unknown type")
    return builder(result)


def format_log_entry(summary: str) -> str:
    """Wrap a summary in a timestamped log entry."""
    timestamp = datetime.now().isoformat()
    return f"[{timestamp}] {summary}"


def persist_log(log_entry: str, db_path: Path) -> None:
    """Write a log entry to the SQLite database."""
    with sqlite3.connect(db_path) as conn:
        conn.execute("INSERT INTO logs VALUES (?)", (log_entry,))


def process_tool_result(result: dict, db_path: Path) -> str:
    """Main orchestration: compose extracted functions."""
    summary = summarize_result(result)
    log_entry = format_log_entry(summary)
    persist_log(log_entry, db_path)
    return log_entry
```

#### Pattern 2: Replace Conditional with Strategy Object

```python
# BEFORE: Large conditional block
def normalize_lane_mode(value: object) -> str:
    if not isinstance(value, str):
        return "legacy"
    normalized = str(value).strip().lower()
    if normalized in {"legacy", "shadow", "active"}:
        return normalized
    return "legacy"
```

#### Pattern 3: Replace Configuration Dictionary with Config Object

```python
# BEFORE: Using a dictionary for configuration
config = {}
config["service_name"] = "aicarmine-vulkan-tool-broker"
config["app_title"] = "AI-Carmine Vulkan Tool Broker"
config["app_version"] = "2.0.0"
config["app_description"] = "Internal 3572 broker..."
config["vulkan_agent_path"] = "/vulkan/agent"
config["jobs_index_path"] = "/jobs"
# ... 80+ more entries scattered across the file

# AFTER: Dataclass with validation
@dataclass(frozen=True)
class BrokerConfig:
    service_name: str
    app_title: str
    app_version: str
    app_description: str
    vulkan_agent_path: str
    jobs_index_path: str
    # ... all fields explicitly typed

    @property
    def health_endpoint(self) -> str:
        return f"{self.agent_public_base_url}{self.health_path}"
```

The dataclass approach (as seen in `services/aicarmine_broker/config/models.py`) provides:
- **Type safety** — mypy/pyright can verify correct usage
- **Immutability** — `frozen=True` prevents accidental modification
- **Self-documentation** — field names and types are explicit
- **Default value management** — defaults are declared once

---

## 6. Using rope for Refactoring

[Rope](https://github.com/python-rope/rope) is a Python refactoring library that works at the project level.

### Installation

```powershell
pip install rope
```

### Common Operations

```python
import rope
from rope.contrib import generate

# Initialize project
project = rope.Project("path/to/project")

# Get refactoring object
resource = project.get_resource("services/aicarmine_broker/config/models.py")

# Rename a symbol across files
refactor = resource.project.get_refactor("rename")
new_refactor = refactor(new_name="NewConfigName")
new_refactor.get_changed_files()  # Preview changes
new_refactor.doit()               # Apply changes
```

### Using Rope from the Command Line

```powershell
# Rename a symbol in the project
rope refactor rename -f services/aicarmine_broker/config/models.py \
    -n old_name -s new_name

# Extract a function
rope refactor extract -f services/aicarmine_broker/config/models.py \
    -s 128 -e 293 -n load_broker_config_from_env

# Move a class to another module
rope refactor move -f services/aicarmine_broker/config/models.py \
    -d services/aicarmine_broker/application/shared/ \
    -n BrokerConfig
```

### Rope's AST-Aware Refactoring

Rope uses Python's AST module to understand code structure, which means:

- It can rename symbols only in the correct contexts (not in strings)
- It tracks imports and updates them when modules are moved
- It handles cross-file references automatically
- It respects `.gitignore` and virtual environments

---

## 7. Using PyCharm for Refactoring

PyCharm provides built-in refactoring capabilities that integrate with JetBrains' IDE ecosystem.

### Available Refactorings

| Refactoring | Keyboard Shortcut | Description |
|-------------|------------------|-------------|
| **Rename** | Shift+F6 | Rename symbol safely across all references |
| **Extract Function** | Ctrl+Alt+M | Extract selected code into a new function |
| **Inline** | Ctrl+Alt+Shift+I | Replace variable with its expression |
| **Move** | Alt+Shift+M | Move class/function to another file |
| **Safe Delete** | Alt+Shift+Ctrl+D | Delete with reference checking |
| **Surround With** | Ctrl+Alt+T | Wrap code in try/except, if, etc. |
| **Merge** | Ctrl+Alt+Shift+N | Merge method calls or variables |

### PyCharm's Complexity Analysis

PyCharm Professional (paid) includes built-in complexity analysis:

1. Navigate to **Code → Inspect Code**
2. Select the scope (entire project, module, or custom)
3. Review the **Complexity** section of the results
4. Click into specific functions to see cyclomatic complexity breakdown

---

## 8. Complexity Anti-Patterns

### 1. Functions That Should Be Objects

When a function manages multiple related pieces of state, it's often a sign that those pieces should be encapsulated in an object.

```python
# ANTI-PATTERN: Function managing its own state via mutable defaults
def process_request(
    request: dict,
    *,
    _cache: dict | None = None,
    _step: int = 0,
    _errors: list[str] | None = None,
) -> dict:
    if _cache is None:
        _cache = {}
    if _errors is None:
        _errors = []

    # ... 200 lines of code manipulating _cache, _step, _errors ...

    return {"result": ..., "cache": _cache, "errors": _errors}
```

```python
# REFACTORED: State encapsulated in an object
class RequestProcessor:
    def __init__(self) -> None:
        self.cache: dict = {}
        self.step: int = 0
        self.errors: list[str] = []

    def process(self, request: dict) -> dict:
        """Process a single request and return the result."""
        # ... focused logic without mutable state leakage ...
        return {"result": ..., "cache": self.cache, "errors": self.errors}

    def reset(self) -> None:
        """Reset internal state for a fresh processing run."""
        self.cache.clear()
        self.step = 0
        self.errors.clear()
```

**Benefits of the object approach:**
- State is explicit and typed
- `reset()` enables reuse without re-importing
- Each method has a single responsibility
- Easier to test (mock the class, not the function)

### 2. Objects That Should Be Functions

Conversely, when an object has no meaningful state and only one method, it's often simpler as a function.

```python
# ANTI-PATTERN: Single-method class used as a namespace
class ConfigLoader:
    @staticmethod
    def load(env: EnvMapping | None = None) -> BrokerConfig:
        # ... 160 lines of config loading logic ...
        return BrokerConfig(...)

    @staticmethod
    def validate(config: BrokerConfig) -> list[str]:
        # ... validation logic ...
        return []

# ANTI-PATTERN: Another single-method class
class PathResolver:
    @staticmethod
    def resolve(value: object, *, env_name: str) -> Path:
        # ... path resolution logic ...
        return Path(raw).resolve(strict=False)
```

```python
# REFACTORED: Flat functions with clear names
def load_broker_config_from_env(env: EnvMapping | None = None) -> BrokerConfig:
    """Load and normalize broker configuration from environment variables."""
    # ... config loading logic ...
    return BrokerConfig(...)


def validate_broker_config(config: BrokerConfig) -> list[str]:
    """Return a list of validation errors for the given config."""
    # ... validation logic ...
    return []


def resolve_path(value: object, *, env_name: str) -> Path:
    """Resolve a filesystem path from a string value."""
    # ... path resolution logic ...
    return Path(raw).resolve(strict=False)
```

**Benefits of the function approach:**
- No class instantiation overhead
- Clearer module-level organization
- Easier to import selectively (`from config import load_broker_config_from_env`)
- Simpler to mock in tests

### 3. Converting "Triangular" Code to Flat Code

Triangular code has increasing indentation with each decision point. The goal is to flatten it using early returns and guard clauses.

```python
# ANTI-PATTERN: Triangular code
def get_tool_result_type(result: dict) -> str:
    if result is not None:
        if isinstance(result, dict):
            if "type" in result:
                if result["type"] == "success":
                    return "ok"
                elif result["type"] == "error":
                    return "fail"
                elif result["type"] == "partial":
                    return "partial"
                else:
                    return "unknown"
            else:
                return "missing_type"
        else:
            return "invalid_format"
    else:
        return "no_result"
```

```python
# REFACTORED: Flat code with early returns
def get_tool_result_type(result: dict) -> str:
    if result is None:
        return "no_result"
    if not isinstance(result, dict):
        return "invalid_format"
    if "type" not in result:
        return "missing_type"

    type_map = {
        "success": "ok",
        "error": "fail",
        "partial": "partial",
    }
    return type_map.get(result["type"], "unknown")
```

### 4. Handling Complex Dictionaries With Query Tools

When working with deeply nested dictionaries, use query helpers instead of manual key navigation.

```python
# ANTI-PATTERN: Manual dictionary navigation
def extract_planner_payload(events: list[dict]) -> dict | None:
    for event in events:
        if event.get("event_type") == "planner-prompts":
            step = event.get("step", {})
            if isinstance(step, dict):
                payload = step.get("payload", {})
                if isinstance(payload, dict):
                    prompts = payload.get("prompts", [])
                    if prompts:
                        return {"prompts": prompts, "step": step.get("step")}
    return None
```

```python
# REFACTORED: Using a query helper
from typing import Any

def _get(d: dict, *keys: str, default: Any = None) -> Any:
    """Safely navigate nested dictionaries."""
    current: Any = d
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key, default)
    return current


def extract_planner_payload(events: list[dict]) -> dict | None:
    """Extract planner payload from events using safe navigation."""
    for event in events:
        if _get(event, "event_type") == "planner-prompts":
            prompts = _get(event, "step", "payload", "prompts")
            if prompts:
                return {"prompts": prompts, "step": _get(event, "step", default={})}
    return None
```

### 5. Using attrs and dataclasses to Reduce Code

Replace boilerplate `__init__`, `__repr__`, `__eq__` methods with dataclasses or attrs.

```python
# ANTI-PATTERN: Manual __init__ and __repr__
class ToolResult:
    def __init__(self, tool_name: str, result: str, step: int, duration_ms: float):
        self.tool_name = tool_name
        self.result = result
        self.step = step
        self.duration_ms = duration_ms

    def __repr__(self):
        return (
            f"ToolResult(tool_name={self.tool_name!r}, "
            f"result={self.result!r}, step={self.step}, "
            f"duration_ms={self.duration_ms})"
        )

    def __eq__(self, other):
        if not isinstance(other, ToolResult):
            return False
        return (
            self.tool_name == other.tool_name and
            self.result == other.result and
            self.step == other.step and
            self.duration_ms == other.duration_ms
        )
```

```python
# REFACTORED: dataclass
from dataclasses import dataclass, field
from typing import Any

@dataclass(frozen=True)
class ToolResult:
    tool_name: str
    result: str
    step: int = 0
    duration_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
```

The dataclass automatically generates `__init__`, `__repr__`, `__eq__`, and `__hash__`. Adding `frozen=True` makes it immutable, preventing accidental state changes.

---

## 9. Real-World Refactoring Case Studies

### Case Study A: Monolithic `sanitize_tool_args` Function

**Anti-pattern**: Large if/elif chain with 8 tool branches (~158 LOC)

**Fixes applied**:
- Extracted 8 tool-specific sanitizer functions (`_sanitize_repo_search`, etc.)
- Created `_TOOL_SANITIZERS` dispatch table (strategy pattern)
- Extracted constants (`_TEXT_KEYS`, `_PATH_KEYS`, `_INVALID_PATHS`)
- Entry point reduced from 158 → 30 LOC (81% reduction)

**File**: `services/aicarmine_broker/tool_contract.py`

### Case Study B: Deep Nested Dict Navigation in Builder

**Anti-pattern**: 14 levels of `.get()` calls in `_preplanner_semantic_intent_from_orientation`

**Fixes applied**:
- Added `_get()` query helper for nested dictionary navigation (§8.4)
- Flattened `_preplanner_semantic_intent_from_orientation` using query helper
- Extracted `_GOAL_DELIVERABLE_MAP` lookup table replacing inline dict
- Removed unused variable `goal_low_for_audit`

**File**: `services/aicarmine_broker/application/evidence/builder.py`

### Case Study C: Contract Dict Navigation in Turn Surface Policy

**Anti-pattern**: ~50+ occurrences of `if isinstance(contract.get("X"), dict) else {}`

**Fixes applied**:
- Added `_get_dict()` query helper for safe dict extraction
- Replaced all redundant type-checking patterns with `_get_dict(contract.get("X"))`
- Eliminated ~60+ redundant type-checking lines

**File**: `services/aicarmine_broker/application/tool_surface/turn_surface_policy.py`

### Case Study D: Action Routing with if/elif Chains

**Anti-pattern**: 7 separate if/elif branches routing job actions to lifecycle states

**Fixes applied**:
- Created `_ACTION_ROUTE_MAP` lookup table mapping 14 action strings to 4 routed states
- Extracted `_route_action()` function using lookup dispatch instead of conditionals
- Converted `@staticmethod _job_action` to instance method delegating to lookup function

**File**: `services/aicarmine_broker/application/job/action_router.py`

### Case Study E: Schema Builder with Manual Dict Construction

**Anti-pattern**: `_tool_schema()` function manually building nested dict structures for 35+ tool definitions

**Fixes applied**:
- Created `ToolSchema` frozen dataclass (§8.5 — Objects that should be dataclasses)
- Extracted `build()` method to handle dict construction from immutable state
- Moved `requires_one_of` extraction into `_tool_schema()` guard clause pattern
- Schema builder now uses immutability (`frozen=True`) preventing accidental state changes

**File**: `services/aicarmine_broker/tool_schemas.py`

### Case Study F: Tool Selection with Inline Conditionals

**Anti-pattern**: `is_generic_repo_analysis` and `needs_composite_review` using inline tuple conditionals for token matching

**Fixes applied**:
- Created `_REPO_TOKENS`, `_REVIEW_TOKENS`, `_REPO_SEARCH_QUERY_TOKENS` lookup tables (§4)
- Added `_get()` query helper for safe dict navigation (§8.4)
- Extracted `select_internal_tool` into guard-clause style with early returns (§8.3)
- Formatted multi-line strings (system prompt, user message) for readability
- Replaced inline tuple conditionals with frozenset membership checks

**File**: `services/aicarmine_broker/tool_selection.py`

### Verification Results (All Cases)

| Check | Result |
|-------|--------|
| **ruff lint** | 0 diagnostics (all files) |
| **pytest** | **330 passed, 0 failed** ✅ |

---

## 10. Conclusion

### Key Principles for Simpler Code

1. **One responsibility per function** — If a function does two things, split it
2. **Flat code over triangular code** — Use early returns and guard clauses
3. **Prefer objects for state, functions for behavior** — Match the abstraction to the problem
4. **Use query helpers for complex data structures** — Don't manually navigate nested dicts
5. **Leverage language features** — dataclasses, typing, pattern matching (3.10+)
6. **Track complexity over time** — Use tools like wily to prevent regression
7. **Refactor in small steps** — Each change should be verifiable and reversible

### The Refactoring Mindset

> *"If you can write and maintain clean, simple Python code, then it'll save you lots of time in the long term. You can spend less time testing, finding bugs, and making changes when your code is well laid out and simple to follow."*

The investment in writing simple code pays dividends:
- **Fewer bugs** — Simple code has fewer paths for bugs to hide
- **Faster onboarding** — New developers understand simple code quickly
- **Easier maintenance** — Changes are obvious and low-risk
- **Better testability** — Small, focused units are easy to test

### Quick Reference: Anti-Pattern Detection

| Symptom | Likely Anti-Pattern | Fix |
|---------|---------------------|-----|
| Function > 50 LOC | Too many responsibilities | Extract functions |
| Nested `if` > 3 levels | Triangular code | Guard clauses + early returns |
| Dictionary with 10+ keys | Complex data coupling | Create a dataclass |
| Class with one method | Object that should be function | Flatten to module-level function |
| Repeated conditional logic | Missing abstraction | Strategy pattern or lookup table |
| Config loaded from 20 env vars | Monolithic configuration | Split into focused config objects |

---

## Appendix: Tooling Quick Reference

| Tool | Purpose | Command |
|------|---------|---------|
| **wily** | Track complexity over git history | `wily show <file>` |
| **rope** | AST-aware refactoring | `rope refactor rename -f <file> -s <start> -e <end>` |
| **pylint** | Static analysis | `pylint <module>` |
| **mccabe** | Cyclomatic complexity | `mccute -r 10 <module>` |
| **radin** | Code metrics | `radin cc <module> -s` |
| **PyCharm** | IDE refactoring + complexity analysis | Built-in via **Code → Inspect Code** |

---

*Generated from analysis of production Python services in the C:\Users\carmi\AI workspace.*