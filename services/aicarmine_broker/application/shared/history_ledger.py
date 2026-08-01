"""Planner history ledger shaping.""from services.aicarmine_broker.error_handling import (
    BrokerError,
    ErrorCategory,
    ErrorSeverity,
    ErrorReport,
    ErrorSummary,
)

"
from __future__ import annotations

from typing import Any

from .clean_values import drop_empty_dict_values
from .diagnostics import diagnostic_row
from .evidence_contract_summary import compact_evidence_contract_summary
from .history_queries import history_tool_result
from ..prompt.context_windows import compact_prompt_context_window_item


def planner_ollama_turn_from_decision(
    decision: dict[str, Any] | None,
    *,
    step: Any = None,
) -> dict[str, Any]:
    if not isinstance(decision, dict):
        return {}
    meta = decision.get("planner_stream_meta") if isinstance(decision.get("planner_stream_meta"), dict) else {}
    if not meta:
        return {}
    turn = {
        "step": step,
        "done_seen": meta.get("ollama_done_seen"),
        "done_reason": meta.get("ollama_done_reason"),
        "load_duration": meta.get("ollama_load_duration"),
        "total_duration": meta.get("ollama_total_duration"),
        "eval_count": meta.get("ollama_eval_count"),
        "prompt_eval_count": meta.get("ollama_prompt_eval_count"),
    }
    return drop_empty_dict_values(turn)


def history_item_ollama_turn(item: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {}
    explicit = item.get("ollama_turn") if isinstance(item.get("ollama_turn"), dict) else {}
    if explicit:
        return explicit
    result = item.get("tool_result") if isinstance(item.get("tool_result"), dict) else {}
    result_turn = result.get("ollama_turn") if isinstance(result.get("ollama_turn"), dict) else {}
    if result_turn:
        return result_turn
    decision = item.get("decision") if isinstance(item.get("decision"), dict) else {}
    turn = planner_ollama_turn_from_decision(decision, step=item.get("step"))
    if turn:
        return turn
    for source in (
        decision.get("rejected_decision") if isinstance(decision.get("rejected_decision"), dict) else {},
        result.get("rejected_decision") if isinstance(result.get("rejected_decision"), dict) else {},
    ):
        turn = planner_ollama_turn_from_decision(source, step=item.get("step"))
        if turn:
            return turn
    return {}


def _ledger_diagnostic(index: int, reason: str, exc: Exception | None = None) -> dict[str, Any]:
    return diagnostic_row(
        reason,
        schema="planner_history_ledger_diagnostic.v1",
        exc=exc,
        history_index=index,
    )


def planner_history_ledger(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ledger: list[dict[str, Any]] = []
    if not isinstance(history, list):
        return [_ledger_diagnostic(-1, "history_not_list")]
    for index, item in enumerate(history):
        if not isinstance(item, dict):
            ledger.append(_ledger_diagnostic(index, "history_item_not_object"))
            continue
        try:
            decision = item.get("decision") if isinstance(item.get("decision"), dict) else {}
            result = history_tool_result(item)
            row: dict[str, Any] = {
                "step": item.get("step"),
                "action": decision.get("action"),
                "tool": result.get("tool") or decision.get("tool"),
                "ok": result.get("ok"),
                "reason": str(decision.get("reason") or "")[:900],
                "arguments": decision.get("arguments") if isinstance(decision.get("arguments"), dict) else None,
                "path": result.get("path"),
                "count": result.get("count"),
                "total_matches": result.get("total_matches"),
                "limit": result.get("limit"),
                "suffix": result.get("suffix"),
                "returncode": result.get("returncode"),
                "artifact": result.get("artifact"),
                "substep": item.get("substep"),
                "db": result.get("db"),
                "record_id": result.get("record_id"),
                "dry_run": result.get("dry_run"),
                "guard_type": result.get("guard_type"),
                "violations": result.get("violations"),
                "classification": result.get("classification"),
                "next_instruction": result.get("next_instruction"),
                "raw_planner_text_preview": result.get("raw_planner_text_preview"),
                "cache_hit": result.get("cache_hit"),
                "cache_key": result.get("cache_key"),
                "cached_from_step": result.get("cached_from_step"),
                "cached_from_artifact": result.get("cached_from_artifact"),
                "repair_cache_hit": result.get("repair_cache_hit"),
                "repair_cache_key": result.get("repair_cache_key"),
                "native_tool_call": decision.get("native_tool_call"),
                "native_tool_calls_seen": decision.get("native_tool_calls_seen"),
                "ollama_turn": history_item_ollama_turn(item),
            }
            if result.get("tool") == "repo_propose_code_edit":
                for key in (
                    "kind", "target_file", "edit_kind", "rationale",
                    "source_writes_performed", "patch_application_performed",
                    "manual_review_required", "validation_commands",
                    "unified_diff", "structured_operations", "errors", "warnings",
                    "target_metadata", "ast_evidence",
                ):
                    if result.get(key) not in (None, "", [], {}):
                        row[key] = result.get(key)
            for key in ("paths_preview", "files_preview", "entries_preview", "matches_preview"):
                if isinstance(result.get(key), list):
                    row[key] = result.get(key)[:120]
            for key in ("paths_total", "files_total", "entries_total", "matches_total", "items_total"):
                if result.get(key) not in (None, "", [], {}):
                    row[key] = result.get(key)
            if isinstance(result.get("matches"), list):
                row["match_count"] = len(result["matches"])
                row["matches_preview"] = result["matches"][:20]
            if isinstance(result.get("items"), list):
                if result.get("tool") == "planner_scratchpad_read" and str(result.get("mode") or "") == "prompt_context_window":
                    row["mode"] = result.get("mode")
                    compact_items: list[dict[str, Any]] = []
                    for sub_index, sub in enumerate(result["items"][:120]):
                        if not isinstance(sub, dict):
                            compact_items.append(_ledger_diagnostic(sub_index, "history_result_item_not_object"))
                            continue
                        try:
                            compact_items.append(compact_prompt_context_window_item(sub))
                        except Exception as _e:
        raise BrokerError(
            message=f"Error in {__name__}:
            error_type=type(_e).__name__,
            error_message=str(_e),
            category=ErrorCategory.RUNTIME,
            severity=ErrorSeverity.HIGH,
        )
                            compact_items.append(_ledger_diagnostic(sub_index, "prompt_context_item_compaction_failed", exc))
                    row["items"] = compact_items
                else:
                    row["items"] = [
                        {"ok": sub.get("ok"), "id": sub.get("id"), "kind": sub.get("kind"),
                         "tag": sub.get("tag"), "path": sub.get("path"),
                         "line_count": sub.get("line_count"), "truncated": sub.get("truncated"),
                         "artifact": sub.get("artifact"),
                         "error": sub.get("error"),
                         "content_preview": str(sub.get("content") or sub.get("content_preview") or "")[:700],
                         "text_preview": str(sub.get("text") or sub.get("text_preview") or "")[:700]}
                        for sub in result["items"][:120]
                        if isinstance(sub, dict)
                    ]
            if isinstance(result.get("python_static_evidence"), list):
                row["python_static_evidence"] = result.get("python_static_evidence")[:120]
                row["python_static_evidence_total"] = result.get("python_static_evidence_total")
            if isinstance(result.get("evidence_contract_summary"), dict):
                row["evidence_contract_summary"] = result.get("evidence_contract_summary")
            elif isinstance(result.get("evidence_contract"), dict):
                row["evidence_contract_summary"] = compact_evidence_contract_summary(
                    result.get("evidence_contract") or {},
                    schema="planner_evidence_contract_history_summary.v1",
                )
            for key in ("evidence_contract_sha256", "evidence_contract_chars"):
                if result.get(key) not in (None, "", [], {}):
                    row[key] = result.get(key)
            if isinstance(result.get("vulkan_repair"), dict):
                repair = result.get("vulkan_repair") or {}
                row["vulkan_repair"] = {
                    k: repair.get(k)
                    for k in (
                        "ok", "error", "repair_cache_key", "repair_cache_hit",
                        "cached_from_step", "raw_planner_text_preview",
                    )
                    if repair.get(k) not in (None, "", [], {})
                }
            ledger.append(drop_empty_dict_values(row))
        except Exception as _e:
        raise BrokerError(
            message=f"Error in {__name__}:
            error_type=type(_e).__name__,
            error_message=str(_e),
            category=ErrorCategory.RUNTIME,
            severity=ErrorSeverity.HIGH,
        )
            ledger.append(_ledger_diagnostic(index, "history_ledger_item_failed", exc))
    return ledger
