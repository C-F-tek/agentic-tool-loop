# Pointer Usage Patterns in IA Broker

**Created:** 2026-08-15  
**Purpose:** Document how pointers, references, and path-based identifiers are used across the IA broker system to track jobs, artifacts, memory records, and tool execution results without duplicating data.

---

## Overview: Pointer Architecture

The IA broker uses **pointer-first design** where identifiers (job_id, record_id, artifact paths) serve as references to actual data stored elsewhere. This avoids embedding large payloads inline and instead points to files, SQLite tables, or JSONL documents.

### Key Principle
| Concept | Implementation | Rationale |
|---------|--------------|-----------|
| **Pointer = identifier + location** | job_id, session_id, record_id, artifact path strings | Reference to actual data source |
| **Payload = actual content** | Full JSON objects, file contents, SQL query results | Real evidence for model consumption |
| **Materialization = pointer → payload resolution** | Reading artifact JSON, loading SQLite rows, reading NDJSON events | Converting references into usable data |

---

## Pointer Categories

### 1. Job Lifecycle Pointers

#### job_id (Primary Identifier)
```python
# job_store.py lines ~100-200
job_id: str
├── agent_job_root(job_id) → Path(f"agent-jobs/{session_id(job_id)}")
│   ├── job.json (state persistence)
│   ├── events.ndjson (event log)
│   └── planner-stream/step-{NNN}.txt (stream artifacts)
├── compact_agent_status(job_id) → loads state + events
├── compact_agent_terminal_response(job_id) → loads final.json + events
└── load_agent_job_state(job_id) → reads job.json
```

**Where:** `services/aicarmine_broker/job_store.py` → `agent_job_root()`, `load_agent_job_state()`, `compact_agent_status()` functions

#### session_id (Session Identifier)
```python
# job_store.py lines ~50-70
session_id: str
├── make_session_id(value) → sanitized slug from value
├── session_root(session_id) → Path(f"workspace/sessions/{slug}")
│   ├── commands/
│   ├── reads/
│   ├── tool-results/
│   └── artifacts/
└── AgentJobActionRouter uses session_id for non-job execution paths
```

**Where:** `services/aicarmine_broker/job_store.py` → `make_session_id()`, `session_root()` functions

### 2. Artifact Pointers

#### artifact (Tool Result Reference)
```python
# job_store.py lines ~300-400
artifact: str  # Path to JSON file in tool-results/ or artifacts/ directory
├── same_tool_artifact_payload(result) → loads artifact JSON if ok=True
│   ├── artifact_path = Path(artifact)
│   ├── If relative: resolved against job_root
│   └── Returns loaded dict or original result on failure
├── _read_job_artifact_json(root, compact_payload.get("artifact"))
│   ├── Validates path is inside job root (security check)
│   ├── Loads JSON content
│   └── Returns (data, {"raw_payload_available": True/False, "artifact": str(path)})
└── helper.py composite helper uses artifact for repo evidence summaries
```

**Where:** `services/aicarmine_broker/job_store.py` → `same_tool_artifact_payload()`, `_read_job_artifact_json()` functions
**Where:** `services/aicarmine_broker/helper.py` → composite helper logic

#### artifact Path Validation Pattern
```python
# job_store.py lines ~350-400
def _path_inside_root(root: Path, path_value: Any) -> Path | None:
    path = Path(path_value) if isinstance(path_value, str) else path_value
    if not path.is_absolute():
        path = root / path
    resolved = path.resolve()
    # Security: ensure resolved path is inside job root
    if not str(resolved).lower().startswith(str(root.resolve()).lower()):
        return None  # Path escapes job root → rejected
    return resolved
```

**Where:** `services/aicarmine_broker/job_html.py` → `_read_job_artifact_json()` function

### 3. Memory Record Pointers

#### record_id (Memory Identifier)
```python
# agent_state.py lines ~116-182
record_id: str  # SHA-256 hash of kind:scope:source:content[:16]
├── MemoryRecord.from_text() → generates record_id from content hash
├── MemoryRecord.from_json() → parses existing record_id
└── build_memory_delta(old, new) → set operations on record_id values
    ├── added = new_ids - old_ids
    ├── removed = old_ids - new_ids
    └── unchanged = old_ids & new_ids
```

**Where:** `services/aicarmine_broker/application/memory/agent_state.py` → `MemoryRecord` dataclass, `build_memory_delta()` function

