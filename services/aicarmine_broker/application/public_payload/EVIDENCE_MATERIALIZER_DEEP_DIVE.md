# Evidence Materializer Deep Dive Reference

**Created:** 2026-08-15  
**Purpose:** Complete deep-dive reference for `evidence_materializer.py` (984 lines). This module is the 3572 broker owner for public evidence fields. It builds three-tier materialized payloads from tool_context_for_30b without loading local files or duplicating payload content inside the index.

---

## Overview: Three-Tier Public Evidence Architecture

The materializer constructs four interconnected dictionaries:

| Field | Schema | Purpose |
|-------|--------|---------|
| `priority_evidence_for_30b` | `openwebui.priority_evidence_for_30b.v1` | High-priority metadata items with pointer-first navigation |
| `payload_index_for_30b` | `openwebui_payload_index.v1` | Indexed concrete/partial/descriptive results with search order |
| `primary_payload_for_30b` | `openwebui.primary_payload_for_30b.v1` | Owner-selected first useful inline payload location |
| `materialization_report` | `public_evidence_materialization.v1` | Diagnostic-only report for operator verification |

**Key Principle:** Concrete payloads are pointer-first. This section carries metadata/hash/location for successful tool artifacts; partial products are marked validator_accepted=false. Content is never duplicated inside the index itself.

---

## PublicEvidenceMaterializer Class

### Structure

```python
@dataclass(frozen=True)
class PublicEvidenceMaterializer:
    """Build the complete 30B evidence surface from broker-side inline context."""
    
    owner: str = "3572_broker"
```

The class is frozen (immutable dataclass). All mutation happens through pure function calls that return new dictionaries rather than modifying inputs.

---

## materialize() Method

### Signature

```python
def materialize(
    self,
    tool_context: dict[str, Any] | str | None,
    evidence_guide: str = "",
    completed: bool = False,
    internal_job_status: dict[str, Any] | None = None,
) -> dict[str, Any]:
```

### Flow

```python
def materialize(self, tool_context, evidence_guide, completed, internal_job_status):
    # Step 1: Parse tool_context to dict
    context = _as_dict(tool_context)
    
    # Step 2: Check coverage missing status
    coverage_missing = bool(_coverage_priority_item(context))
    effective_completed = bool(completed and not coverage_missing)
    
    # Step 3: Build priority evidence (metadata items)
    priority = self._priority_evidence(context, evidence_guide, completed=effective_completed)
    
    # Step 4: Build payload index (concrete/partial/descriptive categorization)
    payload_index = self._payload_index(priority, context, completed=effective_completed)
    
    # Step 5: Add internal job status if provided
    if isinstance(internal_job_status, dict) and internal_job_status:
        payload_index["internal_job_status"] = _clean(internal_job_status)
    
    # Step 6: Build primary payload descriptor (first useful location)
    primary_payload = _primary_payload_descriptor(priority, payload_index)
    
    # Step 7: Build materialization report (diagnostic verification)
    report = self._materialization_report(context, priority, payload_index, evidence_guide)
    
    # Step 8: Return four-field structure
    return {
        "primary_payload_for_30b": primary_payload,
        "payload_index_for_30b": payload_index,
        "priority_evidence_for_30b": priority,
        "materialization_report": report,
    }
```

### Coverage Logic

| Condition | effective_completed | Meaning |
|-----------|-------------------|---------|
| completed=True AND coverage_missing=False | True | Job fully complete, no coverage gaps |
| completed=True AND coverage_missing=True | False | Job marked complete but has missing owner paths |
| completed=False | False | Job still in progress |

---

## _priority_evidence() Method

### Purpose

Builds the `priority_evidence_for_30b.items` list by classifying artifact rows into priority categories. Order depends on job completion status.

### Signature

```python
def _priority_evidence(
    self,
    tool_context: dict[str, Any],
    evidence_guide: str,
    completed: bool,
) -> dict[str, Any]:
```

### Classification Flow

