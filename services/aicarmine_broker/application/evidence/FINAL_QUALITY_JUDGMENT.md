# Final Quality Judgment Reference

**Created:** 2026-08-15  
**Purpose:** Complete reference for `final_quality.py` module. This handles deterministic quality checks for repository-analysis final answers, building LLM judge requests, sanitizing model responses, and detecting shallow/speculative claims that violate evidence requirements.

---

## Overview: Two-Tier Quality Assessment

The final quality system provides two complementary assessment mechanisms:

| Mechanism | Function | Purpose |
|-----------|----------|---------|
| **Deterministic checks** (`repo_analysis_final_answer_quality()`) | Rule-based violation detection on final answer text | Fast, deterministic rejection of shallow answers |
| **Model judge request** (`repo_analysis_final_answer_model_quality_request()`) | Builds structured prompt for LLM to evaluate final answer | Semantic evaluation by external model |
| **Response sanitization** (`sanitize_repo_analysis_final_model_quality()`) | Normalizes and validates model judge JSON response | Converts model output into planner-compatible format |

---

## repo_analysis_final_answer_quality()

### Purpose

Deterministically evaluates a repository-analysis final answer against evidence contract rules. Returns violations list and quality metrics.

### Input Parameters

| Parameter | Type | Purpose |
|-----------|------|---------|
| `final_answer` | str | The proposed final answer text from the planner |
| `contract` | dict | Evidence contract with verified reads, coverage status, pending actions |

### Minimum Requirements Calculation

```python
# Based on read note count:
min_chars = 2200 if len(rows) >= 5 else 900
# rows = _read_note_rows(contract) → operational_notes.read_notes + file_memory entries
```

### Path Hit Requirements

```python
# Extract evidence paths from contract:
paths = _evidence_paths(contract)  # read notes + successful_repo_read_paths + validator_admissible paths
pathish_evidence = {p for p in paths if "/" in p or p.endswith((".md", ".py", ".json", ...))}
min_path_hits = min(6, max(3, len(pathish_evidence) // 3))
if len(paths) >= 8:
    min_path_hits = max(min_path_hits, 5)
path_hits = sum(1 for path in paths if path and path in final_answer)
```

### Core Candidate Hit Requirements

```python
# Extract core candidate directories from contract:
core_candidates = contract.get("ranked_core_candidate_dirs") or []
core_paths = [item.get("path") for item in core_candidates]
core_hits = sum(1 for path in core_paths if path and path in final_answer)
min_core_hits = min(2, len(core_paths))
```

### Violation Detection Rules

| Violation Code | Condition | Severity |
|----------------|-----------|----------|
| `repo_analysis_final_empty` | Final answer is empty string | Critical |
| `repo_analysis_final_too_short:N/NNN` | Character count below minimum | Medium |
| `repo_analysis_final_missing_concrete_paths:N/NN` | Path hits below minimum | High |
| `repo_analysis_final_missing_core_candidate_paths:N/NN` | Core candidate hits below minimum | High |
| `repo_analysis_final_missing_workflow_or_entrypoint` | Missing workflow/entrypoint concepts | Medium |
| `repo_analysis_final_missing_limits_or_validation` | Missing limits/validation concepts | Medium |
| `repo_analysis_final_generic_template_language` | Generic phrases with <3200 chars | Low |
| `repo_analysis_final_follow_up_invitation_instead_of_answer` | Follow-up invitations detected via audit | High |
| `evidence_consumed_but_final_too_short` | Speculative terms + evidence exists but answer too short | High |
| `repo_analysis_final_speculative_claims_without_evidence` | Speculative terms + no evidence available | Critical |
| `repo_analysis_final_generic_no_issue_claim_with_shallow_evidence` | Generic "no issues" claim with <8 read notes | Medium |
| `repo_analysis_final_mentions_unverified_paths:PATH1,PATH2,...` | Final cites paths not in verified reads | High |
| `repo_analysis_final_ignores_required_read_or_search_route` | Required pending actions exist but not declared as limited | High |
| `repo_analysis_final_claims_complete_despite_declared_limits` | Claims deep review while declaring partial coverage | Critical |
| `repo_analysis_final_absolute_no_issue_claim_with_partial_coverage` | Absolute no-issue claim with partial coverage | Critical |
| `repo_analysis_final_confuses_intrinsic_rag_missing_with_planner_rag` | Reports RAG missing when repo_semantic_search is available | Medium |
| `repo_analysis_final_absolute_security_verdict_without_code_coverage` | Security verdict without code_security_coverage.verdict_allowed=True | Critical |

