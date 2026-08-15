# Planner Turn Memory Reference

**Created:** 2026-08-15  
**Purpose:** Complete reference for `planner_turn_memory()` function in `tool_context.py`. This function builds structured turn memory from planner history, separating successful tool turns from failed ones, and providing Ollama turn metadata for model-visible evidence transport to OpenWebUI.

---

## Overview: Turn Memory Construction

The `planner_turn_memory()` function takes planner history records and produces a structured dictionary containing:
- Contract description explaining Ollama done_reason semantics
- List of Ollama turn rows with step/done_reason/action/tool metadata
- List of successful tool turns (ok=True)
- List of failed tool turns (ok=False)

This output is consumed by the terminal result builder, public wrapper, and OpenWebUI bridge to provide model-visible turn context without exposing raw controller audit history.

---

## planner_turn_memory() Function

### Signature

```python
def planner_turn_memory(
    history: list[dict[str, Any]],
    terminal_decision: dict[str, Any] | None = None,
    same_tool_artifact_payload: ArtifactPayloadLoader,
    repo_read_item_full_content: RepoReadContentLoader,
    code_product_build_state_kind: str,
) -> dict[str, Any]:
```

### Parameters

| Parameter | Type | Purpose |
|-----------|------|---------|
| `history` | list[dict] | Planner turn records from job execution |
| `terminal_decision` | dict or None | Terminal decision from planner (finalization outcome) |
| `same_tool_artifact_payload` | Callable[[dict], dict] | Loads artifact payload for a given tool result |
| `repo_read_item_full_content` | Callable[[dict], tuple[str, dict]] | Returns full content + metadata for repo_read items |
| `code_product_build_state_kind` | str | Identifier for code product build state kind (e.g., "codex_app") |

### Return Structure

```python
{
    "contract": "Ollama done_reason closes one planner response turn only; 3572 validator/finalization still decides job status.",
    "ollama_turns": [...],  # List of Ollama turn metadata rows
    "successful_tool_turns": [...],  # Tool turns with ok=True
    "failed_tool_turns": [...],  # Tool turns with ok=False
}
```

---

## ollama_turn_rows() Helper

### Purpose

Builds a list of Ollama turn metadata rows from history, deduplicating by (step, action, tool) key. Each row represents one completed Ollama response turn.

### Input Processing

```python
def ollama_turn_rows(history, terminal_decision):
    rows = []
    seen = set()  # Deduplication key: (step, action, tool)
    
    for item in history:
        if not isinstance(item, dict):
            continue
        decision = item.get("decision") or {}
        result = history_tool_result(item)  # Extract tool_result from item
        
        # Get Ollama turn metadata
        turn = history_item_ollama_turn(item)
        if not turn:
            continue
        
        row = {
            "step": item.get("step"),
            "done_reason": turn.get("done_reason"),
            "done_seen": turn.get("done_seen"),
            "action": decision.get("action"),
            "tool": decision.get("tool") or result.get("tool"),
            "tool_ok": result.get("ok") if result.get("tool") != "controller_guard" else None,
            "guard_type": result.get("guard_type"),
        }
        
        # Deduplicate by (step, action, tool) key
        key = (row.get("step"), str(row.get("action") or ""), str(row.get("tool") or ""))
        if key not in seen:
            seen.add(key)
            rows.append(row)
    
    # Add terminal decision as special row if present
    if isinstance(terminal_decision, dict):
        turn = planner_ollama_turn_from_decision(terminal_decision, step=terminal_decision.get("step"))
        if turn:
            row = {
                "step": terminal_decision.get("step"),
                "done_reason": turn.get("done_reason"),
                "done_seen": turn.get("done_seen"),
                "action": terminal_decision.get("action"),
                "tool": terminal_decision.get("tool"),
                "terminal": True,  # Marks this as the terminal/finalization turn
            }
            key = (row.get("step"), str(row.get("action") or ""), str(row.get("tool") or ""))
            if key not in seen:
                rows.append(row)
    
    return rows
```

### Row Structure

