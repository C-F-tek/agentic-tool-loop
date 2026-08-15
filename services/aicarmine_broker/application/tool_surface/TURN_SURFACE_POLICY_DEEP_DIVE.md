# Turn Surface Policy Deep Dive Reference

**Created:** 2026-08-15  
**Purpose:** Complete deep-dive reference for `turn_surface_policy.py` (1048 lines). This module implements the per-turn planner tool surface policy - a cascading decision system that determines which tools are available to the planner at each turn based on evidence contract state, required next tool calls, coverage status, and finalization conditions.

---

## Overview: Tool Surface Decision Architecture

The `ToolSurfacePolicy` class owns the per-turn planner tool surface. It provides two public methods:

| Method | Purpose | Returns |
|--------|---------|---------|
| `tools_for_turn()` | Determine available tools for current turn | List of normalized tool names in priority order |
| `apply()` | Mutate evidence contract to align candidate actions with policy | Modified evidence contract dict |

**Key Principle:** The policy mutates only the evidence contract it receives through `apply()`. Tool-name ordering stays private so callers cannot mutate the surface halfway through a turn.

---

## Tool Category Classifications (Class Attributes)

### _REPO_DISCOVERY_TOOLS

Tools for repository navigation and content acquisition:

```python
_REPO_DISCOVERY_TOOLS = {
    "repo_read",           # Read specific file content
    "repo_list_files",     # List files in directory  
    "repo_tree",           # Directory tree structure
    "repo_search",         # Generic repo search
    "repo_semantic_search",  # RAG-based semantic search
    "repo_fd_files",       # fd-style file discovery
    "repo_rg_search",      # ripgrep-style content search
}
```

**Usage:** Added to surface when coverage is required, goal class is analysis_only (plus repo_ctags_symbols), or as base tools for most goal classes.

### _AST_DIFF_TOOLS

Tools for AST-based code analysis and diff validation:

```python
_AST_DIFF_TOOLS = {
    "repo_ast_grep_search",     # ast-grep pattern search
    "repo_ast_grep_dry_run",    # ast-grep dry-run without writes
    "repo_tree_sitter_parse",   # tree-sitter syntax parsing
    "repo_unidiff_validate",    # unified diff structure validation
    "repo_git_apply_check",     # git apply patch check
}
```

**Usage:** Added when code_product_required=True or apply_required=True.

### _VALIDATION_TOOLS

Tools for static analysis and testing:

```python
_VALIDATION_TOOLS = {
    "repo_validate",       # Broker-defined validation
    "repo_ruff_check",     # Python linting
    "repo_pyright_check",  # Python type checking
    "repo_pytest_run",     # Test execution
}
```

**Usage:** Added when apply_required=True, or when post_write_validation_failed/post_write_validation_required conditions are met.

### _NON_TERMINAL_SUPPORT_TOOLS

Tools available during non-terminal turns:

```python
_NON_TERMINAL_SUPPORT_TOOLS = {
    "repo_read",                    # Re-read for fresh evidence
    "planner_scratchpad_read",      # Read planner scratchpad memory
    "planner_scratchpad_write",     # Write planner scratchpad memory
    "runtime_sqlite_memory_search",  # Search runtime SQLite memory
    "runtime_sqlite_memory_write",   # Write runtime SQLite memory
}
```

**Usage:** Added to surface when policy_declared_tools returns allowed names and contract_final_required_now is False AND not suppress_non_terminal_support_expansion.

### _ALWAYS_AVAILABLE_SUPPORT_TOOLS

Tools always available even at terminal turns:

```python
_ALWAYS_AVAILABLE_SUPPORT_TOOLS = {
    "planner_scratchpad_read",
    "planner_scratchpad_write",
    "runtime_sqlite_memory_search",
    "runtime_sqlite_memory_write",
}
```

**Usage:** Added when contract_final_required_now=True (final answer required).

---

## tools_for_turn() Method - Cascading Decision Flow

### Signature

```python
def tools_for_turn(
    self,
    *,
    goal: str,
    evidence_contract: dict[str, Any],
    intrinsic_context: dict[str, Any],
    prompt_context_continuation_required: dict[str, Any] | None = None,
) -> list[str]:
```

### Decision Tree (8-Step Cascade)

The method evaluates conditions in strict priority order. First matching condition determines the tool surface:

