"""OpenWebUI context compaction helpers extracted from app.py."""

from __future__ import annotations
from typing import Any


def strip_large_for_openwebui(value: Any, depth: int = 0, compact_text_fn: Any = None) -> Any:
    """Recursively strip large values for OpenWebUI transport limits."""
    if depth > 6:
        return {"omitted": "max_depth"}
    if isinstance(value, str):
        return compact_text_fn(value, 1200) if compact_text_fn else str(value)[:1200]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if isinstance(value, list):
        limit = 30 if depth <= 2 else 12
        out = [strip_large_for_openwebui(v, depth + 1, compact_text_fn) for v in value[:limit]]
        if len(value) > limit:
            out.append({"omitted_items": len(value) - limit})
        return out
    if isinstance(value, dict):
        large_keys = {
            "content", "content_preview", "text", "raw", "raw_text",
            "raw_planner_text", "raw_planner_text_preview", "full_raw",
            "full_result", "items", "files_preview",
        }
        out = {}
        for k, v in value.items():
            if k in large_keys:
                if isinstance(v, str):
                    out[k + "_omitted_chars"] = len(v)
                elif isinstance(v, list):
                    out[k + "_omitted_items"] = len(v)
                else:
                    out[k + "_omitted"] = True
                continue
            out[k] = strip_large_for_openwebui(v, depth + 1, compact_text_fn)
        return out
    result = str(value)
    return result[:500] if compact_text_fn is None else compact_text_fn(result, 500)


def compact_context_for_openwebui(ctx: Any, strip_fn: Any = None) -> Any:
    """Compact a context dict for OpenWebUI by keeping only essential keys."""
    if not isinstance(ctx, dict):
        return ctx
    if strip_fn is None:
        strip_fn = strip_large_for_openwebui
    keep = {}
    for key in (
        "type", "contract_type", "not_a_summary", "openwebui_usage", "job",
        "contract", "execution_contract", "final_answer",
        "next_action_for_30b", "evidence_contract_at_terminal",
        "evidence_contract_at_finish", "blocked_by", "artifacts", "result_digest",
    ):
        if ctx.get(key) not in (None, "", [], {}):
            keep[key] = strip_fn(ctx.get(key))
    planner = ctx.get("planner")
    if isinstance(planner, dict):
        keep["planner"] = {
            "planner_model": planner.get("planner_model"),
            "decisions": strip_fn((planner.get("decisions") or [])[-16:]),
            "validation_rejections": strip_fn((planner.get("validation_rejections") or [])[-10:]),
        }
    executed = ctx.get("executed_tools")
    if isinstance(executed, list):
        keep["executed_tools"] = strip_fn(executed[-24:])
    history = ctx.get("history")
    if isinstance(history, list):
        keep["history_digest"] = strip_fn(history[-12:])
        keep["history_omitted_full_items"] = max(0, len(history) - 12)
    keep.setdefault("openwebui_usage", {})
    if isinstance(keep["openwebui_usage"], dict):
        keep["openwebui_usage"]["rule"] = (
            "Read the top-level evidence_guide_for_30b first. Use evidence_contract_at_terminal, "
            "planner.validation_rejections, executed_tools and artifacts for diagnosis. "
            "Do not ask the user to invent a new plan when next_action_for_30b is present."
        )
    return keep


def compact_payload_for_openwebui(
    decoded: dict[str, Any],
    max_chars: int,
    json_size_fn: Any = None,
) -> dict[str, Any]:
    """Compact a large payload for OpenWebUI by retaining only primary keys."""
    if json_size_fn is None:
        import json
        actual_size = len(json.dumps(decoded, ensure_ascii=False))
    else:
        actual_size = json_size_fn(decoded)
    if actual_size <= max_chars:
        return decoded
    compacted: dict[str, Any] = {}
    keep_keys = (
        "ok", "service", "mode", "required_top_level_keys", "payload_index_for_30b",
        "priority_evidence_for_30b", "openwebui_usage", "tool_context_for_30b",
        "result",
    )
    for key in keep_keys:
        if decoded.get(key) not in (None, "", [], {}):
            compacted[key] = decoded.get(key)
    compacted.setdefault("required_top_level_keys", [
        "ok",
        "service",
        "mode",
        "required_top_level_keys",
        "payload_index_for_30b",
        "priority_evidence_for_30b",
        "openwebui_usage",
        "tool_context_for_30b",
    ])
    compacted.setdefault("openwebui_usage", {
        "primary_payload_fields": [
            "payload_index_for_30b",
            "priority_evidence_for_30b",
            "tool_context_for_30b",
            "result",
        ],
        "rule": "Leggi i payload primari inline; non usare campi narrativi o path locali come sostituti.",
    })
    compacted["bridge_compacted_for_openwebui"] = True
    compacted["bridge_original_response_chars"] = actual_size
    compacted["bridge_compaction_rule"] = (
        "Large nested agent payload retained only through primary inline fields; no narrative/path substitute promoted."
    )
    return compacted