### Concept Detection Patterns

The system detects specific concepts in the final answer text using regex patterns:

| Concept | Pattern Examples (English/Italian) | Purpose |
|---------|-----------------------------------|---------|
| workflow/entrypoint | `\bworkflow\b`, `\bflusso\b`, `\bentrypoint\b`, `\bpunto di ingresso\b` | Must mention workflow or entry point |
| limits/validation | `\bproblem`, `\bproble`, `\bverific`, `\bvalidaz`, `\blimit`, `\bvincol`, `\bcopertura`, `\bcoverage` | Must discuss limits, validation, or coverage |
| absolute no-issue | `\bno\s+(?:critical\s+)?(?:security\s+)?(?:issues|vulnerabilities|flaws)\b`, `\bnessun[ae]?\s+critic` | Detects "no issues found" claims |
| absolute repo no-issue | `\bno\s+(?:semantic\s+)?(?:drift|duplication)`, `\bnessun[ae]?\s+duplicazione` | Detects "no drift/duplication" claims |
| partial/limited coverage | `\breview\s+parzial`, `\bcopertura\s+parzial`, `\blimits?\s+of\s+coverage\b` | Detects declared limitations |
| deep/complete review claim | `\breview\s+complet`, `\baudit\s+complet`, `\bhho completato la review` | Detects over-claiming of completeness |

### Output Structure

```python
{
    "ok": True/False,  # Whether final answer passes quality checks
    "violations": [...],  # List of violation codes
    "metrics": {
        "chars": len(stripped),
        "min_chars": min_chars,
        "path_hits": path_hits,
        "min_path_hits": min_path_hits,
        "core_candidate_hits": core_hits,
        "core_candidate_paths": [...],  # Up to 8 core paths
        "evidence_path_count": len(paths),
        "read_note_count": len(rows),
        "unverified_path_tokens": [...],  # Paths in final but not verified
        "final_audit_red_flags": {...},  # From audit_guidance module
        "hard_pending_read_or_search_actions": [...],  # Up to 4 required actions
    },
    "required_next_output_sections": [...],  # Sections missing from final answer
    "required_next_missing_evidences": [...],  # Concrete paths needing verification
    "required_next_progress": str,  # Instruction for next planner turn if rejected
}

# required_next_progress when rejected:
"Final answer rejected as too shallow for repository analysis. Return action=final with a richer final_answer grounded in operational_notes.read_notes and file_memory: cover workflow/entrypoint, core candidates, concrete file roles, validation/problems or limits, and cite concrete repo-relative paths. Do not call tools unless a new evidence gap is named."
```

---

## _repo_content_analysis_summary()

### Purpose

Generates a comprehensive summary of repo content analysis from verified reads. This helps the model judge assess analysis depth and adjust verdict strictness accordingly.

### Analysis Depth Classification

| Verified Reads Count | Depth Level | Meaning |
|---------------------|-------------|---------|
| 0-1 | `minimal` | Very shallow coverage |
| 2-4 | `partial` | Limited scope |
| 5-9 | `moderate` | Moderate coverage |
| 10-19 | `substantial` | Good coverage |
| 20+ | `comprehensive` | Deep coverage |

### Content Pattern Extraction

The system extracts patterns from verified content previews:

| File Type | Patterns Extracted | Stored In |
|-----------|-------------------|-----------|
| `.py` files | Class names (`class X`), function names (`def Y`), imports (`import Z`) | `python_classes_sample`, `python_functions_sample`, `python_imports_sample` |
| `.md` files | Markdown headings (`# Heading`) | `markdown_topics_sample` |
| Config files (`.yaml`, `.json`, `.toml`) | Top-level keys (`key:`) | `config_keys_sample` |

### Output Structure

```python
{
    "schema": "repo_content_analysis_summary.v1",
    "analysis_depth": "minimal"|"partial"|"moderate"|"substantial"|"comprehensive",
    "total_files_read": N,
    "total_lines_analyzed": N,
    "total_chars_analyzed": N,
    "file_types": {
        "python": N,
        "markdown": N,
        "config": N,
        "other": N,
    },
    "coverage": {
        "covered": N,
        "missing": N,
        "candidates": N,
    },
    "verdict_guidance": [...],  # Human-readable guidance for verdict
    "content_analysis": {
        "python_classes_sample": [...],  # Up to 10 unique classes
        "python_functions_sample": [...],  # Up to 10 unique functions
        "python_imports_sample": [...],  # Up to 10 unique imports
        "markdown_topics_sample": [...],  # Up to 10 unique headings
        "config_keys_sample": [...],  # Up to 10 unique keys
    },
    "judge_expanded_verdicts": True,  # Tells judge to use expanded analysis
}
```