```
Step 1: Continuation tool only?
│   ├── Check: prompt_context_continuation_required.tool exists
│   ├── If "planner_scratchpad_read" → return ["planner_scratchpad_read"]
│   ├── If repo_discovery_tool → return [that_tool]
│   └── Else → None (continue to next step)
│
Step 2: Required next tool call validated and unsatisfied?
│   ├── Check: required_next_tool_call exists AND validated=True AND NOT satisfied
│   └── Return [required_next_tool_call.tool]
│
Step 3: Final rewrite latch active?
│   ├── Check: final_rewrite_latch in {"rewrite_required", "required_gap_only", "terminal_block_required"}
│   ├── If required_tool is repo_discovery_tool AND validated → return [required_tool]
│   ├── If latch is exact match → return [] (empty surface, force block/final)
│   └── Else → None (continue)
│
Step 4: Coverage required but not satisfied?
│   ├── Check: minimum_read_coverage.required=True OR coverage_satisfied≠True
│   └── Return _REPO_DISCOVERY_TOOLS + _NON_TERMINAL_SUPPORT_TOOLS
│
Step 5: Terminal policy locks surface?
│   ├── Check: turn_tool_surface_policy.locked_empty_tool_surface OR contract_final_required_now
│   ├── Get policy_declared_tools from turn_tool_surface_policy.allowed_tool_names
│   └── If found → return allowed names (+ support tools if final required, else + non-terminal support)
│
Step 6: Policy explicitly declared tools?
│   ├── Check: turn_tool_surface_policy.allowed_tool_names exists and is list
│   └── If found → return ordered names (with support expansion logic)
│
Step 7: Final answer required now?
│   ├── Check: _contract_final_required_now() → True
│   └── Return final_composition_tool_names_from_candidates(contract) + _ALWAYS_AVAILABLE_SUPPORT_TOOLS
│
Step 8: Default based on goal classification
    ├── Get semantic_goal_classification.class from contract
    ├── Check code_product_contract.required
    ├── Check goal_requests_apply(goal) or apply_write_contract.required
    ├── Build base tools via _base_tools_for_goal_class()
    ├── Add keyword-matched tools via _add_keyword_tools()
    ├── Add candidate action tools via _add_candidate_tools()
    ├── Add explicit request tool via _add_explicit_request_tool()
    └── Add runtime_sqlite_memory_search if intrinsic_context declares selective memory gap
```

---

## _continuation_tool_only() Helper

### Purpose

Check if prompt context continuation requires a specific single tool. This handles cases where the previous turn ended with a required_next_tool_call that must be completed before continuing.

### Signature

```python
def _continuation_tool_only(self, continuation: dict[str, Any] | None) -> list[str] | None:
```

### Logic

| continuation.tool | Result |
|------------------|--------|
| "planner_scratchpad_read" | ["planner_scratchpad_read"] |
| repo_discovery_tool | [that_tool] |
| Other/None | None (no continuation constraint) |

---

## _required_call_is_deterministically_validated() / _required_call_is_marked_satisfied()

### _required_call_is_deterministically_validated()

```python
@staticmethod
def _required_call_is_deterministically_validated(contract):
    required = contract.get("required_next_tool_call") or {}
    if not required:
        return False
    # Check if validated=True on the required call itself
    if required.get("validated") is True:
        return True
    # Or check top-level flag
    return contract.get("required_next_tool_call_validated") is True
```

**Purpose:** Determines whether a required next tool call has been validated by deterministic checks (validator module) rather than being advisory.

### _required_call_is_marked_satisfied()

```python
@classmethod
def _required_call_is_marked_satisfied(cls, contract):
    required = contract.get("required_next_tool_call") or {}
    if not required:
        return False
    
    # Get canonical key for current required call
    key = canonical_required_tool_call_key(required.get("tool"), required.get("arguments"))
    
    # Check satisfied field in required_next_tool_call_satisfied dict
    current = contract.get("required_next_tool_call_satisfied") or {}
    current_key = current.get("key") or canonical_required_tool_call_key(...)
    if current.get("satisfied") is True and current_key == key:
        return True
    
    # Check stale_required_next_tool_calls list
    for item in contract.get("stale_required_next_tool_calls") or []:
        item_key = item.get("key") or canonical_required_tool_call_key(...)
        if item.get("satisfied") is True and item_key == key:
            return True
    
    return False
```

