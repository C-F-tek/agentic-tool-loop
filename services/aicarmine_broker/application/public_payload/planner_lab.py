"""Operator-only extraction of the payload sent toward OpenWebUI."""

from __future__ import annotations

import hashlib
import json
from typing import Any


SCHEMA = "planner_payload_lab.v1"
DEFAULT_SUMMARY_TEXT_CHARS = 4000
DEFAULT_STEP_SUMMARY_LIMIT = 80
DEFAULT_CODE_PRODUCT_LIMIT = 40
DEFAULT_COMPOSE_PAYLOAD_CHARS = 30000
GLOBAL_NARRATIVE_FIELDS = (
    "evidence_guide_for_30b",
    "answer_for_30b",
    "message_for_30b",
    "summary_for_30b",
    "content",
)
LEGACY_NARRATIVE_ALIAS_FIELDS = (
    "answer_for_30b",
    "message_for_30b",
    "summary_for_30b",
    "content",
)
COMPOSE_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": [
        "answer_markdown",
        "payload_assessment",
        "missing_payload",
        "code_products",
        "apply_readiness",
        "follow_up_questions",
    ],
    "properties": {
        "answer_markdown": {"type": "string"},
        "payload_assessment": {
            "type": "object",
            "required": ["sufficient", "reason", "used_fields"],
            "properties": {
                "sufficient": {"type": "boolean"},
                "reason": {"type": "string"},
                "used_fields": {"type": "array", "items": {"type": "string"}},
            },
        },
        "missing_payload": {"type": "array", "items": {"type": "string"}},
        "code_products": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["candidate_id", "target_file", "summary", "apply_supported"],
                "properties": {
                    "candidate_id": {"type": "string"},
                    "target_file": {"type": "string"},
                    "summary": {"type": "string"},
                    "apply_supported": {"type": "boolean"},
                },
            },
        },
        "apply_readiness": {
            "type": "object",
            "required": ["can_apply_any", "reason"],
            "properties": {
                "can_apply_any": {"type": "boolean"},
                "reason": {"type": "string"},
            },
        },
        "follow_up_questions": {"type": "array", "items": {"type": "string"}},
    },
}


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


def _bounded_json(value: Any, limit: int = DEFAULT_COMPOSE_PAYLOAD_CHARS) -> str:
    return _clip(json.dumps(value, ensure_ascii=False, indent=2, default=str), limit)


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


