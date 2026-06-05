from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Mapping

from aicarmine_broker.contracts import CommandResult


class SubprocessCommandRunner:
    """Minimal argv-only command runner adapter.

    This adapter does not replace guarded command policy in `repo_tools.py`.
    Callers are expected to pass only commands already allowed by the validator
    or an existing guard.
    """

    def run(
        self,
        command: tuple[str, ...],
        *,
        cwd: Path,
        env: Mapping[str, str] | None = None,
        timeout_seconds: int,
    ) -> CommandResult:
        if not command:
            raise ValueError("command must not be empty")
        completed = subprocess.run(
            list(command),
            cwd=str(cwd),
            env=dict(env) if env is not None else None,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            shell=False,
        )
        return CommandResult(
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