**Purpose:** Determines whether a required next tool call has been satisfied (completed) by checking the satisfaction tracking fields in the evidence contract.

---

## _rewrite_latch_tools() / _final_rewrite_latch()

### _final_rewrite_latch()

```python
@classmethod
def _final_rewrite_latch(cls, contract):
    latch = str(contract.get("final_rewrite_latch") or "").strip().lower()
    if latch in {"rewrite_required", "required_gap_only", "terminal_block_required"}:
        return latch
    return ""
```

**Purpose:** Extracts the final rewrite latch state from the evidence contract. This is a special condition that locks the tool surface when the planner must produce a revised final answer or terminal block.

### _rewrite_latch_tools()

```python
def _rewrite_latch_tools(self, contract):
    latch = self._final_rewrite_latch(contract)
    if not latch:
        return None
    
    required = contract.get("required_next_tool_call") or {}
    
    # If already satisfied, no latch constraint applies
    if self._required_call_is_marked_satisfied(contract):
        return None
    
    required_tool = self._required_next_tool_call_tool(required)
    
    # If required tool is repo discovery AND validated → allow it
    if required_tool in self._REPO_DISCOVERY_TOOLS and self._required_call_is_deterministically_validated(contract):
        return [required_tool]
    
    # Otherwise enforce empty surface (force final/block choice)
    if latch in {"rewrite_required", "required_gap_only", "terminal_block_required"}:
        return []  # Empty list = locked surface
    
    return None  # Continue to next cascade step
```

---

## _contract_coverage_required() / _contract_coverage_satisfied()

### _contract_coverage_required()

```python
@classmethod
def _contract_coverage_required(cls, contract):
    coverage = contract.get("minimum_read_coverage") or {}
    if coverage:
        return coverage.get("required") is True
    # Fallback: not satisfied means required
    return contract.get("coverage_satisfied") is not True
```

**Purpose:** Determines whether minimum read coverage is required but not yet satisfied. When True, the tool surface expands to all repo discovery tools plus non-terminal support tools.

### _contract_coverage_satisfied()

```python
@classmethod
def _contract_coverage_satisfied(cls, contract):
    coverage = contract.get("minimum_read_coverage") or {}
    if coverage:
        return coverage.get("coverage_satisfied") is True
    return contract.get("coverage_satisfied") is True
```

---

## _terminal_policy_locks_surface() / _policy_declared_tools()

### _terminal_policy_locks_surface()

```python
def _terminal_policy_locks_surface(self, contract):
    surface_policy = contract.get("turn_tool_surface_policy") or {}
    return bool(
        surface_policy.get("locked_empty_tool_surface")  # Explicit lock
        or self._contract_final_required_now(contract)   # Final required → locked
    )
```

**Purpose:** Determines whether the terminal policy has locked the tool surface to an empty set or explicit allowed list.

### _policy_declared_tools()

```python
def _policy_declared_tools(self, contract):
    surface_policy = contract.get("turn_tool_surface_policy") or {}
    policy_allowed = surface_policy.get("allowed_tool_names")
    
    if not isinstance(policy_allowed, list):
        return None
    
    if surface_policy.get("required_scratchpad_read_continuation"):
        return self._ordered({safe_text(name, limit=160) for name in policy_allowed})
    
    if policy_allowed or surface_policy.get("locked_empty_tool_surface") or self._contract_final_required_now(contract):
        names = {safe_text(name, limit=160) for name in policy_allowed}
        
        # Add support tools based on context
        if self._contract_final_required_now(contract):
            names.update(self._ALWAYS_AVAILABLE_SUPPORT_TOOLS)
        elif not surface_policy.get("suppress_non_terminal_support_expansion"):
            names.update(self._NON_TERMINAL_SUPPORT_TOOLS)
        
        return self._ordered(names)
    
    return None
```

---

## _contract_final_required_now()

### Purpose

Determines whether the final answer is required immediately. This locks the tool surface to final composition tools plus always-available support tools.

### Signature

```python
@classmethod
def _contract_final_required_now(cls, contract) -> bool:
```

### Conditions (Any True → Final Required)

