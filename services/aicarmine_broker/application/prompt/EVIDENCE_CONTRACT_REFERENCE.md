# Evidence Contract Reference

**Created:** 2026-08-15  
**Purpose:** Complete reference for the `evidence_contract` dictionary used throughout the IA broker system. This contract is built by `planner_evidence_contract()` in `application/evidence/builder.py`, compacted by `compact_evidence_contract_for_prompt()` in `application/prompt/evidence_contract.py`, and consumed by planner turns, tool surface policy, validation rejections, and controller guards.

---

## Overview: What Is the Evidence Contract?

The evidence contract is a structured dictionary that captures the planner's understanding of the current job state, what has been verified, what needs to happen next, and whether finalization is allowed. It flows through:

1. **Build phase** (`builder.py::planner_evidence_contract()`) - Built from goal, history, artifacts
2. **Compact phase** (`evidence_contract.py::compact_evidence_contract_for_prompt()`) - Trimmed for prompt budget
3. **Hard-budget phase** (`evidence_contract.py::hard_budget_evidence_contract_summary()`) - Minimal version when context is tight
4. **Windowed storage** (`context_windows.py`) - Stored in SQLite scratchpad with document_id/offset/max_chars
5. **Consumption phase** - Read by planner decision logic, tool surface policy, validation rejections

---

## Evidence Contract Field Taxonomy

### 1. Goal Classification Fields

| Field | Type | Purpose | Where Built |
|-------|------|---------|-------------|
| `semantic_goal_classification` | dict | Intent classification (analysis/code-product/apply/input-envelope) | builder.py |
| `goal_requests_code_product` | bool | Whether goal requires code product output | builder.py |
| `goal_requires_code_product_report` | bool | Whether goal requires report-style output | builder.py |
| `goal_requests_apply` | bool | Whether goal requires applying changes | builder.py |
| `target_kind` | str | Kind of target file/directory | builder.py |
| `resolved_goal_file` | str | Resolved file path for goal | builder.py |
| `resolved_goal_scope` | str | Scope of the goal (repo/project/session) | builder.py |

**Where:** `services/aicarmine_broker/application/evidence/goal_classifier.py` → classification logic

### 2. Action Plan Fields

| Field | Type | Purpose | Where Built |
|-------|------|---------|-------------|
| `action_plan_candidate` | dict | Candidate action plan from planner | builder.py |
| `candidate_next_actions` | list[dict] | Next actionable steps the planner may choose | builder.py, turn_surface_policy.py |
| `required_next_tool_call` | dict | Mandatory next tool call if not yet satisfied | candidate_action_gate.py |
| `required_next_progress` | str | Progress description for required next step | evidence_contract.py |
| `forbidden_repeated_tool_calls` | list[str] | Tools that must not be repeated identically | candidate_action_gate.py |
| `forbidden_repeated_repo_read_paths` | list[str] | Paths that must not be re-read identically | evidence_contract.py |

**Where:** `services/aicarmine_broker/application/tool_surface/candidate_action_gate.py`, `candidate_actions.py` → gating logic

### 3. Repository Evidence Fields

| Field | Type | Purpose | Where Built |
|-------|------|---------|-------------|
| `successful_repo_read_paths` | list[str] | Paths successfully read via repo_read | builder.py |
| `successful_repo_read_count` | int | Count of successful reads | builder.py |
| `verified_content_reads` | list[dict] | Detailed verified content read records | builder.py, evidence_contract.py |
| `verified_content_read_count` | int | Count of verified content reads | builder.py |
| `failed_repo_read_paths` | list[str] | Paths that failed to read | builder.py |
| `failed_repo_list_files_paths` | list[str] | Paths that failed in repo_list_files | builder.py |
| `read_admissible_paths` | list[str] | Paths admissible for reading | builder.py |
| `validator_admissible_repo_read_paths` | list[str] | Paths admissible per validator | builder.py |

