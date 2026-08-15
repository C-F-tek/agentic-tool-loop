# IA Broker Behavioral Flows & Dependencies

**Created:** 2026-08-15  
**Purpose:** Document the behavioral flows, dependencies, and state transitions in the IA (Intelligent Agent) broker system. This is the operational reference for understanding how public tool calls route through the broker to either background job lifecycle or direct selector execution.

---

## Overview: The IA Broker Architecture

The IA broker sits between the public API surface and the internal execution engine. It provides two distinct execution paths:

| Path | Purpose | Lifecycle | Entry Point |
|------|---------|-----------|-------------|
| **Job Lifecycle** | Background agentic loop jobs with status tracking | Per-job, persistent | `action_router.py::handle()` → `start_agent_job()` |
| **Selector Runner** | Direct synchronous tool execution without background job | Per-request, ephemeral | `action_router.py::handle()` → `selector_runner.run()` |

### Key Distinction
| Concept | Role | When Used |
|---------|------|-----------|
| **Job Lifecycle** | Creates agent job, runs planner loop in background, returns job_id for polling | When `job_action` = start/async/background/run/execute or empty |
| **Selector Runner** | Selects internal tool from Vulkan response, dispatches it synchronously, returns result immediately | When no explicit job_action provided (default fallback) |

---

## Entry Point Flow: agent() Function

```python
# agent_entry.py line 130
def agent(payload: dict[str, Any]) -> dict[str, Any]:
    return build_job_action_router().handle(payload)
```

The entry point builds an `AgentJobActionRouter` with all dependencies injected, then delegates to its `handle()` method.

**Where:** `services/aicarmine_broker/agent_entry.py` → `agent()` function

### Dependency Injection Chain

```python
# agent_entry.py lines 46-63
build_job_worker() → AgentJobWorker(
    load_state=load_agent_job_state,
    write_state=write_agent_job_state,
    append_event=append_agent_event,
    agent_job_root=agent_job_root,
    write_json=write_json,
    planner_runner=run_agentic_planner_job,
    agent_runner=agent,
    summary_from_result=summary_from_result,
    agentic_planner_enabled=AGENTIC_PLANNER_ENABLED,
    agentic_fallback_oneshot=AGENTIC_FALLBACK_ONESHOT,
    terminal_finalizer=finalize_agentic_job,
)

# agent_entry.py lines 112-127
build_job_action_router() → AgentJobActionRouter(
    public_tool=public_tool,
    public_args=public_args,
    make_session_id=make_session_id,
    session_root=session_root,
    text_from_payload=text_from_payload,
    parse_bool=parse_bool,
    start_agent_job=start_agent_job,
    compact_agent_status=compact_agent_status,
    compact_agent_terminal_response=compact_agent_terminal_response,
    load_state=load_agent_job_state,
    write_state=write_agent_job_state,
    append_event=append_agent_event,
    selector_runner=build_selector_runner(),
)

# agent_entry.py lines 98-109
build_selector_runner() → SelectorRunner(
    select_internal_tool=select_internal_tool,
    selector_fallback_tool=selector_fallback_tool,
    fail_selector=fail_selector,
    sanitize_tool_args=sanitize_tool_args,
    needs_composite_review=needs_composite_review,
    dispatch_tool=dispatch_tool,
    public_wrapper=deterministic_public_wrapper,
    write_json=write_json,
    now=now,
)
```

**Where:** `services/aicarmine_broker/agent_entry.py` → build functions

---

## Action Router: Payload Routing Logic

### Step 1: Extract Public Tool Metadata
```python
# action_router.py lines 53-62
public_tool_name = self.public_tool(payload)
original_args = self.public_args(payload)
session_id = self.make_session_id(...)
root = self.session_root(session_id)
task = self.text_from_payload(payload, original_args, public_tool_name)
allow_command = self.parse_bool(payload.get("allow_command", True), True)
user_consent = str(payload.get("user_consent") or "")
timeout_seconds = self._timeout_seconds(payload, original_args)
job_action, job_id = self._job_action(payload, original_args, public_tool_name)
```