| Field | Type | Purpose |
|-------|------|---------|
| `step` | int | Producer step number |
| `done_reason` | str | Ollama completion reason (e.g., "stop", "length") |
| `done_seen` | bool | Whether done_reason was observed |
| `action` | str | Planner action (e.g., "tool", "final", "block") |
| `tool` | str | Tool name used |
| `tool_ok` | bool | Whether tool call succeeded (excluded for controller_guard) |
| `guard_type` | str | Guard type if applicable |
| `terminal` | bool | True for terminal/finalization decision row |

---

## _public_tool_turns() Helper

### Purpose

Builds lists of successful or failed tool turns from history, filtering by expected_ok status. Each turn includes Ollama metadata, planner decision, and sanitized tool response.

### Signature

```python
def _public_tool_turns(
    history: list[dict[str, Any]],
    same_tool_artifact_payload: ArtifactPayloadLoader,
    repo_read_item_full_content: RepoReadContentLoader,
    code_product_build_state_kind: str,
    expected_ok: bool,  # True for successful, False for failed
) -> list[dict[str, Any]]:
```

### Turn Structure

Each item in the returned list represents one tool turn:

```python
{
    "step": item.get("step"),
    "substep": item.get("substep"),
    "producer": "controller_preseed" if action == "controller_preseed" else "planner",
    "tool_ok": result.get("ok"),
    "ollama_done_reason": turn.get("done_reason"),
    "ollama_turn": history_item_ollama_turn(item),  # Full Ollama turn metadata
    "tool_call": decision_for_turn_memory(decision),  # Sanitized planner decision
    "tool_response": response if expected_ok else None,  # Tool response or None for failures
    "payload_location": (
        "tool_context_for_30b.artifacts[*].artifact matching step/tool"
        if not expected_ok else None
    ),  # Pointer to where evidence can be found
}
```

### decision_for_turn_memory() Helper

Sanitizes the planner decision dict for turn memory:

```python
def decision_for_turn_memory(decision):
    return {
        "action": decision.get("action"),
        "tool": decision.get("tool"),
        "arguments": decision.get("arguments") if isinstance(decision.get("arguments"), dict) else None,
        "reason": decision.get("reason"),
        "final_answer": decision.get("final_answer"),
        "native_tool_call": decision.get("native_tool_call"),
        "native_tool_calls_seen": decision.get("native_tool_calls_seen"),
    }
```

### public_tool_response() Helper

Builds sanitized tool response based on tool type:

| Tool Type | Response Structure | Content Included |
|-----------|-------------------|------------------|
| `repo_read` | {tool, ok, count, items:[{path, size_bytes, line_count, truncated, content}]} | Full file content from repo_read_item_full_content callable |
| `repo_propose_code_edit` | {tool, ok, kind, target_file, edit_kind, rationale, validation_commands, errors, warnings, ...} | Edit proposal metadata and structured operations or unified diff |
| `repo_tree` | {tool, ok, repo_path, count, entries_total, truncated, entries:[...]} | Directory structure listing with stripped local paths |
| `repo_list_files` | {tool, ok, repo_path, suffix, count, total_matches, limit, truncated, paths:[...], files:[...]} | File path listing with stripped local paths |
| `repo_command`, `terminal_run_command_wait` | {tool, ok, command, returncode, stdout, stderr, stdout_tail, stderr_tail} | Command output with tail truncation |
| Other tools | {tool, ok, key: value for each non-empty field in source} | All non-empty fields from tool result, stripped of local artifact paths |

### Filtering Logic

```python
def _public_tool_turns(history, same_tool_artifact_payload, repo_read_item_full_content, code_product_build_state_kind, expected_ok):
    turns = []
    for item in history:
        if not isinstance(item, dict):
            continue
        
        # Extract tool_result from item
        result = history_tool_result(item)
        
        # Skip controller_guard items and items without tool name
        tool = str(result.get("tool") or "")
        if not tool or tool == "controller_guard":
            continue
        
        # Filter by ok status (successful vs failed)
        if bool(result.get("ok")) is not expected_ok:
            continue
        
        # Build sanitized response using public_tool_response()
        decision = item.get("decision") or {}
        response = public_tool_response(
            result,
            same_tool_artifact_payload=same_tool_artifact_payload,
            repo_read_item_full_content=repo_read_item_full_content,
            code_product_build_state_kind=code_product_build_state_kind,
        )
        
        if not response:
            continue
        
        turns.append({
            "step": item.get("step"),
            "substep": item.get("substep"),
            "producer": "controller_preseed" if str(decision.get("action") or "") == "controller_preseed" else "planner",
            "tool_ok": result.get("ok"),
            "ollama_done_reason": history_item_ollama_turn(item).get("done_reason"),
            "ollama_turn": history_item_ollama_turn(item),
            "tool_call": decision_for_turn_memory(decision),
            "tool_response": response if expected_ok else None,
            "payload_location": "tool_context_for_30b.artifacts[*].artifact matching step/tool" if not expected_ok else None,
        })
    
    return turns
```

