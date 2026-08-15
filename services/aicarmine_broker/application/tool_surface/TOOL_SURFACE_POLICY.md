# Tool Surface Policy Reference

**Created:** 2026-08-15  
**Purpose:** Complete reference for `ToolSurfacePolicy` class in `turn_surface_policy.py`. This policy determines which tools are visible to the planner at each turn, filtering and ordering the tool surface based on evidence contract state, required next tool calls, rewrite latches, coverage gaps, and semantic goal classification.

---

## Overview: Per-Turn Tool Surface Determination

The `ToolSurfacePolicy` class owns the per-turn planner tool surface. It mutates only the evidence contract it receives through the public `apply` method. Tool-name ordering stays private so callers cannot mutate the surface halfway through a turn.

Two public methods:
| Method | Purpose | Returns |
|--------|---------|---------|
| `tools_for_turn()` | Determine which tools are available for this turn | List of tool name strings |
| `apply()` | Keep candidate actions aligned with required progress | Evidence contract dict (mutated in place) |

---

## Tool Category Definitions

### _REPO_DISCOVERY_TOOLS
Tools for repository exploration and file discovery:
```python
{
    "repo_read",
    "repo_list_files",
    "repo_tree",
    "repo_search",
    "repo_semantic_search",
    "repo_fd_files",
    "repo_rg_search",
}
```

### _AST_DIFF_TOOLS
Tools for AST analysis, diff validation, and git operations:
```python
{
    "repo_ast_grep_search",
    "repo_ast_grep_dry_run",
    "repo_tree_sitter_parse",
    "repo_unidiff_validate",
    "repo_git_apply_check",
}
```

### _VALIDATION_TOOLS
Tools for code quality and testing validation:
```python
{
    "repo_validate",
    "repo_ruff_check",
    "repo_pyright_check",
    "repo_pytest_run",
}
```

### _NON_TERMINAL_SUPPORT_TOOLS
Support tools that may be used at any stage (but not terminal):
```python
{
    "repo_read",
    "planner_scratchpad_read",
    "planner_scratchpad_write",
    "runtime_sqlite_memory_search",
    "runtime_sqlite_memory_write",
}
```

### _ALWAYS_AVAILABLE_SUPPORT_TOOLS
Support tools always available regardless of turn state:
```python
{
    "planner_scratchpad_read",
    "planner_scratchpad_write",
    "runtime_sqlite_memory_search",
    "runtime_sqlite_memory_write",
}
```

---

## tools_for_turn() Decision Flow

The `tools_for_turn()` method follows a cascading decision flow. Each condition is checked in order, and the first matching condition determines the tool surface:

### Step 1: Continuation Tool Only (Prompt Context Window)
```python
if prompt_context_continuation_required is not None:
    return continuation_tools  # List of specific tools for context window continuation
```
**When:** Planner needs to read/write prompt context windows stored in SQLite scratchpad.

### Step 2: Required Next Tool Call (Unsatisfied)
```python
required = evidence_contract.get("required_next_tool_call") or {}
if required_validated and not _required_call_is_marked_satisfied(evidence_contract):
    return [required_tool]  # Single mandatory tool
```
**When:** A required next tool call exists, has been deterministically validated by the validator, and has not yet been marked satisfied. This enforces progress on critical paths like missing owner path reads.

### Step 3: Final Rewrite Latch Active
```python
rewrite_latch = _final_rewrite_latch(evidence_contract)
if rewrite_latch:
    return rewrite_latch_tools  # Tools for rewriting rejected proposals
```
**When:** The final rewrite latch is active (e.g., after a malformed planner emission or invalid code-product proposal). Forces the planner to rewrite using real evidence from candidate_next_actions.

### Step 4: Coverage Required but Not Satisfied
```python
if _contract_coverage_required(contract) and not _contract_coverage_satisfied(contract):
    return REPO_DISCOVERY_TOOLS + NON_TERMINAL_SUPPORT_TOOLS
```
**When:** Evidence contract requires coverage (minimum read coverage not satisfied) and coverage has not been met. Provides broad discovery tools to find missing owner paths.

### Step 5: Terminal Policy Locks Surface
```python
if _terminal_policy_locks_surface(contract):
    terminal_policy_tools = _policy_declared_tools(contract)
    if terminal_policy_tools is not None:
        return terminal_policy_tools
```
**When:** Terminal policy explicitly declares which tools are allowed at this stage. Used for final composition or blocked states.

