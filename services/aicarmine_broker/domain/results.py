from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class ToolResult:
    """Result returned by a dispatched internal 3572 tool."""

    tool: str
    ok: bool
    artifact: Mapping[str, Any] = field(default_factory=dict)
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    raw: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ValidationResult:
    """Validator outcome for a normalized planner decision."""

    ok: bool
    violations: tuple[str, ...] = ()
    blocker: str | None = None
    evidence_updates: Mapping[str, Any] = field(default_factory=dict)