**Where:** `services/aicarmine_broker/application/job/action_router.py` → `handle()` method lines 53-71

### Step 2: Route Based on Job Action
```python
# action_router.py lines 72-98
if job_action == "start":
    return start_agent_job(...)       # Background job lifecycle
if job_action == "status":
    return compact_agent_status(job_id, ...)   # Poll job status
if job_action == "result":
    return compact_agent_terminal_response(job_id, audience=...)  # Get terminal result
if job_action == "cancel":
    state["status"] = "cancel_requested"      # Cancel running job
return selector_runner.run(...)               # Direct synchronous execution (default)
```

**Where:** `services/aicarmine_broker/application/job/action_router.py` → `handle()` method lines 72-98

### Job Action Classification
```python
# action_router.py lines 153-169
start_actions = {"", "start", "job_start", "async", "background", "run", "execute"}
status_actions = {"status", "job_status"}
result_actions = {"result", "job_result", "final"}
cancel_actions = {"cancel", "job_cancel"}
```

Special case: If `public_tool_name == "vulkan_helper"` and no job_id, defaults to start.

**Where:** `services/aicarmine_broker/application/job/action_router.py` → `_job_action()` static method

---

## Timeout Handling

### Step 1: Extract timeout from payload or original_args
```python
# action_router.py lines 109-137
raw_timeout = None
raw_source = "default"
for source, container in (("payload", payload), ("arguments", original_args)):
    value = container.get("timeout_seconds") if isinstance(container, dict) else None
    if value not in (None, ""):
        raw_timeout = value
        raw_source = source
        break
if raw_timeout in (None, ""):
    return 120  # Default timeout
try:
    timeout_seconds = float(str(raw_timeout).strip())
    if not math.isfinite(timeout_seconds):
        raise ValueError("timeout_seconds is not finite")
except (TypeError, ValueError):
    timeout_seconds = 120.0
return int(max(15.0, min(timeout_seconds, 240.0)))  # Clamp to [15, 240] range
```

**Where:** `services/aicarmine_broker/application/job/action_router.py` → `_timeout_seconds()` static method lines 109-137

---

## Selector Runner: Direct Execution Path

### Step 1: Select Internal Tool from Vulkan Response
```python
# selector_runner.py lines 49-55
internal_tool, raw_internal_args, selector_response = self.select_internal_tool(
    public_tool_name=public_tool_name,
    task=task,
    original_args=original_args,
    timeout_seconds=timeout_seconds,
)
```

This calls `tool_selection.py::select_internal_tool()` which:
1. Sends task to Ollama/Vulkan on port 11435
2. Parses native tool_call response
3. Returns (internal_tool_name, args, selector_response_dict) or (None, {}, {}) if no usable call

**Where:** `services/aicarmine_broker/tool_selection.py` → `select_internal_tool()` function

### Step 2: Fallback Handling
```python
# selector_runner.py lines 56-86
if not internal_tool:
    fallback_tool, fallback_args = self.selector_fallback_tool(...)
    if fallback_tool:
        internal_tool = fallback_tool
        raw_internal_args = fallback_args
        selector_response["aicarmine_selector_fallback"] = {
            "forced_internal_tool": fallback_tool,
            "reason": "11435/Vulkan was called but did not emit a usable native tool_call.",
        }
    else:
        envelope = self.fail_selector(...)
        self.write_json(root / "broker-session.json", envelope)
        return envelope  # Early return on failure
```

**Where:** `services/aicarmine_broker/application/job/selector_runner.py` → `run()` method lines 56-86

### Step 3: Argument Sanitization
```python
# selector_runner.py lines 87-92
internal_args = self.sanitize_tool_args(
    internal_tool,
    raw_internal_args,
    original_args,
    public_tool_name,
)
```

This calls `tool_contract.py::sanitize_tool_args()` which validates and normalizes arguments against the tool's schema.

