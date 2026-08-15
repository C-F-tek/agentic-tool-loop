# Terminal Payload Specification

**Created:** 2026-08-15  
**Purpose:** Complete specification for the terminal payload surface transported between 3572 broker → 3571 bridge → OpenWebUI. This defines `payload_index_for_30b`, `priority_evidence_for_30b`, `openwebui_usage`, and `tool_context_for_30b` fields that model-visible evidence relies on.

---

## Overview: Three-Tier Evidence Transport Architecture

The IA broker uses a three-tier system for transporting model-visible evidence to OpenWebUI:

| Tier | Field | Purpose | Content Type |
|------|-------|---------|--------------|
| **Tier 1** | `payload_index_for_30b` | Navigation surface for concrete payload fields | Keys, locations, offsets |
| **Tier 2** | `priority_evidence_for_30b` | Pointer-first high-priority navigation metadata + compact analysis evidence | Metadata, hashes, lengths, primary payload locations |
| **Tier 3** | `tool_context_for_30b` | Pretty-printed JSON object with real successful tool outputs | Complete inline payloads (repo reads, code proposals, diffs) |

**Key Principle:** Tier 3 is canonical. Tiers 1 and 2 are pointer-first navigation surfaces over Tier 3 content. They must NOT duplicate large concrete payloads already present under `tool_context_for_30b.artifacts[*].artifact`.

---

## Terminal Payload Structure (v9 Schema)

### Primary Metadata Fields

| Field | Type | Purpose | Source |
|-------|------|---------|--------|
| `job_id` | str | Job identifier | job_store.py |
| `status` | str | Terminal status (completed/failed/max_steps_reached/etc.) | planner.py, validator.py |
| `goal` | str | Original task goal | job_store.py |
| `final_answer` | str | Final answer text from planner | planner.py |
| `evidence_guide_for_30b` | str | Instructions for reading the payload | public_wrapper.py |

### Evidence Transport Fields

| Field | Type | Purpose | Where Built |
|-------|------|---------|-------------|
| `payload_index_for_30b` | dict | First navigation surface mapping keys to locations in tool_context_for_30b | evidence_materializer.py |
| `priority_evidence_for_30b` | list[dict] | Pointer-first high-priority items with metadata, hashes, lengths | evidence_materializer.py |
| `openwebui_usage` | dict | Usage instructions telling model how to read this payload | vulkan_bridge/app.py |
| `tool_context_for_30b` | dict | Pretty-printed JSON object containing complete tool outputs | public_wrapper.py |

### Secondary Fields (After Primary Evidence)

| Field | Type | Purpose | Where Built |
|-------|------|---------|-------------|
| `result` | dict | Terminal/final payload as public result source | vulkan_bridge/app.py |
| `materialization_report` | dict | Diagnostic report with schema `public_evidence_materialization.v1` | evidence_materializer.py |

---

## payload_index_for_30b Specification

### Structure

```python
payload_index_for_30b = {
    "schema": "payload_index_for_30b.v1",
    # Top-level evidence guide field names (canonical locations):
    "top_level_evidence_guide_field": "evidence_guide_for_30b",
    "primary_payload_field": "primary_payload_for_30b",
    "payload_index_field": "payload_index_for_30b",
    "priority_evidence_field": "priority_evidence_for_30b.items",
    "artifact_mirror_field": "tool_context_for_30b.artifacts[*].artifact",
    
    # Key-to-location mapping:
    "keys": {
        "final_answer": "result.final_answer or primary_payload_for_30b",
        "code_product_state": "tool_context_for_30b.code_product_state",
        "unified_diff": "tool_context_for_30b.artifacts[*].artifact.unified_diff",
        "structured_operations": "tool_context_for_30b.artifacts[*].artifact.structured_operations",
        "repo_read_content": "tool_context_for_30b.artifacts[*].artifact.content",
        "validation_diagnostics": "tool_context_for_30b.artifacts[*].artifact.diagnostics",
    },
    
    # Navigation hints:
    "read_first": [
        "evidence_guide_for_30b",
        "payload_index_for_30b.keys",
        "priority_evidence_for_30b.items[0..2]",
    ],
}
```

### Purpose

- Tells the external model WHERE to find evidence in the payload
- Maps field names to canonical locations
- Provides read-first ordering for efficient context usage
- Does NOT duplicate content; only provides pointers

**Where:** `services/aicarmine_broker/application/public_payload/evidence_materializer.py` → materialization logic

---

## priority_evidence_for_30b Specification