```python
# Step 1: Extract artifact rows from tool_context
artifact_rows = [_as_dict(row) for row in _as_list(tool_context.get("artifacts"))]

# Step 2: Build repo_file_full_content items (complete file content)
artifact_items = [
    item for item in (
        _priority_item_from_artifact(row, artifact_index=index)
        for index, row in enumerate(artifact_rows)
    ) if item
]

# Step 3: Build generic tool_result_inline items (non-specialized results)
generic_artifact_items = [
    item for item in (
        _generic_tool_result_priority_item(row, artifact_index=index)
        for index, row in enumerate(artifact_rows)
    ) if item
]

# Step 4: Build partial product items (incomplete candidates)
partial_items = _partial_priority_items(tool_context)

# Step 5: Build coverage gap item (if coverage_satisfied=False)
coverage_item = _coverage_priority_item(tool_context)

# Step 6: Build repo_analysis_summary item (evidence guide + evidence files list)
analysis_item = _analysis_priority_item(tool_context, evidence_guide)

# Step 7: Assemble items list with order depending on completed status
items = []
if coverage_item:
    items.append(coverage_item)  # Coverage always first if present

if completed:
    # Complete job: concrete artifacts first, then partial, then analysis
    items.extend(artifact_items)
    items.extend(generic_artifact_items)
    items.extend(partial_items)
else:
    # Incomplete job: partial first, then concrete artifacts, then generic
    items.extend(partial_items)
    items.extend(artifact_items)
    items.extend(generic_artifact_items)

if analysis_item:
    items.append(analysis_item)  # Analysis summary always last

# Step 8: Clean and return priority structure
return _clean({
    "schema": PRIORITY_SCHEMA,
    "purpose": "...",
    "navigation_hint": "...",
    "items": items,
    "limits": tool_context.get("limits"),
})
```

---

## _priority_item_from_artifact() Helper

### Purpose

Builds a priority item from a single artifact row. Handles two specialized kinds: `repo_file_full_content` and `code_edit_proposal`. Returns empty dict for non-specialized artifacts (those are handled by `_generic_tool_result_priority_item`).

### Signature

```python
def _priority_item_from_artifact(row: dict[str, Any], artifact_index: int) -> dict[str, Any]:
```

### repo_file_full_content Kind

| Condition | Result |
|-----------|--------|
| content is not str or empty | Return {} (skip) |
| truncated=True OR preview_only=True | Return {} (skip - incomplete) |
| All checks pass | Build complete item with content metadata |

**Item Structure:**
```python
{
    "kind": "repo_file_full_content",
    "tool": tool_name,
    "step": producer_step,
    "substep": substep,
    "ok": True/False,
    "path": repo_path,
    "payload_is_complete": True,  # Always true for repo_read items that pass checks
    "chars": len(content),
    "line_count": line_count,
    "sha256": SHA-256 of content string,
    "artifact_index": artifact_index,
    "content_not_duplicated_here": True,
    "primary_payload_location": f"tool_context_for_30b.artifacts[{artifact_index}].artifact.content",
}
```

### code_edit_proposal Kind

| edit_kind | payload_is_complete Condition | primary_payload_location |
|-----------|------------------------------|------------------------|
| `unified_diff` | diff is str and diff.strip() is truthy | `tool_context_for_30b.artifacts[N].artifact.unified_diff` |
| `structured_edit` | structured_operations not in (None, "", [], {}) | `tool_context_for_30b.artifacts[N].artifact.structured_operations` |
| `no_op` | rationale is str and rationale.strip() is truthy | N/A (no location) |
| unknown/empty | False | N/A |

**Item Structure:**
```python
{
    "kind": "code_edit_proposal",
    "tool": tool_name,
    "step": producer_step,
    "substep": substep,
    "ok": True/False,
    "target_file": target_file,
    "edit_kind": edit_kind,
    "payload_is_complete": True/False,  # Depends on edit_kind checks above
    "source_writes_performed": ...,
    "patch_application_performed": ...,
    "manual_review_required": ...,
    "rationale": ...,
    "validation_commands": ...,
    "warnings": ...,
    "errors": ...,
    "target_metadata": ...,
    "ast_evidence": ...,
    "artifact_index": artifact_index,
    "content_not_duplicated_here": True,
    # Optional fields based on edit_kind:
    "chars": len(diff) or len(operations_text),
    "sha256": SHA-256 of diff or operations JSON,
    "structured_operations_count": len(operations),  # Only for structured_edit
    "primary_payload_location": f"tool_context_for_30b.artifacts[{N}].artifact.{field}",
}
```

