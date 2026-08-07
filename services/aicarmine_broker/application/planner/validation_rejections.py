"""Validation rejection signature and prompt compaction helpers."""
from __future__ import annotations

import json
from typing import Any

from ...tool_contract import normalize_tool_name
from ..code_product.state import copyable_example_text
from ..shared.path_tokens import repo_rel_token
from ..prompt.values import prompt_clip_text, text_hash


def _json_hash_or_diagnostic(value: Any) -> tuple[str, dict[str, Any]]:
    try:
        return (
            text_hash(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)),
            {},
        )
    except (TypeError, ValueError, RecursionError) as exc:
        fallback = prompt_clip_text(repr(value), 2000)
        return (
            text_hash(fallback),
            {
                "serialization_error_type": type(exc).__name__,
                "serialization_fallback": "repr_clip",
                "serialization_fallback_chars": len(fallback),
            },
        )


def canonical_invalid_code_product_decision_signature(
    decision: dict[str, Any],
    violations: list[Any] | tuple[Any, ...] | None = None,
) -> dict[str, Any]:
    decision = decision if isinstance(decision, dict) else {}
    if str(decision.get("action") or "tool").strip().lower() != "tool":
        return {}
    tool = normalize_tool_name(str(decision.get("tool") or ""))
    if tool != "repo_propose_code_edit":
        return {}
    args = decision.get("arguments") if isinstance(decision.get("arguments"), dict) else {}
    target = repo_rel_token(args.get("target_file") or args.get("path") or "")
    edit_kind = str(args.get("edit_kind") or "").strip()
    violation_set = {str(v) for v in (violations or []) if str(v)}
    payload_class = ""
    if "repo_propose_code_edit_placeholder_text" in violation_set:
        payload_class = "placeholder_old_new"
    elif "repo_propose_code_edit_missing_unified_diff" in violation_set:
        payload_class = "missing_diff"
    elif "repo_propose_code_edit_old_text_not_from_verified_read" in violation_set:
        payload_class = "old_text_not_verified"
    elif "repo_propose_code_edit_missing_structured_operations" in violation_set:
        payload_class = "missing_structured_operations"
    elif "invalid_code_product_candidate" in violation_set or any(
        str(v).startswith("repo_propose_code_edit_unified_diff_error:")
        for v in violation_set
    ):
        payload_class = "invalid_unified_diff"
    elif edit_kind == "unified_diff":
        old_value = args.get("old_text")
        new_value = args.get("new_text")
        diff_text = args.get("unified_diff")
        if copyable_example_text(old_value) or copyable_example_text(new_value):
            payload_class = "placeholder_old_new"
        elif not isinstance(diff_text, str) or not diff_text.strip():
            payload_class = "missing_diff"
    if not (target and edit_kind and payload_class):
        return {}

    structured_operations_sha256 = ""
    structured_operations_diagnostic: dict[str, Any] = {}
    if args.get("structured_operations") is not None:
        structured_operations_sha256, structured_operations_diagnostic = _json_hash_or_diagnostic(
            args.get("structured_operations")
        )
    normalized_args = {
        "target_file": target,
        "edit_kind": edit_kind,
        "payload_class": payload_class,
        "old_text": prompt_clip_text(args.get("old_text"), 500),
        "new_text": prompt_clip_text(args.get("new_text"), 500),
        "unified_diff_sha256": text_hash(str(args.get("unified_diff") or "")) if args.get("unified_diff") else "",
        "structured_operations_sha256": structured_operations_sha256,
        "rationale": prompt_clip_text(args.get("rationale"), 500),
    }
    args_sha256, args_diagnostic = _json_hash_or_diagnostic(normalized_args)
    signature = {
        "tool": "repo_propose_code_edit",
        "target_file": target,
        "edit_kind": edit_kind,
        "payload_class": payload_class,
        "args_sha256": args_sha256,
    }
    if structured_operations_diagnostic or args_diagnostic:
        signature["signature_diagnostics"] = {
            "schema": "invalid_decision_signature_diagnostics.v1",
            "structured_operations": structured_operations_diagnostic,
            "normalized_args": args_diagnostic,
        }
    return signature


def invalid_decision_signature_key(signature: dict[str, Any]) -> str:
    if not isinstance(signature, dict) or not signature:
        return ""
    return json.dumps(signature, ensure_ascii=False, sort_keys=True, default=str)