**Where:** `services/aicarmine_broker/tool_contract.py` → `sanitize_tool_args()` function

### Step 4: Composite Review Guard
```python
# selector_runner.py lines 93-119
if self.needs_composite_review(public_tool_name, task, original_args, internal_tool, internal_args):
    selector_response["aicarmine_selector_guard"] = {
        "reason": "generic_repo_analysis_requires_composite_evidence",
        "selected_tool_from_vulkan": internal_tool,
        "selected_args_from_vulkan": internal_args,
        "forced_internal_tool": "vulkan_helper",
    }
    internal_tool = "vulkan_helper"
    internal_args = {...}  # Override with composite review args
```

This calls `tool_selection.py::needs_composite_review()` which checks if the public tool name requires gathering multiple repo evidence sources before proceeding. If so, forces the tool to `vulkan_helper` for comprehensive analysis.

**Where:** `services/aicarmine_broker/tool_selection.py` → `needs_composite_review()` function

### Step 5: Tool Dispatch
```python
# selector_runner.py lines 120-133
dispatcher_result = self.dispatch_tool(
    internal_tool,
    internal_args,
    root,
    allow_command,
    user_consent,
)
dispatcher_result.setdefault("called_by_vulkan", internal_tool)
dispatcher_artifact = root / "tool-results" / f"{self.now()}-{internal_tool}-dispatcher-v6.json"
self.write_json(dispatcher_artifact, dispatcher_result)
dispatcher_result.setdefault("artifact", str(dispatcher_artifact))
```

This calls `tool_dispatch.py::dispatch_tool()` which:
1. Validates tool against registry
2. Checks command safety policy
3. Executes the tool with sanitized args
4. Returns result dict with ok/status/execution_time fields

**Where:** `services/aicarmine_broker/tool_dispatch.py` → `dispatch_tool()` function

### Step 6: Public Wrapper & Session Envelope
```python
# selector_runner.py lines 134-143
envelope = self.public_wrapper(
    public_tool_name=public_tool_name,
    original_args=original_args,
    internal_tool=internal_tool,
    internal_args=internal_args,
    dispatcher_result=dispatcher_result,
    selector_response=selector_response if isinstance(selector_response, dict) else {},
    root=root,
)
self.write_json(root / "broker-session.json", envelope)
return envelope
```

This calls `public_wrapper.py::deterministic_public_wrapper()` which:
1. Constructs OpenWebUI-visible response envelope
2. Includes selector metadata, dispatch results, tool info
3. Writes broker-session.json for audit trail
4. Returns public-facing result dict

**Where:** `services/aicarmine_broker/public_wrapper.py` → `deterministic_public_wrapper()` function

---

## State Transitions: Selector Runner Flow

### Normal Execution Path
```
Public tool call → select_internal_tool() → internal_tool found
→ sanitize_tool_args() → needs_composite_review() = False
→ dispatch_tool() → success (ok=True)
→ deterministic_public_wrapper() → return envelope
```

### Fallback Path (No Native Tool Call)
```
Public tool call → select_internal_tool() → internal_tool=None
→ selector_fallback_tool() → fallback found
→ internal_tool=fallback, aicarmine_selector_fallback marker set
→ sanitize_tool_args() → dispatch_tool() → public_wrapper() → return envelope
```

### Failure Path (No Usable Response)
```
Public tool call → select_internal_tool() → internal_tool=None
→ selector_fallback_tool() → fallback=None
→ fail_selector() → write broker-session.json → early return envelope
```

### Composite Review Path
```
Public tool call → select_internal_tool() → internal_tool=repo_search (example)
→ needs_composite_review() = True (generic repo analysis detected)
→ internal_tool forced to vulkan_helper, args overridden
→ dispatch_tool(vulkan_helper) → public_wrapper() → return envelope
```

---

## Job Lifecycle: Background Execution Path

