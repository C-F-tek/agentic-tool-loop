"""Operator-only extraction of the payload sent toward OpenWebUI."""

from __future__ import annotations

import hashlib
import json
from typing import Any


SCHEMA = "planner_payload_lab.v1"
DEFAULT_SUMMARY_TEXT_CHARS = 4000
DEFAULT_STEP_SUMMARY_LIMIT = 80
DEFAULT_CODE_PRODUCT_LIMIT = 40


def bounded_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = default
    return max(minimum, min(parsed, maximum))


def _clip(value: Any, limit: int = DEFAULT_SUMMARY_TEXT_CHARS) -> str:
    text = str(value or "")
    if len(text) <= limit:
        return text
    return text[:limit] + f"... <truncated {len(text) - limit} chars>"


def _json_hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:16]


def _parse_jsonish(value: Any) -> tuple[Any, dict[str, Any]]:
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except Exception as exc:
            return value, {
                "parse_ok": False,
                "raw_type": "str",
                "error_type": type(exc).__name__,
                "error": str(exc)[:1000],
            }
        return decoded, {"parse_ok": True, "raw_type": "str", "decoded_type": type(decoded).__name__}
    return value, {"parse_ok": True, "raw_type": type(value).__name__, "decoded_type": type(value).__name__}


def _iter_dicts(value: Any, *, path: str = "$", depth: int = 0, max_depth: int = 8):
    if depth > max_depth:
        return
    if isinstance(value, dict):
        yield path, value
        for key, item in value.items():
            yield from _iter_dicts(item, path=f"{path}.{key}", depth=depth + 1, max_depth=max_depth)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _iter_dicts(item, path=f"{path}[{index}]", depth=depth + 1, max_depth=max_depth)


def _code_candidate_from_dict(source_path: str, item: dict[str, Any]) -> dict[str, Any] | None:
    target_file = str(item.get("target_file") or item.get("path") or item.get("file") or "").strip()
    unified_diff = item.get("unified_diff") if isinstance(item.get("unified_diff"), str) else ""
    old_text = item.get("old_text") if isinstance(item.get("old_text"), str) else ""
    new_text = item.get("new_text") if isinstance(item.get("new_text"), str) else ""
    structured_operations = item.get("structured_operations")
    if not any((unified_diff, old_text and new_text, structured_operations)):
        return None
    candidate = {
        "candidate_id": _json_hash(
            {
                "target_file": target_file,
                "unified_diff": unified_diff,
                "old_text": old_text,
                "new_text": new_text,
            }
        ),
        "source_path": source_path,
        "kind": str(item.get("kind") or "code_edit_proposal"),
        "tool": str(item.get("tool") or item.get("source_tool") or ""),
        "target_file": target_file,
        "edit_kind": str(item.get("edit_kind") or ("unified_diff" if unified_diff else "structured_edit")),
        "manual_review_required": bool(item.get("manual_review_required", True)),
        "source_writes_performed": bool(item.get("source_writes_performed", False)),
        "patch_application_performed": bool(item.get("patch_application_performed", False)),
        "has_unified_diff": bool(unified_diff),
        "has_old_new_text": bool(target_file and old_text and new_text),
        "unified_diff": unified_diff,
        "old_text": old_text,
        "new_text": new_text,
        "structured_operations": structured_operations if isinstance(structured_operations, list) else [],
        "rationale": _clip(item.get("rationale"), 1200),
    }
    candidate["apply_supported"] = bool(candidate["has_old_new_text"] and not candidate["patch_application_performed"])
    if candidate["apply_supported"]:
        candidate["apply_tool_call"] = {
            "tool": "repo_apply_patch",
            "arguments": {
                "path": target_file,
                "old_text": old_text,
                "new_text": new_text,
                "max_replacements": 1,
            },
        }
    elif unified_diff and not old_text:
        candidate["apply_block_reason"] = "unified_diff_present_but_repo_apply_patch_requires_exact_old_text_new_text"
    else:
        candidate["apply_block_reason"] = "missing_exact_apply_payload"
    return {key: value for key, value in candidate.items() if value not in ("", [], {}, None)}


def extract_code_products(
    *,
    openwebui_payload: dict[str, Any],
    tool_context: Any,
    limit: int = DEFAULT_CODE_PRODUCT_LIMIT,
) -> list[dict[str, Any]]:
    safe_limit = bounded_int(limit, default=DEFAULT_CODE_PRODUCT_LIMIT, minimum=1, maximum=200)
    seen: set[str] = set()
    products: list[dict[str, Any]] = []
    for root_name, root_value in (
        ("openwebui_payload", openwebui_payload),
        ("tool_context_for_30b", tool_context),
    ):
        for source_path, item in _iter_dicts(root_value, path=root_name):
            candidate = _code_candidate_from_dict(source_path, item)
            if not candidate:
                continue
            candidate_id = str(candidate["candidate_id"])
            if candidate_id in seen:
                continue
            seen.add(candidate_id)
            products.append(candidate)
            if len(products) >= safe_limit:
                break
        if len(products) >= safe_limit:
            break
    return products


