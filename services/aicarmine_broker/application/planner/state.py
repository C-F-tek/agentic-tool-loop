"""Planner loop mutable state owner."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ..shared.evidence_contract_summary import evidence_contract_summary_triplet


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
            contract_summary, contract_chars, contract_sha256 = evidence_contract_summary_triplet(
                self._evidence_builder(self._history),
                schema="planner_evidence_contract_state_summary.v1",
            )
            self._state["evidence_contract"] = contract_summary
            self._state["evidence_contract_chars"] = contract_chars
            self._state["evidence_contract_sha256"] = contract_sha256

    def snapshot(self) -> dict[str, Any]:
        return {
            "evidence_contract": self._state.get("evidence_contract"),
        }
