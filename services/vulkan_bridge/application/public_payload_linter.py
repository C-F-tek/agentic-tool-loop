"""Warn-only public payload linter for 3571 OpenWebUI responses."""

from __future__ import annotations

import json
from typing import Any

from .payload_index_resolver import resolve_payload_index


SCHEMA = "public_payload_lint.v1"
LOCAL_PATH_MARKERS = ("C:\\Users\\", "C:/Users/")
LOCAL_PATH_KEYS = {
    "artifact_path",
    "db_path",
    "events_path",
    "final_json",
    "final_markdown_path",
    "final_path",
    "local_artifact_path",
    "local_events_path",
    "local_final_path",
    "local_workspace",
    "operator_error_path",
    "planner_stream_path",
    "sqlite_path",
    "workspace",
}
CONCRETE_PRIORITY_KEYS = {
    "content",
    "new_text",
    "old_text",
    "structured_operations",
    "text",
    "unified_diff",
}
TOOL_CONTEXT_ROOT_NARRATIVE_KEYS = {
    "answer_for_30b",
    "composed_answer",
    "content",
    "evidence_guide_for_30b",
    "final_answer",
    "message_for_30b",
    "summary_for_30b",
    "text",
}
TERMINAL_STATUSES = {
    "blocked_needs_attention",
    "blocked_needs_consent",
    "cancelled",
    "completed",
    "failed",
    "failed_planner_error",
    "failed_tool_error",
    "max_steps",
    "max_steps_reached",
}


def _mode(value: str | None) -> str:
    mode = str(value or "warn").strip().lower()
    return mode if mode in {"off", "warn", "block"} else "warn"


def _looks_local_path(value: str) -> bool:
    return any(marker in value for marker in LOCAL_PATH_MARKERS)


def _path(parts: list[str]) -> str:
    return ".".join(parts) if parts else "$"


def _walk(value: Any, *, parts: list[str], operator_diagnostics: bool = False):
    if isinstance(value, dict):
        for key, item in value.items():
            key_s = str(key)
            next_operator = operator_diagnostics or key_s == "operator_diagnostics"
            yield from _walk(item, parts=parts + [key_s], operator_diagnostics=next_operator)
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            yield from _walk(item, parts=parts + [f"[{index}]"], operator_diagnostics=operator_diagnostics)
        return
    if isinstance(value, str):
        yield parts, value, operator_diagnostics


def _json_serializable(value: Any) -> bool:
    try:
        json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        return False
    return True


def _tool_context_serializable(value: Any) -> bool:
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except Exception:
            return False
        return isinstance(parsed, dict)
    return _json_serializable(value)


def _tool_context_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except Exception:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _priority_items_have_concrete_payload(priority_evidence: dict[str, Any]) -> bool:
    items = priority_evidence.get("items") if isinstance(priority_evidence.get("items"), list) else []
    if not items:
        return True
    for item in items:
        if not isinstance(item, dict):
            continue
        if any(item.get(key) not in (None, "", [], {}) for key in CONCRETE_PRIORITY_KEYS):
            return True
    return False


def _has_concrete_payload(value: Any) -> bool:
    if isinstance(value, dict):
        if any(value.get(key) not in (None, "", [], {}) for key in CONCRETE_PRIORITY_KEYS):
            return True
        return any(_has_concrete_payload(item) for item in value.values())
    if isinstance(value, list):
        return any(_has_concrete_payload(item) for item in value)
    return False


def _tool_context_has_artifacts(tool_context: Any) -> bool:
    parsed = _tool_context_object(tool_context)
    artifacts = parsed.get("artifacts")
    return isinstance(artifacts, list) and bool(artifacts)


def _terminal_status(payload: dict[str, Any]) -> str:
    status = str(payload.get("status") or "").strip().lower()
    payload_index = payload.get("payload_index_for_30b")
    if isinstance(payload_index, dict) and payload_index.get("job_completed") is True:
        return "completed"
    return status


def _tool_context_root_violations(tool_context: Any) -> list[dict[str, Any]]:
    parsed = _tool_context_object(tool_context)
    if not parsed:
        return []
    violations: list[dict[str, Any]] = []
    for key in sorted(TOOL_CONTEXT_ROOT_NARRATIVE_KEYS):
        if parsed.get(key) not in (None, "", [], {}):
            violations.append({
                "rule": "tool_context_root_narrative_alias",
                "path": f"tool_context_for_30b.{key}",
            })
    artifacts = parsed.get("artifacts")
    if isinstance(artifacts, list):
        for index, row in enumerate(artifacts):
            if not isinstance(row, dict):
                violations.append({
                    "rule": "tool_context_artifact_row_not_object",
                    "path": f"tool_context_for_30b.artifacts[{index}]",
                })
                continue
            if "artifact" in row and not isinstance(row.get("artifact"), dict):
                violations.append({
                    "rule": "tool_context_artifact_payload_not_object",
                    "path": f"tool_context_for_30b.artifacts[{index}].artifact",
                })
    return violations


