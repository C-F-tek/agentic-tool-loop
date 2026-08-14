"""Prompt-facing history compaction helpers."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .values import prompt_clip_value


def compact_history_for_prompt(
    history: list[dict[str, Any]],

    history_tail: int,
    prompt_preview_chars: int,
    ledger_builder: Callable[[list[dict[str, Any]]], list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    tail = max(1, int(history_tail or 1))
    source = history[-tail:] if isinstance(history, list) else []
    ledger = ledger_builder(source)
    return [
        prompt_clip_value(row, text_limit=prompt_preview_chars, list_limit=12)
        for row in ledger
    ]