### Step 6: Policy Declares Tools Explicitly
```python
policy_tools = _policy_declared_tools(contract)
if policy_tools is not None:
    return policy_tools
```
**When:** The evidence contract has an explicit `allowed_tool_names` field from a previous policy application.

### Step 7: Final Required Now
```python
if _contract_final_required_now(contract):
    names = final_composition_tool_names_from_candidates(contract)
    names.update(ALWAYS_AVAILABLE_SUPPORT_TOOLS)
    return ordered(names)
```
**When:** Finalization is required now (e.g., code_product_contract.final_allowed=True and coverage satisfied). Provides composition tools for building the final answer.

### Step 8: Default Surface Based on Goal Classification
```python
semantic = evidence_contract.get("semantic_goal_classification") or {}
goal_class = semantic.get("class") or "unknown"
code_product_required = bool(evidence_contract.get("code_product_contract", {}).get("required"))
apply_required = bool(evidence_contract.get("goal_requests_apply")) or goal_requests_apply(goal)
names = _base_tools_for_goal_class(
    goal_class=goal_class,
    code_product_required=code_product_required,
    apply_required=apply_required,
)
_add_keyword_tools(names, goal)
_add_candidate_tools(names, contract)
_add_explicit_request_tool(names, intrinsic_context)
```
**When:** No special conditions apply. Default surface determined by:
- Semantic goal classification (analysis/code-product/apply/input-envelope)
- Whether code product is required
- Whether apply action is requested
- Keyword tools derived from goal text
- Candidate next actions from evidence contract
- Explicit request tool from intrinsic context

---

## apply() Contract Mutation Logic

The `apply()` method mutates the evidence contract to keep candidate actions aligned with required progress:

### Strict Code Product Payload Detection
```python
strict_code_product_payload = any(
    token in progress for token in [
        "route shift required after invalid repo_propose_code_edit payload",
        "no new source window",
        "no unread source window",
        "no remaining state window to read",
        "empty collecting_source writes are rejected",
        "do not write code_product_build_state without a complete payload",
        "do not write code_product_build_state again unless it contains a complete",
        "code_product_route_shift_target_already_read",
    ]
)
```
**When:** Progress text indicates strict code product validation is needed.

### Required Next Tool Call Enforcement
```python
required = evidence_contract.get("required_next_tool_call") or {}
if required_tool in REPO_DISCOVERY_TOOLS and required_validated:
    arguments = required.get("arguments") or {}
    reason = required.get("reason") or "final_rewrite_latch"
    # Enforce that the planner must use this specific tool call
```
**When:** A required next tool call exists for a repo discovery tool and has been validated by the validator.

### Candidate Actions Filtering
```python
raw_actions = evidence_contract.get("candidate_next_actions")
actions = raw_actions if isinstance(raw_actions, list) else []
# Dedupe and filter actions based on policy rules
filtered = dedupe_candidate_actions(actions)
evidence_contract["candidate_next_actions"] = filtered
policy["candidate_actions_filtered"] = True
```
**When:** Candidate next actions exist but need deduplication or filtering based on turn state.

### Final Rewrite Latch Enforcement
```python
rewrite_latch = _final_rewrite_latch(evidence_contract)
if rewrite_latch:
    # Set finalization_contract.reason = "final_rewrite_latch_active"
    # Force planner to use required_next_tool_call
    evidence_contract["required_next_tool_call"] = {tool, arguments, reason}
    evidence_contract["finalization_contract"]["reason"] = "final_rewrite_latch_active"
```
**When:** The final rewrite latch is active, forcing the planner to rewrite rejected proposals using real evidence.

### Required Next Tool Call Pending
```python
if not _required_call_is_marked_satisfied(evidence_contract):
    evidence_contract["candidate_next_actions"] = [required_tool]
    evidence_contract["required_next_tool_call"] = {...}
    evidence_contract["finalization_contract"]["reason"] = "required_next_tool_call_pending"
    policy.update("surface_only": True)  # Lock surface to required tool only
```
**When:** A required next tool call exists but has not yet been satisfied. Locks the tool surface to that specific tool until it is marked satisfied.

---## Tool Surface Policy Rules

### Rule 1: Continuation Takes Priority
If `prompt_context_continuation_required` is set, continuation tools are returned exclusively. This ensures prompt context window reads/writes happen before other actions.