---

## _generic_tool_result_priority_item() Helper

### Purpose

Builds priority items for non-specialized tool results (everything except repo_read and code_edit_proposal). This includes validation tools, search tools, command execution, etc.

### Signature

```python
def _generic_tool_result_priority_item(row: dict[str, Any], artifact_index: int) -> dict[str, Any]:
```

### Filtering Logic

| Artifact Kind | Result |
|---------------|--------|
| `repo_read` | Return {} (skip - handled by _priority_item_from_artifact) |
| `code_edit_proposal` | Return {} (skip - handled by _priority_item_from_artifact) |
| Other kinds | Build generic item |

**Item Structure:**
```python
{
    "kind": "tool_result_inline",
    "tool": tool_name,
    "step": producer_step,
    "substep": substep,
    "ok": True/False,  # Based on row.ok or artifact.ok
    "payload_is_complete": accepted,  # True if not ok=False
    "validator_accepted": accepted,  # Same as payload_is_complete
    "payload_type": kind or "tool_result",
    "artifact_index": artifact_index,
    "result_keys": sorted(list of all keys in artifact dict)[:40],  # Up to 40 key names
    "summary": artifact.get("summary") or row.get("summary"),
    "error": artifact.get("error"),
    "error_type": artifact.get("error_type"),
    "returncode": artifact.get("returncode"),
}
```

---

## _analysis_priority_item() Helper

### Purpose

Builds a `repo_analysis_summary` item from the evidence guide text and artifacts list. This provides the model with a summary of what evidence was gathered during job execution.

### Signature

```python
def _analysis_priority_item(tool_context: dict[str, Any], planner_text: str) -> dict[str, Any]:
```

### Evidence Files Extraction

```python
# For each artifact row in tool_context.artifacts:
for row in tool_context.get("artifacts"):
    artifact = row.get("artifact") or {}
    kind = artifact.get("kind")  # repo_read, repo_tree, repo_list_files, etc.
    path = artifact.get("repo_path") or row.get("arguments", {}).get("path")
    
    # Only include if kind is one of these OR path exists
    if kind not in {"repo_read", "repo_tree", "repo_list_files"} and not path:
        continue
    
    evidence_files.append({
        "step": producer_step,
        "substep": substep,
        "tool": tool_name,
        "kind": kind or "tool_evidence",
        "path": path,
        "truncated": artifact.get("truncated"),
        "preview_only": artifact.get("preview_only"),
        "reason": "successful_tool_evidence_available_in_tool_context_for_30b",
    })
```

**Item Structure:**
```python
{
    "kind": "repo_analysis_summary",
    "payload_is_complete": bool(planner_text),  # True if evidence_guide text exists
    "guide_chars": len(evidence_guide) if evidence_guide else None,
    "guide_sha256": SHA-256 of evidence_guide if evidence_guide else None,
    "primary_payload_location": "evidence_guide_for_30b",
    "summary_not_duplicated_here": True,
    "content_not_duplicated_here": True,
    "evidence_files": evidence_files[:80],  # Up to 80 evidence file entries
}
```

---

## _partial_priority_items() Helper

### Purpose

Builds priority items from partial products (incomplete code product candidates, action plan candidates, repair candidates). These are marked `validator_accepted=False`.

### Signature

```python
def _partial_priority_items(tool_context: dict[str, Any]) -> list[dict[str, Any]]:
```

### Logic

```python
out = []

# Step 1: Extract all partial_products_for_30b items
for row in tool_context.get("partial_products_for_30b"):
    item = dict(row)  # Copy to avoid mutation
    item.setdefault("payload_is_complete", False)
    item.setdefault("validator_accepted", False)
    out.append(_clean(item))

# Step 2: Add best_partial_product_for_30b at position 0 if not duplicate
best = tool_context.get("best_partial_product_for_30b") or {}
if best:
    best = dict(best)
    best.setdefault("payload_is_complete", False)
    best.setdefault("validator_accepted", False)
    
    # Check for deduplication by JSON serialization
    key = json.dumps(best, ensure_ascii=False, sort_keys=True, default=str)
    existing = {json.dumps(item, ensure_ascii=False, sort_keys=True, default=str) for item in out}
    if key not in existing:
        out.insert(0, _clean(best))  # Insert at beginning

return out
```

