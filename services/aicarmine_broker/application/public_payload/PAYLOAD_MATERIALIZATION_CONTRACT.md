# Payload Materialization Contract

**Created:** 2026-08-15  
**Purpose:** Complete contract specification for how `evidence_materializer.py`, `payload_index_resolver.py`, and `terminal_sanitizer.py` work together to materialize, resolve, and sanitize public payload fields for OpenWebUI transport between 3572 broker → 3571 bridge → model-visible evidence surface.

---

## Overview: Three-Package Materialization System

The materialization system consists of three cooperating packages:

| Package | Role | Schema Versions |
|---------|------|-----------------|
| `evidence_materializer.py` | Broker-side owner for inline evidence materialization | `public_evidence_materialization.v1`, `openwebui.primary_payload_for_30b.v1`, `openwebui.priority_evidence_for_30b.v1`, `openwebui_payload_index.v1` |
| `payload_index_resolver.py` | Pure resolver for payload-index path verification | Resolves locations like `tool_context_for_30b.artifacts[0].artifact.content` |
| `terminal_sanitizer.py` | Pure terminal payload sanitizer for public output | Strips local-only pointer fields |

**Key Principle:** Materialization is pointer-first. Complete payloads are canonical under `tool_context_for_30b.artifacts[*].artifact`. The materializer does NOT load local files, does NOT duplicate large payload content into the index, and does NOT alter validator/finalization gates.

---

## evidence_materializer.py: Broker-Side Owner

### Schema Versions Defined

```python
MATERIALIZATION_SCHEMA = "public_evidence_materialization.v1"
PRIMARY_SCHEMA = "openwebui.primary_payload_for_30b.v1"
PRIORITY_SCHEMA = "openwebui.priority_evidence_for_30b.v1"
INDEX_KIND = "openwebui_payload_index.v1"
```

### Materialization Flow

#### Step 1: Build Priority Evidence Items

The materializer iterates over `tool_context.artifacts` array and builds priority items for each artifact kind:

| Artifact Kind | Priority Item Kind | Source Tool | Content Type |
|---------------|-------------------|-------------|--------------|
| `repo_read` | `repo_file_full_content` | repo_read | Full file content with path, line_count, chars, sha256 |
| `code_edit_proposal` | `code_edit_proposal` | repo_propose_code_edit | unified_diff or structured_operations with target_file, edit_kind, rationale |
| `partial_code_product_*` | `partial_code_product_candidate`, etc. | Various | Partial/incomplete code product payloads |
| `coverage_gap` | `coverage_gap` | Coverage status | Missing owner paths when coverage_satisfied=false |
| `tool_result_inline` | `tool_result_inline` | Any tool | Generic tool result metadata |

**Where:** `evidence_materializer.py::_priority_item_from_artifact()` → lines 61-147

#### Step 2: Build Analysis Summary Item

```python
# _analysis_priority_item() builds repo_analysis_summary kind
{
    "kind": "repo_analysis_summary",
    "payload_is_complete": bool(planner_text),
    "guide_chars": len(planner_text),
    "primary_payload_location": "evidence_guide_for_30b",
    "summary_not_duplicated_here": True,
    "content_not_duplicated_here": True,
    "evidence_files": [...],  # Up to 80 evidence file references
}
```

**Where:** `evidence_materializer.py::_analysis_priority_item()` → lines 179-211

#### Step 3: Build Partial Products Items

```python
# _partial_priority_items() builds partial terminal payload items
{
    "kind": "partial_code_product_candidate",
    "payload_is_complete": False,
    "validator_accepted": False,
    ...fields from partial_products_for_30b or best_partial_product_for_30b...
}
```

**Where:** `evidence_materializer.py::_partial_priority_items()` → lines 214-236

#### Step 4: Build Coverage Gap Item

```python
# _coverage_priority_item() builds coverage gap when coverage_satisfied=false
{
    "kind": "coverage_gap",
    "payload_type": "coverage_status",
    "payload_is_complete": False,
    "validator_accepted": False,
    "missing_owner_paths": [...],
    "covered_owner_paths": [...],
    "role": "gap di copertura: non trattare questo payload come completato",
}
```

**Where:** `evidence_materializer.py::_coverage_priority_item()` → lines 239-273

#### Step 5: Build Primary Payload Descriptors

For each priority item, the materializer builds a primary descriptor:

