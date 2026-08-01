from __future__ import annotations

from services.aicarmine_broker.error_handling import (
    BrokerError,
    ErrorCategory,
    ErrorSeverity,
    ErrorReport,
    ErrorSummary,
)

import logging
import subprocess
from pathlib import Path
from typing import Mapping

from aicarmine_broker.contracts import CommandResult


logger = logging.getLogger(__name__)


def _command_preview(command: tuple[str, ...]) -> str:
    return " ".join(str(part) for part in command)[:500]


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
        try:
            bounded_timeout = max(1, int(timeout_seconds))
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"timeout_seconds must be an integer; received={timeout_seconds!r}; "
                f"command_preview={_command_preview(command)}"
            ) from exc
        command_preview = _command_preview(command)
        try:
            completed = subprocess.run(
                list(command),
                cwd=str(cwd),
                env=dict(env) if env is not None else None,
                capture_output=True,
                text=True,
                timeout=bounded_timeout,
                shell=False,
            )
        except subprocess.TimeoutExpired:
            logger.warning(
                "Command timed out. timeout_seconds=%s cwd=%s command_preview=%s",
                bounded_timeout,
                cwd,
                command_preview,
            )
            raise
        except FileNotFoundError:
            logger.debug("Command executable not found. cwd=%s command_preview=%s", cwd, command_preview)
            raise
        except PermissionError:
            logger.warning("Permission denied running command. cwd=%s command_preview=%s", cwd, command_preview)
            raise
        except OSError:
            logger.debug("OS error running command. cwd=%s command_preview=%s", cwd, command_preview)
            raise
        return CommandResult(
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