**Where:** `services/aicarmine_broker/application/evidence/builder.py` → evidence building logic

### 4. Coverage Fields

| Field | Type | Purpose | Where Built |
|-------|------|---------|-------------|
| `minimum_read_coverage` | dict | Minimum coverage requirements | builder.py |
| `coverage_satisfied` | bool | Whether coverage requirements are met | builder.py |
| `covered_owner_paths` | list[str] | Owner paths covered by reads | builder.py |
| `missing_owner_paths` | list[str] | Owner paths not yet covered | builder.py |
| `candidate_owner_paths` | list[str] | Candidate owner paths for coverage | builder.py |

**Where:** `services/aicarmine_broker/application/evidence/required_working_set.py` → coverage logic

### 5. Core Discovery Fields

| Field | Type | Purpose | Where Built |
|-------|------|---------|-------------|
| `core_discovery_status` | dict | Status of core area discovery | builder.py |
| `core_discovery_candidates` | list[dict] | Candidate files/dirs in core areas | builder.py |

**Where:** `services/aicarmine_broker/application/evidence/core_discovery.py` → discovery logic

### 6. Initial Orientation Fields

| Field | Type | Purpose | Where Built |
|-------|------|---------|-------------|
| `initial_orientation_surface` | dict | Initial orientation from RAG/preseed/memory | builder.py |

**Where:** `services/aicarmine_broker/application/evidence/initial_orientation.py` → orientation building

### 7. Finalization Contract Fields

| Field | Type | Purpose | Where Built |
|-------|------|---------|-------------|
| `finalization_contract.final_allowed` | bool | Whether finalization is permitted | validator.py, turn.py |
| `finalization_contract.planner_may_choose_final` | bool | Whether planner may choose final action | validator.py |
| `finalization_contract.planner_may_choose_block` | bool | Whether planner may choose block action | validator.py |
| `finalization_contract.coverage_satisfied` | bool | Coverage satisfied for finalization | validator.py |
| `finalization_contract.missing_owner_paths` | list[str] | Missing paths blocking finalization | validator.py |
| `finalization_contract.reason` | str | Reason for finalization decision | validator.py |

**Where:** `services/aicarmine_broker/application/planner/validator.py` → validation logic

### 8. Code Product Contract Fields

| Field | Type | Purpose | Where Built |
|-------|------|---------|-------------|
| `code_product_contract.required` | bool | Whether code product is required | builder.py |
| `code_product_contract.required_tool` | str | Required tool for code product (repo_propose_code_edit) | builder.py |
| `code_product_contract.successful_proposal_count` | int | Count of successful proposals | builder.py |
| `code_product_contract.latest_target_file` | str | Latest target file path | builder.py |
| `code_product_contract.candidate_target_file` | str | Candidate target file path | builder.py |
| `code_product_contract.candidate_target_line_count` | int | Line count of candidate target | builder.py |
| `code_product_contract.action_plan_candidate_available` | bool | Whether action plan is available | builder.py |
| `code_product_contract.latest_payload_complete` | bool | Whether latest payload is complete | builder.py |
| `code_product_contract.latest_violations` | list[str] | Violations in code product contract | builder.py |
| `code_product_contract.build_state_status` | str | Build state status | code_product/state.py |
| `code_product_contract.inline_payload_required` | bool | Whether inline payload is required | public_outputs.py |
| `code_product_contract.artifact_path_is_not_payload` | bool | Artifact path ≠ actual payload marker | code_edit_proposal_contract.py |

**Where:** `services/aicarmine_broker/application/code_product/state.py`, `public_outputs.py` → code product logic

### 9. Operational Notes Fields

| Field | Type | Purpose | Where Built |
|-------|------|---------|-------------|
| `operational_notes.final_allowed` | bool | Final allowed from operational context | planner.py |
| `operational_notes.next_instruction` | str | Next instruction for operator/model | planner.py |
| `operational_notes.candidate_next_actions` | list[dict] | Candidate actions from operational notes | planner.py |