---

## _coverage_priority_item() Helper

### Purpose

Builds a `coverage_gap` priority item when minimum_read_coverage.coverage_satisfied is False. This signals that required owner paths are missing and need selective repo_read or search.

### Signature

```python
def _coverage_priority_item(tool_context: dict[str, Any]) -> dict[str, Any]:
```

### Source Resolution

| Priority | Source Field | Fallback |
|----------|-------------|----------|
| 1st | `tool_context.coverage_status` | Direct from tool context |
| 2nd | `tool_context.evidence_contract_at_terminal.minimum_read_coverage` | From terminal evidence contract |
| 3rd | `tool_context.evidence_contract_at_finish.minimum_read_coverage` | From finish evidence contract |
| 4th | Build from contract fields | coverage_satisfied, missing_owner_paths, covered_owner_paths |

**Item Structure (when coverage_satisfied=False):**
```python
{
    "kind": "coverage_gap",
    "payload_type": "coverage_status",
    "payload_is_complete": False,
    "validator_accepted": False,
    "coverage_satisfied": False,
    "required": coverage.get("required"),
    "target_kind": coverage.get("target_kind"),
    "required_count": coverage.get("required_count"),
    "covered_count": coverage.get("covered_count"),
    "missing_owner_paths": coverage.get("missing_owner_paths"),  # List of missing paths
    "covered_owner_paths": coverage.get("covered_owner_paths"),  # List of covered paths
    "candidate_owner_paths": coverage.get("candidate_owner_paths"),  # Candidate paths
    "minimum_read_coverage": coverage or full_contract,
    "role": "gap di copertura: non trattare questo payload come completato; serve una lettura/search selettiva o un block tipizzato",
}
```

**Return:** Empty dict {} when coverage_satisfied=True (no gap to report)

---

## _context_location_resolution() Helper

### Purpose

Resolves the concrete JSON path location for a priority item within tool_context_for_30b.artifacts. This enables the model to navigate from metadata to actual content.

### Signature

```python
def _context_location_resolution(tool_context: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
```

### Resolution Logic

| Item Kind | Matching Condition | Location Pattern |
|-----------|-------------------|------------------|
| `code_edit_proposal` | artifact_kind == "code_edit_proposal" AND target_file matches | `tool_context_for_30b.artifacts[N].artifact.unified_diff` or `.structured_operations` or full artifact |
| `repo_file_full_content` | artifact_kind == "repo_read" AND repo_path matches | `tool_context_for_30b.artifacts[N].artifact.content` |
| No match | - | `tool_context_for_30b.artifacts[*].artifact` (unresolved) |

**Return Structure:**
```python
# When resolved:
{
    "location": f"tool_context_for_30b.artifacts[{index}].artifact.{field}",
    "location_resolved": True,
    "location_resolution_reason": "matched_code_edit_proposal_artifact" or "matched_repo_read_artifact",
    "artifact_index": index,
}

# When unresolved:
{
    "location": "tool_context_for_30b.artifacts[*].artifact",
    "location_resolved": False,
    "location_resolution_reason": "matching_artifact_not_found" or "tool_context_artifacts_empty",
    "artifact_index": item.get("artifact_index"),
    "artifact_count": len(artifacts),
}
```

---

## _payload_index() Method

### Purpose

Builds the `payload_index_for_30b` dictionary with categorized concrete/partial/descriptive results and search order. This is the navigation index for model consumption.

### Signature

```python
def _payload_index(
    self,
    priority_evidence: dict[str, Any],
    tool_context: dict[str, Any],
    completed: bool,
) -> dict[str, Any]:
```

### Categorization Logic