---

## repo_analysis_final_answer_model_quality_request()

### Purpose

Builds the structured prompt for sending final answer evaluation to an external LLM model. This is the "model judge" request.

### System Prompt

```
You are the final-quality judge for a repository-analysis agentic loop. Return strict JSON only. You decide whether the proposed final answer is acceptable or whether the planner must continue. The controller will only enforce your JSON. Do not call hidden preplanner RAG. If more semantic discovery is needed, route to the normal planner tool repo_semantic_search. If a concrete file/window is missing, route to repo_read. Do not invent reads or claim coverage not present in the contract.
```

### User Payload Structure

```python
{
    "schema": "repo_analysis_final_model_quality_request.v1",
    "task": "judge_repo_analysis_final_answer_or_route_next_tool",
    "goal": str(goal),  # Original task goal
    "final_answer": clipped(final_answer, 16000 chars),
    "contract_summary": _final_quality_contract_summary(contract),  # Compact evidence contract
    "repo_content_analysis": _repo_content_analysis_summary(contract),  # Content analysis summary
    "semantic_audit_guidance": audit_guidance_for_goal(goal),  # Goal-specific guidance
    "final_quality_judge_role_guidance": role_guidance_for_goal("final_quality_judge", goal),  # Role guidance
    "goal_requests_semantic_audit": bool,  # Whether goal requires semantic audit
    "decision_rules": [...],  # 20+ decision rules for judge to follow
    "judge_expanded_verdicts": True,
    "allowed_required_next_tools": ["list", "of", "tools"],
    "required_json_shape": {...},  # Expected JSON output shape
}
```

### Decision Rules (18 Rules)

| Rule | Description |
|------|-------------|
| 1 | Accept only if final answer is grounded in verified repo evidence and answers the goal |
| 2 | Reject if it declares unread/truncated/missing files that are needed to answer the goal |
| 3 | Reject if it claims complete analysis while naming unresolved coverage limits |
| 4 | Reject if it says no duplication, no semantic drift, or no regression risk from shallow owner reads |
| 5 | Reject if it uses speculative language such as probably/probabilmente for concrete code ownership claims |
| 6 | Reject if it asks the user whether to generate a final, diff, or patch instead of answering the current request |
| 7 | Reject if it cites repo-relative paths not present in verified reads, admissible read paths, or owner candidates |
| 8 | Reject if candidate_next_actions or required_next_tool_call still names a required repo_read/repo_semantic_search route and the final does not explicitly state a bounded limitation |
| 9 | Reject if it reports global RAG missing only because intrinsic_context had no retrieved_rag_chunks; repo_semantic_search is the planner RAG tool |
| 10 | Do not choose required_next_tool_call for a repo_read/search route already present in verified_content_reads, successful_repo_read_paths, or stale_required_next_tool_calls |
| 11 | If broad discovery is still needed, choose required_next_tool_call.tool=repo_semantic_search with a concrete query |
| 12 | If specific unread/truncated paths are named, choose required_next_tool_call.tool=repo_read for those paths or a focused window |
| 13 | required_next_missing_evidences is path-only: include only concrete repo-relative paths already present in contract_summary path fields |
| 14 | Do not ask to repo_read files already present in verified_content_reads or successful_repo_read_paths |
| 15 | For headings, metrics, missing sections, or conceptual gaps, use required_next_progress/required_next_output_sections, or repo_semantic_search with a concrete query |
| 16 | If enough evidence exists but the prose is inconsistent, reject and require a corrected final without a tool call |
| 17 | Use repo_content_analysis to assess analysis depth (minimal/partial/moderate/substantial/comprehensive) and adjust verdict strictness accordingly |
| 18 | When file_types shows Python files analyzed, verify code-level claims against actual source evidence |

### Allowed Route Tools and Arguments

| Tool | Allowed Arguments |
|------|------------------|
| `repo_read` | path, paths, line, line_start, line_count, start_line, end_line, before, after, max_chars |
| `repo_semantic_search` | query, path, limit, top_k, max_results, candidate_limit, rerank, reindex, max_chunk_chars |
| `repo_rg_search` | query, pattern, path, max_results, context |
| `repo_search` | query, pattern, symbol, path, max_results |
| `repo_list_files` | path, limit, suffix, glob, max_files |

