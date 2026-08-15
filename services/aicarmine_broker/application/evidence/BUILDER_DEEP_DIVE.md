# Evidence Builder Deep Dive Reference

**Created:** 2026-08-15  
**Purpose:** Complete deep-dive reference for `builder.py` (2416 lines). This module implements the `EvidenceBuilder` class - the owner for planner evidence contract construction. It builds the complete evidence contract dictionary from goal text, execution history, and intrinsic context. The contract drives tool surface determination, finalization decisions, and candidate action generation.

---

## Overview: Evidence Contract Architecture

The `EvidenceBuilder` class owns the construction of a single comprehensive evidence contract dictionary that contains all state needed by the planner to decide next actions. It integrates multiple subsystems through dependency injection via `_deps` mapping.

### Key Constants

| Constant | Value/Type | Purpose |
|----------|-----------|---------|
| `POST_WRITE_VALIDATION_TOOLS` | frozenset | {"repo_validate", "repo_ruff_check", "repo_pyright_check", "repo_pytest_run"} |
| `POST_WRITE_TOOL_NAMES` | frozenset | {"repo_apply_patch", "repo_write_file"} |
| `MICRO_BATCH_MAX_ACTIONS` | int | 8 (maximum batch size for independent read-only candidates) |
| `_PREPLANNER_GOAL_CLASSES` | frozenset | {"analysis_only", "code_security_analysis", "repo_analysis", "code_product_report", "apply_write", "generic"} |

---

## EvidenceBuilder Class

### Structure

```python
@dataclass(frozen=True)
class EvidenceBuilder:
    """Owner for planner evidence contract construction."""
    
    _deps: Mapping[str, Any]
    _config: Mapping[str, Any]
```

The class is a frozen dataclass. Dependencies are injected via `_deps` mapping containing function references. Configuration comes from `_config` with keys like `CODE_PRODUCT_BUILD_STATE_KIND`, `LAB_REPO`, `REPO_CONCRETE_READ_TARGET`, `SCOPED_CONCRETE_READ_TARGET`.

---

## build() Method - Main Entry Point

### Signature

```python
def build(
    self,
    goal: str,
    history: list[dict[str, Any]],
    intrinsic_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
```

### Dependency Extraction (30+ deps extracted)

The method extracts all dependencies from `self._deps`:

| Category | Dependencies | Purpose |
|----------|-------------|---------|
| Decision paths | `_agentic_v2_decision_paths` | Tool call path resolution |
| Evidence enrichment | `_agentic_v2_enrich_evidence_contract` | Contract field enrichment |
| Goal scope | `_agentic_v2_goal_scope` | Scope extraction from goal |
| Surface policy | `_apply_turn_surface_policy` | Tool surface mutation |
| Notebook building | `_build_operational_notebook` | Operational notebook generation |
| Candidate actions | `_candidate_actions_from_evidence`, `_meaningful_read_candidates_from_evidence`, `_scope_read_candidates_from_evidence` | Action candidate generation |
| Code product | `_canonical_invalid_code_product_decision_signature`, `_disallowed_invalid_code_product_signatures`, `successful_code_edit_proposals`, `code_product_payload_violations`, `latest_code_product_build_state`, `code_product_candidate_action` | Code product validation and state |
| Validation rejections | `_compact_validation_rejections_tail` | Rejection tail compaction |
| Core discovery | `_core_discovery_candidates_from_intrinsic`, `_rank_core_candidates` | Intrinsic context-based path discovery |
| File/memory | `_file_memory_from_history` | File memory tracking |
| Goal analysis | `_goal_exact_text_block`, `_goal_target_file`, `_goal_target_kind`, `_input_error_goal`, `_low_signal_top_dir`, `_repo_analysis_goal` | Goal text parsing and classification |
| Orientation | `_initial_orientation_surface_from_history` | Preplanner orientation surface |
| Path checking | `_path_exists_repo_relative`, `_path_under_scope`, `_paths_from_list_rows`, `_paths_from_result`, `_repo_rel_token` | Path validation and normalization |
| Repo evidence | `_repo_code_file`, `_repo_doc_or_config`, `_repo_list_evidence`, `_repo_readable_evidence_file` | File type classification |
| Read tracking | `successful_repo_read_paths`, `failed_repo_read_paths`, `failed_repo_list_files_paths`, `verified_repo_read_content_rows` | Read success/failure tracking |
| Scratchpad | `_planner_scratchpad_window_signature` | Scratchpad window detection |
| Semantic search | `_successful_window_signatures` | Window signature tracking |

