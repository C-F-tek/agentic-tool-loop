"""Planner repair, Vulkan repair, and replan specialist helpers extracted from planner.py.

This module owns:
- _raw_planner_text_classification
- _raw_planner_text_has_explicit_tool_alias_invocation
- _raw_planner_text_has_many_json_examples
- _raw_planner_text_has_valid_embedded_json_with_prose
- _raw_planner_text_retries_on_gpu1
- _raw_planner_text_looks_like_tool_request
- _should_retry_incomprehensible_planner_output
- _is_unrecoverable_plain_text_planner_output
- _compact_repair_history
- _compact_vulkan_repair_evidence_contract
- _evidence_contract_storage_summary
- _controller_guard_contract_overlay
- _validation_needs_replan_specialist
"""
from __future__ import annotations

import json
import re
from typing import Any


# ---------------------------------------------------------------------------
# Raw planner text classification
# ---------------------------------------------------------------------------

def _list_or_empty(value: Any) -> list:
    """Safely return a list or empty list."""
    if isinstance(value, list):
        return value
    return []


def _dict_or_empty(value: Any) -> dict:
    """Safely return a dict or empty dict."""
    if isinstance(value, dict):
        return value
    return {}


def _prompt_clip_text(text: str, limit: int = 12000) -> str:
    """Clip text to limit characters."""
    if not isinstance(text, str):
        return ""
    return text[:limit]


def _prompt_clip_value(value: Any, *, text_limit: int = 12000, list_limit: int = 8) -> Any:
    """Clip a value (text or list) to specified limits."""
    if isinstance(value, list):
        clipped = [str(v) for v in value[:list_limit]]
        return clipped
    return _prompt_clip_text(str(value or ""), text_limit)


def _text_hash(text: str) -> str:
    """Compute a short hash of text content."""
    import hashlib
    return hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()[:16]


def _normalize_tool_name(value: str) -> str:
    """Normalize tool name to canonical form."""
    return str(value or "").strip().lower()


def _raw_planner_text_classification(text: str) -> str:
    """Classify raw planner output for planner retry vs GPU0 repair.

    ``plain_text_non_json`` and ``mixed_prose_with_embedded_json`` are handled by
    asking the planner to repeat a pure JSON decision. Vulkan/GPU0 repair is
    reserved for JSON-shaped or tool-call shaped emissions that are broken but
    still structurally related to the loop protocol.
    """
    raw = str(text or "")
    stripped = raw.strip()
    if not stripped:
        return "empty"
    if _raw_planner_text_has_many_json_examples(stripped):
        return "long_mixed_json_examples"
    if _raw_planner_text_has_valid_embedded_json_with_prose(stripped):
        return "mixed_prose_with_embedded_json"
    if re.fullmatch(r"```(?:json|JSON)?\s*\r?\n.*?\r?\n```", stripped, re.S):
        return "markdown_fenced_json_non_json"
    low = raw.lower()
    if _raw_planner_text_has_explicit_tool_alias_invocation(raw):
        return "tool_like_malformed"
    if re.search(r"</?JupyterNotebookCell\b", raw, re.I):
        return "native_notebook_cell_output"
    if stripped.startswith("{") or stripped.startswith("["):
        return "corrupt_json"
    if re.search(r"```(?:json|JSON)?\s*[\r\n{]", raw):
        return "corrupt_json"
    if "{" in raw or "}" in raw:
        if re.search(r'["\']?(?:action|tool|arguments|final_answer|reason)["\']?\s*[:=]', raw, re.I):
            return "corrupt_json"
    if re.search(r'["\']?(?:action|tool|arguments)["\']?\s*[:=]', raw, re.I):
        return "tool_like_malformed"
    return "plain_text_non_json"


def _raw_planner_text_has_explicit_tool_alias_invocation(text: str) -> bool:
    """Detect explicit pseudo-tool invocations such as ``SAVE_FILE: ...``."""
    raw = str(text or "")
    if not raw.strip():
        return False
    generic_aliases = {
        "capabilities", "tools", "status", "diff", "search", "grep", "rg",
        "read", "patch", "edit", "validate", "validation",
        "command", "run", "compile", "terminal", "tree", "directory",
        "files",
    }
    aliases = set()
    for alias_text in sorted(generic_aliases, key=len, reverse=True):
        if alias_text in generic_aliases:
            continue
        if "_" in alias_text or alias_text.startswith(("repo", "terminal", "memory", "scratchpad")):
            aliases.add(alias_text)
    for alias in sorted(aliases, key=len, reverse=True):
        if re.search(rf"(?im)^\s*<?{re.escape(alias)}\s*(?:[:=(]|\{{|\[)", raw):
            return True
    return False


