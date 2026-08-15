# Memory System: Persistent vs Non-Persistent Handling

**Created:** 2026-08-15  
**Purpose:** Document how the IA broker manages persistent (SQLite/JSONL) and non-persistent (in-memory/state packet) memory, including record lifecycle, retention policies, selection/ranking logic, and integration with planner turns and job execution.

---

## Overview: Two-Tier Memory Architecture

The IA broker uses a two-tier memory system:

| Tier | Storage | Purpose | Persistence | Access Pattern |
|------|---------|---------|-------------|----------------|
| **Persistent Memory** | SQLite (`agent_memory.db`) + JSONL files | Long-lived operational records, task summaries, validation results, durable constraints | File-based, survives process restart | FTS5 search, SQL queries, policy review |
| **Non-Persistent Memory** | In-memory `list[MemoryRecord]` | State packets built for planner turns, microtask context, ephemeral routing decisions | Lost on process exit | Direct list operations, keyword ranking |

### Key Distinction
| Concept | Persistent Tier | Non-Persistent Tier |
|---------|-----------------|---------------------| | Built from file/DB load | Used only within turn/packet lifecycle |
| **Lifecycle** | Controlled by DEFAULT_RETENTION_POLICY | Transient, scoped to single job or turn |
| **Storage Format** | SQLite table + JSONL export files | Python dataclass in memory |
| **Selection** | FTS5 search → policy review → state packet build | Keyword scoring → confidence sorting → limit clamping |

---

## MemoryRecord Data Model

```python
# agent_state.py lines 116-182
@dataclass(frozen=True)
class MemoryRecord:
    record_id: str          # SHA-256 hash of kind:scope:source:content[:16]
    kind: str               # operator_note, task_summary, validation_result, durable_constraint, memory, source_file
    scope: str              # repo, project, session, operator, memory
    source: str             # File path or origin identifier
    summary: str            # Compact text (max 900 chars)
    content: str            # Full content (max 4200 chars by default)
    tags: tuple[str, ...]   # Non-empty tags preserved in insertion order
    confidence: float       # Bounded to [0.0, 1.0], default 1.0
    created_at: str         # ISO-8601 UTC timestamp
    updated_at: str | None  # Last update timestamp
    expires_at: str | None  # Expiration timestamp
    metadata: dict[str, Any]  # Arbitrary key-value store
```

**Where:** `services/aicarmine_broker/application/memory/agent_state.py` → `MemoryRecord` dataclass lines 116-182

### Record Creation Methods

#### From Text (Ephemeral)
```python
# agent_state.py lines 133-159
MemoryRecord.from_text(
    kind="task_summary",
    scope="repo",
    source="/path/to/file.py",
    text="Full content text...",
    tags=["validated", "architecture"],
    confidence=0.9,
)
```
Creates identity hash from `kind:scope:source:content[:16]`, record_id from SHA-256 of that identity.

**Where:** `services/aicarmine_broker/application/memory/agent_state.py` → `from_text()` classmethod

#### From JSON (Persistent Load)
```python
# agent_state.py lines 161-182
MemoryRecord.from_json('{"record_id": "...", "kind": "...", ...}')
```
Parses JSON string into MemoryRecord with all fields mapped. Used when loading from SQLite or JSONL files.

**Where:** `services/aicarmine_broker/application/memory/agent_state.py` → `from_json()` classmethod

---

## Persistent Memory: Storage Backends

### Backend 1: SQLite Database

#### Schema
```sql
CREATE TABLE agent_memory (
    record_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    scope TEXT NOT NULL,
    source TEXT NOT NULL,
    summary TEXT,
    content TEXT,
    tags TEXT,           -- JSON array string
    confidence REAL,
    created_at TEXT,
    updated_at TEXT,
    expires_at TEXT,
    metadata TEXT        -- JSON object string
);
```

#### Loading Records
```python
# agent_state.py lines 208-245
def load_memory_db(db_path: Path, limit: int = 1000) -> list[MemoryRecord]:
    if not db_path.exists():
        return []
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.execute(
        "SELECT record_id, kind, scope, source, summary, content, tags, confidence, created_at, updated_at, expires_at, metadata FROM agent_memory LIMIT ?",
        (int(limit),)
    )
    records = []
    for row in cursor:
        raw = {"record_id": row[0], "kind": row[1], ...}  # All 12 fields
        try:
            records.append(MemoryRecord.from_json(json.dumps(raw)))
        except Exception:
            continue
    return records
```