---

## successful_tool_turns() and failed_tool_turns() Wrappers

### successful_tool_turns()

Returns tool turns where `ok=True`:

```python
def successful_tool_turns(history, same_tool_artifact_payload, repo_read_item_full_content, code_product_build_state_kind):
    return _public_tool_turns(
        history,
        same_tool_artifact_payload=same_tool_artifact_payload,
        repo_read_item_full_content=repo_read_item_full_content,
        code_product_build_state_kind=code_product_build_state_kind,
        expected_ok=True,
    )
```

**Usage:** Included in `planner_turn_memory()` output as `"successful_tool_turns"` field. Provides model-visible context of what tools succeeded during job execution.

### failed_tool_turns()

Returns tool turns where `ok=False`:

```python
def failed_tool_turns(history, same_tool_artifact_payload, repo_read_item_full_content, code_product_build_state_kind):
    return _public_tool_turns(
        history,
        same_tool_artifact_payload=same_tool_artifact_payload,
        repo_read_item_full_content=repo_read_item_full_content,
        code_product_build_state_kind=code_product_build_state_kind,
        expected_ok=False,
    )
```

**Usage:** Included in `planner_turn_memory()` output as `"failed_tool_turns"` field. Provides model-visible context of what tools failed during job execution, with payload_location pointers to where evidence can be found for analysis.

---

## public_tool_artifact_rows() Function

### Purpose

Builds a list of artifact rows from history, suitable for OpenWebUI visibility. Each row contains an artifact dict with real payloads (never local paths).

### Signature

```python
def public_tool_artifact_rows(
    history: list[dict[str, Any]],
    same_tool_artifact_payload: ArtifactPayloadLoader,
    repo_read_item_full_content: RepoReadContentLoader,
    code_product_build_state_kind: str,
) -> list[dict[str, Any]]:
```

### Return Structure

Each item in the returned list:

```python
{
    "producer_step": item.get("step"),
    "substep": item.get("substep"),
    "tool": tool_name,
    "arguments": decision.get("arguments") or {},
    "ok": result.get("ok"),
    "artifact": {...},  # Tool-specific artifact with kind + payload data
}
```

### Artifact Kind Classification

| Source Tool | Artifact Kind | Content |
|-------------|--------------|---------|
| `repo_read` | `repo_read` | {kind, path, size_bytes, line_count, truncated, content} for each read item |
| `repo_propose_code_edit` | `code_edit_proposal` | {kind, target_file, edit_kind, rationale, structured_operations/unified_diff} |
| `repo_unidiff_validate`, `repo_git_apply_check` | `diff_validation` | Diff validation result |
| `repo_ruff_check`, `repo_pyright_check`, `repo_pytest_run`, `repo_shellcheck`, `repo_semgrep_scan` | `validation_result` | Linter/test/validation diagnostics |
| `repo_ast_grep_search`, `repo_tree_sitter_parse`, `repo_ctags_symbols` | `structural_evidence` | AST/structure analysis results |
| `repo_fd_files`, `repo_rg_search`, `repo_jq_query` | `deterministic_repo_evidence` | File discovery/search results |
| Other tools | `{kind: artifact_payload.get("kind") or "tool_result", ...}` | Generic tool result with kind field |

---

## public_tool_context_limits() Function

### Purpose

Extracts limit conditions from artifact rows, identifying cases where content was truncated, preview-only, or partial (total > visible).

### Signature

```python
def public_tool_context_limits(artifact_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
```

### Limit Types Detected