### Core Processing Flow

```python
build(goal, history, intrinsic_context):
│
├── Step 1: Extract config values
│   ├── CODE_PRODUCT_BUILD_STATE_KIND
│   ├── LAB_REPO
│   ├── REPO_CONCRETE_READ_TARGET
│   └── SCOPED_CONCRETE_READ_TARGET
│
├── Step 2: Extract all dependencies from self._deps
│   └── 30+ function references extracted
│
├── Step 3: Process goal classification and semantic intent
│   ├── fallback_semantic_classification = semantic_goal_classification(goal)
│   ├── preplanner_rag = initial_orientation_surface_from_history(history).get("preplanner_rag")
│   ├── preplanner_semantic_intent = _preplanner_semantic_intent_from_orientation(...)
│   ├── semantic_classification = _semantic_classification_with_preplanner_intent(fallback, preplanner_intent)
│   ├── goal_requests_apply_value = _goal_requests_apply_from_semantics(fallback, preplanner_intent)
│   └── goal_requests_code_product_value = _goal_requests_code_product_from_semantics(fallback, preplanner_intent)
│
├── Step 4: Process history for read tracking and evidence paths
│   ├── successful_repo_read_paths (read_ok)
│   ├── verified_content_reads from verified_repo_read_content_rows
│   ├── missing_full_content_reads (verified but not full content)
│   ├── failed_repo_read_paths
│   ├── failed_repo_list_files_paths
│   ├── latest_file_list_result(history) → known_paths
│   └── semantic_search_followup from repo_semantic_search tool results
│
├── Step 5: Build file memory and orientation surface
│   ├── file_memory = _file_memory_from_history(history)
│   ├── initial_orientation_surface = _initial_orientation_surface_from_history(history)
│   ├── ranked_preplanner_paths, selected_preplanner_paths
│   ├── semantic_preplanner_target_paths, semantic_target_read_paths
│   └── doc_reads (markdown/config), code_reads (code files)
│
├── Step 6: Determine coverage requirements by target_kind
│   ├── target_file → "file" coverage
│   ├── target_scope → "scope" coverage
│   ├── code_security_coverage_required → "code_security" coverage
│   ├── goal_requests_apply + apply_target_files → "apply_targets" coverage
│   ├── repo_goal → "repo_owner_core" coverage
│   └── default → "tool_evidence" coverage
│   └── Build owner_candidate_paths, covered_owner_paths, missing_owner_paths
│
├── Step 7: Determine final_allowed status
│   ├── target_kind == "file" → file_read_done
│   ├── scoped_inspection → scope_listed AND scope_content_reads >= scope_required_count
│   ├── repo_goal → strict_repo_evidence OR analysis_repo_evidence
│   └── non-repository → read_ok or meaningful_lists
│   └── Additional checks: apply_write requires repo_apply_patch, code_security requires sufficient reads
│
├── Step 8: Build candidate actions from evidence
│   ├── candidates = _candidate_actions_from_evidence(goal, file_memory, list_rows, ...)
│   ├── semantic_suggested_actions from valid_unread_suggested_read_paths
│   ├── explicit_request_context handling (target_internal_tool + target_arguments)
│   ├── apply_preloop_candidate_paths and apply_target_files
│   └── post_write_validation_candidates
│
├── Step 9: Process code_product state if required
│   ├── code_product_proposals = successful_code_edit_proposals(history)
│   ├── latest_code_product_violations = code_product_payload_violations(...)
│   ├── code_product_blocks_final if violations exist
│   ├── code_product_build_state = latest_code_product_build_state(...)
│   └── candidate actions for code_product_target_file
│
├── Step 10: Build validation_rejections tail from history
│   ├── controller_guard results with violations
│   ├── failed_code_edit_proposal validations
│   └── Extract stale_required_next_tool_calls, latest_required_next_tool_call
│
├── Step 11: Assemble complete evidence contract dictionary
│   ├── semantic_goal_classification, preplanner_semantic_intent
│   ├── goal_requests flags (python_file_review, code_product, apply)
│   ├── apply_write_contract, post_write_validation_contract
│   ├── target_kind, resolved_goal_file/scope, known_paths
│   ├── read tracking (successful, verified, missing, failed)
│   ├── user_scope_claims, core_discovery_status/candidates
│   ├── explicit_request_context
│   ├── scoped_concrete_read_target/count/candidates
│   ├── repo_concrete_read_target/count/candidates
│   ├── code_security_coverage gate
│   ├── failed_repo_read/list_files paths
│   ├── semantic_search_followup
│   ├── candidate_next_actions, disallowed_decision_signatures
│   ├── minimum_read_coverage, coverage_satisfied/missing/covered
│   ├── planner_may_choose_final, finalization_contract
│   ├── agentic_codex_quality quality gate
│   ├── initial_orientation_surface
│   └── required_next_tool_call, stale_required markers
│
├── Step 12: Process rewrite_latch active conditions
│   ├── If valid_unread_suggested_read_paths exist AND no latest_required call
│   └── Promote semantic followup to required_next_tool_call with validated=True
│
└── Step 13: Apply turn surface policy and return contract
    ├── _apply_turn_surface_policy(contract) → mutates candidate_next_actions
    └── Return complete evidence contract dictionary
```

