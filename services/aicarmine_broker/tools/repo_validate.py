from __future__ import annotations

from pathlib import Path
from typing import Any

from aicarmine_broker.config import COMMAND_TIMEOUT_SECONDS, LAB_REPO, parse_bool
from aicarmine_broker.infrastructure.command_runner import SubprocessCommandRunner
from aicarmine_broker.job_store import now, write_json


def _run_ps(command: str, timeout: int = COMMAND_TIMEOUT_SECONDS) -> dict[str, Any]:
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


def repo_validate(args: dict[str, Any], root: Path) -> dict[str, Any]:
    default_cmds = [
        "git diff --check",
        (
            "python -m compileall -q ia_carmine; "
            "if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; "
            "python -m compileall -q Tools"
        ),
    ]
    commands = (
        [str(c) for c in args["commands"][:10] if str(c).strip()]
        if isinstance(args.get("commands"), list) and args["commands"]
        else default_cmds
    )
    timeout = int(args.get("timeout_seconds") or 300)
    continue_on_failure = parse_bool(args.get("continue_on_failure", False), False)

    results = []
    ok = True
    for idx, cmd in enumerate(commands, start=1):
        r = _run_ps(cmd, timeout=timeout)
        item = {
            "index": idx,
            "command": cmd,
            "returncode": r["returncode"],
            "stdout_tail": r["stdout_tail"],
            "stderr_tail": r["stderr_tail"],
            "ok": r["returncode"] == 0,
        }
        results.append(item)
        ok = ok and item["ok"]
        if not item["ok"] and not continue_on_failure:
            break

    payload = {"ok": ok, "tool": "repo_validate", "results": results}
    write_json(root / "tool-results" / f"{now()}-repo_validate.json", payload)
    return payload