```python
concrete_results = []   # payload_is_complete=True AND validator_accepted=True/None
partial_results = []    # kind starts with "partial_" OR validator_accepted=False
descriptive_only = []     # kind == "repo_analysis_summary" (evidence guide metadata)
suggestions_only = []     # code_edit_proposal review/metadata fields

for index, item in enumerate(priority_evidence.get("items")):
    item = _as_dict(item)
    
    # Build location row for this item
    location = _payload_index_row(item, index, tool_context)
    
    if location:
        # Categorize based on kind and validation status
        if str(location.get("kind") or "").startswith("partial_") or location.get("validator_accepted") is False:
            partial_results.append(location)
        else:
            concrete_results.append(location)
        
        # Track suggestions/review metadata for code_edit_proposal
        if item.get("kind") == "code_edit_proposal":
            base = f"priority_evidence_for_30b.items[{index}]"
            suggestions_only.extend([
                {"field": f"{base}.manual_review_required"},
                {"field": f"{base}.validation_commands"},
            ])
        continue
    
    # Handle repo_analysis_summary (evidence guide)
    if item.get("kind") == "repo_analysis_summary":
        descriptive_only.append({
            "field": "evidence_guide_for_30b",
            "full_context_location": "evidence_guide_for_30b",
        })

# Build code_product_gate diagnostic
code_product_gate = _code_product_gate(priority_evidence, tool_context)

# Build search order for navigation
search_order = _payload_search_order(concrete_results, partial_results, descriptive_only)

return {
    "index_kind": INDEX_KIND,
    "job_completed": completed,
    "same_request_rule": "...",  # Italian instruction about when to call again
    "concrete_results": concrete_results,
    "partial_results": partial_results,
    "descriptive_only": descriptive_only,
    "code_product_gate": code_product_gate,
    "suggestions_or_review_metadata_only": suggestions_only + [
        {"field": "priority_evidence_for_30b.limits"},
        {"field": "openwebui_usage"},
    ],
    "search_order": search_order,
}
```

### Same Request Rule

| Condition | Rule Text |
|-----------|----------|
| has_indexed_payload (any concrete/partial/descriptive) | "Rispondi usando i campi indicizzati qui quando esistono concrete_results, partial_results o descriptive_only. Non richiamo vulkan_helper per la stessa richiesta solo perche' job_completed=false; quello e' uno stato del job interno, non assenza di payload." |
| No indexed payload | "Nessun payload indicizzato disponibile; solo in questo caso una nuova chiamata puo' essere necessaria per la stessa richiesta." |

---

## _payload_index_row() Helper

### Purpose

Builds a payload index row for a single priority item. Determines the primary_location and full_context_location for navigation.

### Signature

```python
def _payload_index_row(item: dict[str, Any], index: int, tool_context: dict[str, Any]) -> dict[str, Any]:
```

### Kind-Based Row Building

| Kind | Payload Type | Primary Location Pattern |
|------|-------------|------------------------|
| `repo_file_full_content` | `file_content` | `tool_context_for_30b.artifacts[N].artifact.content` (resolved via _context_location_resolution) |
| `code_edit_proposal` + unified_diff | `unified_diff` | `tool_context_for_30b.artifacts[N].artifact.unified_diff` |
| `code_edit_proposal` + structured_edit | `structured_operations` | `tool_context_for_30b.artifacts[N].artifact.structured_operations` |
| `partial_code_product_candidate` etc. with unified_diff | `partial_unified_diff` | `priority_evidence_for_30b.items[N].unified_diff` |
| `partial_*` with structured_operations | `partial_structured_operations` | `priority_evidence_for_30b.items[N].structured_operations` |
| `partial_*` with old_text/new_text | `partial_old_text_new_text` | {"old_text": "...", "new_text": "..."} (dict location) |
| `partial_*` with state_text | `partial_code_product_state` | `priority_evidence_for_30b.items[N].state_text` |
| `partial_*` with rationale | `partial_rationale` | `priority_evidence_for_30b.items[N].rationale` |
| `partial_*` with violations | `partial_validation_violations` | `priority_evidence_for_30b.items[N].violations` |
| `partial_*` no field | `partial_metadata` | `priority_evidence_for_30b.items[N]` (full item) |
| `tool_result_inline` | payload_type or "tool_result" | `tool_context_for_30b.artifacts[N].artifact` |
| `coverage_gap` | `coverage_status` | `priority_evidence_for_30b.items[N].missing_owner_paths` |

---

## _code_product_gate() Helper

### Purpose

Builds a diagnostic-only dictionary assessing whether code product editing is feasible based on available evidence. Used by the materialization report but not as a validator decision.

### Signature