**Where:** `services/aicarmine_broker/application/memory/agent_state.py` → `load_memory_db()` function lines 208-245

#### Key Characteristics
- Read-only access via `_connect_db()` helper
- Bounded by `limit` parameter (default 1000)
- JSON parsing fallback on malformed rows
- Connection closed in finally block

---

### Backend 2: JSONL Export Files

#### Loading Records
```python
# agent_state.py lines 185-198
def load_memory_jsonl(path: Path) -> list[MemoryRecord]:
    records = []
    if not path.exists():
        return records
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(MemoryRecord.from_json(line))
        except Exception:
            continue
    return records
```

**Where:** `services/aicarmine_broker/application/memory/agent_state.py` → `load_memory_jsonl()` function lines 185-198

#### Writing Records
```python
# agent_state.py lines 345-354
def build_memory_index_jsonl(records, output_path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(record.__dict__, ensure_ascii=False) for record in records]
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
```

**Where:** `services/aicarmine_broker/application/memory/agent_state.py` → `build_memory_index_jsonl()` function lines 345-354

#### Key Characteristics
- One JSON object per line (JSONL format)
- UTF-8 with BOM support (`utf-8-sig`)
- Silent skip on malformed lines
- Parent directories created automatically

---

## Retention Policy: DEFAULT_RETENTION_POLICY

### Policy Structure
```python
# agent_memory_policy.py lines 25-70
DEFAULT_RETENTION_POLICY = {
    "schema_version": 1,
    "max_records_per_scope": 500,
    "max_content_chars": 4200,
    "review_after_days": {
        "operator_note": 14,
        "task_summary": 30,
        "validation_result": 45,
        "source_file": 30,
        "durable_constraint": 180,
        "memory": 45,
    },
    "expire_after_days": {
        "operator_note": 60,
        "task_summary": 180,
        "validation_result": 180,
        "source_file": 90,
        "durable_constraint": 365,
        "memory": 120,
    },
    "promotion_tags": ["architecture", "audio", "blender", "durable", "guardrail", "retention_candidate", "validated"],
    "promotable_kinds": ["durable_constraint", "task_summary", "validation_result"],
    "protected_tags": ["pinned", "project_contract"],
    "blocked_secret_patterns": [
        r"(?i)\b(api[_-]?key|secret|password|passwd|token)\b\s*[:=]\s*\S+",
        r"(?i)\bsk-[A-Za-z0-9_\-]{16,}\b",
        r"(?i)\bghp_[A-Za-z0-9_]{20,}\b",
        r"(?i)\baws_access_key_id\b\s*[:=]\s*\S+",
        r"(?i)\baws_secret_access_key\b\s*[:=]\s*\S+",
    ],
}
```

**Where:** `services/aicarmine_broker/application/memory/agent_memory_policy.py` → `DEFAULT_RETENTION_POLICY` constant lines 25-70

### Policy Fields Explained

| Field | Purpose | Values |
|-------|---------|--------|
| `max_records_per_scope` | Hard cap per scope value | 500 records |
| `max_content_chars` | Max content length per record | 4200 chars |
| `review_after_days` | Days since creation triggers human review | Per-kind thresholds |
| `expire_after_days` | Days since creation triggers expiration | Per-kind thresholds |
| `promotion_tags` | Tags that make records promotion candidates | 7 tag values |
| `promotable_kinds` | Record kinds eligible for manual promotion | 3 kind values |
| `protected_tags` | Tags that prevent automatic expiration | 2 tag values |
| `blocked_secret_patterns` | Regex patterns that trigger quarantine | 5 secret patterns |

---

## Memory Review: Policy Evaluation

