"""Text window primitives for prompt and payload composition."""
from __future__ import annotations

from typing import Any

from .values import text_hash


def window_text(
    text: str,
    
    center: str = "",
    max_chars: int = 6000,
) -> dict[str, Any]:
    full = str(text or "")
    budget = max(500, int(max_chars or 6000))
    if len(full) <= budget:
        return {
            "text": full,
            "window_start": 0,
            "window_end": len(full),
            "full_chars": len(full),
            "window_chars": len(full),
            "complete": True,
            "has_more_before": False,
            "has_more_after": False,
            "sha256": text_hash(full),
            "window_sha256": text_hash(full),
        }
    start = 0
    if center:
        idx = full.find(center)
        if idx >= 0:
            start = max(0, idx - budget // 3)
    end = min(len(full), start + budget)
    start = max(0, end - budget)
    return {
        "text": full[start:end],
        "window_start": start,
        "window_end": end,
        "full_chars": len(full),
        "window_chars": end - start,
        "complete": False,
        "has_more_before": start > 0,
        "has_more_after": end < len(full),
        "sha256": text_hash(full),
        "window_sha256": text_hash(full[start:end]),
    }


def diff_chunks(diff_text: str, chunk_chars: int = 6000) -> list[dict[str, Any]]:
    text = str(diff_text or "")
    if not text:
        return []
    chunks: list[dict[str, Any]] = []
    start = 0
    index = 1
    while start < len(text):
        end = min(len(text), start + max(1000, int(chunk_chars or 6000)))
        if end < len(text):
            newline = text.rfind("\n", start, end)
            if newline > start:
                end = newline + 1
        part = text[start:end]
        chunks.append({
            "index": index,
            "start": start,
            "end": end,
            "chars": len(part),
            "sha256": text_hash(part),
            "text": part,
        })
        start = end
        index += 1
    return chunks