**Where:** `services/aicarmine_broker/planner.py` → planner decision logic

### 10. Micro Batch Contract Fields

| Field | Type | Purpose | Where Built |
|-------|------|---------|-------------|
| `micro_batch_contract.schema` | str | Schema identifier (micro_batch_contract.v1) | builder.py |
| `micro_batch_contract.allowed` | bool | Whether micro batch is allowed | builder.py |
| `micro_batch_contract.mode` | str | Mode of micro batch operation | builder.py |
| `micro_batch_contract.max_batch_size` | int | Maximum batch size | builder.py |
| `micro_batch_contract.allowed_tools` | list[str] | Tools allowed in micro batch | builder.py |
| `micro_batch_contract.reason` | str | Reason for micro batch decision | builder.py |
| `micro_batch_contract.allowed_batch_actions` | list[dict] | Batch actions with action_id, tool, arguments | builder.py |

**Where:** `services/aicarmine_broker/application/evidence/builder.py` → micro batch logic

### 11. Validation Rejection Fields

| Field | Type | Purpose | Where Built |
|-------|------|---------|-------------|
| `validation_rejections_tail` | list[dict] | Recent validation rejection records | validator.py, validation_rejections.py |

**Where:** `services/aicarmine_broker/application/planner/validation_rejections.py` → rejection tracking

### 12. File Memory Fields

| Field | Type | Purpose | Where Used |
|-------|------|---------|-------------|
| `file_memory[].path` | str | Path in file memory | evidence_contract.py compacted |
| `file_memory[].line_count` | int | Line count of file | evidence_contract.py compacted |
| `file_memory[].truncated` | bool | Whether file content was truncated | evidence_contract.py compacted |
| `file_memory[].key_lines` | list[str] | Key lines extracted from file | evidence_contract.py compacted |
| `file_memory[].content_excerpt` | str | Content excerpt from file | evidence_contract.py compacted |

**Where:** `services/aicarmine_broker/application/prompt/evidence_contract.py` → compaction logic

---

## Evidence Contract Compaction Flow

### Step 1: Build Full Contract
```python
# builder.py::planner_evidence_contract()
contract = {
    "semantic_goal_classification": {...},
    "goal_requests_code_product": True,
    "target_kind": "analysis",
    "successful_repo_read_paths": ["/path/to/file.py"],
    "verified_content_reads": [...],
    "candidate_next_actions": [...],
    "finalization_contract": {"final_allowed": False, ...},
    "code_product_contract": {...},
    "validation_rejections_tail": [...],
    # ... all fields from taxonomy above
}
```

### Step 2: Compact for Prompt Preview
```python
# evidence_contract.py::compact_evidence_contract_for_prompt()
compact = {
    key: contract.get(key)
    for key in EVIDENCE_PROMPT_KEEP_KEYS  # 40+ field names defined at line 9-43
}
# Applied transformations:
# - verified_content_reads → _compact_verified_content_reads(item_limit=8)
# - Path lists → _apply_counted_top_list(item_limit=24, text_limit=180)
# - candidate_next_actions → _apply_counted_top_list(item_limit=8, text_limit=320)
# - initial_orientation_surface → prompt_clip_value(text_limit=360, list_limit=6)
# - file_memory → truncated to 6 items with key_lines/content_excerpt
# - operational_notes → clipped next_instruction (500 chars), candidate_next_actions (6 items)
# - micro_batch_contract → compacted schema fields + allowed_batch_actions
```

**Where:** `services/aicarmine_broker/application/prompt/evidence_contract.py` → lines 120-214