def _first_non_empty_text(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def build_payload_redundancy_audit(
    *,
    openwebui_payload: dict[str, Any],
    tool_context: Any,
    evidence_guide: str,
) -> dict[str, Any]:
    guide = str(evidence_guide or "").strip()
    top_level_present = [
        key
        for key in GLOBAL_NARRATIVE_FIELDS
        if isinstance(openwebui_payload.get(key), str) and str(openwebui_payload.get(key) or "").strip()
    ]
    duplicated_top_level_aliases = [
        key
        for key in LEGACY_NARRATIVE_ALIAS_FIELDS
        if guide and str(openwebui_payload.get(key) or "").strip() == guide
    ]
    non_duplicate_top_level_aliases = [
        key
        for key in LEGACY_NARRATIVE_ALIAS_FIELDS
        if (
            isinstance(openwebui_payload.get(key), str)
            and str(openwebui_payload.get(key) or "").strip()
            and str(openwebui_payload.get(key) or "").strip() != guide
        )
    ]
    tool_context_root_aliases: list[str] = []
    tool_context_duplicate_aliases: list[str] = []
    if isinstance(tool_context, dict):
        for key in GLOBAL_NARRATIVE_FIELDS:
            value = tool_context.get(key)
            if isinstance(value, str) and value.strip():
                tool_context_root_aliases.append(key)
                if guide and value.strip() == guide:
                    tool_context_duplicate_aliases.append(key)
    violations = []
    if duplicated_top_level_aliases:
        violations.append("top_level_duplicate_narrative_aliases")
    if tool_context_root_aliases:
        violations.append("tool_context_root_narrative_aliases")
    return {
        "schema": "planner_payload_redundancy_audit.v1",
        "single_global_guide_field": "evidence_guide_for_30b",
        "top_level_narrative_fields_present": top_level_present,
        "duplicated_top_level_aliases": duplicated_top_level_aliases,
        "non_duplicate_top_level_aliases": non_duplicate_top_level_aliases,
        "tool_context_root_aliases": tool_context_root_aliases,
        "tool_context_duplicate_aliases": tool_context_duplicate_aliases,
        "ok": not violations,
        "violations": violations,
        "rule": (
            "Keep one global evidence_guide_for_30b. tool_context_for_30b must "
            "contain structured evidence/context, not duplicate answer/message/"
            "summary/content aliases. Nested artifact.content remains valid "
            "payload when it is real tool output."
        ),
    }


def build_chat_turn_summary(
    *,
    job_id: str,
    ia_view_payload: dict[str, Any],
    openwebui_payload: dict[str, Any],
    model_visible_text: dict[str, str],
    payload_readiness: dict[str, Any],
    step_summaries: list[dict[str, Any]],
    code_products: list[dict[str, Any]],
    summary_text_chars: int,
) -> dict[str, Any]:
    job = ia_view_payload.get("job") if isinstance(ia_view_payload.get("job"), dict) else {}
    user_message = _first_non_empty_text(job.get("goal"), openwebui_payload.get("task"), openwebui_payload.get("request"))
    assistant_message = _first_non_empty_text(
        model_visible_text.get("evidence_guide_for_30b"),
        model_visible_text.get("content"),
    )
    warnings = list(payload_readiness.get("warnings") or []) if isinstance(payload_readiness.get("warnings"), list) else []
    if not assistant_message:
        warnings.append("assistant_message_missing_from_openwebui_payload")
    return {
        "schema": "planner_lab_chat_turn.v1",
        "job_id": job_id,
        "status": job.get("status") or openwebui_payload.get("status"),
        "user_message": _clip(user_message, summary_text_chars),
        "assistant_message": _clip(assistant_message, summary_text_chars),
        "assistant_visible_fields": model_visible_text,
        "openwebui_payload_fields": sorted(str(key) for key in openwebui_payload.keys()),
        "payload_gaps": sorted(set(str(item) for item in warnings)),
        "thinking_step_summary": step_summaries,
        "thinking_summary": {
            "steps": len(step_summaries),
            "last_step": step_summaries[-1] if step_summaries else {},
            "code_product_candidates": len(code_products),
            "apply_supported_candidates": len([item for item in code_products if item.get("apply_supported")]),
        },
    }


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
    evidence_guide = _first_non_empty_text(
        openwebui_payload.get("evidence_guide_for_30b"),
        openwebui_payload.get("content"),
        openwebui_payload.get("message_for_30b"),
        openwebui_payload.get("summary_for_30b"),
        openwebui_payload.get("answer_for_30b"),
    )
    model_visible_text = {
        "evidence_guide_for_30b": _clip(evidence_guide, safe_summary_chars),
    }
    redundancy_audit = build_payload_redundancy_audit(
        openwebui_payload=openwebui_payload,
        tool_context=tool_context,
        evidence_guide=evidence_guide,
    )
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
    if not redundancy_audit.get("ok"):
        readiness_warnings.extend(redundancy_audit.get("violations") or [])
    payload_readiness = {
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
    }
    step_summaries = build_step_summaries(ia_view_payload, limit=safe_step_limit)
    chat_turn = build_chat_turn_summary(
        job_id=job_id,
        ia_view_payload=ia_view_payload,
        openwebui_payload=openwebui_payload,
        model_visible_text={key: value for key, value in model_visible_text.items() if value},
        payload_readiness=payload_readiness,
        step_summaries=step_summaries,
        code_products=code_products,
        summary_text_chars=safe_summary_chars,
    )
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
        "payload_readiness": payload_readiness,
        "chat_turn": chat_turn,
        "model_visible_text": {key: value for key, value in model_visible_text.items() if value},
        "redundancy_audit": redundancy_audit,
        "step_summaries": step_summaries,
        "thinking_step_summary": step_summaries,
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


def build_planner_lab_compose_request(
    lab_payload: dict[str, Any],
    *,
    model: str,
    user_instruction: str = "",
    conversation: list[dict[str, Any]] | None = None,
    think: bool = False,
    max_payload_chars: int = DEFAULT_COMPOSE_PAYLOAD_CHARS,
) -> dict[str, Any]:
    safe_payload_chars = bounded_int(
        max_payload_chars,
        default=DEFAULT_COMPOSE_PAYLOAD_CHARS,
        minimum=5000,
        maximum=80000,
    )
    compact_payload = {
        "job": lab_payload.get("job"),
        "chat_turn": lab_payload.get("chat_turn"),
        "model_visible_text": lab_payload.get("model_visible_text"),
        "payload_readiness": lab_payload.get("payload_readiness"),
        "redundancy_audit": lab_payload.get("redundancy_audit"),
        "thinking_step_summary": lab_payload.get("thinking_step_summary"),
        "code_products": lab_payload.get("code_products"),
        "payload_index_for_30b": lab_payload.get("payload_index_for_30b"),
        "priority_evidence_for_30b": lab_payload.get("priority_evidence_for_30b"),
    }
    system = (
        "You are the operator-only Planner Payload Lab composer. "
        "Do not call tools. Do not invent repository evidence. "
        "Answer only from the provided OpenWebUI-bound payload. "
        "Treat guided_conversation_tail as the local operator chat history; "
        "answer the latest operator_instruction as the next assistant turn. "
        "If the payload is insufficient, mark missing_payload explicitly. "
        "Use answer_markdown as the readable operator answer and use "
        "payload_assessment to explain which payload fields support it. "
        "Return only JSON matching the provided schema."
    )
    user = {
        "operator_instruction": str(user_instruction or "").strip(),
        "guided_conversation_tail": [
            {
                "role": str(item.get("role") or ""),
                "content": _clip(item.get("content"), 4000),
            }
            for item in (conversation or [])[-8:]
            if isinstance(item, dict)
        ],
        "task": (
            "Continue the guided payload conversation. Generate a readable structured "
            "answer from the payload, explain whether the payload is sufficient, "
            "summarize code-product candidates, and state whether any candidate can "
            "be applied through repo_apply_patch. If the operator asks for details "
            "that are not present in the payload, do not guess; list missing_payload."
        ),
        "openwebui_bound_payload_window": _bounded_json(compact_payload, safe_payload_chars),
    }
    return {
        "model": str(model or ""),
        "stream": False,
        "think": bool(think),
        "format": COMPOSE_RESPONSE_SCHEMA,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(user, ensure_ascii=False, default=str)},
        ],
    }


def parse_planner_lab_compose_response(response: dict[str, Any]) -> dict[str, Any]:
    message = response.get("message") if isinstance(response.get("message"), dict) else {}
    content = str(message.get("content") or response.get("response") or "").strip()
    thinking = str(message.get("thinking") or response.get("thinking") or "").strip()
    if not content:
        return {
            "ok": False,
            "error": "compose_response_missing_content",
            "thinking": _clip(thinking, 8000),
            "raw_response": response,
        }
    try:
        parsed = json.loads(content)
    except Exception as exc:
        return {
            "ok": False,
            "error": "compose_response_not_json",
            "error_type": type(exc).__name__,
            "content": _clip(content, 12000),
            "thinking": _clip(thinking, 8000),
            "raw_response": response,
        }
    if not isinstance(parsed, dict):
        return {
            "ok": False,
            "error": "compose_response_json_not_object",
            "content": _clip(content, 12000),
            "thinking": _clip(thinking, 8000),
            "raw_response": response,
        }
    return {
        "ok": True,
        "schema": "planner_lab_compose_result.v1",
        "structured_answer": parsed,
        "thinking": _clip(thinking, 8000),
        "raw_content": content,
    }