### Start Agent Job
```python
# agent_entry.py lines 89-95
def start_agent_job(payload, public_tool_name, original_args, task):
    return build_job_lifecycle().start(payload, public_tool_name, original_args, task)
```

This creates an `AgentJobLifecycle` instance and calls its `start()` method which:
1. Initializes job database if needed
2. Generates session_id and job_id
3. Writes initial job state (status=pending)
4. Starts background thread with AgentJobWorker
5. Returns job_id + status immediately

**Where:** `services/aicarmine_broker/agent_entry.py` → `start_agent_job()` function
**Where:** `services/aicarmine_broker/application/job/lifecycle.py` → `AgentJobLifecycle.start()` method

### Job Worker Execution
```python
# agent_entry.py lines 46-63
build_job_worker() → AgentJobWorker(
    load_state=load_agent_job_state,
    write_state=write_agent_job_state,
    append_event=append_agent_event,
    planner_runner=run_agentic_planner_job,
    agent_runner=agent,
    ...
)
```

The worker runs in background thread and:
1. Loads job state
2. If AGENTIC_PLANNER_ENABLED → runs agentic planner loop (planner.py::run_agentic_planner_job)
3. Otherwise → runs direct agent execution (agent_entry.py::agent)
4. Writes terminal response via finalize_agentic_job
5. Updates job status to completed/failed/cancelled

**Where:** `services/aicarmine_broker/application/job/worker.py` → `AgentJobWorker.run()` method

### Status Query
```python
# action_router.py lines 79-80
if job_action == "status":
    return self.compact_agent_status(job_id, include_events=True)
```

Returns compact job state with status, step count, events summary.

**Where:** `services/aicarmine_broker/job_store.py` → `compact_agent_status()` function

### Result Query
```python
# action_router.py lines 81-83
if job_action == "result":
    audience = self._result_audience(payload, original_args)
    return self.compact_agent_terminal_response(job_id, audience=audience)
```

Returns terminal response formatted for operator/OpenWebUI/internal audiences.

**Where:** `services/aicarmine_broker/job_store.py` → `compact_agent_terminal_response()` function

### Cancel Request
```python
# action_router.py lines 84-97
if job_action == "cancel":
    state = self.load_state(job_id)
    if not state:
        return self.compact_agent_status(job_id, include_events=True)
    state["status"] = "cancel_requested"
    self.write_state(state)
    self.append_event(job_id, "cancel_requested", "Cancel requested by user.", {}, step=None)
    return self.compact_agent_status(job_id, include_events=True)
```

Sets status to cancel_requested and appends event. Actual cancellation handled by worker loop check.

**Where:** `services/aicarmine_broker/application/job/action_router.py` → `handle()` method lines 84-97

---

## Job Action State Machine

```
[start] ← "", "start", "job_start", "async", "background", "run", "execute"
   │
   ▼
[pending] → [running] → [completed] / [failed] / [cancelled]
   │              │
   │              ├→ status query → compact_agent_status()
   │              ├→ result query → compact_agent_terminal_response()
   │              └→ cancel request → state["status"] = "cancel_requested"
   │
[status] ← "status", "job_status"
   │
   ▼
[current state]

[result] ← "result", "job_result", "final"
   │
   ▼
[terminal response]

[cancel] ← "cancel", "job_cancel"
   │
   ▼
[cancel_requested]
```

**Where:** `services/aicarmine_broker/application/job/action_router.py` → `_job_action()` method

---

## Artifact Writing: Audit Trail

### Dispatcher Artifact
```python
# selector_runner.py lines 129-133
dispatcher_artifact = root / "tool-results" / f"{self.now()}-{internal_tool}-dispatcher-v6.json"
self.write_json(dispatcher_artifact, dispatcher_result)
```

Writes tool execution result with timestamp-based filename for deduplication.

**Location:** `services/aicarmine_broker/application/job/selector_runner.py` → `run()` method

### Broker Session Envelope
```python
# selector_runner.py line 85, 143
self.write_json(root / "broker-session.json", envelope)
```

Writes complete session envelope including selector metadata and dispatch results.

