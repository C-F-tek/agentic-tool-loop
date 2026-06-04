from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


from aicarmine_broker.application.history_prompt_contract import (  # noqa: E402
    compact_history_for_prompt,
)


def test_compact_history_for_prompt_uses_tail_and_ledger_builder() -> None:
    seen: list[list[dict[str, Any]]] = []

    def ledger_builder(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen.append(rows)
        return [{"step": row["step"], "text": row["text"]} for row in rows]

    history = [
        {"step": 1, "text": "a"},
        {"step": 2, "text": "b" * 80},
        {"step": 3, "text": "c"},
    ]

    payload = compact_history_for_prompt(
        history,
        history_tail=2,
        prompt_preview_chars=30,
        ledger_builder=ledger_builder,
    )

    assert seen == [history[-2:]]
    assert payload[0]["step"] == 2
    assert payload[0]["text"].endswith("<prompt_preview_truncated>")
    assert payload[1] == {"step": 3, "text": "c"}


def test_compact_history_for_prompt_has_minimum_tail() -> None:
    def ledger_builder(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return rows

    payload = compact_history_for_prompt(
        [{"step": 1}, {"step": 2}],
        history_tail=0,
        prompt_preview_chars=100,
        ledger_builder=ledger_builder,
    )

    assert payload == [{"step": 2}]