| Condition | Check | Meaning |
|-----------|-------|---------|
| Coverage not satisfied | `_contract_coverage_satisfied()` returns False | Short-circuit: never require final if coverage missing |
| finalization_contract.final_allowed=True | `finalization.get("final_allowed") is True` | Explicit final allowed flag |
| terminal_decision_required + tool_calls_disallowed | Both fields in terminal_guidance | Terminal decision required, no more tool calls |
| terminal_decision_required_by_step_budget + tool_calls_disallowed_by_step_budget | Both fields in final_contract | Step budget reached, must finalize |
| finalization_contract.final_required=True | `final_contract.get("final_required") is True` | Explicit final required flag |

---

## _base_tools_for_goal_class()

### Purpose

Builds the base set of tools based on semantic goal classification and apply/code_product requirements.

### Signature

```python
def _base_tools_for_goal_class(
    self,
    *,
    goal_class: str,
    code_product_required: bool,
    apply_required: bool,
) -> set[str]:
```

### Tool Selection Matrix

| Condition | Base Tools |
|-----------|-----------|
| code_product_required=True | _REPO_DISCOVERY_TOOLS + _AST_DIFF_TOOLS + {repo_propose_code_edit, planner_scratchpad_write} |
| apply_required=True | _REPO_DISCOVERY_TOOLS + _AST_DIFF_TOOLS + _VALIDATION_TOOLS + {repo_apply_patch, repo_command, terminal_run_command_wait} |
| goal_class == "analysis_only" | _REPO_DISCOVERY_TOOLS + {repo_ctags_symbols} |
| Default (any other class) | _REPO_DISCOVERY_TOOLS + {repo_status} |

---

## _add_keyword_tools()

### Purpose

Adds tools based on keyword matching in the goal text. This enables semantic tool selection from natural language goals.

### Signature

```python
def _add_keyword_tools(self, names: set[str], goal: str) -> None:
```

### Keyword Matching Rules

| Goal Contains | Tool Added | Pattern Examples |
|---------------|------------|------------------|
| "json", "payload", "schema", "openapi" | repo_jq_query | JSON query operations |
| "security", "sicurezza", "vulnerability", "vulnerabil", "sast", "semgrep" | repo_semgrep_scan | Security scanning |
| "shell", "bash", ".sh", "shellcheck" | repo_shellcheck | Shell script validation |
| "benchmark", "performance", "prestazioni", "hyperfine" | repo_hyperfine_benchmark | Performance benchmarking |

---

## _add_candidate_tools() / _candidate_tool_names()

### _candidate_tool_names()

```python
@classmethod
def _candidate_tool_names(cls, contract):
    names = set()
    actions = contract.get("candidate_next_actions") or []
    for action in actions:
        if isinstance(action, dict):
            name = normalize_tool_name(safe_text(action.get("tool"), limit=160))
            if name:
                names.add(name)
    return names
```

**Purpose:** Extracts tool names from candidate_next_actions list in the evidence contract. These represent previously computed candidate actions that should remain available.

### _add_candidate_tools()

```python
def _add_candidate_tools(self, names: set[str], contract):
    for candidate in self._candidate_tool_names(contract):
        # Exclude memory/search tools (handled separately)
        if candidate.startswith("runtime_sqlite_memory_"):
            continue
        if candidate == "planner_scratchpad_read":
            continue
        names.add(candidate)  # Add to base tools
```

---

## _add_explicit_request_tool()

### Purpose

Adds a tool explicitly requested by the intrinsic context. This handles cases where the prompt or system explicitly requests a specific internal tool.

### Signature

```python
def _add_explicit_request_tool(self, names: set[str], intrinsic_context: dict[str, Any]) -> None:
```

### Logic

```python
explicit = intrinsic_context.get("explicit_request_context") or {}
if not isinstance(explicit, dict):
    return

target = normalize_tool_name(safe_text(explicit.get("target_internal_tool"), limit=160))
if target:
    names.add(target)  # Add explicitly requested tool
```

---

## _intrinsic_context_declares_selective_memory_gap()

### Purpose

Checks whether the intrinsic context indicates a gap in retrieved memory or RAG chunks. When True, runtime_sqlite_memory_search is added to the surface for selective memory retrieval.

### Signature

```python
@classmethod
def _intrinsic_context_declares_selective_memory_gap(cls, intrinsic_context) -> bool:
```

### Conditions