#### artifact (SQLite Pointer in Scratchpad Tools)
```python
# memory_tools.py lines ~100-200
artifact: str  # Path to planner_composer.sqlite or planner_scratchpad.json
├── planner_scratchpad_read() → {"artifact": str(db_path), "count": N}
│   ├── Loads from SQLite window mode or JSON generic mode
│   └── Returns pointer to source + count of items
├── planner_scratchpad_write() → {"artifact": str(db_path), "record_id": int(lastrowid)}
│   ├── Inserts into SQLite table
│   └── Returns record_id for later retrieval
└── runtime_sqlite_memory_search() → {"artifact": str(db_path), "record_id": ...}
    ├── FTS5 search on broker_memory_records table
    └── Returns pointers to matching records
```

**Where:** `services/aicarmine_broker/memory_tools.py` → scratchpad and memory tool implementations

### 4. Path Pointers (File System References)

#### stream_path / events_path / final_path / error_path
```python
# job_store.py lines ~100-200
stream_path: str  # Path to planner-stream directory
events_path: str  # Path to events.ndjson file
final_path: str   # Path to final.json file
error_path: str   # Path to error.txt file
├── agent_job_root(job_id) → base directory for all paths
│   ├── planner-stream/step-{NNN}.txt
│   ├── events.ndjson
│   ├── final.json
│   └── error.txt
├── compact_agent_terminal_response() → loads final_path content
└── compact_agent_status() → includes events_path reference
```

**Where:** `services/aicarmine_broker/job_store.py` → path construction functions, terminal response builders

### 5. Tool Execution Pointers

#### artifact in Tool Results
```python
# job_store.py lines ~300-400
artifact: str  # Path to tool-results/{timestamp}-{tool}-dispatcher-v6.json
├── SelectorRunner writes dispatcher result here
│   ├── internal_tool execution result
│   └── {"called_by_vulkan": internal_tool, "artifact": str(path)}
├── same_tool_artifact_payload() rehydrates from this path
│   ├── Loads JSON if ok=True
│   └── Returns full payload for evidence materialization
└── Public wrapper includes artifact pointer in response envelope
```

**Where:** `services/aicarmine_broker/application/job/selector_runner.py` → `run()` method lines 120-133

---

## Pointer Resolution Flow

### Step 1: Extract Pointer from Result Dict
```python
# job_store.py lines ~300-400
def same_tool_artifact_payload(result):
    artifact = str(result.get("artifact") or "")
    if not artifact:
        return result  # No pointer → return original
    
    # Resolve relative paths against job root
    artifact_path = Path(artifact)
    if not artifact_path.is_absolute():
        artifact_path = job_root / artifact_path
    resolved_artifact = artifact_path.resolve()
    
    # Security check: path must be inside job root
    if not str(resolved_artifact).lower().startswith(str(job_root.resolve()).lower()):
        return result  # Reject escaped paths
    
    loaded = read_json(resolved_artifact, {})
    return loaded if isinstance(loaded, dict) else result
```

**Where:** `services/aicarmine_broker/job_store.py` → `same_tool_artifact_payload()` function

### Step 2: Materialize Evidence from Pointer
```python
# evidence_materializer.py lines ~100-200
def materialize_inline_evidence(tool_context):
    for artifact in tool_context.get("artifacts", []):
        artifact_path = artifact.get("artifact")
        if not artifact_path:
            continue
        
        # Resolve and load
        content = _load_artifact_content(job_root, artifact_path)
        if content:
            # Promote to priority_evidence_for_30b
            priority_evidence.append({
                "source": artifact_path,
                "content": content,
                "hash": sha256_text(content),
            })
```

**Where:** `services/aicarmine_broker/application/public_payload/evidence_materializer.py` → materialization logic

### Step 3: Strip Local Pointers for Public Output
```python
# terminal_sanitizer.py lines ~100-200
def sanitize_terminal_payload(payload):
    sanitized = dict(payload)
    # Remove local-only pointer fields
    for key in ("artifact", "stream_path", "events_path", "error_path", "final_path"):
        if key in sanitized:
            del sanitized[key]  # Pointer not usable by model
    return sanitized
```

**Where:** `services/aicarmine_broker/application/public_payload/terminal_sanitizer.py` → sanitizer functions

---

## Pointer Security Patterns

### Path Inside Root Validation
```python
# job_html.py lines ~200-300
def _path_inside_root(root: Path, path_value: Any) -> Path | None:
    """Validate that a pointer path stays inside the expected root."""
    path = Path(path_value) if isinstance(path_value, str) else path_value
    if not path.is_absolute():
        path = root / path
    resolved = path.resolve()
    # Reject paths that escape the job root (security check)
    if not str(resolved).lower().startswith(str(root.resolve()).lower()):
        return None
    return resolved
```