def _raw_planner_text_has_many_json_examples(text: str) -> bool:
    """Detect excessive JSON examples in planner output."""
    raw = str(text or "")
    low = raw.lower()
    fenced_json_count = len(re.findall(r"```(?:json|JSON)?\s*\r?\n\s*[\[{]", raw))
    if fenced_json_count >= 4:
        return True
    example_marker_count = sum(
        low.count(marker)
        for marker in (
            "出力の例",
            "output example",
            "example ",
            "esempio",
            "ejemplo",
            "例",
        )
    )
    if len(raw) >= 4096 and fenced_json_count >= 2 and example_marker_count >= 2:
        return True
    if len(raw) >= 4096 and fenced_json_count >= 2:
        repeated_tool_mentions = sum(
            low.count(f'"tool": "{tool.lower()}"') + low.count(f'"tool":"{tool.lower()}"')
            for tool in ("repo_read", "repo_search", "repo_tree", "repo_list_files")
        )
        return repeated_tool_mentions >= 3
    return False


def _raw_planner_text_has_valid_embedded_json_with_prose(text: str) -> bool:
    """Detect valid JSON embedded in prose without extracting it as a decision."""
    raw = str(text or "").strip()
    if not raw:
        return False
    fenced = list(re.finditer(r"```(?:json|JSON)?\s*\r?\n(?P<body>.*?)\r?\n```", raw, re.S))
    if len(fenced) == 1:
        match = fenced[0]
        try:
            json.loads(match.group("body"))
        except json.JSONDecodeError:
            pass
        else:
            outside = (raw[: match.start()] + raw[match.end() :]).strip()
            return bool(outside)
    if raw.startswith("{") or raw.startswith("["):
        return False
    decoder = json.JSONDecoder()
    spans: list[tuple[int, int]] = []
    for match in re.finditer(r"[\[{]", raw):
        try:
            decoded, end = decoder.raw_decode(raw[match.start() :])
        except json.JSONDecodeError:
            continue
        if isinstance(decoded, dict):
            spans.append((match.start(), match.start() + end))
    if len(spans) != 1:
        return False
    start, end = spans[0]
    outside = (raw[:start] + raw[end:]).strip()
    return bool(outside)


def _raw_planner_text_retries_on_gpu1(text: str) -> bool:
    """Check if text should retry on GPU1 (planner CUDA lane)."""
    classification = _raw_planner_text_classification(text)
    return classification in {
        "plain_text_non_json",
        "mixed_prose_with_embedded_json",
        "markdown_fenced_json_non_json",
        "long_mixed_json_examples",
        "native_notebook_cell_output",
    }


def _raw_planner_text_looks_like_tool_request(text: str) -> bool:
    """Detect malformed-but-recognizable tool/JSON requests for GPU0 repair."""
    classification = _raw_planner_text_classification(text)
    return classification in {"corrupt_json", "tool_like_malformed"}


# ---------------------------------------------------------------------------
# Retry budget logic
# ---------------------------------------------------------------------------

def _should_retry_incomprehensible_planner_output(
    decision: dict[str, Any],
    history: list[dict[str, Any]],
    retry_limit: int,
) -> bool:
    """Retry only raw non-JSON planner output, without inventing a controller action."""
    decision = decision if isinstance(decision, dict) else {}
    if str(decision.get("action") or "").strip().lower() != "block":
        return False
    reason = str(decision.get("reason") or "")
    retryable_reason = (
        reason == "INVALID_PLANNER_OUTPUT_NON_JSON_PURE"
        or reason.startswith("PLANNER_DEGENERATE_OUTPUT")
        or "timeout" in reason.lower()
        or "non_json" in reason.lower()
        or "no_json" in reason.lower()
        or "non-json" in reason.lower()
    )
    if not retryable_reason:
        return False
    raw_planner_text = str(
        decision.get("raw_planner_text")
        or decision.get("raw_planner_text_preview")
        or decision.get("partial_content")
        or ""
    )
    if not raw_planner_text.strip():
        return False
    if not _raw_planner_text_retries_on_gpu1(raw_planner_text):
        return False
    if int(retry_limit or 0) <= 0:
        return False
    # Count consecutive planner-repeat streak from history tail
    count = 0
    for item in reversed(history if isinstance(history, list) else []):
        if not isinstance(item, dict):
            break
        result = item.get("tool_result") if isinstance(item.get("tool_result"), dict) else {}
        guard_type = str(result.get("guard_type") or "")
        if guard_type in {"planner_retry_required", "planner_memory_false_unavailable_claim"}:
            count += 1
            continue
        break
    return count < int(retry_limit)