| Section | Field | Condition |
|---------|-------|---------|
| retrieved_memory | gap=True OR available=False | Memory retrieval gap detected |
| retrieved_rag_chunks | gap=True OR available=False | RAG chunk retrieval gap detected |

---

## apply() Method - Contract Mutation Logic

### Purpose

Mutates the evidence contract to align candidate_next_actions with the tool surface policy. This ensures that the planner's candidate actions list matches the allowed tools for the current turn.

### Signature

```python
def apply(self, contract: dict[str, Any]) -> dict[str, Any]:
```

### Decision Flow (12-Step Contract Processing)

```python
apply(contract):
│
├── Step 1: Validate input is dict
│   └── If not → return diagnostic_row("tool_surface_contract_not_object", ...)
│
├── Step 2: Extract candidate_next_actions and required_next_progress
│   ├── raw_actions = contract.get("candidate_next_actions") or []
│   └── progress = contract.get("required_next_progress").lower()[:4000]
│
├── Step 3: Check strict_code_product_payload tokens in progress
│   └── Tokens: "route shift after invalid repo_propose_code_edit payload", 
│       "no new source window", "empty collecting_source writes rejected", etc.
│
├── Step 4: Final rewrite latch processing
│   ├── If rewrite_latch active AND required_tool is repo_discovery AND validated:
│   │   ├── Build single action for required tool
│   │   ├── Set candidate_next_actions=[action]
│   │   ├── Update required_next_tool_call with validated=True
│   │   ├── Disable final_allowed and planner_may_choose_final
│   │   └── Return contract (early exit)
│   ├── If required exists but NOT validated:
│   │   ├── Move to required_next_tool_call_advisory (unvalidated)
│   │   ├── Remove validated fields
│   │   └── Continue processing
│   └── If required satisfied → clear required fields, continue
│
├── Step 5: Required scratchpad read continuation
│   ├── If required.tool == "planner_scratchpad_read" AND validated:
│   │   ├── Call enforce_required_scratchpad_read_continuation_contract()
│   │   ├── Clear contract, update with enforced dict
│   │   └── Return contract (early exit)
│
├── Step 6: Required repo discovery tool call
│   ├── If required_tool in _REPO_DISCOVERY_TOOLS AND validated:
│   │   ├── Build action for required tool
│   │   ├── Set candidate_next_actions=[action]
│   │   ├── Update required_next_tool_call with validated=True
│   │   ├── Disable final_allowed in finalization_contract
│   │   └── Return contract (early exit)
│
├── Step 7: Unvalidated advisory handling
│   └── If required exists but NOT validated → set unvalidated_advisory flag, continue
│
├── Step 8: Coverage required processing
│   ├── Filter actions to repo_discovery_tools only
│   ├── If coverage_actions exist → set_actions(contract, policy, coverage_actions, "minimum_read_coverage_required")
│   ├── Else → set_surface_only(contract, policy, _REPO_DISCOVERY_TOOLS, ...)
│   ├── Set required_next_progress with missing_owner_paths list
│   └── Return contract (early exit)
│
├── Step 9: Final required now processing
│   └── Filter actions to planner_scratchpad_write with kind="answer_chunk"
│       └── set_actions(contract, policy, final_actions, "final_allowed_and_required_now")
│
├── Step 10: Post-write validation handling
│   ├── If post_write_validation_contract.required AND NOT validation_done:
│   │   ├── If validation_failed → allow _VALIDATION_TOOLS + {repo_read, repo_apply_patch}
│   │   └── Else → filter to VALIDATION_TOOLS actions
│       └── Return contract (early exit)
│
├── Step 11: Apply write processing
│   ├── If apply_required AND NOT patch_applied:
│   │   ├── Check progress tokens for specific states:
│   │   │   ├── "apply_write_target_not_resolved" → empty surface
│   │   │   ├── "target acquisition mode"/"unread apply target" → repo_read actions
│   │   │   ├── "repo_apply_patch" in progress → repo_apply_patch actions
│   │   │   └── Default → {repo_apply_patch, repo_read} surface
│       └── Return contract (early exit)
│
├── Step 12: Code product processing
│   ├── If code_product_contract.required:
│   │   ├── Check progress tokens for specific states:
│   │   │   ├── "return action=block"+"blocked_incomplete" → empty surface
│   │   │   ├── "call repo_propose_code_edit"+"ready_for_propose" → complete propose actions
│   │   │   ├── "read internal code_product_build_state" → build_state read actions
│   │   │   ├── "advance with one real step"/"write new progress" → mixed propose+build_state
│   │   │   ├── "persist code_product_build_state"/"write with real progress" → build_state write
│   │   │   ├── "candidate_next_actions[0]" → first action only
│   │   │   ├── "target already read"+"do not repeat repo_read" → filter out repo_read
│   │   │   ├── "read target with repo_read" → repo_read/tree/list_files/search
│   │   │   └── "call repo_propose_code_edit" → complete propose actions
│   │   └── Default: remove incomplete proposals, filter by progress tokens
│
├── Step 13: Finalize policy
│   ├── If allowed_tool_names empty → locked_empty_tool_surface=True
│   └── Set turn_tool_surface_policy=policy in contract, return contract
```

