"""Planner-facing tool result digest helpers."""
from __future__ import annotations

from typing import Any

from .prompt_context_windows import compact_prompt_context_window_item


def planner_last_result_digest(result: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {}
    digest = {
        "tool": result.get("tool"), "ok": result.get("ok"),
        "path": result.get("path"), "count": result.get("count"),
        "total_matches": result.get("total_matches"), "limit": result.get("limit"),
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
        "stderr_tail": str(result.get("stderr_tail") or "")[:1200],
        "stdout_tail": str(result.get("stdout_tail") or "")[:1200],
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
                digest[key] = result.get(key)
        return {k: v for k, v in digest.items() if v not in (None, "", [], {})}
    for key in ("paths_preview", "files_preview", "entries_preview", "matches_preview"):
        if isinstance(result.get(key), list):
            digest[key] = result.get(key)[:120]
    for key in ("paths_total", "files_total", "entries_total", "matches_total", "items_total"):
        if result.get(key) not in (None, "", [], {}):
            digest[key] = result.get(key)
    if isinstance(result.get("matches"), list):
        digest["match_count"] = len(result["matches"])
        digest["matches_preview"] = result["matches"][:20]
    if isinstance(result.get("items"), list):
        if result.get("tool") == "planner_scratchpad_read" and str(result.get("mode") or "") == "prompt_context_window":
            digest["mode"] = result.get("mode")
            digest["items"] = [
                compact_prompt_context_window_item(x)
                for x in result["items"][:120]
                if isinstance(x, dict)
            ]
        else:
            digest["items"] = [
                {"ok": x.get("ok"), "id": x.get("id"), "kind": x.get("kind"),
                 "tag": x.get("tag"), "path": x.get("path"),
                 "line_count": x.get("line_count"), "truncated": x.get("truncated"),
                 "artifact": x.get("artifact"),
                 "error": x.get("error"),
                 "content_preview": str(x.get("content") or x.get("content_preview") or "")[:700],
                 "text_preview": str(x.get("text") or x.get("text_preview") or "")[:700]}
                for x in result["items"][:120]
                if isinstance(x, dict)
            ]
    if isinstance(result.get("python_static_evidence"), list):
        digest["python_static_evidence"] = result.get("python_static_evidence")[:120]
        digest["python_static_evidence_total"] = result.get("python_static_evidence_total")
    if isinstance(result.get("evidence_contract"), dict):
        digest["evidence_contract"] = result.get("evidence_contract")
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
    return {k: v for k, v in digest.items() if v not in (None, "", [], {})}