def build_step_summaries(
    ia_view_payload: dict[str, Any],
    *,
    limit: int = DEFAULT_STEP_SUMMARY_LIMIT,
) -> list[dict[str, Any]]:
    safe_limit = bounded_int(limit, default=DEFAULT_STEP_SUMMARY_LIMIT, minimum=1, maximum=500)
    summaries: list[dict[str, Any]] = []
    steps = ia_view_payload.get("steps") if isinstance(ia_view_payload.get("steps"), list) else []
    for step in steps[:safe_limit]:
        if not isinstance(step, dict):
            continue
        decision = step.get("planner_decision") if isinstance(step.get("planner_decision"), dict) else {}
        tool_result = (
            step.get("history_tool_result_fed_back_to_planner")
            if isinstance(step.get("history_tool_result_fed_back_to_planner"), dict)
            else {}
        )
        guard = step.get("validator_guard") if isinstance(step.get("validator_guard"), dict) else {}
        runtime_packet = guard.get("runtime_debug_packet") if isinstance(guard.get("runtime_debug_packet"), dict) else {}
        summaries.append(
            {
                "step": step.get("step"),
                "events": len(step.get("events") or []) if isinstance(step.get("events"), list) else 0,
                "planner_action": decision.get("action"),
                "planner_tool": decision.get("tool"),
                "tool_result_tool": tool_result.get("tool"),
                "tool_result_ok": tool_result.get("ok"),
                "validator_guard": guard.get("guard_type") or guard.get("reason"),
                "violations": guard.get("violations") or runtime_packet.get("validator_result", {}).get("violations"),
                "required_next_progress": (
                    runtime_packet.get("required_next_progress_model", {}).get("human_text")
                    if isinstance(runtime_packet.get("required_next_progress_model"), dict)
                    else ""
                ),
                "coverage_score": (
                    runtime_packet.get("evidence_coverage", {}).get("coverage_score")
                    if isinstance(runtime_packet.get("evidence_coverage"), dict)
                    else None
                ),
            }
        )
    return [
        {key: value for key, value in summary.items() if value not in (None, "", [], {})}
        for summary in summaries
    ]


