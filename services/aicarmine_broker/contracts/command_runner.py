from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Protocol


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


class CommandRunner(Protocol):
    """Guarded command execution port."""

    def run(
        self,
        command: tuple[str, ...],
        *,
        cwd: Path,
        env: Mapping[str, str] | None = None,
        timeout_seconds: int,
    ) -> CommandResult:
        """Run a bounded command without bypassing existing guards."""
