"""Warn-only public payload linter for 3571 OpenWebUI responses."""

from __future__ import annotations

import json
from typing import Any


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
        return True
    return _json_serializable(value)


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
            violations.append({"rule": "tool_context_for_30b_not_serializable", "path": "tool_context_for_30b"})
        payload_index = payload.get("payload_index_for_30b") if isinstance(payload.get("payload_index_for_30b"), dict) else {}
        priority_evidence = payload.get("priority_evidence_for_30b")
        payload_index_text = json.dumps(payload_index, ensure_ascii=False, default=str).lower()
        if "priority_evidence_for_30b" in payload_index_text and not isinstance(priority_evidence, dict):
            warnings.append({"rule": "payload_index_references_missing_priority_evidence", "path": "payload_index_for_30b"})
        if isinstance(priority_evidence, dict) and not _priority_items_have_concrete_payload(priority_evidence):
            warnings.append({"rule": "priority_evidence_items_have_no_concrete_payload", "path": "priority_evidence_for_30b.items"})

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