---

## _preplanner_semantic_intent_from_orientation() Helper

### Purpose

Extracts preplanner semantic intent from the initial orientation surface. This provides a refined goal classification based on RAG query plan analysis.

### Signature

```python
def _preplanner_semantic_intent_from_orientation(
    initial_orientation_surface: Mapping[str, Any],
) -> dict[str, Any]:
```

### Extraction Flow

```python
# Navigate nested structure: initial_orientation_surface → preplanner_rag → ranking → query_plan → semantic_intent
orientation = initial_orientation_surface if isinstance(initial_orientation_surface, Mapping) else {}
preplanner_rag = orientation.get("preplanner_rag") if isinstance(orientation, Mapping) else {}
ranking = preplanner_rag.get("ranking") if isinstance(preplanner_rag, Mapping) else {}
query_plan = ranking.get("query_plan") if isinstance(ranking, Mapping) else {}
intent = query_plan.get("semantic_intent") if isinstance(query_plan, Mapping) else {}

# Validate schema and goal_class
if str(intent.get("schema") or "") != "agentic_loop_preplanner_semantic_intent.v1":
    return {}
goal_class = str(intent.get("goal_class") or "").strip()
if goal_class not in _PREPLANNER_GOAL_CLASSES:
    return {}

return {str(key): value for key, value in intent.items()}
```

---

## _semantic_classification_with_preplanner_intent() Helper

### Purpose

Merges fallback semantic classification with preplanner intent when available. Adjusts contract class based on preplanner goal_class and code_product_requested flag.

### Signature

```python
def _semantic_classification_with_preplanner_intent(
    fallback: Mapping[str, Any],
    preplanner_intent: Mapping[str, Any],
) -> dict[str, Any]:
```

### Classification Logic

| Preplanner goal_class | Contract Class Adjustment | Code Product Required | Security Coverage Required |
|----------------------|--------------------------|----------------------|---------------------------|
| "repo_analysis" or "generic" | → "analysis_only" | False | Depends on intent.requires_code_security_coverage |
| "code_product_report" AND NOT code_product_requested | → "analysis_only" | False | N/A |
| "code_product_report" AND code_product_requested | → "code_product_report" | True | N/A |
| "code_security_analysis" | → "code_security_analysis" | N/A | True |

**Return:** Fallback classification with additional fields: schema, class, confidence (≥0.9), reason, requested_deliverable, must_produce_code_product, requires_code_security_coverage, regex overrides, preplanner_semantic_intent, preplanner_goal_class.

---

## _goal_requests_code_product_from_semantics() / _goal_requests_apply_from_semantics()

### _goal_requests_code_product_from_semantics()

```python
def _goal_requests_code_product_from_semantics(fallback_value: bool, preplanner_intent: Mapping[str, Any]) -> bool:
    if isinstance(preplanner_intent, Mapping) and str(preplanner_intent.get("source") or "") == "planner_query_plan":
        return str(preplanner_intent.get("goal_class") or "").strip() == "code_product_report" and preplanner_intent.get("code_product_requested") is True
    return bool(fallback_value)
```