---

## sanitize_repo_analysis_final_model_quality()

### Purpose

Normalizes and validates the model judge response. Invalid model output rejects final answer quality check.

### Input

Model judge JSON response with fields: decision, ok, violations, required_next_progress, required_next_tool_call, confidence, etc.

### Validation Logic

```python
# Decision must be one of: accept, reject, continue_required
decision = str(value.get("decision") or "").strip().lower()
if decision not in {"accept", "reject", "continue_required"}:
    return {**base, "raw_decision": ...}  # Reject with invalid code

# Violations extracted from list:
violations = [code for code in (_violation_code(item) for item in violation_items) if code]

# ok = True only when decision == "accept" and value.get("ok") is not False
ok = decision == "accept" and value.get("ok") is not False

# required_next_tool_call sanitized via _sanitize_required_next_tool_call():
required_next_tool_call = _sanitize_required_next_tool_call(value.get("required_next_tool_call"), contract, diagnostics)
# Validates tool is in allowed set, arguments match allowed args, query/pattern/symbol present for search tools, paths are concrete admissible repo paths

# required_next_output_sections sanitized:
required_next_output_sections = _sanitize_required_next_output_sections(value.get("required_next_output_sections"))
# Deduplicated list of strings, up to 12 items

# required_next_missing_evidences sanitized:
required_next_missing_evidences = _sanitize_required_next_missing_evidences(value.get("required_next_missing_evidences"), contract)
# Concrete repo-relative paths from allowlist, up to 24 items
```

### Output Structure

```python
{
    "schema": "repo_analysis_final_model_quality.v1",
    "model_decision_available": True/False,  # Whether valid model response received
    "ok": True/False,  # Whether final answer passes quality check
    "decision": "accept"|"reject"|"continue_required"|"invalid",
    "violations": [...],  # List of violation codes (empty if ok=True)
    "required_next_progress": clipped(1000 chars),
    "required_next_tool_call": {...} or {},  # Sanitized tool call or empty
    "confidence": value.get("confidence"),  # Model confidence score
    "required_next_output_sections": [...],  # Missing sections
    "required_next_missing_evidences": [...],  # Missing evidence paths
    "raw_decision": compacted(value, text_limit=500, list_limit=6),  # Raw model output for debugging
}

# Invalid response defaults:
{
    "schema": "repo_analysis_final_model_quality.v1",
    "model_decision_available": False,
    "ok": False,
    "decision": "invalid",
    "violations": ["repo_analysis_final_model_quality_invalid"],
    "required_next_progress": "Final answer quality requires a valid model judge decision. Retry final quality or continue with an evidence-bound repo_semantic_search/repo_read if a concrete gap is known.",
}
```

---

## _sanitize_required_next_tool_call()

### Purpose

Validates and normalizes required_next_tool_call from model judge response. Rejects invalid tool calls.

### Validation Checks

| Check | Condition for Rejection | Diagnostic Recorded |
|-------|----------------------|---------------------|
| Tool not in allowed set | `tool` not in {repo_read, repo_semantic_search, repo_rg_search, repo_search, repo_list_files} | "final-quality proposed a required_next_tool_call tool outside the allowed route set" |
| Missing query/pattern/symbol | Search tool without query, pattern, symbol, needle, or text | "{tool} required_next_tool_call was missing query, pattern, symbol, needle, or text" |
| Non-concrete query | Query looks like heading/metric/violation label/path token | "{tool} query looked like a heading, metric, violation label, or path token" |
| Invalid path for search | Path not in known paths or dirs | Diagnostic recorded, path removed from args |
| Missing path/paths for repo_read | `repo_read` without path or paths field | "repo_read required_next_tool_call was missing path or paths" |
| No valid admissible paths | All paths in repo_read are invalid/not admissible | "repo_read required_next_tool_call contained no concrete unread admissible repo paths" |
| Invalid list_files path | Path is prose/metric or not a known directory | "repo_list_files path was not a known concrete repo directory" |

### Allowed Final Quality Route Tools and Args