### Step 1: Evaluate One Record
```python
# agent_memory_policy.py lines 149-206 (continued)
def review_record(record, now, policy=None) -> MemoryReview:
    active_policy = dict(DEFAULT_RETENTION_POLICY)
    if policy:
        active_policy.update(policy)
    
    issues = []
    age_days = days_since(record.updated_at or record.created_at, now)
    review_after = kind_threshold(active_policy, "review_after_days", record.kind)
    expire_after = kind_threshold(active_policy, "expire_after_days", record.kind)
    protected = bool(set(record.tags) & set(active_policy.get("protected_tags", [])))
    
    # Issue detection
    if record.confidence < 0.5:
        issues.append("low_confidence")
    if len(record.content) > int(active_policy.get("max_content_chars", 4200)):
        issues.append("oversized_content")
    if not record.content.strip():
        issues.append("empty_content")
    issues.extend(detect_secret_patterns(record, active_policy))
    if expires_at is not None and expires_at <= now:
        issues.append("explicitly_expired")
    if age_days >= expire_after and not protected:
        issues.append("stale_by_age")
    elif age_days >= review_after:
        issues.append("review_due")
    
    # Action determination
    reason = promotion_reason(record, active_policy)
    has_blocker = any(issue in {"blocked_secret_pattern", "empty_content", "explicitly_expired", "stale_by_age"} for issue in issues)
    candidate = bool(reason and not has_blocker and record.confidence >= 0.75)
    
    if "blocked_secret_pattern" in issues:
        action = "quarantine"
    elif "explicitly_expired" in issues or "stale_by_age" in issues:
        action = "expire_review"
    elif "oversized_content" in issues:
        action = "trim_review"
    elif "review_due" in issues or "low_confidence" in issues:
        action = "human_review"
    elif candidate:
        action = "promote_candidate"
    else:
        action = "keep"
```

**Where:** `services/aicarmine_broker/application/memory/agent_memory_policy.py` → `review_record()` function lines 149-206+

### Review Actions Mapping

| Issue Conditions | Action | Effect |
|------------------|--------|--------|
| blocked_secret_pattern detected | quarantine | Record flagged for secret removal |
| explicitly_expired OR stale_by_age | expire_review | Record marked for expiration review |
| oversized_content | trim_review | Record content needs truncation |
| review_due OR low_confidence | human_review | Requires operator attention |
| promotion reason + no blocker + confidence >= 0.75 | promote_candidate | Eligible for manual documentation promotion |
| No issues | keep | Record remains active |

---

## Non-Persistent Memory: State Packet Construction

### Build State Packet

```python
# agent_state.py lines 248-284
def build_state_packet(
    objective: str,
    memory_records: list[MemoryRecord],
    repo_root: Path,
    max_chars: int = DEFAULT_MAX_MEMORY_CHARS,  # Default 24000
) -> dict[str, Any]:
    sorted_records = sorted(memory_records, key=lambda r: (-r.confidence, r.created_at))
    selected = []
    used = 0
    for record in sorted_records:
        chunk = {
            "record_id": record.record_id,
            "kind": record.kind,
            "scope": record.scope,
            "source": relative_path(Path(record.source), repo_root),
            "summary": record.summary,
            "content": record.content,
            "tags": list(record.tags),
            "confidence": record.confidence,
        }
        chunk_text = json.dumps(chunk, ensure_ascii=False)
        if used + len(chunk_text) > max_chars:
            break
        selected.append(chunk)
        used += len(chunk_text)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "agent_state_packet",
        "objective": objective,
        "generated_at": utc_now_iso(),
        "max_chars": max_chars,
        "used_chars": used,
        "record_count": len(selected),
        "records": selected,
    }
```

**Where:** `services/aicarmine_broker/application/memory/agent_state.py` → `build_state_packet()` function lines 248-284

### Key Characteristics
- Sorts by confidence descending, then creation time
- Truncates to `max_chars` (default 24000)
- Converts source paths to repo-relative format
- Returns structured packet with metadata

---

## Memory Selection: Keyword Ranking

### Select Memory Against Objective

```python
# agent_state.py lines 299-342
def select_memory(
    records,
    objective: str,
    kind_filter=None,
    scope_filter=None,
    tag_filter=None,
    min_confidence=0.0,
    limit=100,
) -> list[MemoryRecord]:
    # Phase 1: Filter
    filtered = []
    for record in records:
        if kind_filter and record.kind != kind_filter:
            continue
        if scope_filter and record.scope != scope_filter:
            continue
        if tag_filter and tag_filter not in record.tags:
            continue
        if record.confidence < min_confidence:
            continue
        filtered.append(record)
    
    # Phase 2: Keyword scoring
    keywords_obj = keywords(objective, limit=64)
    scored = []
    for record in filtered:
        score = 0
        if record.kind in keywords_obj:
            score += 10
        if record.scope in keywords_obj:
            score += 8
        for tag in record.tags:
            if tag.lower() in keywords_obj:
                score += 5
        if record.summary:
            for kw in keywords_obj:
                if kw in record.summary.lower():
                    score += 3
        if record.content:
            for kw in keywords_obj:
                if kw in record.content.lower():
                    score += 2
        scored.append((score, record.record_id, record))
    
    # Phase 3: Sort and limit
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [r for _, _, r in scored[:limit]]
```