**Location:** `services/aicarmine_broker/application/job/selector_runner.py` → `run()` method

### Job Events
```python
# action_router.py lines 90-96
self.append_event(
    job_id,
    "cancel_requested",
    "Cancel requested by user.",
    {},
    step=None,
)
```

Appends structured events to job event log for audit trail.

**Location:** `services/aicarmine_broker/job_store.py` → `append_agent_event()` function

---

## File Reference Map: IA Broker Flows

| Concept | Primary Implementation | Secondary References |
|---------|----------------------|---------------------|
| Entry point | `agent_entry.py::agent()` | `tool_dispatch.py`, `planner.py` |
| Action routing | `action_router.py::handle()` | `_job_action()`, `_timeout_seconds()` |
| Selector path | `selector_runner.py::run()` | `select_internal_tool()`, `dispatch_tool()` |
| Job lifecycle | `lifecycle.py::AgentJobLifecycle.start()` | `worker.py::AgentJobWorker.run()` |
| Tool selection | `tool_selection.py::select_internal_tool()` | `needs_composite_review()`, `selector_fallback_tool()` |
| Tool dispatch | `tool_dispatch.py::dispatch_tool()` | `command_safety.py`, `tool_registry.py` |
| Public wrapper | `public_wrapper.py::deterministic_public_wrapper()` | `field_names.py`, `evidence_materializer.py` |
| Artifact writing | `job_store.py::write_json()` | `compact_agent_status()`, `append_agent_event()` |

---

## Quick Reference: IA Broker Flow Diagram

```
Public tool call (payload)
│
├── agent_entry.py::agent(payload)
│   └── build_job_action_router().handle(payload)
│       │
│       ├── [1] Extract metadata: public_tool_name, original_args, session_id, task
│       ├── [2] Parse job_action + job_id from payload/args
│       ├── [3] Parse timeout_seconds (default 120, clamped to [15, 240])
│       │
│       ├── IF job_action in {start, async, background, run, execute}:
│       │   → start_agent_job() → AgentJobLifecycle.start() → background thread
│       │
│       ├── IF job_action == "status":
│       │   → compact_agent_status(job_id) → current state + events summary
│       │
│       ├── IF job_action == "result":
│       │   → compact_agent_terminal_response(job_id, audience) → terminal response
│       │
│       ├── IF job_action == "cancel":
│       │   → load_state(), state["status"]="cancel_requested", append_event()
│       │
│       └── DEFAULT (no explicit job_action):
│           → selector_runner.run(public_tool_name, task, original_args, ...)
│               │
│               ├── [1] select_internal_tool() → internal_tool, raw_args, selector_response
│               │   → Ollama/Vulkan 11435 call, parse native tool_call
│               │
│               ├── [2] If no internal_tool:
│               │   → selector_fallback_tool() → fallback or fail_selector()
│               │   → fail path: write broker-session.json, early return
│               │
│               ├── [3] sanitize_tool_args(internal_tool, raw_args, ...)
│               │   → validate against tool schema
│               │
│               ├── [4] If needs_composite_review():
│               │   → force internal_tool="vulkan_helper", override args
│               │
│               ├── [5] dispatch_tool(internal_tool, internal_args, root, allow_command, user_consent)
│               │   → execute tool, write dispatcher artifact to tool-results/
│               │
│               └── [6] deterministic_public_wrapper(...)
│                   → construct envelope, write broker-session.json, return
│
└── Return public-facing result dict
```

---

## Related Documentation Files

| File | Purpose |
|------|---------|
| `TURNS_MAPPING.md` | Planner turn logic flow and decision processing |
| `TURNS_SUBTURNS_DEPENDENCIES.md` | Turn-subturn dependency graph and state transitions |
| `IA_BROKER_FLOWS.md` (this file) | IA broker behavioral flows, routing logic, selector vs job paths |
| `SUBTURNS_EXPLORATION.md` | Subturn tool implementations and validator retry mechanism |