```python
def _code_product_gate(priority_evidence: dict[str, Any], tool_context: dict[str, Any]) -> dict[str, Any]:
```

### Diagnostic Checks

| Check | Condition for True | Meaning |
|-------|-------------------|---------|
| `target_file` | Extracted from code_edit_proposal artifacts or priority items | Target file path being edited |
| `target_read` | A repo_read artifact with matching path and non-empty content exists | Target file has been read |
| `repo_propose_code_edit_ok` | At least one proposal row with ok=True/ok not False | Tool call succeeded |
| `complete_payload_inline` | At least one item with payload_is_complete=True | Complete edit payload available |
| `edit_kind` | "unified_diff", "structured_edit", "no_op", or "unknown" | Kind of edit proposed |
| `final_allowed` | finalization_contract.final_allowed=True OR planner_may_choose_final=True | Planner may produce final answer |

**Return Structure:**
```python
{
    "schema": "openwebui_payload_index.code_product_gate.v1",
    "diagnostic_only": True,
    "target_file": target_file,
    "target_read": True/False,
    "repo_propose_code_edit_ok": True/False,
    "complete_payload_inline": True/False,
    "edit_kind": "unified_diff"|"structured_edit"|"no_op"|"unknown",
    "final_allowed": True/False,
    "source": "Derived from tool_context_for_30b artifacts and priority evidence; diagnostic only, not a validator or apply/write decision.",
}
```

---

## _primary_payload_descriptor() Helper

### Purpose

Builds the `primary_payload_for_30b` descriptor - the owner-selected first useful inline payload location. This tells the model where to read first for maximum information gain.

### Signature

```python
def _primary_payload_descriptor(
    priority_evidence: dict[str, Any],
    payload_index: dict[str, Any],
) -> dict[str, Any]:
```

### Selection Logic

```python
# Step 1: Check concrete_results and partial_results sections in order
for section in ("concrete_results", "partial_results"):
    for row in payload_index.get(section):
        row = _as_dict(row)
        if not row:
            continue
        
        # Extract item index from location string (e.g., "priority_evidence_for_30b.items[5]")
        location = row.get("primary_location") or row.get("field")
        item_index = _item_index_from_location(location)
        
        # Get corresponding priority item
        item = priority_items[item_index] if valid index else {}
        if not item:
            item = {"kind": ..., "tool": ..., ...}  # Build minimal item from row fields
        
        # Build and return primary descriptor
        return _primary_descriptor_from_row(row, item, item_index, section)

# Step 2: If no concrete/partial results, check for repo_analysis_summary
for index, item in enumerate(priority_items):
    if item.get("kind") != "repo_analysis_summary":
        continue
    return _primary_descriptor_from_row(
        row={
            "kind": "repo_analysis_summary",
            "payload_type": "repo_analysis_summary",
            "primary_location": "evidence_guide_for_30b",
            "full_context_location": "evidence_guide_for_30b",
            "payload_is_complete": item.get("payload_is_complete"),
            "validator_accepted": True,
        },
        item=item,
        item_index=index,
        section="descriptive_only",
    )

# Step 3: No primary payload found
return {}
```

### Primary Descriptor Structure

```python
{
    "schema": PRIMARY_SCHEMA,
    "owner": owner,  # e.g., "application.evidence", "application.code_product"
    "request_type": request_type,  # e.g., "repo_analysis", "code_product"
    "payload_kind": payload_kind,  # kind field from item/row
    "kind": item.get("kind") or row.get("kind"),
    "tool": item.get("tool") or row.get("tool"),
    "step": item.get("step") or row.get("step"),
    "substep": item.get("substep") or row.get("substep"),
    "path": item.get("path") or row.get("path"),
    "target_file": item.get("target_file") or row.get("target_file"),
    "item_index": item_index,
    "source_index_section": section,  # "concrete_results", "partial_results", etc.
    "primary_location": primary_location,  # Resolved JSON path
    "full_context_location": full_context_location,  # Full context path
    "payload_is_complete": payload_is_complete,
    "validator_accepted": validator_accepted,
    "read_before_payload_index": True,  # Always true for primary descriptors
    "content_not_duplicated_here": True,  # Never duplicates content
    "reason": "This is the owner-selected first useful inline payload location. Read the referenced field in this same JSON payload; this descriptor does not copy the content.",
}
```