def _is_unrecoverable_plain_text_planner_output(
    decision: dict[str, Any],
    history: list[dict[str, Any]],
    retry_limit: int,
) -> bool:
    """Check if planner output is unrecoverable plain text."""
    decision = decision if isinstance(decision, dict) else {}
    if str(decision.get("action") or "").strip().lower() != "block":
        return False
    raw_planner_text = str(
        decision.get("raw_planner_text")
        or decision.get("raw_planner_text_preview")
        or decision.get("partial_content")
        or ""
    )
    if not raw_planner_text.strip():
        return False
    if not _raw_planner_text_retries_on_gpu1(raw_planner_text):
        return False
    reason = str(decision.get("reason") or "").lower()
    relevant_reason = (
        "invalid_planner_output_non_json" in reason
        or "non-json" in reason
        or "non_json" in reason
        or "no_json" in reason
        or "degenerate" in reason
        or "timeout" in reason
    )
    if not relevant_reason:
        return False
    if int(retry_limit or 0) > 0:
        # Count consecutive streak from history tail
        count = 0
        for item in reversed(history if isinstance(history, list) else []):
            if not isinstance(item, dict):
                break
            result = item.get("tool_result") if isinstance(item.get("tool_result"), dict) else {}
            guard_type = str(result.get("guard_type") or "")
            if guard_type in {"planner_retry_required", "planner_memory_false_unavailable_claim"}:
                count += 1
                continue
            break
        return count >= int(retry_limit)
    return True


# ---------------------------------------------------------------------------
# Compact repair helpers
# ---------------------------------------------------------------------------

def _compact_repair_history(history: list[dict[str, Any]], limit: int = 8) -> list[dict[str, Any]]:
    """Compact history for Vulkan repair payload."""
    rows: list[dict[str, Any]] = []
    for item in (history or [])[-limit:]:
        if not isinstance(item, dict):
            continue
        decision = _dict_or_empty(item.get("decision"))
        result = _dict_or_empty(item.get("tool_result"))
        rows.append({
            "step": item.get("step"),
            "decision": {
                k: decision.get(k)
                for k in ("action", "tool", "arguments", "reason", "final_answer")
                if decision.get(k) not in (None, "", [], {})
            },
            "tool_result": {
                k: result.get(k)
                for k in ("tool", "ok", "summary", "path", "count", "total_matches", "truncated", "violations")
                if result.get(k) not in (None, "", [], {})
            },
        })
    return rows


def _compact_vulkan_repair_evidence_contract(contract: dict[str, Any]) -> dict[str, Any]:
    """Compact evidence contract for Vulkan repair payload."""
    if not isinstance(contract, dict):
        return {}
    compact: dict[str, Any] = {"schema": "vulkan_repair_evidence_contract.v1"}
    for key in (
        "semantic_goal_classification",
        "goal_requests_code_product",
        "goal_requires_code_product_report",
        "goal_requests_apply",
        "target_kind",
        "resolved_goal_file",
        "resolved_goal_scope",
        "successful_repo_read_count",
        "verified_content_read_count",
        "minimum_read_coverage",
        "coverage_satisfied",
        "covered_owner_paths",
        "missing_owner_paths",
        "planner_may_choose_final",
        "required_next_progress",
    ):
        value = contract.get(key)
        if value not in (None, "", [], {}):
            compact[key] = _prompt_clip_value(value, text_limit=260, list_limit=4)
    for key in (
        "known_paths_from_latest_repo_list_files",
        "successful_repo_read_paths",
        "read_admissible_paths",
        "validator_admissible_repo_read_paths",
        "failed_repo_read_paths",
        "failed_repo_list_files_paths",
    ):
        value = contract.get(key)
        if value not in (None, "", [], {}):
            compact[key] = _prompt_clip_value(value, text_limit=140, list_limit=16)
    for key in (
        "code_product_contract",
        "finalization_contract",
        "core_discovery_status",
    ):
        value = contract.get(key)
        if value not in (None, "", [], {}):
            compact[key] = _prompt_clip_value(value, text_limit=260, list_limit=4)
    code_contract = contract.get("code_product_contract")
    if isinstance(code_contract, dict) and code_contract.get("replan_role_guidance"):
        compact["code_product_replan_role_guidance"] = _prompt_clip_value(
            code_contract.get("replan_role_guidance"),
            text_limit=500,
            list_limit=6,
        )
    candidates = contract.get("candidate_next_actions")
    if isinstance(candidates, list) and candidates:
        compact["candidate_next_actions"] = _prompt_clip_value(
            candidates,
            text_limit=260,
            list_limit=4,
        )
    rejections = contract.get("validation_rejections_tail")
    if isinstance(rejections, list) and rejections:
        compact["validation_rejections_tail"] = _prompt_clip_value(
            rejections,
            text_limit=260,
            list_limit=4,
        )
    return _prompt_clip_value(compact, text_limit=500, list_limit=16)