### Structure

```python
priority_evidence_for_30b = [
    {
        "kind": "repo_read",  # or "code_edit_proposal", "diff_validation", etc.
        "step": 6,
        "tool": "repo_read",
        "ok": True,
        "path": "/src/main.py",
        "line_count": 150,
        "content_length": 4200,
        "hash_sha256": "abc123...",
        "location": "tool_context_for_30b.artifacts[0].artifact.content",
        "priority": 1,
        "summary": "Core module with authentication logic",
    },
    {
        "kind": "code_edit_proposal",
        "step": 8,
        "tool": "repo_propose_code_edit",
        "ok": True,
        "target_file": "/src/auth.py",
        "edit_kind": "unified_diff",
        "diff_length": 890,
        "hash_sha256": "def456...",
        "location": "tool_context_for_30b.artifacts[1].artifact.unified_diff",
        "priority": 2,
        "rationale": "Fix authentication bypass vulnerability",
    },
]
```

### Rules for priority_evidence_for_30b Items

| Rule | Description | Enforcement |
|------|-------------|-------------|
| **No duplication** | Must not duplicate large content already in tool_context_for_30b | evidence_materializer.py checks artifact_mirror_field |
| **Pointer-first** | Contains metadata, hashes, lengths, locations - NOT full content | materialization_report.ok=true when inline JSON evidence present |
| **Bounded** | Limited to most important items (typically top 12) | evidence_materializer.py limits list length |
| **Sorted by priority** | Most critical evidence first | materialization logic sorts before appending |
| **Canonical location reference** | Each item references tool_context_for_30b.artifacts[*].artifact as source | payload_index_resolver.py verifies locations |

### Kinds Supported

| Kind | Source Tool | Content Type | Where Built |
|------|-------------|--------------|-------------|
| `repo_read` | repo_read | File content with path, line_count, content | evidence_materializer.py |
| `code_edit_proposal` | repo_propose_code_edit | unified_diff or structured_operations | evidence_materializer.py |
| `diff_validation` | repo_unidiff_validate, repo_git_apply_check | Diff structure validation result | evidence_materializer.py |
| `validation_result` | repo_ruff_check, repo_pyright_check, repo_pytest_run, repo_shellcheck, repo_semgrep_scan | Linter/test/validation diagnostics | evidence_materializer.py |
| `structural_evidence` | repo_ast_grep_search, repo_tree_sitter_parse, repo_ctags_symbols | AST/structure analysis results | evidence_materializer.py |
| `deterministic_repo_evidence` | repo_fd_files, repo_rg_search, repo_jq_query | File discovery/search results | evidence_materializer.py |
| `repo_tree` | repo_tree | Directory structure listing | evidence_materializer.py |
| `repo_list_files` | repo_list_files | File path listing | evidence_materializer.py |
| `command_result` | repo_command, terminal_run_command_wait | Command stdout/stderr output | evidence_materializer.py |

**Where:** `services/aicarmine_broker/application/public_payload/evidence_materializer.py` → kind classification logic

---

## openwebui_usage Specification

### Structure

```python
openwebui_usage = {
    "schema": "openwebui_usage.v1",
    "rule": (
        "This context is a public evidence mirror, not a job dump. Read "
        "evidence_guide_for_30b, primary_payload_for_30b and "
        "payload_index_for_30b before using artifacts[*].artifact."
    ),
    "top_level_evidence_guide_field": "evidence_guide_for_30b",
    "primary_payload_field": "primary_payload_for_30b",
    "payload_index_field": "payload_index_for_30b",
    "priority_evidence_field": "priority_evidence_for_30b.items",
    "artifact_mirror_field": "tool_context_for_30b.artifacts[*].artifact",
}
```

### Purpose

- Tells the external model HOW to read and interpret this payload
- Provides field-level navigation instructions
- Prevents models from treating local paths as evidence
- Establishes that this is a mirror, not a dump

**Where:** `services/aicarmine_broker/application/public_payload/tool_context.py` → `_public_context_usage()` function

---

## tool_context_for_30b Specification

### Structure

