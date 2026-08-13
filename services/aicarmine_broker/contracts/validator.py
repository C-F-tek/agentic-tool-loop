from __future__ import annotations

from typing import Protocol

from ..domain import EvidenceContract, PlannerDecision, ValidationResult


class PlannerValidator(Protocol):
    """Validation port between planner decisions and dispatch/finalization."""

    def validate(
        self,
        decision: PlannerDecision,
        evidence: EvidenceContract,
    ) -> ValidationResult:
        """Return whether the decision is executable under current evidence."""
