"""Planner status helpers with no runtime side effects."""

from __future__ import annotations

from typing import Any


def summarize_history_artifacts(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return a bounded artifact summary for planner done-token finalization."""
    out: list[dict[str, Any]] = []
    for item in history:
        if not isinstance(item, dict):
            continue
        result = item.get("tool_result")
        if not isinstance(result, dict):
            continue
        if result.get("artifact") or result.get("tool"):
            out.append({
                "step": item.get("step"),
                "tool": result.get("tool"),
                "ok": result.get("ok"),
                "artifact": result.get("artifact"),
                "path": result.get("path"),
            })
    return out[-10:]


def planner_done_token(raw_text: str) -> bool:
    text = str(raw_text or "").strip().strip("` \r\n\t.。").lower()
    return text in {
        "done",
        "completed",
        "complete",
        "finished",
        "terminato",
        "completato",
        "fatto",
        "eseguito",
        "выполнено",
    }