```python
{
    "schema": PRIMARY_SCHEMA,
    "owner": "application.evidence" or "application.code_product" etc.,
    "request_type": "repo_analysis" or "code_product" etc.,
    "payload_kind": kind of payload,
    "tool": tool name,
    "step": producer step number,
    "substep": substep number,
    "path": file path if applicable,
    "target_file": target file if applicable,
    "item_index": index in priority_evidence array,
    "source_index_section": "concrete_results" or "partial_results",
    "primary_location": location string like "priority_evidence_for_30b.items[0]",
    "full_context_location": where to find full content,
    "payload_is_complete": True/False,
    "validator_accepted": True/False,
    "read_before_payload_index": True,  # Must read before payload_index
    "content_not_duplicated_here": True,  # Content not copied here
}
```

**Where:** `evidence_materializer.py::_primary_descriptor_from_row()` → lines 658-692

#### Step 6: Build Payload Index Rows

For each priority item, the materializer builds a payload index row mapping metadata to canonical locations:

| Priority Item Kind | Payload Type | Primary Location Pattern |
|-------------------|--------------|-------------------------|
| `repo_file_full_content` | `file_content` | `tool_context_for_30b.artifacts[N].artifact.content` |
| `code_edit_proposal` (unified_diff) | `unified_diff` | `tool_context_for_30b.artifacts[N].artifact.unified_diff` |
| `code_edit_proposal` (structured_edit) | `structured_operations` | `tool_context_for_30b.artifacts[N].artifact.structured_operations` |
| `partial_*` kinds | Various | `priority_evidence_for_30b.items[N].field_name` |
| `tool_result_inline` | Tool-specific | `tool_context_for_30b.artifacts[N].artifact` |

**Where:** `evidence_materializer.py::_payload_index_row()` → lines 330-469

#### Step 7: Build Materialization Report

```python
materialization_report = {
    "schema": MATERIALIZATION_SCHEMA,
    "owner": "3572_broker",  # or "3571_bridge" for emergency fallback
    "ok": True/False,  # Whether inline JSON evidence was materialized
    "tool_context_json_object_parseable": True/False,
    "priority_evidence_items_count": N,
    "artifacts_complete_inline_count": M,
    "missing_inline_evidence": [...],  # Tools with ok=True but no inline content
}
```

**Where:** `evidence_materializer.py` → report building logic (lines ~800-900)

---

## payload_index_resolver.py: Location Verification

### Purpose

The resolver verifies that locations referenced in priority items actually resolve to real fields within the tool_context_for_30b artifacts array. It distinguishes three states:

| State | Meaning | When Reported |
|-------|---------|---------------|
| `resolved` | Location matches a real field in artifacts | Complete evidence found |
| `missing` | Location does not match any artifact | Evidence incomplete |
| `empty` | Field exists but is empty/null | Partial evidence |

### Resolution Logic

```python
# _context_location_resolution() checks each priority item against artifacts
def _context_location_resolution(tool_context, item):
    kind = item.get("kind")  # e.g., "repo_file_full_content", "code_edit_proposal"
    target_file = item.get("target_file") or ""
    path = item.get("path") or ""
    
    artifacts = tool_context.get("artifacts", [])
    if not artifacts:
        return {
            "location": "tool_context_for_30b.artifacts[*].artifact",
            "location_resolved": False,
            "location_resolution_reason": "tool_context_artifacts_empty",
        }
    
    for index, row in enumerate(artifacts):
        artifact = row.get("artifact") or {}
        artifact_kind = artifact.get("kind") or ""
        
        # Match code_edit_proposal by target_file + edit_kind
        if kind == "code_edit_proposal" and artifact_kind == "code_edit_proposal":
            if target_file and artifact.get("target_file") != target_file:
                continue
            edit_kind = artifact.get("edit_kind") or ""
            location = f"tool_context_for_30b.artifacts[{index}].artifact.{edit_kind}"
            return {"location": location, "location_resolved": True, ...}
        
        # Match repo_read by path
        if kind == "repo_file_full_content" and artifact_kind == "repo_read":
            if path and artifact.get("repo_path") != path:
                continue
            location = f"tool_context_for_30b.artifacts[{index}].artifact.content"
            return {"location": location, "location_resolved": True, ...}
    
    # No match found
    return {
        "location": "tool_context_for_30b.artifacts[*].artifact",
        "location_resolved": False,
        "location_resolution_reason": "matching_artifact_not_found",
    }
```

**Where:** `evidence_materializer.py::_context_location_resolution()` → lines 276-322

### Code Product Gate Diagnostic

The resolver also builds a diagnostic-only code product gate:

