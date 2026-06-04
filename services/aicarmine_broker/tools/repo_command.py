from __future__ import annotations

from pathlib import Path
from typing import Any

from aicarmine_broker.config import COMMAND_TIMEOUT_SECONDS
from aicarmine_broker.job_store import now, write_json
from aicarmine_broker.tools.command_safety import dangerous_command
from aicarmine_broker.tools.powershell_runner import run_ps


def repo_command(
    args: dict[str, Any],
    root: Path,
    allow_command: bool,
    user_consent: str,
) -> dict[str, Any]:
    if not allow_command:
        return {"ok": False, "tool": "repo_command", "error": "commands disabled by request"}

    command = str(args.get("command") or "").strip()
    timeout = int(args.get("timeout_seconds") or COMMAND_TIMEOUT_SECONDS)

    if not command:
        return {"ok": False, "tool": "repo_command", "error": "missing command"}

    if command.lower() in {"compile", "build", "compila"}:
        command = (
            "python -m compileall -q ia_carmine; "
            "if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; "
            "python -m compileall -q Tools"
        )

    if dangerous_command(command) and (
        "confirm" not in user_consent.lower()
        and "confermo" not in user_consent.lower()
    ):
        return {
            "ok": False,
            "tool": "repo_command",
            "needs_consent": True,
            "command": command,
            "error": "dangerous command blocked without user_consent",
        }

    result = run_ps(command, timeout=timeout)
    artifact = root / "commands" / f"command-{now()}.json"
    write_json(artifact, {"command": command, "result": result})
    return {
        "ok": result["returncode"] == 0,
        "tool": "repo_command",
        "command": command,
        "returncode": result["returncode"],
        "stdout_tail": result["stdout_tail"],
        "stderr_tail": result["stderr_tail"],
        "artifact": str(artifact),
    }