**Purpose:** Determines whether the goal requests code product based on preplanner semantic intent. Returns True only when goal_class is "code_product_report" AND code_product_requested is True.

### _goal_requests_apply_from_semantics()

```python
def _goal_requests_apply_from_semantics(fallback_value: bool, preplanner_intent: Mapping[str, Any]) -> bool:
    if isinstance(preplanner_intent, Mapping) and str(preplanner_intent.get("source") or "") == "planner_query_plan":
        return str(preplanner_intent.get("goal_class") or "").strip() == "apply_write"
    return bool(fallback_value)
```

**Purpose:** Determines whether the goal requests apply/edit/write based on preplanner semantic intent. Returns True only when goal_class is "apply_write".

---

## _micro_batch_contract_from_candidates() Helper

### Purpose

Builds a micro-batch contract for independent read-only candidate actions that may share one planner turn. Filters to CACHEABLE_READ_TOOLS only, deduplicates by call key and action ID.

### Signature

```python
def _micro_batch_contract_from_candidates(
    candidates: list[dict[str, Any]],
    max_actions: int = MICRO_BATCH_MAX_ACTIONS,
) -> dict[str, Any]:
```

### Filtering Logic

| Condition | Behavior |
|-----------|----------|
| tool not in CACHEABLE_READ_TOOLS | Skip (non-read tools excluded) |
| call_key already seen | Skip (deduplication by canonical_batch_call_key) |
| action_id missing or duplicate | Skip (deduplication by action_id) |
| max_actions reached | Stop processing |

**Return:**
```python
{
    "schema": "planner_micro_batch_contract.v1",
    "allowed": len(visible_actions) >= 2 or _native_mode_enabled,  # Native mode allows ≥1
    "mode": "native_message_tool_calls_only",
    "max_batch_size": min(limit, len(visible_actions)),
    "allowed_tools": sorted(tool names),
    "allowed_batch_actions": visible_actions[:limit],
    "candidate_action_count": len(candidates),
    "batchable_candidate_count": len(visible_actions),
    "guard": "...",  # Italian instruction about batch validation
    "writes_allowed": False,
    "validation_tools_allowed": False,
    "reason": "at_least_two_independent_read_only_candidates" or "fewer_than_two...",
}
```

---

## _post_write_validation_contract() Helper

### Purpose

Analyzes history to determine post-write validation state. Tracks write events (repo_apply_patch/repo_write_file) and subsequent validation events (repo_validate/repo_ruff_check/repo_pyright_check/repo_pytest_run).

### Signature

```python
def _post_write_validation_contract(
    history: list[dict[str, Any]],
    repo_rel_token: Callable[[Any], str],
) -> dict[str, Any]:
```

### Processing Flow

```python
# Step 1: Collect write events from history
write_events = []
for index, row in enumerate(history):
    result = _history_result(row)
    tool = str(result.get("tool") or "")
    if tool not in {"repo_apply_patch", "repo_write_file"} or result.get("ok") is not True:
        continue
    if tool == "repo_apply_patch" and result.get("changed") is False:
        continue
    paths = _tool_result_paths(result, repo_rel_token=repo_rel_token)
    write_events.append({"index": index, "tool": tool, "paths": paths, "changed": result.get("changed")})

# Step 2: Collect modified files from write events
modified_files = []
for event in write_events:
    for path in event.get("paths"):
        if path not in modified_files:
            modified_files.append(path)

# Step 3: Collect validation events after latest write
validation_events = []
latest_write_index = max(event["index"] for event in write_events) if write_events else -1
for index, row in enumerate(history):
    if index <= latest_write_index:
        continue
    result = _history_result(row)
    tool = str(result.get("tool") or "")
    if tool not in POST_WRITE_VALIDATION_TOOLS:
        continue
    paths = _tool_result_paths(result, repo_rel_token=repo_rel_token)
    covers_modified_files = _validation_covers_modified_files(paths, modified_files)
    validation_events.append({"index": index, "tool": tool, "ok": result.get("ok") is True, "paths": paths, "covers_modified_files": covers_modified_files})

# Step 4: Determine validation status
latest_covering_validation = next((event for event in reversed(validation_events) if event.get("covers_modified_files")), {})
validation_done = bool(latest_covering_validation and latest_covering_validation.get("ok") is True)
validation_failed = bool(latest_covering_validation and latest_covering_validation.get("ok") is not True)
status = "not_required" if not write_events else "passed" if validation_done else "failed" if validation_failed else "pending"

# Step 5: Build candidate actions for failed/missing validation
candidate_next_actions = _post_write_validation_candidates(modified_files, validation_failed=validation_failed)

return {
    "schema": "post_write_validation_contract.v1",
    "required": bool(write_events),
    "status": status,
    "validation_done": validation_done,
    "validation_failed": validation_failed,
    "modified_files": modified_files[:32],
    "latest_write_index": latest_write_index if latest_write_index >= 0 else None,
    "write_events": write_events[-8:],
    "validation_events_after_latest_write": validation_events[-8:],
    "latest_validation": latest_covering_validation or None,
    "candidate_next_actions": candidate_next_actions if write_events and not validation_done else [],
}
```

