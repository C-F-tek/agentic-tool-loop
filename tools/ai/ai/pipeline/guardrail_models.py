"""Typed models for artifact-pipeline remediation queue handling."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class GuardrailRequest:
    """Normalized remediation request from a queue item."""

    suggested_stage: str
    action_type: str
    auto_safe: bool
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, payload: Any) -> "GuardrailRequest | None":
        if not isinstance(payload, dict):
            return None
        return cls(
            suggested_stage=str(payload.get("suggested_stage") or "unknown"),
            action_type=str(payload.get("action_type") or "unknown"),
            auto_safe=bool(payload.get("auto_safe")),
            raw=dict(payload),
        )


@dataclass(frozen=True)
class GuardrailPlan:
    """Grouped remediation requests for one processing pass."""

    requests: tuple[GuardrailRequest, ...]

    @property
    def request_count(self) -> int:
        return len(self.requests)

    @property
    def by_stage(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in self.requests:
            counts[item.suggested_stage] = counts.get(item.suggested_stage, 0) + 1
        return counts

    @property
    def by_type(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in self.requests:
            counts[item.action_type] = counts.get(item.action_type, 0) + 1
        return counts

    @property
    def stages(self) -> set[str]:
        return {item.suggested_stage for item in self.requests}

    @classmethod
    def from_raw_requests(cls, raw_requests: list[Any]) -> "GuardrailPlan":
        normalized = [GuardrailRequest.from_mapping(item) for item in raw_requests]
        return cls(tuple(item for item in normalized if item is not None))

    @classmethod
    def from_queue(cls, raw_queue: Any) -> "GuardrailPlan":
        items = raw_queue if isinstance(raw_queue, list) else []
        normalized = [GuardrailRequest.from_mapping(item) for item in items]
        return cls(tuple(item for item in normalized if item is not None and item.auto_safe))

    def signature(self) -> str:
        import json

        return json.dumps(self.by_stage, sort_keys=True)

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_count": self.request_count,
            "by_stage": self.by_stage,
            "by_type": self.by_type,
            "requests": [item.raw for item in self.requests],
        }


@dataclass(frozen=True)
class GuardrailPassResult:
    """Serializable remediation pass result."""

    pass_index: int
    status: str
    plan: GuardrailPlan
    steps: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "pass_index": self.pass_index,
            "status": self.status,
            "plan": self.plan.to_dict(),
            "steps": self.steps,
        }