---

## _set_actions() / _set_surface_only() / _add_allowed_tools()

### _set_actions()

Sets candidate_next_actions to a filtered list and updates policy with allowed tool names.

```python
def _set_actions(self, contract, policy, filtered, reason, suppress_support_expansion=False):
    filtered = dedupe_candidate_actions(filtered)
    contract["candidate_next_actions"] = filtered
    policy["candidate_actions_filtered"] = True
    policy["reason"] = reason
    
    if suppress_support_expansion:
        policy["suppress_non_terminal_support_expansion"] = True
    
    # Build allowed_tool_names from filtered actions
    policy["allowed_tool_names"] = self._ordered({
        name for name in (candidate_action_tool(item) for item in filtered) if name
    })
    
    # If single action, set required_next_tool_call explicitly
    if len(filtered) == 1:
        policy["required_next_tool_call"] = {
            "tool": candidate_action_tool(filtered[0]),
            "arguments": candidate_action_args(filtered[0]),
            "reason": reason,
        }
    
    contract["turn_tool_surface_policy"] = policy
```

### _set_surface_only()

Sets the tool surface to a specific allowed set without relying on candidate actions. Filters existing actions and tracks removed ones as stale.

```python
def _set_surface_only(self, contract, policy, allowed_names, reason, suppress_support_expansion=False):
    normalized_allowed = {normalize_tool_name(safe_text(name, limit=160)) for name in allowed_names}
    
    existing_actions = contract.get("candidate_next_actions") or []
    kept_actions = [a for a in existing_actions if candidate_action_tool(a) in normalized_allowed]
    removed_actions = [a for a in existing_actions if candidate_action_tool(a) not in normalized_allowed]
    
    contract["candidate_next_actions"] = dedupe_candidate_actions(kept_actions)
    
    # Track removed actions as stale (up to 32)
    if removed_actions:
        stale = contract.get("stale_candidate_next_actions") or []
        contract["stale_candidate_next_actions"] = dedupe_candidate_actions(removed_actions + stale)[:32]
    
    policy["candidate_actions_filtered"] = bool(removed_actions)
    policy["reason"] = reason
    
    if suppress_support_expansion:
        policy["suppress_non_terminal_support_expansion"] = True
    
    policy["allowed_tool_names"] = self._ordered(normalized_allowed)
    
    if not normalized_allowed:
        policy["locked_empty_tool_surface"] = True
    
    contract["turn_tool_surface_policy"] = policy
```

### _add_allowed_tools()

Adds tools to the existing allowed_tool_names set without replacing it.

```python
def _add_allowed_tools(self, contract, policy, allowed_names):
    current = {normalize_tool_name(safe_text(name, limit=160)) for name in policy.get("allowed_tool_names", [])}
    current.update({normalize_tool_name(safe_text(name, limit=160)) for name in allowed_names})
    policy["allowed_tool_names"] = self._ordered(current)
    contract["turn_tool_surface_policy"] = policy
```

---

## Module-Level Compatibility Functions

### candidate_tool_names()

```python
def candidate_tool_names(contract):
    return ToolSurfacePolicy._candidate_tool_names(contract)
```

**Purpose:** Static accessor for extracting tool names from candidate actions without instantiating the class.

### contract_final_required_now()

```python
def contract_final_required_now(contract):
    return ToolSurfacePolicy._contract_final_required_now(contract)
```

