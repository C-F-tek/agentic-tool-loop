"""Code-product required working-set helpers."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from ..shared.history_queries import history_tool_result


TextWindowBuilder = Callable[..., dict[str, Any]]
TextHash = Callable[[str], str]


def latest_code_product_for_prompt(
    history: list[dict[str, Any]],
    *,
    job_root: Path,
    goal: str,
    window_chars: int,
    compact_mode: bool,
    store_prompt_text_window: TextWindowBuilder,
    text_hash: TextHash,
) -> dict[str, Any]:
    for row in reversed(history if isinstance(history, list) else []):
        result = history_tool_result(row)
        if result.get("tool") != "repo_propose_code_edit":
            continue
        out = {
            "ok": result.get("ok"),
            "target_file": result.get("target_file"),
            "edit_kind": result.get("edit_kind"),
            "rationale": result.get("rationale"),
            "validation_commands": result.get("validation_commands"),
            "errors": result.get("errors"),
            "warnings": result.get("warnings"),
            "source_writes_performed": result.get("source_writes_performed"),
            "patch_application_performed": result.get("patch_application_performed"),
        }
        if result.get("unified_diff") not in (None, ""):
            diff_text = str(result.get("unified_diff") or "")
            max_diff_chars = max(800, int(window_chars or 3000))
            if not compact_mode and len(diff_text) <= max_diff_chars:
                out["unified_diff"] = diff_text
            else:
                window = store_prompt_text_window(
                    job_root,
                    section=f"repo_propose_code_edit:{result.get('target_file') or 'diff'}",
                    text=diff_text,
                    query=goal,
                    max_chars=max_diff_chars,
                    metadata={
                        "kind": "repo_propose_code_edit_unified_diff",
                        "target_file": result.get("target_file"),
                    },
                )
                out["unified_diff_window"] = window
                if window.get("document_id") and window.get("has_more_after") is True:
                    out["planner_can_request_more"] = {
                        "tool": "planner_scratchpad_read",
                        "arguments": {
                            "kind": "prompt_context_window",
                            "document_id": window.get("document_id"),
                            "offset": window.get("window_end"),
                            "max_chars": max_diff_chars,
                        },
                    }
                out["unified_diff_chars"] = len(diff_text)
                out["unified_diff_sha256"] = text_hash(diff_text)
        if result.get("structured_operations") not in (None, "", [], {}):
            out["structured_operations"] = result.get("structured_operations")
        return {k: v for k, v in out.items() if v not in (None, "", [], {})}
    return {}