```python
tool_context_for_30b = {
    "type": "agentic_loop_public_evidence_context",
    "contract_type": "agentic_loop_public_evidence_context",
    "not_a_summary": True,
    "openwebui_usage": openwebui_usage,
    
    # Job metadata:
    "job": {
        "job_id": "...",
        "status": "completed",
        "goal": "...",
    },
    
    # Evidence arrays:
    "artifacts": [...],  # Complete tool result artifacts with real payloads
    "partial_products_for_30b": [...],  # Rejected/partial code-product attempts
    "best_partial_product_for_30b": {...},  # Best partial product if any
    
    # Evidence digests/views:
    "evidence_digest_for_30b": {...},  # Compact summary of evidence state
    "evidence_view_for_30b": [...],  # Detailed evidence view items
    
    # Orientation and next action:
    "initial_orientation_surface": {...},  # Initial orientation data
    "next_action_for_30b": {...},  # Next recommended action
    
    # Coverage status:
    "coverage_status": {...},  # Read coverage metrics
    
    # Context build diagnostics:
    "context_build_diagnostics": {...},  # How context was built
    
    # Evidence contract summary:
    "evidence_contract_summary": {...},  # Contract summary triplet
    "evidence_contract_sha256": "...",  # SHA-256 of full contract
    "evidence_contract_chars": 12450,  # Character count of contract
}
```

### Artifacts Array Structure

Each item in `artifacts` array represents a complete tool result:

```python
{
    "producer_step": 6,
    "substep": 0,
    "tool": "repo_read",
    "arguments": {"paths": ["/src/main.py"]},
    "ok": True,
    "artifact": {
        "kind": "repo_read",
        "path": "/src/main.py",
        "size_bytes": 4200,
        "line_count": 150,
        "truncated": False,
        "content": "... full file content ...",
    },
}
```

### Key Rules for tool_context_for_30b

| Rule | Description | Enforcement |
|------|-------------|-------------|
| **Complete payloads canonical** | `tool_context_for_30b.artifacts[*].artifact` is the canonical complete payload location | CODEX_OPENWEBUI_PAYLOAD_LIMITATION.md contract |
| **No local paths as evidence** | Must not expose internal artifact paths outside operator diagnostics | terminal_sanitizer.py strips LOCAL_REFERENCE_KEYS |
| **Real successful tool outputs** | Only ok=True tool results with real content | public_tool_response() filters by ok field |
| **Stripped of local pointers** | Fields like artifact, stream_path, events_path removed for public output | terminal_sanitizer.py sanitization |

### PUBLIC_LOCAL_REFERENCE_KEYS Stripped

```python
PUBLIC_LOCAL_REFERENCE_KEYS = {
    "cached_from_artifact",
    "stream_path",
    "events_path",
    "error_path",
    "final_path",
    "db",
    "workspace",
    "operator_error_path",
    "document_id",
    "final_json",
    "final_markdown",
    "events_ndjson",
    "planner_stream",
}
```

**Where:** `services/aicarmine_broker/application/public_payload/tool_context.py` → strip_public_local_references() function

---

## Materialization Report Schema

### Structure

```python
materialization_report = {
    "schema": "public_evidence_materialization.v1",
    "owner": "3572_broker",  # or "3571_bridge" for emergency rehydration
    "ok": True,  # Whether inline JSON evidence was materialized
    "tool_context_json_object_parseable": True,  # Whether tool_context_for_30b is valid JSON object
    "priority_evidence_items_count": N,  # Number of priority items
    "artifacts_complete_inline_count": M,  # Number of complete inline artifacts
    "missing_inline_evidence": [...],  # Tools with ok=True but no inline content
}
```

### Owner Values

| Owner | Purpose | When Used |
|-------|---------|-----------|
| `3572_broker` | Normal materialization from job worker | Standard terminal result building |
| `3571_bridge` | Emergency rehydration/fallback | When 3572 did not produce proper materialization |

**Where:** `services/aicarmine_broker/application/public_payload/evidence_materializer.py` → materialization report building

---

## Terminal Payload Flow: 3572 → 3571 → OpenWebUI

### Step 1: 3572 Broker Builds Final State
```python
# planner.py::finalize_agentic_job()
# Writes final state to job_store
final_state = {
    "job_id": "...",
    "status": "completed",
    "goal": "...",
    "final_answer": "...",
    "history": [...],
    "planner_decision": {...},
}
# job_store writes job.json, events.ndjson, final.json
```

**Where:** `services/aicarmine_broker/planner.py` → finalization logic

### Step 2: 3572 Job Worker Builds Terminal Response
```python
# job_store.py::compact_agent_terminal_response()
terminal = {
    "job_id": "...",
    "status": "...",
    "goal": "...",
    "result": {...},  # Loaded from final.json or state
    "evidence_guide_for_30b": "...",
    "payload_index_for_30b": payload_index_resolver.resolve(...),
    "priority_evidence_for_30b": evidence_materializer.materialize(...),
}
# Includes tool_context_for_30b with complete artifacts
```