**Purpose:** Static checker for whether final answer is required now.

### intrinsic_context_declares_selective_memory_gap()

```python
def intrinsic_context_declares_selective_memory_gap(intrinsic_context):
    return ToolSurfacePolicy._intrinsic_context_declares_selective_memory_gap(intrinsic_context)
```

**Purpose:** Static checker for memory/RAG gaps in intrinsic context.

### tool_surface_names_for_turn()

```python
def tool_surface_names_for_turn(
    *,
    goal,
    evidence_contract,
    intrinsic_context,
    order_tool_names,
    prompt_context_continuation_required=None,
):
    return ToolSurfacePolicy(order_tool_names=order_tool_names).tools_for_turn(...)
```

**Purpose:** Factory function that instantiates and calls tools_for_turn(). Used by planner.py and other callers.

### apply_turn_surface_policy()

```python
def apply_turn_surface_policy(contract, *, order_tool_names):
    return ToolSurfacePolicy(order_tool_names=order_tool_names).apply(contract)
```

**Purpose:** Factory function that instantiates and calls apply(). Used by validator.py and loop helpers.

---

## Quick Reference: Turn Surface Decision Flow Diagram

```
tools_for_turn(goal, evidence_contract, intrinsic_context, prompt_context_continuation_required)
│
├── Cascade Step 1: Continuation constraint?
│   ├── prompt_context_continuation_required.tool == "planner_scratchpad_read" → ["planner_scratchpad_read"]
│   ├── prompt_context_continuation_required.tool in _REPO_DISCOVERY_TOOLS → [that_tool]
│   └── No continuation constraint → continue
│
├── Cascade Step 2: Validated required call unsatisfied?
│   ├── required_next_tool_call.validated=True AND NOT satisfied
│   └── Return [required_next_tool_call.tool]
│
├── Cascade Step 3: Final rewrite latch active?
│   ├── final_rewrite_latch in {rewrite_required, required_gap_only, terminal_block_required}
│   ├── If validated repo_discovery tool → return [tool]
│   ├── If exact latch match → return [] (empty surface)
│   └── Continue if no latch
│
├── Cascade Step 4: Coverage gap?
│   ├── minimum_read_coverage.required=True OR coverage_satisfied≠True
│   └── Return _REPO_DISCOVERY_TOOLS + _NON_TERMINAL_SUPPORT_TOOLS
│
├── Cascade Step 5: Terminal policy lock?
│   ├── turn_tool_surface_policy.locked_empty_tool_surface OR contract_final_required_now
│   └── Return turn_tool_surface_policy.allowed_tool_names (+ support expansion logic)
│
├── Cascade Step 6: Policy declared tools?
│   └── turn_tool_surface_policy.allowed_tool_names exists → return ordered names
│
├── Cascade Step 7: Final required now?
│   ├── _contract_final_required_now() → True
│   └── Return final_composition_tools + _ALWAYS_AVAILABLE_SUPPORT_TOOLS
│
└── Cascade Step 8: Default goal-class selection
    ├── Build base from _base_tools_for_goal_class(goal_class, code_product_required, apply_required)
    ├── Add keyword-matched tools (json→jq, security→semgrep, shell→shellcheck, benchmark→hyperfine)
    ├── Add candidate action tools (from contract.candidate_next_actions)
    ├── Add explicit request tool (from intrinsic_context.explicit_request_context)
    ├── Add runtime_sqlite_memory_search if memory gap detected
    └── Return ordered unique tool names list

apply(contract):
│
├── Process final rewrite latch → single required action or empty surface
├── Process required scratchpad read continuation → enforced dict
├── Process validated repo discovery required call → single action
├── Process unvalidated advisory → remove validated fields
├── Process coverage required → filter to repo_discovery actions
├── Process final required now → answer_chunk scratchpad write actions
├── Process post-write validation → VALIDATION_TOOLS + repo_read/apply_patch
├── Process apply write → target acquisition, patch application, or read
├── Process code product → propose/edit/build_state based on progress tokens
└── Finalize: set turn_tool_surface_policy=policy in contract
```

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
| `TURN_SURFACE_POLICY_DEEP_DIVE.md` (this file) | Deep-dive into ToolSurfacePolicy class, tools_for_turn() cascading decision tree, apply() contract mutation logic, all helper methods for per-turn tool surface determination |