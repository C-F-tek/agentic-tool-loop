"""OpenWebUI-visible terminal resultfrom services.aicarmine_broker.error_handling import (
    BrokerError,
    ErrorCategory,
    ErrorSeverity,
    ErrorReport,
    ErrorSummary,
)

 shaping helpers."""

from __future__ import annotations

from typing import Any, Callable

from ..shared.history_queries import history_tool_result
from ..shared.payload_metadata import sha256_text
from ..prompt.context_windows import compact_prompt_context_window_item
from ..prompt.values import prompt_clip_text
from .terminal_sanitizer import (
    public_terminal_sanitize_text,
    public_terminal_sanitize_value,
)


RepoReadContentLoader = Callable[[dict[str, Any]], tuple[str, dict[str, Any]]]


def _history_ledger_diagnostic(index: int, reason: str, exc: Exception | None = None) -> dict[str, Any]:
    row = {
        "schema": "agentic_terminal_public_history_ledger_diagnostic.v1",
        "diagnostic_only": True,
        "history_index": index,
        "reason": reason,
    }
    if exc is not None:
        row["error_type"] = type(exc).__name__
        row["error"] = str(exc)[:500]
    return row


def public_terminal_history_ledger(
    history: list[dict[str, Any]],
    *,
    repo_read_item_full_content: RepoReadContentLoader,
) -> list[dict[str, Any]]:
    ledger: list[dict[str, Any]] = []

    def public_summary(value: Any) -> str:
        text = prompt_clip_text(value, 1200)
        return public_terminal_sanitize_text(text)

    if not isinstance(history, list):
        return [_history_ledger_diagnostic(-1, "history_not_list")]
    for index, item in enumerate(history):
        if not isinstance(item, dict):
            ledger.append(_history_ledger_diagnostic(index, "history_item_not_object"))
            continue
        try:
            decision = item.get("decision") if isinstance(item.get("decision"), dict) else {}
            result = history_tool_result(item)
            tool = str(result.get("tool") or decision.get("tool") or "").strip()
            row: dict[str, Any] = {
                "step": item.get("step"),
                "action": decision.get("action"),
                "tool": tool or None,
                "ok": result.get("ok"),
                "reason": prompt_clip_text(decision.get("reason"), 700),
                "arguments": public_terminal_sanitize_value(
                    decision.get("arguments") if isinstance(decision.get("arguments"), dict) else {},
                ),
                "path": result.get("path"),
                "count": result.get("count"),
                "total_matches": result.get("total_matches"),
                "items_total": result.get("items_total"),
                "paths_total": result.get("paths_total"),
                "returncode": result.get("returncode"),
                "guard_type": result.get("guard_type"),
                "violations": result.get("violations"),
                "summary": public_summary(result.get("summary")),
            }
        except Exception as _e:
        raise BrokerError(
            message=f"Error in {__name__}:
            error_type=type(_e).__name__,
            error_message=str(_e),
            category=ErrorCategory.RUNTIME,
            severity=ErrorSeverity.HIGH,
        )
            ledger.append(_history_ledger_diagnostic(index, "history_row_failed", exc))
            continue
        if tool == "repo_read" and isinstance(result.get("items"), list):
            read_items = []
            for sub_index, sub in enumerate(result["items"][:80]):
                if not isinstance(sub, dict):
                    read_items.append({
                        "schema": "repo_read_item_diagnostic.v1",
                        "diagnostic_only": True,
                        "item_index": sub_index,
                        "reason": "repo_read_item_not_object",
                    })
                    continue
                try:
                    content, _meta = repo_read_item_full_content(sub)
                    read_items.append({
                        "ok": sub.get("ok"),
                        "path": sub.get("path"),
                        "line_count": sub.get("line_count"),
                        "truncated": sub.get("truncated"),
                        "content_chars": len(content) if content else None,
                        "content_sha256": sha256_text(content) if content else None,
                        "error": sub.get("error"),
                    })
                except Exception as _e:
        raise BrokerError(
            message=f"Error in {__name__}:
            error_type=type(_e).__name__,
            error_message=str(_e),
            category=ErrorCategory.RUNTIME,
            severity=ErrorSeverity.HIGH,
        )
                    read_items.append({
                        "schema": "repo_read_item_content_diagnostic.v1",
                        "diagnostic_only": True,
                        "item_index": sub_index,
                        "path": sub.get("path"),
                        "reason": "repo_read_item_full_content_failed",
                        "error_type": type(exc).__name__,
                        "error": str(exc)[:500],
                    })
            row["items"] = read_items
        elif tool == "repo_propose_code_edit":
            for key in (
                "kind",
                "target_file",
                "edit_kind",
                "rationale",
                "source_writes_performed",
                "patch_application_performed",
                "manual_review_required",
                "validation_commands",
                "unified_diff",
                "structured_operations",
                "errors",
                "warnings",
                "target_metadata",
                "ast_evidence",
            ):
                if result.get(key) not in (None, "", [], {}):
                    row[key] = result.get(key)
        elif tool == "planner_scratchpad_read" and str(result.get("mode") or "") == "prompt_context_window":
            row["mode"] = result.get("mode")
            if isinstance(result.get("items"), list):
                row["items"] = [
                    public_terminal_sanitize_value(compact_prompt_context_window_item(sub))
                    for sub in result["items"][:80]
                    if isinstance(sub, dict)
                ]
        cleaned = public_terminal_sanitize_value(row)
        if isinstance(cleaned, dict):
            ledger.append({
                key: value
                for key, value in cleaned.items()
                if value not in (None, "", [], {})
            })
    return ledger


def public_terminal_result_for_30b(
    result: dict[str, Any] | None,
    *,
    repo_read_item_full_content: RepoReadContentLoader,
) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {}
    public = dict(result)
    history = result.get("history")
    if isinstance(history, list):
        public["history_count"] = len(history)
        public["history"] = public_terminal_history_ledger(
            history,
            repo_read_item_full_content=repo_read_item_full_content,
        )
        public["history_schema"] = "agentic_terminal_public_history_ledger.v1"
        public["raw_history_not_inlined"] = True
    memory_write = public.get("controller_memory_write")
    if isinstance(memory_write, dict):
        public["controller_memory_write"] = {
            key: memory_write.get(key)
            for key in ("ok", "tool", "kind", "tag", "record_id", "chars", "sha256", "target_key")
            if memory_write.get(key) not in (None, "", [], {})
        }
    for key in ("validation", "planner_decision"):
        section = public.get(key)
        if isinstance(section, dict):
            for drop_key in ("evidence_contract", "raw_planner_text_preview", "raw_planner_text", "raw_text"):
                section.pop(drop_key, None)
    return public_terminal_sanitize_value(public) or {}