### Rule 2: Required Next Tool Call Must Be Satisfied First
If a required next tool call exists and is deterministically validated but not yet satisfied, ONLY that tool is available. The planner cannot choose alternative actions until the requirement is fulfilled.

**Enforcement:** `_required_call_is_deterministically_validated()` checks validator evidence; `_required_call_is_marked_satisfied()` checks contract state.

### Rule 3: Final Rewrite Latch Forces Evidence-Based Rewriting
When the final rewrite latch is active (e.g., after malformed planner emissions), the planner must use real evidence from `candidate_next_actions` or `required_next_tool_call`. Placeholder old_text/new_text pairs are rejected.

**Enforcement:** `_final_rewrite_latch()` detects latch activation; policy locks surface to required tools only.

### Rule 4: Coverage Gap Triggers Broad Discovery
If coverage is required but not satisfied, the tool surface expands to include all repo discovery tools plus support tools. This gives the planner maximum flexibility to find missing owner paths.

**Enforcement:** `_contract_coverage_required()` and `_contract_coverage_satisfied()` check minimum_read_coverage state.

### Rule 5: Terminal Policy Can Lock Surface
When terminal policy explicitly declares allowed tools, those tools override default surface determination. This is used for final composition or blocked states where only specific actions are valid.

**Enforcement:** `_terminal_policy_locks_surface()` detects lock; `_policy_declared_tools()` returns declared set.

### Rule 6: Default Surface Based on Semantic Classification
When no special conditions apply, the tool surface is determined by semantic goal classification, code product requirements, apply requirements, keyword analysis of goal text, candidate next actions, and intrinsic context explicit requests.

**Enforcement:** `_base_tools_for_goal_class()`, `_add_keyword_tools()`, `_add_candidate_tools()`, `_add_explicit_request_tool()` build the default surface.

---## Tool Surface Policy Diagnostic Fields

The `apply()` method produces diagnostic rows when issues are detected:

| Diagnostic | Condition | Schema |
|------------|---------|--------|
| `candidate_next_actions_not_list` | candidate_next_actions is not a list | `turn_tool_surface_policy_diagnostic.v1` |
| `final_rewrite_latch_active` | Rewrite latch active but required tool not satisfied | `planner_turn_tool_surface_policy.v1` |
| `required_next_tool_call_pending` | Required call exists but not yet marked satisfied | `planner_turn_tool_surface_policy.v1` |
| `surface_only_lockout` | Policy locks surface to specific tools only | `planner_turn_tool_surface_policy.v1` |

---## Quick Reference: Tool Surface Decision Tree

```
tools_for_turn(goal, evidence_contract, intrinsic_context, prompt_context_continuation_required)
│
├── Step 1: Is prompt_context_continuation_required set?
│   └── YES → return continuation_tools (context window read/write)
│   └── NO → continue
│
├── Step 2: Is required_next_tool_call unsatisfied and validated?
│   └── YES → return [required_tool] (single mandatory tool)
│   └── NO → continue
│
├── Step 3: Is final_rewrite_latch active?
│   └── YES → return rewrite_latch_tools (evidence-based rewriting)
│   └── NO → continue
│
├── Step 4: Is coverage required but not satisfied?
│   └── YES → return REPO_DISCOVERY_TOOLS + NON_TERMINAL_SUPPORT_TOOLS
│   └── NO → continue
│
├── Step 5: Does terminal policy lock surface?
│   └── YES → return policy_declared_tools if available
│   └── NO → continue
│
├── Step 6: Does policy explicitly declare allowed tools?
│   └── YES → return policy_declared_tools
│   └── NO → continue
│
├── Step 7: Is final required now (finalization_allowed=True)?
│   └── YES → return final_composition_tools + ALWAYS_AVAILABLE_SUPPORT_TOOLS
│   └── NO → continue
│
└── Step 8: Default surface based on goal classification
    ├── semantic_goal_classification.class → base tools for that class
    ├── code_product_contract.required → add code product tools if True
    ├── goal_requests_apply → add apply tools if True
    ├── goal text keywords → add keyword-derived tools
    ├── candidate_next_actions → add from evidence contract
    └── intrinsic_context.explicit_request → add explicit request tool
```

---## Related Documentation Files

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
| `TOOL_SURFACE_POLICY.md` (this file) | Per-turn tool surface determination logic based on evidence contract state |