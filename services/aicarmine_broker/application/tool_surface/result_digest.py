"""Planner-facing tool result digestfrom services.aicarmine_broker.error_handling import (
    BrokerError,
    ErrorCategory,
    ErrorSeverity,
    ErrorReport,
    ErrorSummary,
)

 helpers."""
from __future__ import annotations

from typing import Any

from ..prompt.context_windows import compact_prompt_context_window_item
from ..shared.diagnostics import diagnostic_row, safe_text
from ..shared.payload_metadata import compact_value


def _keep_value(value: Any) -> bool:
    try:
        return value not in (None, "", [], {})
    except Exception:
        return True


def planner_last_result_digest(result: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(result, dict):
        return diagnostic_row(
            "result_digest_input_not_object",
            schema="planner_last_result_digest_diagnostic.v1",
            received_type=type(result).__name__,
        )
    try:
        digest = {
            "tool": result.get("tool"), "ok": result.get("ok"),
            "path": result.get("path"), "count": result.get("count"),
            "total_matches": result.get("total_matches"), "limit": result.get("limit"),
            "candidate_limit": result.get("candidate_limit"),
            "suggested_next_tool": result.get("suggested_next_tool"),
            "suggested_repo_read": result.get("suggested_repo_read"),
            "suffix": result.get("suffix"), "returncode": result.get("returncode"),
            "artifact": result.get("artifact"),
            "guard_type": result.get("guard_type"),
            "cache_hit": result.get("cache_hit"),
            "cache_key": result.get("cache_key"),
            "cached_from_step": result.get("cached_from_step"),
            "cached_from_artifact": result.get("cached_from_artifact"),
            "repair_cache_hit": result.get("repair_cache_hit"),
            "repair_cache_key": result.get("repair_cache_key"),
            "violations": result.get("violations"),
            "warnings": result.get("warnings"),
            "error": result.get("error"),
            "error_type": result.get("error_type"),
            "stderr_tail": safe_text(result.get("stderr_tail"), limit=1200),
            "stdout_tail": safe_text(result.get("stdout_tail"), limit=1200),
        }
    except Exception as _e:
        raise BrokerError(
            message=f"Error in {__name__}:
            error_type=type(_e).__name__,
            error_message=str(_e),
            category=ErrorCategory.RUNTIME,
            severity=ErrorSeverity.HIGH,
        )
        return diagnostic_row("result_digest_header_failed", schema="planner_last_result_digest_diagnostic.v1", exc=exc)
    if result.get("tool") == "repo_propose_code_edit":
        for key in (
            "kind", "target_file", "edit_kind", "rationale",
            "source_writes_performed", "patch_application_performed",
            "manual_review_required", "validation_commands",
            "unified_diff", "structured_operations", "errors", "warnings",
            "target_metadata", "ast_evidence",
        ):
            if result.get(key) not in (None, "", [], {}):
                digest[key] = result.get(key)
        return {k: v for k, v in digest.items() if v not in (None, "", [], {})}
    for key in ("paths_preview", "files_preview", "entries_preview", "matches_preview"):
        if isinstance(result.get(key), list):
            digest[key] = compact_value(result.get(key)[:120], text_limit=700, list_limit=120)
    if isinstance(result.get("paths"), list) and "paths_preview" not in digest:
        digest["paths_preview"] = compact_value(result.get("paths")[:120], text_limit=700, list_limit=120)
        digest["paths_total"] = len(result.get("paths") or [])
    for key in ("paths_total", "files_total", "entries_total", "matches_total", "items_total"):
        if result.get(key) not in (None, "", [], {}):
            digest[key] = result.get(key)
    if isinstance(result.get("matches"), list):
        digest["match_count"] = len(result["matches"])
        digest["matches_preview"] = compact_value(result["matches"][:20], text_limit=700, list_limit=20)
    if isinstance(result.get("items"), list):
        if result.get("tool") == "planner_scratchpad_read" and str(result.get("mode") or "") == "prompt_context_window":
            digest["mode"] = result.get("mode")
            items = []
            for item_index, item in enumerate(result["items"][:120]):
                if not isinstance(item, dict):
                    items.append(diagnostic_row(
                        "result_digest_item_not_object",
                        schema="planner_last_result_digest_diagnostic.v1",
                        item_index=item_index,
                        received_type=type(item).__name__,
                    ))
                    continue
                try:
                    items.append(compact_prompt_context_window_item(item))
                except Exception as _e:
        raise BrokerError(
            message=f"Error in {__name__}:
            error_type=type(_e).__name__,
            error_message=str(_e),
            category=ErrorCategory.RUNTIME,
            severity=ErrorSeverity.HIGH,
        )
                    items.append(diagnostic_row(
                        "result_digest_prompt_context_item_failed",
                        schema="planner_last_result_digest_diagnostic.v1",
                        exc=exc,
                        item_index=item_index,
                    ))
            digest["items"] = items
        else:
            items = []
            for item_index, item in enumerate(result["items"][:120]):
                if not isinstance(item, dict):
                    items.append(diagnostic_row(
                        "result_digest_item_not_object",
                        schema="planner_last_result_digest_diagnostic.v1",
                        item_index=item_index,
                        received_type=type(item).__name__,
                    ))
                    continue
                items.append({
                    "ok": item.get("ok"), "id": item.get("id"), "kind": item.get("kind"),
                    "tag": item.get("tag"), "path": item.get("path"),
                    "line_count": item.get("line_count"), "truncated": item.get("truncated"),
                    "artifact": item.get("artifact"),
                    "error": item.get("error"),
                    "content_preview": safe_text(item.get("content") or item.get("content_preview"), limit=700),
                    "text_preview": safe_text(item.get("text") or item.get("text_preview"), limit=700),
                })
            digest["items"] = items
    if isinstance(result.get("python_static_evidence"), list):
        digest["python_static_evidence"] = result.get("python_static_evidence")[:120]
        digest["python_static_evidence_total"] = result.get("python_static_evidence_total")
    if isinstance(result.get("evidence_contract_summary"), dict):
        digest["evidence_contract_summary"] = result.get("evidence_contract_summary")
    if result.get("evidence_contract_sha256") not in (None, "", [], {}):
        digest["evidence_contract_sha256"] = result.get("evidence_contract_sha256")
    if result.get("evidence_contract_chars") not in (None, "", [], {}):
        digest["evidence_contract_chars"] = result.get("evidence_contract_chars")
    if isinstance(result.get("vulkan_repair"), dict):
        repair = result.get("vulkan_repair") or {}
        digest["vulkan_repair"] = {
            k: repair.get(k)
            for k in (
                "ok", "error", "repair_cache_key", "repair_cache_hit",
                "cached_from_step", "raw_planner_text_preview",
            )
            if repair.get(k) not in (None, "", [], {})
        }
    return {k: v for k, v in digest.items() if _keep_value(v)}
