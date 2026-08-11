"""Safe subprocess helpers for capability probes."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any


def command_available(command: str) -> bool:
    return shutil.which(command) is not None


def run_command(
    args: list[str],
    timeout_seconds: int,
    cwd: Path | None = None,
    enabled: bool = True,
) -> dict[str, Any]:
    if not enabled:
        return {"requested": args, "skipped": True, "passed": False, "reason": "external probes disabled"}
    if not args or not command_available(args[0]):
        return {"requested": args, "skipped": True, "passed": False, "reason": "command not found"}
    try:
        proc = subprocess.run(
            args,
            cwd=cwd,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {"requested": args, "skipped": False, "passed": False, "reason": "timeout"}
    except Exception as exc:  # noqa: BLE001 - serialized probe diagnostic.
        return {"requested": args, "skipped": False, "passed": False, "reason": f"{type(exc).__name__}: {exc}"}
    return {
        "requested": args,
        "skipped": False,
        "passed": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": proc.stdout[-4000:],
        "stderr": proc.stderr[-4000:],
    }