**Where:** `services/aicarmine_broker/job_html.py` → `_path_inside_root()` helper function

### Artifact Audit Metadata
```python
# job_html.py lines ~250-350
def _tool_payload_audit(compact_payload, raw_payload):
    violations = []
    
    # Check for preview-only violation (pointer without real content)
    if compact_payload.get("content_preview") and not compact_payload.get("content"):
        violations.append("preview_only_violation")
    
    # Check for artifact-only violation (pointer with no useful keys)
    if compact_payload.get("artifact") and raw_available:
        useful_keys = [k for k in compact_payload if k not in {"tool", "ok", "summary", "artifact"}]
        if not useful_keys:
            violations.append("artifact_only_violation")
    
    return {"violations": violations, "raw_payload_loaded_in_heavy_view": bool(raw_payload)}
```

**Where:** `services/aicarmine_broker/job_html.py` → `_tool_payload_audit()` function

---

## Pointer Usage by Component

### job_store.py - Primary Pointer Manager
```
job_id pointers:
├── agent_job_root(job_id) → filesystem base path
├── agent_job_state_path(job_id) → job.json location
├── agent_job_events_path(job_id) → events.ndjson location
├── agent_job_planner_stream_dir(job_id) → planner-stream/ directory
└── job_url(job_id) → HTTP URL reference

session_id pointers:
├── make_session_id(value) → sanitized slug generator
└── session_root(session_id) → workspace/sessions/{slug} base

artifact pointers:
├── same_tool_artifact_payload(result) → rehydrates from artifact path
└── compact_agent_terminal_response() → loads final_path content
```

**Where:** `services/aicarmine_broker/job_store.py` → all pointer construction functions

### memory_tools.py - SQLite Pointer Manager
```
planner_scratchpad_read/write:
├── artifact: str(db_path) → pointer to planner_composer.sqlite
└── record_id: int → pointer to specific row in SQLite table

runtime_sqlite_memory_search/write:
├── artifact: str(db_path) → pointer to broker_memory_records.db
└── record_id: int/str → pointer to specific memory record
```

**Where:** `services/aicarmine_broker/memory_tools.py` → scratchpad and memory tool implementations

### public_payload/ - Pointer Materialization & Sanitization
```
evidence_materializer.py:
├── Promotes complete artifacts from tool_context_for_30b.artifacts[*].artifact
└── Builds payload_index_for_30b pointers to resolved locations

terminal_sanitizer.py:
├── Removes local path/pointer fields (artifact, stream_path, events_path)
└── Preserves real content and diff text fields

payload_index_resolver.py:
├── Verifies locations like tool_context_for_30b.artifacts[0].artifact.content
└── Distinguishes resolved vs missing vs empty targets
```

**Where:** `services/aicarmine_broker/application/public_payload/` → materializer, sanitizer, resolver modules

---

## Pointer Lifecycle Patterns

### Creation → Resolution → Stripping

```
1. CREATION (Tool Execution)
   selector_runner.run() → dispatch_tool() → writes artifact JSON
   └── artifact = root / "tool-results" / f"{now()}-{internal_tool}-dispatcher-v6.json"
   └── result["artifact"] = str(artifact)  ← pointer embedded in result dict

2. RESOLUTION (Evidence Materialization)
   compact_agent_terminal_response(job_id) → loads final_path
   same_tool_artifact_payload(result) → rehydrates from artifact path
   evidence_materializer.materialize_inline_evidence() → promotes to priority_evidence
   
3. STRIPPING (Public Output)
   terminal_sanitizer.sanitize_terminal_payload() → removes local pointers
   public_tool_response() → strips PUBLIC_LOCAL_REFERENCE_KEYS
   └── artifact, stream_path, events_path, error_path, final_path removed
```

**Where:** Integration across `selector_runner.py`, `job_store.py`, `evidence_materializer.py`, `terminal_sanitizer.py`

---

## Pointer Reference Tables

### Primary Identifiers

