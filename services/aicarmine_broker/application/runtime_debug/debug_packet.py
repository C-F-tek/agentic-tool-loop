"""Bounded runtime debug packets for planner/controller rejection paths."""

from __future__ import annotations

import json
from typing import Any


SCHEMA = "runtime_debug_packet.v1"
MAX_STRING_LENGTH = 1000
MAX_LIST_LENGTH = 20

_LOCAL_PATH_MARKERS = ("C:\\Users\\", "C:/Users/")
_SENSITIVE_PATH_KEYS = {
    "artifact_path",
    "events_path",
    "final_markdown_path",
    "final_path",
    "local_artifact_path",
    "local_events_path",
    "local_final_path",
    "local_workspace",
    "planner_stream_path",
    "workspace",
}
_LARGE_PAYLOAD_KEYS = {
    "content",
    "content_preview",
    "full_content",
    "raw_planner_text",
    "raw_planner_text_preview",
    "unified_diff",
}


def _clip_text(value: str, limit: int = MAX_STRING_LENGTH) -> str:
    text = str(value)
    for marker in _LOCAL_PATH_MARKERS:
        if marker in text:
            text = text.replace(marker, "<local_path>/")
    if len(text) <= limit:
        return text
    return text[:limit] + f"...<truncated:{len(text) - limit}>"


def _bounded_jsonable(value: Any, *, key: str = "", depth: int = 0) -> Any:
    try:
        if depth > 12:
            return {"_bounded_json_error": "depth_limit", "diagnostic_only": True}
        key_l = str(key or "").lower()
        if key_l in _SENSITIVE_PATH_KEYS:
            return "<redacted:local_operator_path>"
        if key_l in _LARGE_PAYLOAD_KEYS:
            return "<redacted:large_runtime_payload>"
        if value is None or isinstance(value, (bool, int, float)):
            return value
        if isinstance(value, str):
            return _clip_text(value)
        if isinstance(value, dict):
            out: dict[str, Any] = {}
            for idx, (item_key, item_value) in enumerate(value.items()):
                if idx >= MAX_LIST_LENGTH:
                    out["_truncated_keys"] = max(0, len(value) - MAX_LIST_LENGTH)
                    break
                try:
                    out[str(item_key)] = _bounded_jsonable(
                        item_value,
                        key=str(item_key),
                        depth=depth + 1,
                    )
                except Exception as exc:
                    out[str(item_key)] = {
                        "_bounded_json_error": type(exc).__name__,
                        "diagnostic_only": True,
                    }
            return out
        if isinstance(value, (list, tuple, set)):
            seq = list(value)
            out = [
                _bounded_jsonable(item, key=key, depth=depth + 1)
                for item in seq[:MAX_LIST_LENGTH]
            ]
            if len(seq) > MAX_LIST_LENGTH:
                out.append({"_truncated_items": len(seq) - MAX_LIST_LENGTH})
            return out
        return _clip_text(str(value))
    except Exception as exc:
        return {
            "_bounded_json_error": type(exc).__name__,
            "diagnostic_only": True,
            "key": str(key or "")[:120],
        }


def _json_roundtrip(value: dict[str, Any]) -> dict[str, Any]:
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str))
    except (TypeError, ValueError, RecursionError) as exc:
        return {
            "schema": SCHEMA,
            "diagnostic_only": True,
            "runtime_debug_packet_error": {
                "error_type": type(exc).__name__,
                "error": str(exc)[:500],
            },
        }