| Condition | Kind Value | Structure |
|-----------|-----------|-----------|
| `artifact.truncated == True` | `"truncated"` | {step, substep, tool, path} |
| `artifact.preview_only == True` | `"preview_only"` | {step, substep, tool, path} |
| `total_matches > count` or `entries_total > count` | `"partial_list"` | {step, substep, tool, path, visible, total} |

**Usage:** Included in `tool_context_for_30b.limits` array when building public evidence context. Tells the model where content was bounded or truncated.

---

## ollama_turn_summary_text() Function

### Purpose

Builds a human-readable text summary of Ollama turns for inclusion in final markdown output.

### Output Format

```
Turni Ollama conclusi:
- step=6 done_reason=stop action=tool tool=repo_read tool_ok=True
- step=8 done_reason=length action=final tool=None terminal=true
...
```

**Usage:** Called by `final_summary_with_ollama_done_reasons()` to append turn summary to terminal final answer.

---

## final_summary_with_ollama_done_reasons() Function

### Purpose

Appends Ollama turn summary to the final summary text, with special note about max_steps_reached status.

### Signature

```python
def final_summary_with_ollama_done_reasons(
    status: str,
    final_summary: str,
    result: dict[str, Any],
) -> str:
```

### Logic

```python
def final_summary_with_ollama_done_reasons(status, final_summary, result):
    summary = final_summary or "Job terminale senza final_summary."
    
    # Don't duplicate if already present
    if "Turni Ollama conclusi:" in summary:
        return summary
    
    history = result.get("history") if isinstance(result.get("history"), list) else []
    terminal_decision = result.get("planner_decision") if isinstance(result.get("planner_decision"), dict) else {}
    turn_text = ollama_turn_summary_text(history, terminal_decision)
    
    if not turn_text:
        return summary
    
    suffix = turn_text
    
    # Add special note for max_steps_reached status
    if str(status or "") == "max_steps_reached":
        suffix += "\nNota stato: i done_reason chiudono i turni Ollama; non equivalgono a completed senza final accettato dal validator 3572."
    
    return summary + "\n\n" + suffix
```

---

## Quick Reference: Turn Memory Construction Flow Diagram

```
planner_turn_memory(history, terminal_decision, same_tool_artifact_payload, repo_read_item_full_content, code_product_build_state_kind)
│
├── Step 1: Build ollama_turn_rows()
│   ├── For each history item, extract Ollama turn metadata (done_reason, done_seen)
│   ├── Extract decision action/tool from planner decision or tool_result
│   ├── Deduplicate by (step, action, tool) key
│   └── Add terminal decision row with "terminal": True marker if present
│
├── Step 2: Build successful_tool_turns() via _public_tool_turns(expected_ok=True)
│   ├── Filter history items to those with ok=True
│   ├── Skip controller_guard items and items without tool name
│   ├── Build sanitized tool response using public_tool_response()
│   │   ├── repo_read → {tool, ok, count, items:[{path, content}]}
│   │   ├── repo_propose_code_edit → {tool, ok, edit_kind, target_file, rationale, operations/diff}
│   │   ├── repo_tree/repo_list_files → {tool, ok, count, entries/paths, stripped local paths}
│   │   └── Other tools → {tool, ok, key:value for each non-empty field}
│   ├── Include Ollama turn metadata and planner decision
│   └── Set payload_location pointer for failed turns (not successful)
│
├── Step 3: Build failed_tool_turns() via _public_tool_turns(expected_ok=False)
│   ├── Same logic as successful but filter to ok=False items
│   └── tool_response set to None in turn structure
│
└── Step 4: Return structured dict
    ├── "contract": description of Ollama done_reason semantics
    ├── "ollama_turns": list of Ollama turn metadata rows
    ├── "successful_tool_turns": list of successful tool turn records
    └── "failed_tool_turns": list of failed tool turn records
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
| `VALIDATION_REJECTIONS.md` | Validation rejection signature tracking, deduplication, and compaction |
| `FINAL_QUALITY_JUDGMENT.md` | Deterministic quality checks, model judge request building, response sanitization |
| `PLANNER_TURN_MEMORY_REFERENCE.md` (this file) | Turn memory construction from history, Ollama turn metadata extraction, successful/failed turn separation for OpenWebUI transport |