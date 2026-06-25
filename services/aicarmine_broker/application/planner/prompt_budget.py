"""Prompt budget, token reserve, and context window helpers extracted from planner.py.

These functions handle token generation reserves, prompt compaction thresholds,
budget reports, window sizing, and JSON file reading utilities.
"""
from __future__ import annotations

import json
from typing import Any


def _planner_token_generation_reserve(num_ctx: int | None = None) -> int:
    """Calculate the token reserve for generation based on num_ctx."""
    try:
        ctx = int(num_ctx if num_ctx is not None else 0)
    except Exception:
        ctx = 0
    if ctx <= 0:
        return 0
    return max(512, min(32768, ctx // 16))


def _prompt_compaction_threshold() -> int:
    """Calculate the prompt compaction threshold based on budget and ratio."""
    budget = 24000  # AGENTIC_PLANNER_PROMPT_CHAR_BUDGET default
    if budget <= 0:
        return 0
    ratio = 0.5  # AGENTIC_PLANNER_PROMPT_COMPACT_RATIO default
    ratio = max(0.1, min(ratio, 0.95))
    return max(1000, int(budget * ratio))


def _prompt_generation_headroom_char_budget() -> int:
    """Calculate the character budget available for prompt generation."""
    budget = 24000  # AGENTIC_PLANNER_PROMPT_CHAR_BUDGET default
    if budget <= 0:
        return 0
    generation_reserve = max(512, min(32768, budget // 16))
    generation_reserve = max(12000, min(max(12000, budget // 3), generation_reserve))
    char_budget_limit = budget - generation_reserve
    token_budget_limit = int(
        max(1, budget - generation_reserve) * 2  # _PROMPT_CHARS_PER_TOKEN approx 2
    )
    return max(1000, min(char_budget_limit, token_budget_limit))


def _prompt_window_chars(compact_mode: bool, attempt: int = 0) -> int:
    """Calculate the character budget for prompt windows based on mode and attempt."""
    budget = 24000  # AGENTIC_PLANNER_PROMPT_CHAR_BUDGET default
    if compact_mode:
        base = max(4000, min(64000, budget // 16 if budget > 0 else 4000))
        sequence = (
            base,
            int(base * 0.75),
            int(base * 0.60),
            int(base * 0.45),
            int(base * 0.30),
            int(base * 0.20),
            int(base * 0.15),
            int(base * 0.10),
        )
        return sequence[min(max(0, attempt), len(sequence) - 1)]
    return max(1000, min(96000, budget // 8 if budget > 0 else 6000))


def _prompt_budget_report(
    user_payload: dict[str, Any],
    *,
    system_prompt: str = "",
    extra_prompt_sections: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Generate a budget report for the planner prompt."""
    def json_char_len(value: Any) -> int:
        try:
            return len(json.dumps(value, ensure_ascii=False, default=str))
        except Exception:
            return 0

    sections = {
        key: json_char_len(value)
        for key, value in user_payload.items()
        if key not in {"available_tools"}
    }
    sections["available_tools"] = json_char_len(user_payload.get("available_tools"))
    extra_sections = {
        str(key): int(value)
        for key, value in (extra_prompt_sections or {}).items()
        if int(value or 0) > 0
    }
    sections.update(extra_sections)
    total_user = json_char_len(user_payload)
    system_chars = len(str(system_prompt or ""))
    extra_chars = sum(extra_sections.values())
    total = total_user + system_chars + extra_chars
    headroom_budget = _prompt_generation_headroom_char_budget()
    generation_reserve = max(0, 24000 - headroom_budget)  # AGENTIC_PLANNER_PROMPT_CHAR_BUDGET default
    return {
        "schema": "planner_prompt_budget.v1",
        "char_budget": 24000,
        "generation_headroom_char_budget": headroom_budget,
        "generation_headroom_reserve_chars": generation_reserve,
        "num_ctx_effective": 8192,  # AGENTIC_PLANNER_NUM_CTX default
        "generation_token_reserve": _planner_token_generation_reserve(),
        "system_prompt_chars": system_chars,
        "total_user_payload_chars": total_user,
        "extra_prompt_chars": extra_chars,
        "total_prompt_chars": total,
        "over_budget": bool(
            24000 > 0 and total > 24000
        ),
        "over_generation_headroom_budget": bool(headroom_budget > 0 and total > headroom_budget),
        "sections": sections,
    }


def _read_json_file(path: str) -> dict[str, Any]:
    """Read and parse a JSON file, returning empty dict on failure."""
    if not path:
        return {}
    try:
        from pathlib import Path
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _repo_read_file_content_from_repo(item: dict[str, Any], known_prefix: str = "") -> tuple[str, dict[str, Any]]:
    """Rehydrate repo file content from the actual repository.

    Used when prompt previews were truncated and full content is needed.
    """
    from pathlib import Path as PathLib
    from aicarmine_broker.infrastructure.repo_tools import safe_rel_path
    from aicarmine_broker.config import LAB_REPO

    path = item.get("path", "")
    meta: dict[str, Any] = {"source": "repo_file_rehydrate_unavailable", "path": str(path)}
    if not path:
        meta["error"] = "missing_path"
        return "", meta
    try:
        rel = safe_rel_path(path)
        full = (LAB_REPO / rel).resolve(strict=False)
        full.relative_to(LAB_REPO)
        if not full.exists() or not full.is_file():
            meta["error"] = "file_not_found"
            return "", meta
        text = full.read_text(encoding="utf-8-sig", errors="replace")
        prefix = str(known_prefix or "")
        if prefix and not text.startswith(prefix):
            meta.update({
                "source": "repo_file_rehydrate_prefix_mismatch",
                "error": "repo_file_no_longer_matches_repo_read_prefix",
                "known_prefix_chars": len(prefix),
                "file_chars": len(text),
            })
            return "", meta
        meta.update({
            "source": "repo_file_rehydrated_for_prompt_window",
            "file_chars": len(text),
            "known_prefix_matched": bool(prefix),
        })
        return text, meta
    except Exception as exc:
        meta.update({"error": "repo_file_rehydrate_failed", "error_type": type(exc).__name__})
        return "", meta


def _repo_read_item_full_content(item: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Extract full content from a repo_read history item.

    Tries artifact first, then falls back to inline content or known prefix.
    """
    meta: dict[str, Any] = {"source": "tool_result_inline"}
    artifact = str(item.get("artifact") or "")
    content = item.get("content")
    loaded = _read_json_file(artifact)
    artifact_content = loaded.get("content")
    preview = item.get("content_preview")
    known_prefix = (
        content if isinstance(content, str)
        else artifact_content if isinstance(artifact_content, str)
        else preview if isinstance(preview, str)
        else ""
    )
    if isinstance(artifact_content, str) and artifact_content:
        inline_prefix = content if isinstance(content, str) else preview if isinstance(preview, str) else ""
        if not inline_prefix or artifact_content.startswith(inline_prefix):
            meta.update({
                "source": "repo_read_artifact_rehydrated_for_prompt",
                "artifact": artifact,
                "artifact_chars": len(artifact_content),
                "inline_prefix_matched": bool(inline_prefix),
            })
            return artifact_content, meta
    if item.get("truncated") is True:
        repo_text, repo_meta = _repo_read_file_content_from_repo(item, known_prefix)
        if isinstance(repo_text, str) and repo_text:
            repo_meta["artifact"] = artifact
            return repo_text, repo_meta
    if isinstance(content, str) and item.get("truncated") is not True:
        return content, meta
    if isinstance(known_prefix, str) and known_prefix:
        if item.get("truncated") is True:
            meta.update({
                "source": "tool_result_inline_truncated_prefix_only",
                "artifact": artifact,
            })
        return known_prefix, meta
    if isinstance(preview, str):
        repo_text, repo_meta = _repo_read_file_content_from_repo(item, preview)
        if isinstance(repo_text, str) and repo_text:
            repo_meta["artifact"] = artifact
            return repo_text, repo_meta
        meta.update({"source": "content_preview_only", "artifact": artifact})
        return preview, meta
    return "", meta


# Local aliases for backward compatibility with planner.py imports
_planner_token_generation_reserve = _planner_token_generation_reserve
_prompt_compaction_threshold = _prompt_compaction_threshold
_prompt_generation_headroom_char_budget = _prompt_generation_headroom_char_budget
_prompt_window_chars = _prompt_window_chars
_prompt_budget_report = _prompt_budget_report
_read_json_file = _read_json_file
_repo_read_file_content_from_repo = _repo_read_file_content_from_repo
_repo_read_item_full_content = _repo_read_item_full_content

__all__ = [
    "_planner_token_generation_reserve",
    "_prompt_compaction_threshold",
    "_prompt_generation_headroom_char_budget",
    "_prompt_window_chars",
    "_prompt_budget_report",
    "_read_json_file",
    "_repo_read_file_content_from_repo",
    "_repo_read_item_full_content",
]