### Step 3: Hard Budget Summary
```python
# evidence_contract.py::hard_budget_evidence_contract_summary()
compact = {
    "schema": "planner_evidence_contract_hard_budget.v1",
    "windowed_due_to_prompt_budget": True,
    "full_contract_available_from_sqlite_window": True,
    "hard_budget_reason": "context_window_exceeded",
    # Only most critical fields kept:
    "semantic_goal_classification": ...,
    "target_kind": ...,
    "finalization_contract": {...},
    "code_product_contract": {...},
    "candidate_next_actions": [...],  # text_limit=700, list_limit=3
}
```

**Where:** `services/aicarmine_broker/application/prompt/evidence_contract.py` → lines 240-344

### Step 4: Windowed Storage (SQLite Scratchpad)
```python
# context_windows.py::store_prompt_value_window()
window = {
    "document_id": str(db_path),
    "section": "evidence_contract",
    "offset": 0,
    "max_chars": window_chars,
    "value": compact_contract_json,
    "has_more_after": True/False,
    "metadata": {"kind": "evidence_contract", "format": "json"},
}
# Stored in planner_scratchpad SQLite table for later retrieval
```

**Where:** `services/aicarmine_broker/application/prompt/context_windows.py` → window storage logic

---

## Evidence Contract Consumption Points

### Planner Decision Logic (`planner.py`)
```python
# Lines where evidence contract is consumed:
contract = validation.get("evidence_contract") if isinstance(validation.get("evidence_contract"), dict) else {}
finalization_allowed = bool(contract.get("finalization_contract", {}).get("final_allowed"))
planner_may_choose_final = contract.get("planner_may_choose_final") is True
candidates = contract.get("candidate_next_actions") or []
forbidden_repeated = contract.get("forbidden_repeated_tool_calls") or []
required_next = contract.get("required_next_tool_call") or {}
```

**Where:** `services/aicarmine_broker/planner.py` → planner decision functions

### Tool Surface Policy (`tool_surface/turn_surface_policy.py`)
```python
# Lines where evidence contract determines tool surface:
contract = evidence_contract if isinstance(evidence_contract, dict) else {}
actions = contract.get("candidate_next_actions") or []
final_contract = contract.get("finalization_contract") or {}
may_final = final_contract.get("planner_may_choose_final") is True
may_block = final_contract.get("planner_may_choose_block") is True
base_reason = contract.get("base_tool_surface_reason") or ""
```

**Where:** `services/aicarmine_broker/application/tool_surface/turn_surface_policy.py` → policy enforcement

### Candidate Action Gate (`tool_surface/candidate_action_gate.py`)
```python
# Lines where evidence contract gates actions:
evidence = payload.get("evidence_contract") if isinstance(payload.get("evidence_contract"), dict) else {}
prev_actions = previous_evidence_contract.get("candidate_next_actions") or []
current_actions = evidence.get("candidate_next_actions") or []
required = previous_evidence_contract.get("required_next_tool_call") or {}
satisfied = previous_evidence_contract.get("required_next_tool_call_satisfied") is True
```

**Where:** `services/aicarmine_broker/application/tool_surface/candidate_action_gate.py` → action gating logic

### Validation Rejections (`planner/validation_rejections.py`)
```python
# Lines where evidence contract tracks rejections:
contract = validation.get("evidence_contract") if isinstance(validation.get("evidence_contract"), dict) else {}
violations = contract.get("violations") or []
semantic = contract.get("semantic_goal_classification") or {}
required_continuation = _determine_required_continuation(violations, contract, decision)
```

**Where:** `services/aicarmine_broker/application/planner/validation_rejections.py` → rejection handling

---

## Evidence Contract Schema Versions

| Schema | Purpose | Location |
|--------|---------|----------|
| `planner_evidence_contract.v1` | Full evidence contract from builder | builder.py |
| `planner_evidence_contract_hard_budget.v1` | Hard-budget compacted version | evidence_contract.py |
| `vulkan_repair_evidence_contract.v1` | Repaired contract for malformed emissions | planner.py |
| `planner_evidence_contract_storage_summary.v1` | Storage summary with chars/sha256 | evidence_contract.py |
| `controller_guard_contract_overlay.v1` | Guard overlay on contract | planner.py |

