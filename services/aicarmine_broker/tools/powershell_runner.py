from __future__ import annotations

from typing import Any

from ..config import COMMAND_TIMEOUT_SECONDS, LAB_REPO
from ..infrastructure.command_runner import SubprocessCommandRunner


def run_ps(command: str, timeout: int = COMMAND_TIMEOUT_SECONDS) -> dict[str, Any]:
    completed = SubprocessCommandRunner().run(
        ("powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command),
        cwd=LAB_REPO,
        timeout_seconds=timeout,
    )
    return {
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "stdout_tail": completed.stdout[-4000:],
        "stderr_tail": completed.stderr[-4000:],
    }