def invalid_code_product_decision_signature_from_history_item(item: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {}
    result = item.get("tool_result") if isinstance(item.get("tool_result"), dict) else {}
    existing = result.get("invalid_decision_signature")
    if isinstance(existing, dict) and existing:
        return existing
    violations = result.get("violations") if isinstance(result.get("violations"), list) else []
    rejected = result.get("rejected_decision") if isinstance(result.get("rejected_decision"), dict) else {}
    if not rejected:
        decision = item.get("decision") if isinstance(item.get("decision"), dict) else {}
        if decision.get("action") == "tool":
            rejected = decision
    return canonical_invalid_code_product_decision_signature(rejected, violations)


def invalid_code_product_decision_signature_count(
    history: list[dict[str, Any]],
    signature: dict[str, Any],
) -> int:
    key = invalid_decision_signature_key(signature)
    if not key:
        return 0
    count = 0
    for item in history if isinstance(history, list) else []:
        item_key = invalid_decision_signature_key(
            invalid_code_product_decision_signature_from_history_item(item)
        )
        if item_key == key:
            count += 1
    return count


def disallowed_invalid_code_product_signatures(
    validation_rejections: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    counts: dict[str, dict[str, Any]] = {}
    for row in validation_rejections if isinstance(validation_rejections, list) else []:
        if not isinstance(row, dict):
            continue
        existing = row.get("invalid_decision_signature")
        signature = existing if isinstance(existing, dict) else canonical_invalid_code_product_decision_signature(
            row.get("rejected_decision") if isinstance(row.get("rejected_decision"), dict) else {},
            row.get("violations") if isinstance(row.get("violations"), list) else [],
        )
        key = invalid_decision_signature_key(signature)
        if not key:
            continue
        if key not in counts:
            counts[key] = {"signature": signature, "count": 0}
        counts[key]["count"] = int(counts[key]["count"] or 0) + 1
    out = []
    for item in counts.values():
        if int(item.get("count") or 0) >= 2:
            out.append({
                **item["signature"],
                "repeat_count": int(item.get("count") or 0),
                "rule": "do_not_repeat_invalid_code_product_decision",
            })
    return out


def canonical_block_rejection_signature(decision: dict[str, Any], violations: list[Any] | tuple[Any, ...] | None = None) -> dict[str, Any]:
    """Return a signature identifying block rejection pattern for dedup detection."""
    decision = decision if isinstance(decision, dict) else {}
    if str(decision.get("action") or "").strip().lower() != "block":
        return {}
    reason = str(decision.get("reason") or "").strip()
    violation_set = {str(v) for v in (violations or []) if str(v)}
    if "block_not_allowed_by_evidence_contract" not in violation_set:
        return {}
    return {
        "tool": "block",
        "action": "block",
        "reason": reason[:200],
        "violation": "block_not_allowed_by_evidence_contract",
        "schema": "block_rejection_signature.v1",
    }


def block_decision_signature_from_history_item(item: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {}
    result = item.get("tool_result") if isinstance(item.get("tool_result"), dict) else {}
    existing = result.get("block_rejection_signature")
    if isinstance(existing, dict) and existing:
        return existing
    violations = result.get("violations") if isinstance(result.get("violations"), list) else []
    rejected = result.get("rejected_decision") if isinstance(result.get("rejected_decision"), dict) else {}
    if not rejected:
        decision = item.get("decision") if isinstance(item.get("decision"), dict) else {}
        if decision.get("action") == "block":
            rejected = decision
    return canonical_block_rejection_signature(rejected, violations)


def block_decision_signature_count(history: list[dict[str, Any]], signature: dict[str, Any] | None = None) -> int:
    if not signature:
        sig = canonical_block_rejection_signature({"action": "block", "reason": "evidence_contract_violation"})
    else:
        sig = signature
    key = json.dumps(sig, ensure_ascii=False, sort_keys=True, default=str)
    count = 0
    for item in history if isinstance(history, list) else []:
        item_sig = block_decision_signature_from_history_item(item)
        if item_sig and json.dumps(item_sig, ensure_ascii=False, sort_keys=True, default=str) == key:
            count += 1
    return count


def detect_repeated_identical_sequence(rejection_history: list[dict[str, Any]]) -> dict[str, Any]:
    """Detect when same tool sequence repeats after rejection.
    
    Returns pattern info with suggested alternatives.
    """
    if not isinstance(rejection_history, list):
        return {"pattern_type": "none", "count": 0}
    
    sequences: list[list[str]] = []
    for item in rejection_history:
        if not isinstance(item, dict):
            continue
        decision = item.get("decision") if isinstance(item.get("decision"), dict) else {}
        tool = str(decision.get("tool") or "").strip()
        action = str(decision.get("action") or "").strip()
        sequences.append([action, tool])
    
    # Count sequence repetitions
    seq_counts: dict[str, int] = {}
    for seq in sequences:
        key = "|".join(seq)
        seq_counts[key] = seq_counts.get(key, 0) + 1
    
    # Find most common sequence
    most_common_seq = ""
    most_common_count = 0
    for seq_key, cnt in seq_counts.items():
        if cnt > most_common_count:
            most_common_count = cnt
            most_common_seq = seq_key
    
    # Determine if we should suggest alternatives (2+ identical sequences)
    should_suggest = most_common_count >= 2
    
    # Generate alternative suggestions
    alternatives = []
    if should_suggest:
        current_tools = set(sequences[-1] if sequences else [])
        repo_tools = {"repo_list_files", "repo_read", "repo_search", "repo_semantic_search"}
        planning_tools = {"planner_scratchpad_write", "planner_scratchpad_read"}
        terminal_tools = {"terminal_run_command_wait"}
        
        untried = []
        for cat in [repo_tools, planning_tools, terminal_tools]:
            if not cat.issubset(current_tools):
                for t in cat - current_tools:
                    untried.append({"tool": t, "reason": f"Different category from [{', '.join(sequences[-1])}]; try {t}"})
        alternatives = untried[:5]
    
    return {
        "pattern_type": "identical_sequence" if should_suggest else "single",
        "count": most_common_count,
        "sequence": list(sequences[-1]) if sequences else [],
        "should_suggest_alternatives": should_suggest,
        "suggested_alternatives": alternatives,
    }


def compact_validation_rejections_tail(
    validation_rejections: list[dict[str, Any]],
    *,
    limit: int = 5,
) -> list[dict[str, Any]]:
    compacted: list[dict[str, Any]] = []
    index_by_signature: dict[str, int] = {}
    for item in validation_rejections:
        if not isinstance(item, dict):
            continue
        rejected = item.get("rejected_decision") if isinstance(item.get("rejected_decision"), dict) else {}
        args = rejected.get("arguments") if isinstance(rejected.get("arguments"), dict) else {}
        compact_args: dict[str, Any] = {}
        for key in (
            "target_file",
            "path",
            "edit_kind",
            "old_text",
            "new_text",
            "unified_diff",
            "structured_operations",
            "rationale",
        ):
            if key in args:
                value = args.get(key)
                if isinstance(value, str):
                    compact_args[key] = value if len(value) <= 700 else value[:700] + "...[truncated in rejection digest]"
                else:
                    compact_args[key] = value
        compact_rejected = {
            "action": rejected.get("action"),
            "tool": rejected.get("tool"),
            "arguments": compact_args,
            "reason": str(rejected.get("reason") or "")[:700],
        }
        row = {
            "step": item.get("step"),
            "guard_type": item.get("guard_type"),
            "summary": item.get("summary"),
            "classification": item.get("classification"),
            "semantic_goal_classification": item.get("semantic_goal_classification"),
            "next_instruction": item.get("next_instruction"),
            "required_next_tool_call": (
                item.get("required_next_tool_call")
                if isinstance(item.get("required_next_tool_call"), dict)
                else {}
            ),
            "action_plan_candidate": prompt_clip_text(item.get("action_plan_candidate"), 4000),
            "raw_planner_text_preview": str(item.get("raw_planner_text_preview") or "")[:700],
            "violations": item.get("violations") or [],
            "rejected_decision": {
                k: v for k, v in compact_rejected.items() if v not in (None, "", [], {})
            },
            "invalid_decision_signature": (
                item.get("invalid_decision_signature")
                if isinstance(item.get("invalid_decision_signature"), dict)
                else canonical_invalid_code_product_decision_signature(
                    compact_rejected,
                    item.get("violations") if isinstance(item.get("violations"), list) else [],
                )
            ),
            "repeat_count": 1,
        }
        if not row["invalid_decision_signature"]:
            row.pop("invalid_decision_signature", None)
        signature = json.dumps(
            {
                "guard_type": row.get("guard_type"),
                "violations": row.get("violations"),
                "invalid_decision_signature": row.get("invalid_decision_signature"),
                "rejected_decision": row.get("rejected_decision"),
            },
            sort_keys=True,
            ensure_ascii=False,
            default=str,
        )
        existing = index_by_signature.get(signature)
        if existing is not None:
            compacted[existing]["repeat_count"] = int(compacted[existing].get("repeat_count") or 1) + 1
            compacted[existing]["last_step"] = row.get("step")
            continue
        index_by_signature[signature] = len(compacted)
        compacted.append(row)
    return compacted[-limit:]