**Where:** `services/aicarmine_broker/job_store.py` → terminal response building

### Step 3: 3571 Bridge Wraps for OpenWebUI
```python
# vulkan_bridge/app.py::_agentic_v9_build_openwebui_response()
response = {
    # Primary metadata (kept):
    "job_id": ...,
    "status": ...,
    "goal": ...,
    "final_answer": ...,
    
    # Evidence transport fields (kept, in order):
    "payload_index_for_30b": ...,
    "priority_evidence_for_30b": ...,
    "openwebui_usage": ...,
    "tool_context_for_30b": ...,
    
    # Result field (after evidence):
    "result": {...},  # Terminal/final payload as public result source
    
    # Materialization report:
    "materialization_report": {...},
}
# Strips local-only pointer fields from tool_context_for_30b
```

**Where:** `services/vulkan_bridge/app.py` → `_agentic_v9_build_openwebui_response()` function

### Step 4: OpenWebUI Receives Payload
- Model sees: primary metadata + `payload_index_for_30b` + `priority_evidence_for_30b` + `openwebui_usage` + pretty JSON `tool_context_for_30b`
- NOT exposed: raw controller audit history, local artifact paths, blocked/prose narrative as primary answer
- Evidence guide tells model to read tiered structure efficiently

---

## Terminal Payload Validation Rules

### From CODEX_OPENWEBUI_PAYLOAD_LIMITATION.md Contract

| Rule | Description | Violation Detection |
|------|-------------|---------------------|
| **No preview-only** | Preview/metadata without real content is not successful evidence | `_tool_payload_audit()` checks for preview_only_violation |
| **No artifact-only** | Artifact path without useful keys is not sufficient | `_tool_payload_audit()` checks for artifact_only_violation |
| **No local paths as evidence** | Internal storage paths are not model-visible | terminal_sanitizer.py strips PUBLIC_LOCAL_REFERENCE_KEYS |
| **Complete payloads canonical** | `artifacts[*].artifact` is the canonical location | materialization_report tracks missing inline evidence |
| **Priority index navigation** | `priority_evidence_for_30b` is pointer-first, not duplicate | payload_index_resolver verifies resolved vs missing vs empty |

### Violation Types Detected

| Violation | Condition | Where Detected |
|-----------|---------|-----------------|
| `preview_only_violation` | content_preview present but no real content | job_html.py::_tool_payload_audit() |
| `artifact_only_violation` | artifact path present but no useful keys in payload | job_html.py::_tool_payload_audit() |
| `missing_inline_evidence` | ok=True tool result but no inline JSON evidence | evidence_materializer.py materialization report |

---

## Quick Reference: Terminal Payload Field Ordering

The terminal response must follow this field order:

```python
response = {
    # 1. Primary metadata (always kept):
    "job_id": ...,
    "status": ...,
    "goal": ...,
    "final_answer": ...,
    
    # 2. Evidence transport fields (in order):
    "payload_index_for_30b": ...,       # First navigation surface
    "priority_evidence_for_30b": ...,   # Pointer-first high-priority items
    "openwebui_usage": ...,             # Usage instructions
    "tool_context_for_30b": {...},      # Pretty-printed complete tool outputs
    
    # 3. Result field (after evidence when present):
    "result": {...},                    # Terminal/final payload source
    
    # 4. Materialization report:
    "materialization_report": {...},    # Diagnostic-only report
}
```

**Critical Rule:** `result` must NOT appear before the primary evidence fields. Terminal wrapping uses compact digest only when terminal payload has no `result`.

---

## Related Documentation Files

| File | Purpose |
|------|---------|
| `TURNS_MAPPING.md` | Planner turn logic flow and decision processing |
| `TURNS_SUBTURNS_DEPENDENCIES.md` | Turn-subturn dependency graph and state transitions |
| `IA_BROKER_FLOWS.md` | IA broker behavioral flows, routing logic, selector vs job paths |
| `MEMORY_SYSTEM.md` | Persistent vs non-persistent memory handling, retention policy |
| `POINTER_USAGE_PATTERNS.md` | How pointers/references are used across the codebase |
| `EVIDENCE_CONTRACT_REFERENCE.md` | Complete reference for evidence_contract dictionary fields |
| `TERMINAL_PAYLOAD_SPECIFICATION.md` (this file) | Terminal payload structure, field ordering, materialization flow between 3572→3571→OpenWebUI |