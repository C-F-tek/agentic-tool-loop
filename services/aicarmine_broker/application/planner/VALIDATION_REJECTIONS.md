# Validation Rejections Reference

**Created:** 2026-08-15  
**Purpose:** Complete reference for `validation_rejections.py` module. This handles tracking, signature generation, deduplication, and compaction of invalid code-product decisions rejected by the validator during planner turns. It prevents the planner from repeating identical invalid proposals.

---

## Overview: Invalid Decision Signature Tracking

The validation rejections system tracks rejected `repo_propose_code_edit` tool calls that failed validator checks. Each rejection is assigned a canonical signature based on its arguments, enabling detection of repeated violations. The system compacting these signatures into a tail history stored in the evidence contract's `validation_rejections_tail` field.

Two key functions:
| Function | Purpose | Returns |
|----------|---------|---------|
| `canonical_invalid_code_product_decision_signature()` | Build canonical signature for invalid proposal | Dict with args_sha256, payload_class, target_file |
| `compact_validation_rejections_tail()` | Compact rejection history to limit items | List of compacted rejection records |

---

## canonical_invalid_code_product_decision_signature()

### Purpose

Builds a deterministic SHA-256 signature for an invalid `repo_propose_code_edit` decision. This signature identifies repeated violations so the planner knows not to repeat them.

### Violation Classification (payload_class)

| Violation Set Member | payload_class | Meaning |
|---------------------|---------------|---------|
| `repo_propose_code_edit_placeholder_text` | `placeholder_old_new` | old_text/new_text contains copyable example text (not real source) |
| `repo_propose_code_edit_missing_unified_diff` | `missing_diff` | No unified_diff provided |
| `repo_propose_code_edit_old_text_not_from_verified_read` | `old_text_not_verified` | old_text does not match any verified read content |
| `repo_propose_code_edit_missing_structured_operations` | `missing_structured_operations` | Missing structured_operations for structured_edit kind |
| `invalid_code_product_candidate` or `repo_propose_code_edit_unified_diff_error:*` | `invalid_unified_diff` | Unified diff validation failed |
| copyable_example_text(old_value) or copyable_example_text(new_value) | `placeholder_old_new` | Placeholder text detected in arguments |
| not isinstance(diff_text, str) or not diff_text.strip() | `missing_diff` | Empty or missing unified_diff |

### Signature Structure

```python
signature = {
    "tool": "repo_propose_code_edit",
    "target_file": repo_rel_token(args.get("target_file") or args.get("path")),
    "edit_kind": edit_kind ("unified_diff" or "structured_edit"),
    "payload_class": payload_class (see table above),
    "args_sha256": SHA-256 of normalized_args dict,
    # Optional diagnostics:
    "signature_diagnostics": {
        "schema": "invalid_decision_signature_diagnostics.v1",
        "structured_operations": {...},  # Serialization error details
        "normalized_args": {...},  # Normalization error details
    },
}

# normalized_args contains:
{
    "target_file": target_path,
    "edit_kind": edit_kind,
    "payload_class": payload_class,
    "old_text": prompt_clip_text(args.get("old_text"), 500),
    "new_text": prompt_clip_text(args.get("new_text"), 500),
    "unified_diff_sha256": SHA-256 of unified_diff string or "",
    "structured_operations_sha256": SHA-256 of structured_operations JSON or "",
    "rationale": prompt_clip_text(args.get("rationale"), 500),
}
```

### Key Properties

| Property | Description |
|----------|-------------|
| Deterministic | Same arguments always produce same signature (sort_keys=True, ensure_ascii=False) |
| Bounded | old_text/new_text/rationale clipped to 500 chars |
| Hash-based | unified_diff and structured_operations stored as SHA-256 only |
| Diagnostic-aware | Serialization errors captured in signature_diagnostics |

---

## invalid_code_product_decision_signature_from_history_item()

### Purpose

Extracts the invalid decision signature from a history item (planner turn record). This enables scanning through job history to find repeated violations.

### Extraction Logic

```python
# From tool_result:
result = item.get("tool_result") or {}
existing_sig = result.get("invalid_decision_signature")
if existing_sig:
    return existing_sig

# From rejected_decision + violations:
violations = result.get("violations") or []
rejected = item.get("decision") if item.get("decision", {}).get("action") == "tool" else result.get("rejected_decision")
return canonical_invalid_code_product_decision_signature(rejected, violations)
```

**Where:** `validation_rejections.py::invalid_code_product_decision_signature_from_history_item()` → lines 109-122

---

## invalid_decision_signature_key()

### Purpose

Converts a signature dict to a JSON string for comparison/deduplication. This key is used to identify duplicate signatures across history items.

