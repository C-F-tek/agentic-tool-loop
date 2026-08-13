from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Protocol


@dataclass(frozen=True)
class CommandResult:
    """Bounded result of a guarded command execution.

    Contains the return code, stdout, and stderr from a subprocess command
    execution, used by the deterministic tool runner to validate command output.
    """
    returncode: int
    stdout: str
    stderr: str


class CommandRunner(Protocol):
    """Guarded command execution port.

    Defines the interface for bounded command execution that respects
    existing safety guards and validation constraints.
    """
    def run(
        self,
        command: tuple[str, ...],
        *,
        cwd: Path,
        env: Mapping[str, str] | None = None,
        timeout_seconds: int,
    ) -> CommandResult:
        """Run a bounded command without bypassing existing guards."""