```python
{
    "schema": "openwebui_payload_index.code_product_gate.v1",
    "diagnostic_only": True,
    "target_file": "...",
    "target_read": True/False,  # Whether target file was read
    "repo_propose_code_edit_ok": True/False,  # Whether repo_propose_code_edit succeeded
    "complete_payload_inline": True/False,  # Whether complete inline payload exists
    "edit_kind": "unified_diff" or "structured_edit" or "no_op" or "unknown",
    "final_allowed": True/False,  # From finalization_contract
}
```

**Where:** `evidence_materializer.py::_code_product_gate()` → lines 510-577

---

## terminal_sanitizer.py: Pointer Stripping

### Purpose

The sanitizer removes local-only pointer fields from the terminal payload before public output. These fields are internal storage paths that must NOT be exposed to OpenWebUI/models as evidence.

### Fields Stripped

| Field | Reason | Where Detected |
|-------|--------|----------------|
| `artifact` | Internal artifact path, not model-visible | terminal_sanitizer.py |
| `stream_path` | Local file reference | terminal_sanitizer.py |
| `events_path` | Local file reference | terminal_sanitizer.py |
| `final_path` | Local file reference | terminal_sanitizer.py |
| `error_path` | Local file reference | terminal_sanitizer.py |
| `db` | SQLite database path | terminal_sanitizer.py |
| `workspace` | Workspace directory path | terminal_sanitizer.py |
| `document_id` | Scratchpad document identifier | terminal_sanitizer.py |

### Stripping Logic

```python
# sanitize_terminal_payload() removes local pointers
def sanitize_terminal_payload(payload):
    sanitized = dict(payload)
    
    # Remove pointer fields
    for key in ("artifact", "stream_path", "events_path", "final_path", 
                 "error_path", "db", "workspace", "document_id"):
        if key in sanitized:
            del sanitized[key]  # Pointer not usable by model
    
    # Preserve real evidence content
    # - sanitized["content"] = "...", kept
    # - sanitized["unified_diff"] = "...", kept
    # - sanitized["code_product_state"] = {...}, kept
    
    return sanitized
```

**Where:** `services/aicarmine_broker/application/public_payload/terminal_sanitizer.py` → sanitizer functions

---

## Materialization Contract Rules

### Rule 1: No Duplication

Priority items must NOT duplicate large concrete payloads already present under `tool_context_for_30b.artifacts[*].artifact`. Each priority item contains metadata, hashes, lengths, and location references only.

**Enforcement:** `_priority_item_from_artifact()` sets `"content_not_duplicated_here": True` for every item.

### Rule 2: Pointer-First Navigation

`payload_index_for_30b` and `priority_evidence_for_30b` are navigation surfaces over canonical content in `tool_context_for_30b.artifacts[*].artifact`. They tell the model WHERE to find evidence, not WHAT the evidence is.

**Enforcement:** `_payload_index_row()` builds primary_location strings pointing to artifact fields.

### Rule 3: Complete Payloads Canonical

`tool_context_for_30b.artifacts[*].artifact` is the canonical complete payload location. If a successful tool result needs to be visible to OpenWebUI, the full inline content must be present there.

**Enforcement:** Materialization report tracks `"artifacts_complete_inline_count"` and `"missing_inline_evidence"`.

### Rule 4: No Local Paths as Evidence

Internal storage paths (artifact, stream_path, events_path, etc.) are diagnostic-only and must NOT be exposed outside operator diagnostics. They are stripped before public output.

**Enforcement:** `terminal_sanitizer.py` strips all PUBLIC_LOCAL_REFERENCE_KEYS.

### Rule 5: Validator Acceptance Tracking

Each priority item tracks whether it was accepted by the validator:
- `payload_is_complete`: Whether the payload has complete content
- `validator_accepted`: Whether the validator marked this as acceptable evidence

**Enforcement:** `_priority_item_from_artifact()` sets these fields based on artifact content validation.

### Rule 6: Owner Attribution

Each priority item is attributed to its owning application package:

| Kind | Owner | Request Type |
|------|-------|--------------|
| `repo_file_full_content`, `repo_analysis_summary` | `application.evidence` | `repo_analysis` |
| `code_edit_proposal`, `partial_code_product_*` | `application.code_product` | `code_product` |
| `coverage_gap` | `application.evidence` | `minimum_read_coverage` |
| `tool_result_inline` | `application.tool_surface` | `tool_result` |
| `partial_terminal_payload` | `application.public_payload` | `partial_terminal_payload` |

**Enforcement:** `_owner_for_priority_item()` → lines 639-655

---

