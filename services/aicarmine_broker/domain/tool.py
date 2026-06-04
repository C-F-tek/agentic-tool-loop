from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class ToolSpec:
    """Planner-visible schema summary for one internal tool."""

    name: str
    description: str
    parameters: Mapping[str, Any] = field(default_factory=dict)
    write_guarded: bool = False
    public_3571_visible: bool = False
