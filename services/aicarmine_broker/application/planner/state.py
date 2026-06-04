"""Planner loop mutable state owner."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


HistoryLedgerBuilder = Callable[[list[dict[str, Any]]], Any]
EvidenceBuilder = Callable[[list[dict[str, Any]]], dict[str, Any]]


@dataclass
class PlannerLoopState:
    """Controlled mutation boundary for planner loop history state."""

    _state: dict[str, Any]
    _history: list[dict[str, Any]]
    _history_ledger: HistoryLedgerBuilder
    _evidence_builder: EvidenceBuilder

    def append_history_row(self, row: dict[str, Any], *, update_evidence: bool = True) -> None:
        self._history.append(row)
        self.refresh_history(update_evidence=update_evidence)

    def refresh_history(self, *, update_evidence: bool = True) -> None:
        self._state["history"] = self._history_ledger(self._history)
        self._state["history_count"] = len(self._history)
        if update_evidence:
            self._state["evidence_contract"] = self._evidence_builder(self._history)

    def snapshot(self) -> dict[str, Any]:
        return {
            "history_count": len(self._history),
            "evidence_contract": self._state.get("evidence_contract"),
        }