```python
def invalid_decision_signature_key(signature):
    return json.dumps(signature, ensure_ascii=False, sort_keys=True, default=str)
```

**Where:** `validation_rejections.py::invalid_decision_signature_key()` → lines 103-106

---

## invalid_code_product_decision_signature_count()

### Purpose

Counts how many times a specific invalid signature appears in job history. This enables detection of repeated violations.

```python
def invalid_code_product_decision_signature_count(history, signature):
    key = invalid_decision_signature_key(signature)
    count = 0
    for item in history:
        item_key = invalid_decision_signature_key(
            invalid_code_product_decision_signature_from_history_item(item)
        )
        if item_key == key:
            count += 1
    return count
```

**Where:** `validation_rejections.py::invalid_code_product_decision_signature_count()` → lines 125-139

---

## disallowed_invalid_code_product_signatures()

### Purpose

Identifies signatures that have been repeated >= 2 times across validation rejections. These are "disallowed" because the planner must not repeat them again.

```python
def disallowed_invalid_code_product_signatures(validation_rejections):
    counts = {}
    for row in validation_rejections:
        sig = row.get("invalid_decision_signature") or canonical_invalid_code_product_decision_signature(...)
        key = invalid_decision_signature_key(sig)
        if key not in counts:
            counts[key] = {"signature": sig, "count": 0}
        counts[key]["count"] += 1
    
    out = []
    for item in counts.values():
        if int(item.get("count")) >= 2:
            out.append({
                **item["signature"],
                "repeat_count": int(item.get("count")),
                "rule": "do_not_repeat_invalid_code_product_decision",
            })
    return out
```

**Where:** `validation_rejections.py::disallowed_invalid_code_product_signatures()` → lines 142-168

### Usage

This function is called by the validator to determine if a new proposal repeats a previously rejected pattern. If the signature appears >= 2 times, it's added to the disallowed list with `"rule": "do_not_repeat_invalid_code_product_decision"`.

---

## compact_validation_rejections_tail()

### Purpose

Compacts validation rejection history into a limited tail (default: last 5 items) for storage in the evidence contract. This provides recent rejection context without overwhelming the prompt budget.

### Compaction Logic

```python
def compact_validation_rejections_tail(validation_rejections, limit=5):
    compacted = []
    index_by_signature = {}
    
    for item in validation_rejections:
        rejected = item.get("rejected_decision") or {}
        args = rejected.get("arguments") or {}
        
        # Compact arguments to key fields only
        compact_args = {
            k: v[:700] + "...[truncated]" if len(v) > 700 else v
            for k, v in args.items()
            if k in ("target_file", "path", "edit_kind", "old_text", "new_text", 
                     "unified_diff", "structured_operations", "rationale")
            and isinstance(v, str)
        }
        
        row = {
            "step": item.get("step"),
            "guard_type": item.get("guard_type"),
            "summary": item.get("summary"),
            "classification": item.get("classification"),
            "semantic_goal_classification": item.get("semantic_goal_classification"),
            "next_instruction": item.get("next_instruction"),
            "required_next_tool_call": item.get("required_next_tool_call") or {},
            "action_plan_candidate": prompt_clip_text(item.get("action_plan_candidate"), 4000),
            "raw_planner_text_preview": str(item.get("raw_planner_text_preview"))[:700],
            "violations": item.get("violations") or [],
            "rejected_decision": compact_args,
            "invalid_decision_signature": canonical_invalid_code_product_decision_signature(...),
            "repeat_count": 1,
        }
        
        # Deduplicate by signature
        signature = json.dumps({...}, sort_keys=True, default=str)
        existing = index_by_signature.get(signature)
        if existing is not None:
            compacted[existing]["repeat_count"] += 1
            compacted[existing]["last_step"] = row.get("step")
            continue
        
        index_by_signature[signature] = len(compacted)
        compacted.append(row)
    
    return compacted[-limit:]  # Return last N items
```

**Where:** `validation_rejections.py::compact_validation_rejections_tail()` → lines 171-253

### Compact Rejection Record Structure

| Field | Type | Purpose |
|-------|------|---------|
| `step` | int | Producer step number |
| `guard_type` | str | Guard type that rejected the decision |
| `summary` | str | Human-readable rejection summary |
| `classification` | str | Semantic classification of rejection |
| `semantic_goal_classification` | dict | Goal classification at time of rejection |
| `next_instruction` | str | Next instruction given to planner |
| `required_next_tool_call` | dict | Required tool call if applicable |
| `action_plan_candidate` | str | Action plan at time of rejection (clipped to 4000 chars) |
| `raw_planner_text_preview` | str | Raw planner text preview (clipped to 700 chars) |
| `violations` | list[str] | List of violation strings that caused rejection |
| `rejected_decision` | dict | Compact arguments of rejected proposal |
| `invalid_decision_signature` | dict | Canonical signature for deduplication |
| `repeat_count` | int | How many times this signature has appeared |