**Where:** `services/aicarmine_broker/application/memory/agent_state.py` → `select_memory()` function lines 299-342

### Scoring Weights

| Match Location | Weight |
|----------------|--------|
| kind field | +10 per keyword match |
| scope field | +8 per keyword match |
| tags (any) | +5 per tag per keyword match |
| summary field | +3 per keyword match |
| content field | +2 per keyword match |

---

## Memory Delta: Change Tracking

### Build Delta Between Record Sets

```python
# agent_state.py lines 366-385
def build_memory_delta(old_records, new_records) -> dict[str, Any]:
    old_ids = {r.record_id for r in old_records}
    new_ids = {r.record_id for r in new_records}
    added = sorted(new_ids - old_ids)
    removed = sorted(old_ids - new_ids)
    unchanged = sorted(old_ids & new_ids)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "memory_delta",
        "added": added,
        "removed": removed,
        "unchanged": unchanged,
        "added_count": len(added),
        "removed_count": len(removed),
        "unchanged_count": len(unchanged),
    }
```

**Where:** `services/aicarmine_broker/application/memory/agent_state.py` → `build_memory_delta()` function lines 366-385

---

## Keyword Extraction: Deterministic Ranking

### Extract Keywords from Text

```python
# agent_state.py lines 91-100
def keywords(text, limit=32) -> tuple[str, ...]:
    counts = {}
    for match in WORD_RE.finditer(text.lower()):
        word = match.group(0)
        if word in STOP_WORDS or word.isdigit():
            continue
        counts[word] = counts.get(word, 0) + 1
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return tuple(word for word, _count in ranked[:limit])
```

**Where:** `services/aicarmine_broker/application/memory/agent_state.py` → `keywords()` function lines 91-100

### Key Characteristics
- Regex matches words with 3+ alphanumeric characters
- Stop words filtered (Italian and English common words)
- Deterministic: same input always produces same output
- Frequency-based ranking with alphabetical tiebreaker

---

## Integration Points: Memory ↔ Planner Turns

### How Persistent Memory Feeds Turn Decisions

```
Job execution starts
→ load_memory_db() or load_memory_jsonl() → list[MemoryRecord]
→ select_memory(records, objective=goal, kind_filter=None, limit=100)
→ build_state_packet(objective, selected_records, repo_root, max_chars=24000)
→ State packet injected into planner turn context
→ Planner evaluates evidence contract with memory records as context
```

**Where:** `services/aicarmine_broker/application/memory/agent_state.py` → integration via `build_state_packet()` function

### How Retention Policy Affects Available Memory

```
review_record(memory_record, now, DEFAULT_RETENTION_POLICY)
→ action = "keep" OR "human_review" OR "promote_candidate" OR ...
→ Only records with action="keep" or action="promote_candidate" included in state packet
→ Records with action="expire_review", "quarantine", "trim_review" excluded or flagged
```

**Where:** `services/aicarmine_broker/application/memory/agent_memory_policy.py` → `review_record()` function

---

## State Packet Integration with Planner Turns

### Step 1: Build Objective from Goal
```python
# External code (planner turn context builder)
objective = goal_text  # Natural language user request
```

### Step 2: Load Persistent Memory
```python
memory_records = load_memory_db(db_path, limit=1000)
# OR
memory_records = load_memory_jsonl(jsonl_path)
```

### Step 3: Filter and Rank
```python
selected = select_memory(
    memory_records,
    objective=objective,
    kind_filter=None,  # Or specific kind like "task_summary"
    scope_filter="repo",  # Or None for all scopes
    tag_filter="validated",  # Or None for all tags
    min_confidence=0.5,
    limit=100,
)
```