---

## EVIDENCE_PROMPT_KEEP_KEYS Reference

These 40+ keys are preserved during compaction (defined at line 9-43 of evidence_contract.py):

```python
EVIDENCE_PROMPT_KEEP_KEYS = (
    "semantic_goal_classification",
    "goal_requests_code_product",
    "goal_requires_code_product_report",
    "goal_requests_apply",
    "action_plan_candidate",
    "target_kind",
    "resolved_goal_file",
    "resolved_goal_scope",
    "successful_repo_read_paths",
    "successful_repo_read_count",
    "verified_content_read_count",
    "verified_content_reads",
    "user_scope_claims",
    "core_discovery_status",
    "core_discovery_candidates",
    "initial_orientation_surface",
    "candidate_next_actions",
    "micro_batch_contract",
    "minimum_read_coverage",
    "coverage_satisfied",
    "covered_owner_paths",
    "missing_owner_paths",
    "candidate_owner_paths",
    "planner_may_choose_final",
    "code_product_contract",
    "finalization_contract",
    "required_next_progress",
    "required_next_tool_call",
    "validation_rejections_tail",
    "failed_repo_read_paths",
    "failed_repo_list_files_paths",
    "forbidden_repeated_repo_read_paths",
    "read_admissible_paths",
    "validator_admissible_repo_read_paths",
)
```

---

## Quick Reference: Evidence Contract Flow Diagram

```
planner_evidence_contract(goal, history, artifacts)  [builder.py]
│
├── Phase 1: Build full contract from goal classification + history analysis
│   ├── semantic_goal_classification (goal_classifier.py)
│   ├── repository evidence (successful/failed paths, verified reads)
│   ├── coverage status (required_working_set.py)
│   ├── core discovery (core_discovery.py)
│   ├── initial orientation (initial_orientation.py)
│   └── finalization/code_product contracts (validator.py, code_product/state.py)
│
├── Phase 2: Compact for prompt preview  [evidence_contract.py::compact_evidence_contract_for_prompt()]
│   ├── Keep only EVIDENCE_PROMPT_KEEP_KEYS (40+ fields)
│   ├── verified_content_reads → truncated to 8 items with metadata
│   ├── Path lists → truncated to 24 items with text limit 180
│   ├── candidate_next_actions → truncated to 8 items with text limit 320
│   ├── file_memory → truncated to 6 items with key_lines/content_excerpt
│   └── operational_notes → clipped next_instruction (500 chars), actions (6 items)
│
├── Phase 3: Hard budget (if context exceeded)  [evidence_contract.py::hard_budget_evidence_contract_summary()]
│   ├── schema: "planner_evidence_contract_hard_budget.v1"
│   ├── Only most critical fields kept
│   ├── finalization_contract → clipped to 4 fields, text_limit=260
│   ├── code_product_contract → clipped to 13 fields, text_limit=320
│   └── candidate_next_actions → text_limit=700, list_limit=3
│
├── Phase 4: Windowed storage in SQLite scratchpad  [context_windows.py]
│   ├── document_id = db_path
│   ├── section = "evidence_contract"
│   ├── offset/max_chars for pagination
│   └── has_more_after = True if truncated
│
└── Phase 5: Consumption by downstream systems
    ├── planner.py::planner_decision() → reads final_allowed, may_choose_final, candidates
    ├── turn_surface_policy.py → determines visible tools based on contract fields
    ├── candidate_action_gate.py → gates required_next_tool_call satisfaction
    ├── validation_rejections.py → tracks violations and semantic classification
    └── public_wrapper.py / terminal_result.py → includes evidence_contract_summary in terminal output
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
| `EVIDENCE_CONTRACT_REFERENCE.md` (this file) | Complete reference for evidence_contract dictionary fields, compaction flow, and consumption points |