```python
_ALLOWED_FINAL_QUALITY_ROUTE_TOOLS = {
    "repo_read",
    "repo_semantic_search",
    "repo_rg_search",
    "repo_search",
    "repo_list_files",
}

_ALLOWED_FINAL_QUALITY_ROUTE_ARGS = {
    "repo_read": {"path", "paths", "line", "line_start", "line_count", "start_line", "end_line", "before", "after", "max_chars"},
    "repo_semantic_search": {"query", "path", "limit", "top_k", "max_results", "candidate_limit", "rerank", "reindex", "max_chunk_chars"},
    "repo_rg_search": {"query", "pattern", "path", "max_results", "context"},
    "repo_search": {"query", "pattern", "symbol", "path", "max_results"},
    "repo_list_files": {"path", "limit", "suffix", "glob", "max_files"},
}
```

---

## repo_analysis_final_answer_too_shallow()

### Purpose

Simple boolean check for whether a final answer is too shallow. Wraps `repo_analysis_final_answer_quality()` and checks the `ok` field.

```python
def repo_analysis_final_answer_too_shallow(final_answer, contract):
    return not repo_analysis_final_answer_quality(final_answer, contract).get("ok")
```

**Usage:** Called by validator to determine if final answer needs rejection/rewrite.

---

## Quality Assessment Flow in Validator Logic

### Step 1: Deterministic Check

When the planner produces a final answer, the validator first runs deterministic quality checks via `repo_analysis_final_answer_quality()`. This detects violations like missing concrete paths, shallow content, generic template language, speculative claims without evidence, etc.

If `violations` list is non-empty, the answer is rejected immediately with `required_next_progress` instruction for the planner to produce a richer answer.

### Step 2: Model Judge Request (if deterministic check passes)

If deterministic checks pass but the system wants semantic evaluation, the validator builds a model judge request via `repo_analysis_final_answer_model_quality_request()`. This sends the final answer + contract summary + content analysis + decision rules to an external LLM.

### Step 3: Sanitize Model Response

When the model judge response arrives, it's sanitized via `sanitize_repo_analysis_final_model_quality()`. Invalid responses default to rejection. Valid responses extract decision, violations, required next tool call, missing evidence paths, and output sections.

### Step 4: Enforce Quality Decision

The sanitized quality result is enforced:
- If `ok=True` and `decision="accept"` → Final answer accepted, job completes
- If `ok=False` or `decision="reject"` → Planner must continue with required_next_tool_call or rewrite final answer
- Violations are stored in evidence contract for tracking
- required_next_missing_evidences provides concrete paths needing verification

---

## Quick Reference: Final Quality Assessment Flow Diagram

```
planner produces final_answer text
│
├── Step 1: Deterministic quality check
│   ├── Calculate min_chars based on read note count (900 or 2200)
│   ├── Calculate min_path_hits based on evidence path count
│   ├── Count path hits and core candidate hits in final_answer text
│   ├── Detect concept presence (workflow, limits, coverage, etc.)
│   ├── Run audit red flag detection
│   ├── Check for unverified path tokens in final answer
│   ├── Check for partial coverage + absolute no-issue claim contradiction
│   └── Return {ok, violations, metrics, required_next_progress}
│
├── Step 2: If ok=False → Reject final answer
│   ├── Set validation rejection with violation codes
│   ├── Provide required_next_progress instruction
│   └── Planner must produce richer final answer from verified evidence
│
├── Step 3: If ok=True → Build model judge request (optional)
│   ├── Generate _final_quality_contract_summary(contract)
│   ├── Generate _repo_content_analysis_summary(contract)
│   ├── Include semantic_audit_guidance and role_guidance for goal
│   ├── List 18 decision rules for judge to follow
│   └── Send to external LLM for evaluation
│
├── Step 4: Sanitize model judge response
│   ├── Validate decision is accept/reject/continue_required
│   ├── Extract violation codes via _violation_code()
│   ├── Sanitize required_next_tool_call (validate tool, args, query, paths)
│   ├── Sanitize required_next_output_sections (deduplicated strings)
│   ├── Sanitize required_next_missing_evidences (concrete repo-relative paths)
│   └── Return {ok, decision, violations, required_next_*, raw_decision}
│
└── Step 5: Enforce sanitized quality result
    ├── ok=True + decision="accept" → Final accepted, job completes
    ├── ok=False or decision="reject" → Continue with required_next_tool_call
    ├── Violations tracked in evidence contract for monitoring
    └── required_next_missing_evidences provides concrete verification targets
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
| `FINAL_QUALITY_JUDGMENT.md` (this file) | Deterministic quality checks, model judge request building, response sanitization for repository-analysis final answers |