### Step 4: Build Compact Packet
```python
packet = build_state_packet(
    objective=objective,
    memory_records=selected,
    repo_root=Path("/path/to/repo"),
    max_chars=24000,
)
# Returns: {"schema_version": 1, "kind": "agent_state_packet", "objective": "...", "records": [...], ...}
```

### Step 5: Inject into Turn Context
The packet's `records` field is included in the evidence contract or planner prompt context, providing historical operational data for the current turn decision.

**Where:** Integration via `services/aicarmine_broker/application/memory/agent_state.py` → `build_state_packet()` function

---

## Memory Routing Policy: agent_memory_routing_policy.py

### Purpose
Determines how memory records are routed between persistent storage and in-memory state packets based on record kind, scope, and tags.

### Key Behaviors
- Records with `kind="memory"` and `scope="repo"` → Persistent SQLite storage
- Records with `kind="task_summary"` → Both persistent + state packet candidate
- Records with `tags=["pinned"]` → Protected from expiration
- Records matching `blocked_secret_patterns` → Quarantined (excluded from packets)

**Where:** `services/aicarmine_broker/application/memory/agent_memory_routing_policy.py` → routing logic

---

## File Reference Map: Memory System

| Concept | Primary Implementation | Secondary References |
|---------|----------------------|---------------------|
| MemoryRecord model | `agent_state.py::MemoryRecord` | dataclass, from_text(), from_json() |
| Persistent SQLite storage | `agent_state.py::load_memory_db()` | _connect_db(), sqlite3 module |
| Persistent JSONL storage | `agent_state.py::load_memory_jsonl()` | path.read_text(), utf-8-sig encoding |
| Retention policy | `agent_memory_policy.py::DEFAULT_RETENTION_POLICY` | review_record(), kind_threshold() |
| Policy evaluation | `agent_memory_policy.py::review_record()` | detect_secret_patterns(), promotion_reason() |
| State packet construction | `agent_state.py::build_state_packet()` | relative_path(), compact_text() |
| Keyword ranking | `agent_state.py::select_memory()` | keywords(), STOP_WORDS filter |
| Memory delta tracking | `agent_state.py::build_memory_delta()` | set operations on record_id |
| Memory routing | `agent_memory_routing_policy.py` | kind/scope/tag-based routing logic |

---

## Quick Reference: Memory Flow Diagram

```
Memory Creation (any tool execution, job step, operator action)
│
├── Persistent Storage Path
│   ├── Write to SQLite agent_memory table
│   ├── OR write JSONL export file
│   └── Apply DEFAULT_RETENTION_POLICY review
│       ├── action="keep" → remains accessible
│       ├── action="expire_review" → flagged for removal
│       ├── action="quarantine" → secret patterns detected
│       └── action="promote_candidate" → eligible for documentation
│
├── Non-Persistent State Packet Path
│   ├── load_memory_db() or load_memory_jsonl() → list[MemoryRecord]
│   ├── select_memory(records, objective=goal, limit=100)
│   │   ├── Phase 1: kind_filter/scope_filter/tag_filter/min_confidence filtering
│   │   ├── Phase 2: keyword scoring (kind:+10, scope:+8, tags:+5, summary:+3, content:+2)
│   │   └── Phase 3: sort by (-score, record_id), take top N
│   ├── build_state_packet(objective, selected_records, repo_root, max_chars=24000)
│   │   ├── Sort by (-confidence, created_at)
│   │   ├── Truncate to max_chars budget
│   │   └── Convert source paths to repo-relative format
│   └── Inject into planner turn context / evidence contract
│
└── Memory Delta Tracking
    ├── old_ids = {r.record_id for r in old_records}
    ├── new_ids = {r.record_id for r in new_records}
    ├── added = new_ids - old_ids
    ├── removed = old_ids - new_ids
    └── unchanged = old_ids & new_ids
```

---

## Related Documentation Files

| File | Purpose |
|------|---------|
| `TURNS_MAPPING.md` | Planner turn logic flow and decision processing |
| `TURNS_SUBTURNS_DEPENDENCIES.md` | Turn-subturn dependency graph and state transitions |
| `IA_BROKER_FLOWS.md` | IA broker behavioral flows, routing logic, selector vs job paths |
| `MEMORY_SYSTEM.md` (this file) | Persistent vs non-persistent memory handling, retention policy, state packet construction |
| `SUBTURNS_EXPLORATION.md` | Subturn tool implementations and validator retry mechanism |