---

## _owner_for_priority_item() Helper

### Purpose

Determines the owner module and request type for a priority item based on its kind field. This categorizes items by responsibility domain.

### Classification Table

| Kind | Owner Module | Request Type |
|------|-------------|--------------|
| `repo_file_full_content`, `repo_analysis_summary` | `application.evidence` | `repo_analysis` |
| `code_edit_proposal`, `partial_code_product_*` | `application.code_product` | `code_product` |
| `partial_*` (generic) | `application.public_payload` | `partial_terminal_payload` |
| `coverage_gap` | `application.evidence` | `minimum_read_coverage` |
| `tool_result_inline` | `application.tool_surface` | `tool_result` |
| Any kind with tool == "repo_apply_patch" | `application.patch_apply` | `apply_patch` |
| Default fallback | `application.public_payload` | `generic_payload` |

---

## _materialization_report() Helper

### Purpose

Builds a diagnostic-only report verifying the materialization process. Used by operators to confirm payload integrity and resolution status.

### Signature

```python
def _materialization_report(
    self,
    tool_context: dict[str, Any],
    priority_evidence: dict[str, Any],
    payload_index: dict[str, Any],
    evidence_guide: str,
) -> dict[str, Any]:
```

### Report Structure

```python
{
    "schema": MATERIALIZATION_SCHEMA,
    "owner": "3572_broker",
    "target_owner": "3572_broker",
    "ok": True/False,  # Resolution ok AND (tool_context exists AND (concrete_items or partial_results))
    "diagnostic_only": True,
    "inline_json_required": True,  # Content must be inline in JSON, not external files
    "objects_are_not_transport": True,  # These are objects, not transport wrappers
    "bridge_role": "transport_wrapper_and_final_lint_only",
    
    # Tool context verification
    "tool_context": {
        "json_object": bool(tool_context),
        "artifact_rows": len(artifacts),
        "public_scope": "tool_context_for_30b.artifacts[*].artifact",
        "not_full_job_dump": bool(tool_context.get("not_a_summary")),
    },
    
    # Priority evidence verification
    "priority_evidence": {
        "items": len(priority_items),
        "concrete_items": len(concrete_items),  # Items with payload_is_complete not False
        "has_evidence_guide": bool(evidence_guide.strip()),
    },
    
    # Artifact resolution verification
    "artifacts": {
        "refs_seen": len(artifacts),
        "refs_resolved": len(artifacts),  # All artifacts are resolved
        "materialized": len(concrete_items),  # Number of concrete items materialized
        "unresolved_refs": [],  # Empty - all refs resolved
    },
    
    # Payload index verification (via resolve_payload_index)
    "payload_index": {
        "ok": bool(resolution.ok),
        "resolved_count": len(resolution.resolved or []),
        "unresolved": resolution.unresolved or [],
        "empty_targets": resolution.empty_targets or [],
    },
    
    # Local path policy
    "local_paths": {
        "omitted_from_public_payload": True,
        "operator_diagnostics_only": True,
    },
}
```

---

## Helper Utility Functions

### _as_dict() / _as_list() / _clean()

| Function | Purpose | Behavior |
|----------|---------|----------|
| `_as_dict(value)` | Convert to dict | If str, try json.loads; else return {} if not dict |
| `_as_list(value)` | Convert to list | Return value if list, else [] |
| `_clean(value)` | Remove empty values | Recursively strip None/""//[]/{}/values from dicts/lists |

### _iter_location_strings() / _item_index_from_location()

| Function | Purpose | Behavior |
|----------|---------|----------|
| `_iter_location_strings(value)` | Yield all location strings | Recursive traversal of dict/list to find string values |
| `_item_index_from_location(value)` | Extract index from location string | Regex match on `priority_evidence_for_30b.items[\d+]` pattern |

### _first_location_value() / _append_unique()

| Function | Purpose | Behavior |
|----------|---------|----------|
| `_first_location_value(row)` | Get first non-empty location | Check primary_location, field, full_context_location in order |
| `_append_unique(values, value)` | Append if not duplicate | Strip whitespace, check membership, append if unique |

### _payload_search_order()

Builds ordered list of JSON path locations for model navigation:

