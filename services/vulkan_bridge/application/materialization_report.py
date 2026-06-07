"""Diagnostic report for public OpenWebUI inline evidence materialization."""

from __future__ import annotations

import json
from typing import Any

from .payload_index_resolver import resolve_payload_index


SCHEMA = "public_evidence_materialization.v1"
CONCRETE_KEYS = {
    "content",
    "content_chunks",
    "new_text",
    "old_text",
    "stdout",
    "stderr",
    "structured_operations",
    "text",
    "unified_diff",
}


def _parse_context(value: Any) -> tuple[dict[str, Any], bool]:
    if isinstance(value, dict):
        return value, True
    if not isinstance(value, str):
        return {}, False
    try:
        parsed = json.loads(value)
    except Exception:
        return {}, False
    return (parsed, True) if isinstance(parsed, dict) else ({}, False)



def _artifact_rows(tool_context: dict[str, Any]) -> list[dict[str, Any]]:
    rows = tool_context.get("artifacts")
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def build_materialization_report(
    payload: dict[str, Any],
    *,
    owner: str = "3571_bridge",
    bridge_emergency_rehydration_used: bool = False,
) -> dict[str, Any]:
    """Build a bounded, metadata-only report for the public payload."""

    tool_context, context_ok = _parse_context(payload.get("tool_context_for_30b"))
    artifact_rows = _artifact_rows(tool_context)
    artifact_materialized = 0
    for row in artifact_rows:
        artifact = row.get("artifact")
        if _has_concrete_payload(artifact):
            artifact_materialized += 1
    priority = payload.get("priority_evidence_for_30b")
    priority_items = priority.get("items") if isinstance(priority, dict) and isinstance(priority.get("items"), list) else []
    priority_concrete_count = sum(1 for item in priority_items if _has_concrete_payload(item))
    index_resolution = resolve_payload_index(payload)
    ok = bool(
        context_ok
        and index_resolution.get("ok")
        and (artifact_materialized or priority_concrete_count or not artifact_rows)
    )
    return {
        "schema": SCHEMA,
        "owner": owner,
        "ok": ok,
        "diagnostic_only": True,
        "inline_json_required": True,
        "objects_are_not_transport": True,
        "bridge_emergency_rehydration_used": bool(bridge_emergency_rehydration_used),
        "tool_context": {
            "json_object": context_ok,
            "public_scope": "tool_context_for_30b.artifacts[*].artifact",
            "not_full_job_dump": True,
        },
        "priority_evidence": {
            "items_seen": len(priority_items),
            "concrete_items": priority_concrete_count,
        },
        "artifacts": {
            "refs_seen": len(artifact_rows),
            "refs_resolved": len(artifact_rows),
            "materialized": artifact_materialized,
            "unresolved_refs": [],
        },
        "payload_index": {
            "ok": bool(index_resolution.get("ok")),
            "resolved_count": len(index_resolution.get("resolved") or []),
            "unresolved": index_resolution.get("unresolved") or [],
            "empty_targets": index_resolution.get("empty_targets") or [],
        },
        "local_paths": {
            "omitted": True,
            "operator_diagnostics_only": True,
        },
    }