---

## _post_write_validation_candidates() Helper

### Purpose

Builds candidate actions for post-write validation scenarios. Includes repo_read for modified files when validation failed, plus deterministic validation tools.

### Signature

```python
def _post_write_validation_candidates(
    modified_files: list[str],
    validation_failed: bool,
) -> list[dict[str, Any]]:
```

### Candidate Generation

| Condition | Candidates Generated |
|-----------|---------------------|
| validation_failed=True AND modified_files exist | [{"tool": "repo_read", "arguments": {"paths": paths[:8], "max_chars": 50000}, ...}] |
| Always (if write_events) | [{"tool": "repo_validate", "arguments": {"paths": paths[:8], "timeout_seconds": 300}, ...}] |
| python_paths exist | [{"tool": "repo_ruff_check", "arguments": {"paths": python_paths, "timeout_seconds": 180}, ...}] |

---

## _history_result() Helper

```python
def _history_result(row: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(row, dict):
        return {}
    result = row.get("tool_result") if isinstance(row.get("tool_result"), dict) else {}
    if result:
        return result
    return row if row.get("tool") else {}
```

**Purpose:** Extracts tool_result from history row. Falls back to the row itself if it has a "tool" field but no explicit tool_result. Used consistently throughout builder for accessing tool execution results.

---

## _collect_result_paths() / _tool_result_paths()

### _collect_result_paths()

```python
def _collect_result_paths(
    value: Any,
    repo_rel_token: Callable[[Any], str],
    output: list[str],
) -> None:
```

**Purpose:** Recursively collects file paths from nested structures (dict/list/tuple/set). Checks keys: path, paths, target, targets, target_file, modified_paths, compile_target_resolution.targets. Normalizes via repo_rel_token and adds to output if not already present.

### _tool_result_paths()

```python
def _tool_result_paths(result: dict[str, Any], repo_rel_token: Callable[[Any], str]) -> list[str]:
```

**Purpose:** Extracts all paths from a tool result dictionary by checking standard key names in order. Returns deduplicated list of normalized relative paths.

---

## _goal_mentions_repo_path() / _path_covers_target()

### _goal_mentions_repo_path()

```python
def _goal_mentions_repo_path(goal_low: str, path: str) -> bool:
    normalized = str(path or "").replace("\\", "/").strip("/").lower()
    basename = normalized.rsplit("/", 1)[-1]
    stem = basename.rsplit(".", 1)[0] if "." in basename else basename
    return (
        normalized in goal_low
        or (basename and basename in goal_low)
        or (stem and len(stem) >= 6 and stem in goal_low)
    )
```

**Purpose:** Checks whether a goal text mentions a specific repo path. Matches full normalized path, basename, or filename stem (if ≥6 chars). Used for apply_write and code_product target resolution.

### _path_covers_target()

```python
def _path_covers_target(path: str, target: str) -> bool:
    path = str(path or "").strip().strip("/")
    target = str(target or "").strip().strip("/")
    if not path or not target:
        return False
    return path == target or target.startswith(path + "/") or path.startswith(target + "/")
```

**Purpose:** Checks whether a validation path covers a modified file target. Matches exact equality, parent directory, or child directory relationship.

---

## _validation_covers_modified_files() / _path_under_scope()

### _validation_covers_modified_files()

```python
def _validation_covers_modified_files(validation_paths: list[str], modified_files: list[str]) -> bool:
    if not modified_files:
        return True  # No files to validate → satisfied
    if not validation_paths:
        return True  # No validation paths → satisfied (no coverage check)
    return all(any(_path_covers_target(path, target) for path in validation_paths) for target in modified_files)
```

