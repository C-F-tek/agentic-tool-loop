from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True)
class AgentJobSnapshot:
    """Immutable view of a 3572 job state used by orchestration ports."""

    job_id: str
    status: str
    goal: str
    workspace: Path
    history: tuple[Mapping[str, Any], ...] = ()
    state: Mapping[str, Any] = field(default_factory=dict)