## Materialization Report Schema

### Structure

```python
{
    "schema": "public_evidence_materialization.v1",
    "owner": "3572_broker" or "3571_bridge",
    "ok": True/False,  # Whether materialization succeeded
    "tool_context_json_object_parseable": True/False,  # Whether tool_context is valid JSON object
    "priority_evidence_items_count": N,  # Number of priority items built
    "artifacts_complete_inline_count": M,  # Number of complete inline artifacts
    "missing_inline_evidence": [...],  # Tools with ok=True but no inline content available
    "concrete_results_count": C,  # Complete evidence items count
    "partial_results_count": P,  # Partial/incomplete evidence items count
}
```

### Owner Values

| Owner | Purpose | When Used |
|-------|---------|-----------|
| `3572_broker` | Normal materialization from job worker | Standard terminal result building in `planner.py::finalize_agentic_job()` |
| `3571_bridge` | Emergency rehydration/fallback | When 3572 did not produce proper materialization; used by `vulkan_bridge/app.py::_agentic_v9_build_openwebui_response()` |

---

## Payload Search Order

The materializer builds a search order for efficient model reading:

```python
search_order = [
    "evidence_guide_for_30b",           # First: read evidence guide
    "primary_payload_for_30b.primary_location",  # Second: primary payload location
    "payload_index_for_30b.concrete_results[0..N]",  # Third: complete evidence items
    "priority_evidence_for_30b.items[0..M].location",  # Fourth: priority item locations
    "payload_index_for_30b.partial_results[0..P]",  # Fifth: partial evidence items
    "tool_context_for_30b.artifacts[*].artifact",  # Fallback: full artifacts array
]
```

**Where:** `evidence_materializer.py::_payload_search_order()` → lines 615-636

---

## Quick Reference: Materialization Flow Diagram

```
input: tool_context (dict from job terminal result)
│
├── Step 1: Build priority_evidence_for_30b.items
│   ├── Iterate over tool_context.artifacts
│   ├── For each artifact, build _priority_item_from_artifact()
│   │   ├── repo_read → repo_file_full_content kind
│   │   ├── code_edit_proposal → code_edit_proposal kind
│   │   └── partial_* → partial_code_product_candidate kinds
│   ├── Add _analysis_priority_item() for repo analysis summary
│   ├── Add _partial_priority_items() for partial products
│   ├── Add _coverage_priority_item() when coverage_satisfied=false
│   └── Each item gets: kind, tool, step, substep, payload_is_complete, sha256, location
│
├── Step 2: Build primary_payload_for_30b descriptors
│   ├── For each priority item, build _primary_descriptor_from_row()
│   │   ├── owner = application.evidence / code_product / tool_surface / public_payload
│   │   ├── request_type = repo_analysis / code_product / tool_result
│   │   ├── primary_location = "priority_evidence_for_30b.items[N].field"
│   │   └── content_not_duplicated_here = True
│   └── Each descriptor tracks validator_accepted and payload_is_complete
│
├── Step 3: Build payload_index_for_30b rows
│   ├── For each priority item, build _payload_index_row()
│   │   ├── kind → payload_type mapping
│   │   ├── primary_location → canonical artifact field reference
│   │   └── full_context_location → where to find complete content
│   └── Resolve locations via _context_location_resolution() against artifacts array
│
├── Step 4: Build materialization_report
│   ├── schema = "public_evidence_materialization.v1"
│   ├── owner = "3572_broker" (or "3571_bridge")
│   ├── ok = True when inline JSON evidence present
│   ├── priority_evidence_items_count = N
│   ├── artifacts_complete_inline_count = M
│   └── missing_inline_evidence = tools with ok=True but no inline content
│
├── Step 5: Verify location resolution
│   ├── _context_location_resolution() checks each item against artifacts
│   ├── resolved = matches artifact by kind + target_file/path
│   ├── missing = no matching artifact found
│   └── code_product_gate builds diagnostic-only gate for code product state
│
└── Step 6: Sanitize for public output
    ├── terminal_sanitizer removes local pointer fields (artifact, stream_path, etc.)
    ├── Preserves real evidence content (content, unified_diff, code_product_state)
    └── Returns sanitized payload ready for OpenWebUI transport
```

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
| `TERMINAL_PAYLOAD_SPECIFICATION.md` | Terminal payload structure, field ordering, materialization flow |
| `PAYLOAD_MATERIALIZATION_CONTRACT.md` (this file) | Contract between evidence_materializer, payload_index_resolver, and terminal_sanitizer for public payload construction |