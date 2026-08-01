from __future__ import annotations

from aicarmine_broker.error_handling import (
    BrokerError,
    ErrorCategory,
    ErrorSeverity,
    ErrorReport,
    ErrorSummary,
)

from pathlib import Path
from typing import Any

from aicarmine_broker.config import LAB_REPO, parse_bool
from aicarmine_broker.job_store import now, write_json
from aicarmine_broker.tools.command_safety import classify_command
from aicarmine_broker.tools.powershell_runner import run_ps as _run_ps
from aicarmine_broker.tools.repo_command import (
    _compile_command_for_targets,
    resolve_compile_targets,
)
from aicarmine_broker.tools.deterministic_common import (
    bounded_int_arg as _bounded_int_arg,
    deterministic_input_error as _deterministic_input_error,
)


def repo_validate(args: dict[str, Any], root: Path) -> dict[str, Any]:
    target_resolution = resolve_compile_targets(args, LAB_REPO)
    default_cmds = [
        "git diff --check",
    ]
    targets = tuple(target_resolution.get("targets") or ())
    if targets:
        default_cmds.append(_compile_command_for_targets(targets))
    commands = (
        [str(c) for c in args["commands"][:10] if str(c).strip()]
        if isinstance(args.get("commands"), list) and args["commands"]
        else default_cmds
    )
    try:
        timeout = _bounded_int_arg(args, "timeout_seconds", default=300, minimum=1, maximum=1800)
    except Exception as exc:
        return _deterministic_input_error("repo_validate", exc)
    continue_on_failure = parse_bool(args.get("continue_on_failure", False), False)

    results = []
    ok = True
    for idx, cmd in enumerate(commands, start=1):
        classification = classify_command(cmd)
        if classification.consent_required:
            item = {
                "index": idx,
                "command": cmd,
                "command_class": classification.command_class,
                "consent_required": True,
                "policy": classification.reason,
                "ok": False,
                "error": "command_requires_consent",
                "required_consent": "Use repo_command with explicit user_consent for non-validation commands.",
            }
            results.append(item)
            ok = False
            break
        r = _run_ps(cmd, timeout=timeout)
        item = {
            "index": idx,
            "command": cmd,
            "command_class": classification.command_class,
            "consent_required": classification.consent_required,
            "policy": classification.reason,
            "returncode": r["returncode"],
            "stdout_tail": r["stdout_tail"],
            "stderr_tail": r["stderr_tail"],
            "ok": r["returncode"] == 0,
        }
        results.append(item)
        ok = ok and item["ok"]
        if not item["ok"] and not continue_on_failure:
            break

    payload = {
        "ok": ok,
        "tool": "repo_validate",
        "paths": list(targets),
        "results": results,
        "compile_target_resolution": target_resolution,
    }
    write_json(root / "tool-results" / f"{now()}-repo_validate.json", payload)
    return payload
