from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class ToolDecision:
    """A planner request to execute an internal 3572 tool."""

    tool: str
    arguments: Mapping[str, Any] = field(default_factory=dict)
    reason: str = ""
    native_tool_call: bool = False


@dataclass(frozen=True)
class FinalDecision:
    """A planner final answer candidate before validator acceptance."""

    final_answer: str
    source: str = "final_answer"


@dataclass(frozen=True)
class PlannerDecision:
    """Normalized planner decision independent from Ollama transport shape."""

    action: str
    raw: Mapping[str, Any] = field(default_factory=dict)
    tool_call: ToolDecision | None = None
    final: FinalDecision | None = None
    violations: tuple[str, ...] = ()