| Pointer | Type | Source | Resolution Target | Where Used |
|---------|------|--------|-------------------|------------|
| `job_id` | str | AgentJobSnapshot.domain.models | job.json + events.ndjson + final.json | job_store.py |
| `session_id` | str | make_session_id() | workspace/sessions/{slug}/ | job_store.py |
| `record_id` | str | MemoryRecord.dataclass | SQLite row or JSONL line | agent_state.py |
| `artifact` | str | selector_runner.run() | tool-results/{timestamp}-{tool}.json | job_store.py, helper.py |
| `stream_path` | str | agent_job_planner_stream_path() | planner-stream/step-{NNN}.txt | job_html.py |
| `events_path` | str | agent_job_events_path() | events.ndjson | job_store.py |
| `final_path` | str | state.final_path field | final.json | job_store.py |
| `error_path` | str | state.error field | error.txt | job_store.py |

### Pointer Resolution Functions

| Function | Input Pointer | Output | Location |
|----------|--------------|--------|----------|
| `same_tool_artifact_payload(result)` | result["artifact"] | Loaded JSON dict or original result | job_store.py |
| `_read_job_artifact_json(root, artifact)` | artifact path | (data, metadata) tuple | job_html.py |
| `load_agent_job_state(job_id)` | job_id | State dict from job.json | job_store.py |
| `compact_agent_terminal_response(job_id)` | job_id + final_path | Terminal response with evidence | job_store.py |
| `planner_scratchpad_read()` | artifact (db path) | Items list + count | memory_tools.py |
| `runtime_sqlite_memory_search()` | artifact (db path) | Memory records from FTS5 | memory_tools.py |

### Pointer Stripping Rules

| Field | Stripped for Public Output? | Reason | Location |
|-------|----------------------------|--------|----------|
| `artifact` | Yes | Internal storage path, not model-visible | terminal_sanitizer.py |
| `stream_path` | Yes | Local file reference | terminal_sanitizer.py |
| `events_path` | Yes | Local file reference | terminal_sanitizer.py |
| `final_path` | Yes | Local file reference | terminal_sanitizer.py |
| `error_path` | Yes | Local file reference | terminal_sanitizer.py |
| `content` | No | Real evidence content | Preserved |
| `unified_diff` | No | Real evidence content | Preserved |
| `code_product_state` | No | Real evidence content | Preserved |

---

## Quick Reference: Pointer Flow Diagram

```
Tool Execution (selector_runner.run)
│
├── dispatch_tool(internal_tool, internal_args, ...) → result dict
│   └── result["artifact"] = str(tool-results/{timestamp}-{tool}.json)  ← POINTER CREATED
│   └── result["called_by_vulkan"] = internal_tool
│
├── public_wrapper(...) → envelope with artifact pointer
│   └── envelope["artifact"] = str(artifact_path)
│   └── write_json(root / "broker-session.json", envelope)  ← POINTER WRITTEN
│
Evidence Materialization (compact_agent_terminal_response)
│
├── load_agent_job_state(job_id) → state dict
│   └── final_path = state.get("final_path")  ← POINTER EXTRACTED
│   └── loaded_final = read_json(Path(final_path), {})  ← RESOLVED
│
├── same_tool_artifact_payload(result) → rehydrated payload
│   └── artifact = result.get("artifact")  ← POINTER EXTRACTED
│   └── artifact_path = Path(artifact) or job_root / artifact  ← RESOLVED
│   └── loaded = read_json(resolved_artifact, {})  ← RESOLVED
│   └── Returns loaded dict with real content
│
Public Output (terminal_sanitizer.sanitize)
│
├── Remove local-only pointers:
│   ├── del sanitized["artifact"]  ← STRIPPED
│   ├── del sanitized["stream_path"]  ← STRIPPED
│   ├── del sanitized["events_path"]  ← STRIPPED
│   ├── del sanitized["final_path"]  ← STRIPPED
│   └── del sanitized["error_path"]  ← STRIPPED
│
└── Preserve real evidence:
    ├── sanitized["content"] = "..."  ← KEPT
    ├── sanitized["unified_diff"] = "..."  ← KEPT
    └── sanitized["code_product_state"] = {...}  ← KEPT
```

---

## Related Documentation Files

| File | Purpose |
|------|---------|
| `TURNS_MAPPING.md` | Planner turn logic flow and decision processing |
| `TURNS_SUBTURNS_DEPENDENCIES.md` | Turn-subturn dependency graph and state transitions |
| `IA_BROKER_FLOWS.md` | IA broker behavioral flows, routing logic, selector vs job paths |
| `MEMORY_SYSTEM.md` | Persistent vs non-persistent memory handling, retention policy |
| `POINTER_USAGE_PATTERNS.md` (this file) | How pointers/references are used across the codebase for job tracking, artifact resolution, and evidence materialization |