def build_planner_payload_lab(
    *,
    job_id: str,
    ia_view_payload: dict[str, Any],
    terminal_response: dict[str, Any],
    summary_text_chars: int = DEFAULT_SUMMARY_TEXT_CHARS,
    step_summary_limit: int = DEFAULT_STEP_SUMMARY_LIMIT,
    code_product_limit: int = DEFAULT_CODE_PRODUCT_LIMIT,
) -> dict[str, Any]:
    safe_summary_chars = bounded_int(
        summary_text_chars,
        default=DEFAULT_SUMMARY_TEXT_CHARS,
        minimum=500,
        maximum=50000,
    )
    safe_step_limit = bounded_int(
        step_summary_limit,
        default=DEFAULT_STEP_SUMMARY_LIMIT,
        minimum=1,
        maximum=500,
    )
    safe_code_product_limit = bounded_int(
        code_product_limit,
        default=DEFAULT_CODE_PRODUCT_LIMIT,
        minimum=1,
        maximum=200,
    )
    openwebui_payload = terminal_response if isinstance(terminal_response, dict) else {}
    raw_tool_context = openwebui_payload.get("tool_context_for_30b")
    if raw_tool_context in (None, "", {}, []) and isinstance(ia_view_payload.get("openwebui_30b_payload"), dict):
        raw_tool_context = ia_view_payload["openwebui_30b_payload"]
    tool_context, tool_context_meta = _parse_jsonish(raw_tool_context)
    payload_index = openwebui_payload.get("payload_index_for_30b") if isinstance(openwebui_payload.get("payload_index_for_30b"), dict) else {}
    priority_evidence = (
        openwebui_payload.get("priority_evidence_for_30b")
        if isinstance(openwebui_payload.get("priority_evidence_for_30b"), dict)
        else {}
    )
    code_products = extract_code_products(
        openwebui_payload=openwebui_payload,
        tool_context=tool_context,
        limit=safe_code_product_limit,
    )
    model_visible_text = {
        "message_for_30b": _clip(openwebui_payload.get("message_for_30b"), safe_summary_chars),
        "summary_for_30b": _clip(openwebui_payload.get("summary_for_30b"), safe_summary_chars),
        "content": _clip(openwebui_payload.get("content"), safe_summary_chars),
    }
    priority_items = priority_evidence.get("items") if isinstance(priority_evidence.get("items"), list) else []
    concrete_results = payload_index.get("concrete_results") if isinstance(payload_index.get("concrete_results"), list) else []
    partial_results = payload_index.get("partial_results") if isinstance(payload_index.get("partial_results"), list) else []
    readiness_warnings: list[str] = []
    if not tool_context_meta.get("parse_ok"):
        readiness_warnings.append("tool_context_for_30b_not_parseable")
    if not raw_tool_context:
        readiness_warnings.append("tool_context_for_30b_missing")
    if not concrete_results and not priority_items:
        readiness_warnings.append("no_priority_or_concrete_payload_index")
    if not code_products and "diff" in json.dumps(openwebui_payload, ensure_ascii=False, default=str).lower():
        readiness_warnings.append("diff_goal_without_extractable_code_product")
    return {
        "ok": True,
        "schema": SCHEMA,
        "surface": "3572_operator_dashboard_only",
        "read_only": True,
        "operator_limits": {
            "summary_text_chars": safe_summary_chars,
            "step_summary_limit": safe_step_limit,
            "code_product_limit": safe_code_product_limit,
        },
        "job": ia_view_payload.get("job") if isinstance(ia_view_payload.get("job"), dict) else {"job_id": job_id},
        "payload_readiness": {
            "tool_context_parse_ok": bool(tool_context_meta.get("parse_ok")),
            "tool_context_raw_type": tool_context_meta.get("raw_type"),
            "has_tool_context_for_30b": bool(raw_tool_context),
            "has_payload_index_for_30b": bool(payload_index),
            "has_priority_evidence_for_30b": bool(priority_evidence),
            "priority_evidence_items": len(priority_items),
            "concrete_results": len(concrete_results),
            "partial_results": len(partial_results),
            "code_product_candidates": len(code_products),
            "apply_supported_candidates": len([item for item in code_products if item.get("apply_supported")]),
            "warnings": readiness_warnings,
        },
        "model_visible_text": {key: value for key, value in model_visible_text.items() if value},
        "step_summaries": build_step_summaries(ia_view_payload, limit=safe_step_limit),
        "code_products": code_products,
        "payload_index_for_30b": payload_index,
        "priority_evidence_for_30b": priority_evidence,
        "tool_context_for_30b_parse": tool_context_meta,
    }


def find_code_product_candidate(lab_payload: dict[str, Any], candidate_id: str) -> dict[str, Any]:
    for candidate in lab_payload.get("code_products") or []:
        if isinstance(candidate, dict) and str(candidate.get("candidate_id") or "") == str(candidate_id or ""):
            return candidate
    return {}


def build_planner_lab_apply_tool_call(
    lab_payload: dict[str, Any],
    *,
    candidate_id: str,
    confirm_apply: bool,
) -> dict[str, Any]:
    if confirm_apply is not True:
        return {
            "ok": False,
            "tool": "planner_lab_apply",
            "error": "apply_requires_confirm_apply_true",
            "diagnostic_only": False,
        }
    cleaned_candidate_id = str(candidate_id or "").strip()
    if not cleaned_candidate_id:
        return {"ok": False, "tool": "planner_lab_apply", "error": "missing_candidate_id"}
    candidate = find_code_product_candidate(lab_payload, cleaned_candidate_id)
    if not candidate:
        return {
            "ok": False,
            "tool": "planner_lab_apply",
            "error": "candidate_not_found",
            "candidate_id": cleaned_candidate_id,
        }
    apply_call = candidate.get("apply_tool_call") if isinstance(candidate.get("apply_tool_call"), dict) else {}
    arguments = apply_call.get("arguments") if isinstance(apply_call.get("arguments"), dict) else {}
    if not candidate.get("apply_supported") or not arguments:
        return {
            "ok": False,
            "tool": "planner_lab_apply",
            "error": "candidate_not_apply_supported",
            "candidate_id": cleaned_candidate_id,
            "reason": candidate.get("apply_block_reason"),
        }
    return {
        "ok": True,
        "tool": "planner_lab_apply",
        "candidate_id": cleaned_candidate_id,
        "apply_tool": "repo_apply_patch",
        "arguments": arguments,
        "candidate": {
            "target_file": candidate.get("target_file"),
            "source_path": candidate.get("source_path"),
            "candidate_id": cleaned_candidate_id,
        },
    }