def _payload_index_copy_violations(payload_index: dict[str, Any]) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    for section in ("concrete_results", "partial_results"):
        rows = payload_index.get(section)
        if not isinstance(rows, list):
            continue
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            for key in sorted(CONCRETE_PRIORITY_KEYS):
                if row.get(key) not in (None, "", [], {}):
                    violations.append({
                        "rule": "payload_index_contains_concrete_payload_copy",
                        "path": f"payload_index_for_30b.{section}[{index}].{key}",
                    })
    return violations


def lint_public_payload(payload: dict[str, Any], *, mode: str = "warn") -> dict[str, Any]:
    selected_mode = _mode(mode)
    warnings: list[dict[str, Any]] = []
    violations: list[dict[str, Any]] = []
    if selected_mode == "off":
        return {
            "schema": SCHEMA,
            "ok": True,
            "mode": "off",
            "enforcement": "off",
            "would_block": False,
            "warnings": [],
            "violations": [],
            "diagnostic_only": True,
        }
    if not isinstance(payload, dict):
        violations.append({"rule": "payload_not_object", "path": "$"})
    else:
        for parts, value, operator_diagnostics in _walk(payload, parts=[]):
            key = parts[-1] if parts else ""
            key_l = key.lower()
            if key_l in LOCAL_PATH_KEYS and not operator_diagnostics:
                violations.append({"rule": "local_pointer_key_outside_operator_diagnostics", "path": _path(parts)})
            if _looks_local_path(value) and not operator_diagnostics:
                violations.append({"rule": "local_path_value_outside_operator_diagnostics", "path": _path(parts)})
        tool_context = payload.get("tool_context_for_30b")
        if tool_context is not None and not _tool_context_serializable(tool_context):
            violations.append({"rule": "tool_context_for_30b_string_not_json_object", "path": "tool_context_for_30b"})
        violations.extend(_tool_context_root_violations(tool_context))
        payload_index = payload.get("payload_index_for_30b") if isinstance(payload.get("payload_index_for_30b"), dict) else {}
        violations.extend(_payload_index_copy_violations(payload_index))
        priority_evidence = payload.get("priority_evidence_for_30b")
        payload_index_text = json.dumps(payload_index, ensure_ascii=False, default=str).lower()
        if "priority_evidence_for_30b" in payload_index_text and not isinstance(priority_evidence, dict):
            violations.append({"rule": "payload_index_references_missing_priority_evidence", "path": "payload_index_for_30b"})
        index_resolution = resolve_payload_index(payload)
        for row in index_resolution.get("unresolved") or []:
            violations.append({
                "rule": "payload_index_target_missing",
                "path": row.get("path"),
                "section": row.get("section"),
                "row_index": row.get("row_index"),
            })
        for row in index_resolution.get("empty_targets") or []:
            violations.append({
                "rule": "payload_index_target_empty",
                "path": row.get("path"),
                "section": row.get("section"),
                "row_index": row.get("row_index"),
            })
        if isinstance(priority_evidence, dict) and not _priority_items_have_concrete_payload(priority_evidence):
            warnings.append({"rule": "priority_evidence_items_have_no_concrete_payload", "path": "priority_evidence_for_30b.items"})
        terminal_status = _terminal_status(payload)
        if terminal_status in TERMINAL_STATUSES and not isinstance(payload.get("materialization_report"), dict):
            violations.append({"rule": "terminal_payload_missing_materialization_report", "path": "materialization_report"})
        if terminal_status == "completed" and _tool_context_has_artifacts(tool_context):
            context_obj = _tool_context_object(tool_context)
            if not (_has_concrete_payload(priority_evidence) or _has_concrete_payload(context_obj.get("artifacts"))):
                violations.append({
                    "rule": "completed_payload_with_artifacts_has_no_concrete_inline_evidence",
                    "path": "priority_evidence_for_30b.items",
                })

    return {
        "schema": SCHEMA,
        "ok": not violations,
        "mode": selected_mode,
        "enforcement": "warn_only",
        "would_block": bool(violations and selected_mode == "block"),
        "warnings": warnings,
        "violations": violations,
        "diagnostic_only": True,
    }