**Purpose:** Checks whether validation tool execution covers all modified files. Every modified file must be covered by at least one validation path.

### _path_under_scope()

```python
def _path_under_scope(path: str, scope: str) -> bool:
    """Check if path is under scope directory."""
    ...
```

**Purpose:** Determines whether a path falls within a scoped directory boundary. Used for scoped_concrete_read_target calculations.

---

## build() Method - Contract Dictionary Structure

The final contract dictionary contains these major sections:

| Section | Schema/Key | Purpose |
|---------|-----------|---------|
| `contract_type` | "planner_decides_controller_validates" | Controller/planner responsibility assignment |
| `semantic_goal_classification` | planner_goal_classification.v1 | Goal class, confidence, deliverable type |
| `preplanner_semantic_intent` | agentic_loop_preplanner_semantic_intent.v1 | RAG query plan intent |
| `apply_write_contract` | apply_write_contract.v1 | Apply/edit/write target files and state |
| `post_write_validation_contract` | post_write_validation_contract.v1 | Validation status after write events |
| `code_product_contract` | (inline) | Code product proposal state and build state |
| `minimum_read_coverage` | minimum_read_coverage.v1 | Coverage requirements by target_kind |
| `finalization_contract` | (inline) | Final allowed status and evidence requirements |
| `agentic_codex_quality` | (inline) | Quality gate assessment for repo goals |
| `code_security_coverage` | code_security_coverage_gate.v1 | Security analysis coverage gate |
| `semantic_search_followup` | semantic_search_followup.v1 | Suggested reads from semantic search |
| `candidate_next_actions` | (list) | Generated candidate actions |
| `required_next_tool_call` | (dict) | Validated required next call |
| `validation_rejections_tail` | (list[:5]) | Recent validation rejections |
| `initial_orientation_surface` | (dict) | Preplanner orientation data |

---

## Quick Reference: Coverage Target Kinds

| target_kind | Required Count | Covered Paths Source | Missing Paths Logic |
|-------------|---------------|---------------------|---------------------|
| "file" | 1 | verified_read_path_set containing target_file | Files not in verified set |
| "scope" | scope_required_read_count | scope_content_reads under target_scope | Available candidates minus covered |
| "code_security" | min(5, len(code_available)) or 3 | code_reads | Code files not verified |
| "apply_targets" | len(apply_target_files) | apply_verified_target_reads | Apply targets not read |
| "repo_owner_core" | max(orientative ? 1 : repo_required, semantic_target_required) | semantic_target_read_paths + meaningful_content_reads | Owner/core paths not covered |
| "tool_evidence" | 1 | verified_read_paths | Any verified reads |

---

## Related Documentation Files

| File | Purpose |
|------|---------|
| `EVIDENCE_CONTRACT_REFERENCE.md` | Complete reference for evidence_contract dictionary fields |
| `TERMINAL_PAYLOAD_SPECIFICATION.md` | Terminal payload structure, field ordering, materialization flow |
| `PAYLOAD_MATERIALIZATION_CONTRACT.md` | Contract between evidence_materializer, payload_index_resolver, and terminal_sanitizer |
| `TOOL_SURFACE_POLICY.md` | High-level overview of ToolSurfacePolicy class and per-turn tool surface determination |
| `VALIDATION_REJECTIONS.md` | Validation rejection signature tracking, deduplication, and compaction |
| `FINAL_QUALITY_JUDGMENT.md` | Deterministic quality checks, model judge request building, response sanitization |
| `PLANNER_TURN_MEMORY_REFERENCE.md` | Turn memory construction from history, Ollama turn metadata extraction |
| `EVIDENCE_MATERIALIZER_DEEP_DIVE.md` | Deep-dive into PublicEvidenceMaterializer class, materialize() flow |
| `TURN_SURFACE_POLICY_DEEP_DIVE.md` | Deep-dive into ToolSurfacePolicy class, tools_for_turn() cascading decision tree |
| `BUILDER_DEEP_DIVE.md` (this file) | Deep-dive into EvidenceBuilder class, build() method flow, all helper functions for evidence contract construction including goal classification, coverage requirements, finalization logic, and candidate action generation |