def _decision_summary(decision: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(decision, dict):
        return {}
    arguments = decision.get("arguments") if isinstance(decision.get("arguments"), dict) else {}
    return {
        key: value
        for key, value in {
            "action": decision.get("action"),
            "tool": decision.get("tool"),
            "native_tool_call": bool(decision.get("native_tool_call")),
            "arguments_keys": sorted(str(k) for k in arguments.keys())[:MAX_LIST_LENGTH],
            "has_final_answer": bool(str(decision.get("final_answer") or "").strip()),
            "reason": _bounded_jsonable(decision.get("reason"), key="reason"),
        }.items()
        if value not in (None, "", [], {})
    }


def _validator_summary(validator_result: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(validator_result, dict):
        return {}
    out = {
        "ok": bool(validator_result.get("ok")),
        "violations": _bounded_jsonable(
            validator_result.get("violations") if isinstance(validator_result.get("violations"), list) else [],
            key="violations",
        ),
    }
    for key in (
        "semantic_goal_classification",
        "invalid_decision_signature",
        "invalid_decision_repeat_count",
        "action_plan_candidate",
    ):
        if validator_result.get(key) not in (None, "", [], {}):
            out[key] = _bounded_jsonable(validator_result.get(key), key=key)
    return out


def _evidence_summary(contract: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(contract, dict):
        return {}
    finalization_contract = (
        contract.get("finalization_contract")
        if isinstance(contract.get("finalization_contract"), dict)
        else {}
    )
    verified_reads = contract.get("verified_content_reads")
    missing_reads = contract.get("missing_full_content_reads")
    candidate_actions = contract.get("candidate_next_actions")
    rejected_actions = contract.get("rejected_candidate_actions")
    return {
        "planner_may_choose_final": bool(contract.get("planner_may_choose_final")),
        "final_allowed": bool(finalization_contract.get("final_allowed")),
        "verified_content_read_count": len(verified_reads) if isinstance(verified_reads, list) else 0,
        "missing_full_content_read_count": len(missing_reads) if isinstance(missing_reads, list) else 0,
        "candidate_next_actions_count": len(candidate_actions) if isinstance(candidate_actions, list) else 0,
        "rejected_candidate_actions_count": len(rejected_actions) if isinstance(rejected_actions, list) else 0,
    }


def build_runtime_debug_packet(
    *,
    job_id: str,
    step: int,
    phase: str,
    goal: str,
    decision: dict[str, Any],
    validator_result: dict[str, Any] | None = None,
    evidence_contract: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a bounded, JSON-serializable diagnostics packet.

    The packet is diagnostic-only. It summarizes validation state without
    changing planner decisions, validator gates, dispatch, or finalization.
    """
    contract = evidence_contract if isinstance(evidence_contract, dict) else {}
    candidate_actions = contract.get("candidate_next_actions") if isinstance(contract.get("candidate_next_actions"), list) else []
    packet = {
        "schema": SCHEMA,
        "diagnostic_only": True,
        "job_id": str(job_id or ""),
        "step": int(step or 0),
        "phase": str(phase or "").strip().upper() or "UNKNOWN",
        "goal": _bounded_jsonable(str(goal or ""), key="goal"),
        "decision_summary": _decision_summary(decision),
        "validator_result": _validator_summary(validator_result),
        "evidence_contract_summary": _evidence_summary(contract),
        "required_next_progress_model": _bounded_jsonable(
            contract.get("required_next_progress_model")
            if isinstance(contract.get("required_next_progress_model"), dict)
            else {},
            key="required_next_progress_model",
        ),
        "evidence_coverage": _bounded_jsonable(
            contract.get("evidence_coverage") if isinstance(contract.get("evidence_coverage"), dict) else {},
            key="evidence_coverage",
        ),
        "forbidden_next_actions": _bounded_jsonable(
            contract.get("forbidden_next_actions") if isinstance(contract.get("forbidden_next_actions"), list) else [],
            key="forbidden_next_actions",
        ),
        "candidate_next_actions_preview": _bounded_jsonable(
            candidate_actions[:MAX_LIST_LENGTH],
            key="candidate_next_actions_preview",
        ),
    }
    if isinstance(extra, dict) and extra:
        packet["extra"] = _bounded_jsonable(extra, key="extra")
    return _json_roundtrip(packet)