# ---------------------------------------------------------------------------
# Evidence contract storage and overlay
# ---------------------------------------------------------------------------

def _evidence_contract_storage_summary(contract: dict[str, Any]) -> tuple[dict[str, Any], int, str]:
    """Return (summary_dict, char_count, sha256) for evidence contract."""
    if not isinstance(contract, dict):
        return {}, 0, ""
    compact = {k: v for k, v in contract.items() if v not in (None, "", [], {})}
    text = json.dumps(compact, ensure_ascii=False, default=str)
    chars = len(text)
    import hashlib
    sha = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    return compact, chars, sha


def _controller_guard_contract_overlay(contract: dict[str, Any]) -> dict[str, Any]:
    """Persist only turn-control fields needed to rebuild the next planner contract."""
    contract = _dict_or_empty(contract)
    overlay: dict[str, Any] = {}
    for key in (
        "planner_cuda_rewrite_required",
        "final_rewrite_latch",
        "planner_final_quality_reject_count",
        "planner_may_choose_final",
        "planner_may_choose_block",
        "required_next_missing_evidences",
        "required_next_output_sections",
        "invalid_required_next_tool_call_paths",
        "invalid_required_next_tool_call_query",
        "invalid_required_next_tool_call_reason",
        "required_next_tool_call_validated",
        "required_next_tool_call_validation_source",
        "stale_required_next_tool_calls",
    ):
        if key not in contract:
            continue
        value = contract.get(key)
        if isinstance(value, (bool, int)):
            overlay[key] = value
        elif isinstance(value, str) and value.strip():
            overlay[key] = _prompt_clip_text(value, 2000)
        elif isinstance(value, list) and value:
            overlay[key] = value[:20]
        elif isinstance(value, dict) and value:
            overlay[key] = value

    progress = str(contract.get("required_next_progress") or "").strip()
    if progress:
        overlay["required_next_progress"] = _prompt_clip_text(progress, 4000)

    required_call = _dict_or_empty(contract.get("required_next_tool_call"))
    if required_call:
        overlay["required_next_tool_call"] = required_call

    candidate_next_actions = _list_or_empty(contract.get("candidate_next_actions"))
    if candidate_next_actions:
        overlay["candidate_next_actions"] = candidate_next_actions[:6]

    final_contract = _dict_or_empty(contract.get("finalization_contract"))
    if final_contract:
        overlay["finalization_contract"] = {
            key: final_contract.get(key)
            for key in (
                "final_allowed",
                "planner_may_choose_final",
                "planner_may_choose_block",
                "reason",
            )
            if key in final_contract and final_contract.get(key) not in (None, "", [], {})
        }
    return overlay


# ---------------------------------------------------------------------------
# Replan specialist validation
# ---------------------------------------------------------------------------

_REPLAN_SPECIALIST_ROUTE_TOOLS = frozenset({
    "repo_read",
    "repo_semantic_search",
    "repo_rg_search",
    "repo_search",
    "repo_list_files",
    "planner_scratchpad_read",
})


def _validation_needs_replan_specialist(
    violations: list[Any],
    contract: dict[str, Any],
    decision: dict[str, Any],
) -> bool:
    """Check if validator needs replan specialist intervention."""
    text = " ".join(str(value or "") for value in violations).lower()
    code_contract = _dict_or_empty(contract.get("code_product_contract"))
    tool = str(decision.get("tool") or "").strip()
    if code_contract.get("required") or code_contract.get("route_shift_after_payload_rejection"):
        return True
    if tool in {"repo_propose_code_edit", "planner_scratchpad_write", "planner_scratchpad_read"} and any(
        token in text
        for token in (
            "code_product",
            "repo_propose_code_edit",
            "planner_scratchpad",
            "support",
            "ready_without_complete_payload",
        )
    ):
        return True
    return any(
        token in text
        for token in (
            "planner_repeated_invalid_code_product_decision",
            "invalid_code_product_candidate",
            "code_product_route_shift_required",
            "support_subturn_validation_failed",
            "repo_read_window_already_successful_without_progress",
            "planner_scratchpad_window_already_successful_without_progress",
            "repo_read_already_successful",
            "required_next_tool_call_pending",
            "required_next_tool_call_from_previous_guard",
            "ignores_pending_actions",
            "inconsistent_flow_mapping",
            "duplicate_window",
        )
    )