---

## Validation Rejection Flow in Planner Decision Logic

### Step 1: Validator Detects Violation

When the validator processes a `repo_propose_code_edit` tool call, it checks for violations like:
- Placeholder text in old_text/new_text
- Missing unified_diff or structured_operations
- old_text not matching any verified read content
- Invalid unified diff structure

If violations are found, the decision is rejected and added to validation_rejections list.

**Where:** `planner/validator.py` → validation logic

### Step 2: Build Invalid Decision Signature

The system builds a canonical signature for the rejected proposal using `canonical_invalid_code_product_decision_signature()`. This signature captures:
- Target file path (relative token)
- Edit kind (unified_diff or structured_edit)
- Payload class (violation type)
- SHA-256 hashes of bounded arguments

### Step 3: Count Repeated Signatures in History

The system scans job history to count how many times this signature has appeared before using `invalid_code_product_decision_signature_count()`.

**Where:** `validation_rejections.py::invalid_code_product_decision_signature_count()` → lines 125-139

### Step 4: Identify Disallowed Signatures

Signatures appearing >= 2 times are marked as disallowed with `"rule": "do_not_repeat_invalid_code_product_decision"`. This tells the planner not to repeat these patterns.

**Where:** `validation_rejections.py::disallowed_invalid_code_product_signatures()` → lines 142-168

### Step 5: Compact Rejection Tail for Evidence Contract

The last N (default 5) rejection records are compacted and stored in `evidence_contract.validation_rejections_tail`. This provides recent context without overwhelming prompt budget.

**Where:** `validation_rejections.py::compact_validation_rejections_tail()` → lines 171-253

### Step 6: Planner Decision Uses Rejection Context

When building candidate next actions, the planner checks disallowed signatures against new proposals. If a proposal matches a disallowed signature, it's rejected and the planner must choose a different action.

**Where:** `planner/validator.py` → decision validation logic

---

## Validation Rejection Diagnostic Schema

```python
{
    "schema": "invalid_decision_signature_diagnostics.v1",
    "structured_operations": {
        "serialization_error_type": "TypeError" or "ValueError" or "RecursionError",
        "serialization_fallback": "repr_clip",
        "serialization_fallback_chars": 2000,
    },
    "normalized_args": {
        "serialization_error_type": ...,
        "serialization_fallback": ...,
        "serialization_fallback_chars": ...,
    },
}
```

**Purpose:** Captures serialization errors when building signatures. Used for debugging malformed proposals.

---

## Quick Reference: Validation Rejection Flow Diagram

```
validator detects violation in repo_propose_code_edit proposal
│
├── Step 1: Build canonical signature
│   ├── Extract target_file, edit_kind, violations from proposal
│   ├── Classify payload_class (placeholder_old_new, missing_diff, etc.)
│   ├── Compute SHA-256 of bounded arguments (old_text, new_text, unified_diff)
│   └── Return signature dict with args_sha256 field
│
├── Step 2: Count repeats in history
│   ├── For each history item, extract invalid_decision_signature
│   ├── Compare JSON keys to detect duplicates
│   └── Return count for this signature across all steps
│
├── Step 3: Identify disallowed signatures
│   ├── Build counts dict mapping signature_key → {signature, count}
│   ├── Filter to signatures with count >= 2
│   └── Add "rule": "do_not_repeat_invalid_code_product_decision" marker
│
├── Step 4: Compact rejection tail
│   ├── For each rejection record, compact arguments to key fields only
│   ├── Clip strings to bounded lengths (700 chars for args, 4000 for action_plan)
│   ├── Deduplicate by signature JSON key
│   └── Return last N items (default limit=5)
│
└── Step 5: Store in evidence contract
    ├── validation_rejections_tail = compacted list
    ├── Planner reads this when building candidate_next_actions
    ├── Disallowed signatures prevent repeating invalid proposals
    └── repeat_count field tracks how many times each violation occurred
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
| `PAYLOAD_MATERIALIZATION_CONTRACT.md` | Contract between evidence_materializer, payload_index_resolver, and terminal_sanitizer |
| `TOOL_SURFACE_POLICY.md` | Per-turn tool surface determination logic based on evidence contract state |
| `VALIDATION_REJECTIONS.md` (this file) | Validation rejection signature tracking, deduplication, and compaction for invalid code-product proposals |