```python
order = []
_append_unique(order, "evidence_guide_for_30b")  # Always first
_append_unique(order, "primary_payload_for_30b.primary_location")  # Always second

if concrete_results:
    _append_unique(order, "payload_index_for_30b.concrete_results")
    for row in concrete_results:
        _append_unique(order, _first_location_value(row))

if partial_results:
    _append_unique(order, "payload_index_for_30b.partial_results")
    for row in partial_results:
        _append_unique(order, _first_location_value(row))

for row in descriptive_only:
    _append_unique(order, _first_location_value(row))

if not concrete_results and not partial_results:
    _append_unique(order, "tool_context_for_30b.artifacts[*].artifact")  # Fallback

return order
```

---

## materialize_public_evidence() Compatibility Function

### Signature

```python
def materialize_public_evidence(
    tool_context: dict[str, Any] | str | None,
    evidence_guide: str = "",
    completed: bool = False,
    internal_job_status: dict[str, Any] | None = None,
) -> dict[str, Any]:
```

**Purpose:** Wrapper that instantiates `PublicEvidenceMaterializer` and calls `materialize()`. Provides backward compatibility for existing broker code that expects a function rather than class method.

---

## Quick Reference: Materialization Flow Diagram

```
materialize(tool_context, evidence_guide, completed, internal_job_status)
│
├── Step 1: Determine effective_completed status
│   ├── coverage_missing = bool(_coverage_priority_item(context))
│   └── effective_completed = completed AND NOT coverage_missing
│
├── Step 2: Build priority_evidence_for_30b
│   ├── Classify artifact rows into repo_file_full_content / generic_tool_result_inline
│   ├── Extract partial_products_for_30b items (marked validator_accepted=False)
│   ├── Check for coverage_gap item (if coverage_satisfied=False)
│   ├── Build repo_analysis_summary from evidence_guide + artifacts list
│   └── Assemble items list with order depending on effective_completed status
│
├── Step 3: Build payload_index_for_30b
│   ├── For each priority item, build _payload_index_row() with location resolution
│   ├── Categorize into concrete_results / partial_results / descriptive_only
│   ├── Build code_product_gate diagnostic
│   ├── Build suggestions_or_review_metadata_only for code_edit_proposal items
│   └── Build search_order navigation sequence
│
├── Step 4: Build primary_payload_for_30b
│   ├── Check concrete_results and partial_results sections in order
│   ├── Extract item index from location string via regex
│   ├── Get corresponding priority item by index
│   └── Build _primary_descriptor_from_row() with owner/request_type classification
│
├── Step 5: Build materialization_report
│   ├── Run resolve_payload_index() on payload structure for verification
│   ├── Count concrete_items, artifact_refs_seen, artifact_refs_resolved
│   └── Return diagnostic-only report with ok status and resolution details
│
└── Step 6: Return four-field dictionary
    ├── primary_payload_for_30b: First useful inline payload location
    ├── payload_index_for_30b: Indexed concrete/partial/descriptive results + search order
    ├── priority_evidence_for_30b: High-priority metadata items list
    └── materialization_report: Diagnostic verification report
```

---

## Related Documentation Files

| File | Purpose |
|------|---------|
| `EVIDENCE_CONTRACT_REFERENCE.md` | Complete reference for evidence_contract dictionary fields |
| `TERMINAL_PAYLOAD_SPECIFICATION.md` | Terminal payload structure, field ordering, materialization flow |
| `PAYLOAD_MATERIALIZATION_CONTRACT.md` | Contract between evidence_materializer, payload_index_resolver, and terminal_sanitizer |
| `TOOL_SURFACE_POLICY.md` | Per-turn tool surface determination logic based on evidence contract state |
| `VALIDATION_REJECTIONS.md` | Validation rejection signature tracking, deduplication, and compaction |
| `FINAL_QUALITY_JUDGMENT.md` | Deterministic quality checks, model judge request building, response sanitization |
| `PLANNER_TURN_MEMORY_REFERENCE.md` | Turn memory construction from history, Ollama turn metadata extraction |
| `EVIDENCE_MATERIALIZER_DEEP_DIVE.md` (this file) | Deep-dive into PublicEvidenceMaterializer class, materialize() flow, all helper functions for three-tier payload construction |