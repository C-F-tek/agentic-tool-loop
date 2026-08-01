from __future__ import annotations

from aicarmine_broker.error_handling import (
    BrokerError,
    ErrorCategory,
    ErrorSeverity,
    ErrorReport,
    ErrorSummary,
)

import os
import re
import subprocess
from pathlib import Path
from typing import Any

from aicarmine_broker.config import COMMAND_TIMEOUT_SECONDS, LAB_REPO, parse_bool
from aicarmine_broker.application.command import evaluate_command_execution_policy
from aicarmine_broker.application.search import assess_search_quality
from aicarmine_broker.config.env_loader import env_str
from aicarmine_broker.job_store import now, write_json
from aicarmine_broker.tools.command_safety import classify_command, dangerous_command


_ANSI_ESCAPE_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def _terminal_input_error(tool: str, exc: Exception) -> dict[str, Any]:
    """Helper locale per errori di input senza dipendenze circolari."""
    return {
        "ok": False,
        "tool": tool,
        "error": str(exc),
        "error_type": type(exc).__name__,
    }


def _bounded_int_arg(args: dict[str, Any], names: str | tuple[str, ...], *, default: int, minimum: int, maximum: int) -> int:
    """Helper locale per parsing bounded int senza dipendenze circolari."""
    keys = (names,) if isinstance(names, str) else names
    selected: Any = None
    for key in keys:
        value = args.get(key)
        if value is not None and str(value).strip() != "":
            selected = value
            break
    if selected is None:
        selected = default
    try:
        parsed = int(selected)
    except (TypeError, ValueError, OverflowError):
        parsed = default
    return max(minimum, min(parsed, maximum))


def strip_terminal_ansi(value: str) -> str:
    return _ANSI_ESCAPE_RE.sub("", str(value or ""))


def _terminal_user_home() -> Path:
    return Path(env_str("USERPROFILE", "") or str(Path.home())).resolve(strict=False)


def terminal_preferred_cwd() -> Path:
    candidates = [
        env_str("AICARMINE_LAB_REPO", ""),
        env_str("AICARMINE_OPEN_TERMINAL_WORKDIR", ""),
        env_str("OPEN_TERMINAL_CWD", ""),
        str(_terminal_user_home() / "AI" / "services"),
        str(_terminal_user_home()),
    ]
    for item in candidates:
        if not item:
            continue
        try:
            path = Path(str(item)).expanduser().resolve(strict=False)
            if path.exists() and path.is_dir():
                return path
        except Exception:
            continue
    return _terminal_user_home()


def normalize_terminal_path(value: str | None = None, *, base: Path | None = None) -> Path:
    return normalize_terminal_path_details(value, base=base)["resolved_path_obj"]


def normalize_terminal_path_details(value: str | None = None, *, base: Path | None = None) -> dict[str, Any]:
    home = _terminal_user_home()
    base = (base or terminal_preferred_cwd()).resolve(strict=False)
    raw = str(value or "").strip().strip(chr(34) + chr(39))
    if not raw or raw in {".", "./"}:
        return {
            "input_path": str(value or ""),
            "resolved_path": str(base),
            "resolved_path_obj": base,
            "path_normalized": False,
            "normalization_reason": "",
        }

    raw = os.path.expandvars(raw).replace("/", "\\")
    input_path = raw
    normalized = False
    reason = ""
    no_lead = raw.lstrip("\\")
    if no_lead.lower().startswith("users\\"):
        raw = (home.drive or "C:") + "\\" + no_lead
        normalized = True
        reason = "missing_drive_under_users"

    path = Path(raw)
    if not path.is_absolute():
        path = base / raw
        normalized = True
        reason = reason or "relative_path_resolved_against_base"
    resolved = path.resolve(strict=False)
    return {
        "input_path": input_path,
        "resolved_path": str(resolved),
        "resolved_path_obj": resolved,
        "path_normalized": normalized,
        "normalization_reason": reason,
    }


def terminal_environment_contract() -> dict[str, Any]:
    cwd = terminal_preferred_cwd()
    home = _terminal_user_home()
    return {
        "platform": "windows",
        "shell": "powershell_noninteractive",
        "cwd": str(cwd),
        "user_home": str(home),
        "preferred_workdir": str(cwd),
        "path_rules": {
            "absolute_windows_path_required_for_native_open_terminal_list_files": True,
            "external_open_terminal_requires_drive": True,
            "internal_tool_normalizes_missing_drive": True,
            "normalization_is_compatibility_behavior": True,
            "recommended_path_format": "C:\\Users\\...",
            "valid_example": str(cwd),
            "invalid_examples": [
                "\\\\Users\\\\carmi\\\\AI\\\\services",
                "/Users/carmi/AI/services",
                "Users/carmi/AI/services",
            ],
            "normalizer_accepts_missing_drive_under_users": True,
        },
        "command_rules": {
            "do_not_use": ["ls -la", "find . -type f", "grep", "cat", "pwd", "cd /d"],
            "use": "powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command ... | Out-String",
            "run_command_is_async_in_open_terminal": True,
            "exit_code_null_means_running_not_empty_result": True,
            "prefer_internal_tool": "terminal_run_command_wait",
        },
    }


def _terminal_command_repair(command: str) -> dict[str, Any] | None:
    raw = str(command or "").strip()
    low = raw.lower().strip()
    repaired = ""
    if re.fullmatch(r"ls\s+-la", low):
        repaired = "Get-ChildItem -Force | Format-Table -AutoSize | Out-String"
    elif re.fullmatch(r"find\s+\.\s+-type\s+f", low):
        repaired = "Get-ChildItem -Recurse -File -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName | Out-String"
    elif re.fullmatch(r"pwd", low):
        repaired = "(Get-Location).Path | Out-String"
    elif re.match(r"cat\s+([A-Za-z0-9_./\\\\:-]+)$", raw, flags=re.I):
        target = re.match(r"cat\s+([A-Za-z0-9_./\\\\:-]+)$", raw, flags=re.I).group(1)
        repaired = f"Get-Content -Raw '{target}' | Out-String"
    elif re.match(r"grep\s+(.+?)\s+([A-Za-z0-9_./\\\\:-]+)$", raw, flags=re.I):
        match = re.match(r"grep\s+(.+?)\s+([A-Za-z0-9_./\\\\:-]+)$", raw, flags=re.I)
        pattern = match.group(1).strip("'\"")
        target = match.group(2)
        repaired = f"Select-String -Path '{target}' -Pattern '{pattern}' -ErrorAction SilentlyContinue | Out-String"
    if "\\\\users\\\\" in low or low.startswith("\\users\\") or low.startswith("/users/"):
        return {
            "ok": False,
            "error_type": "invalid_command_for_windows_shell",
            "bad_command": raw,
            "auto_repair_available": False,
            "reason": "path_missing_drive",
            "repairs": ["Use an absolute Windows path with drive, e.g. C:\\Users\\carmi\\AI\\services"],
            "terminal_environment_contract": terminal_environment_contract(),
        }
    if not repaired:
        return None
    classification = classify_command(repaired)
    if classification.command_class not in {"readonly", "validation"} or classification.consent_required:
        return {
            "ok": False,
            "error_type": "invalid_command_for_windows_shell",
            "bad_command": raw,
            "auto_repair_available": False,
            "reason": "not_readonly_or_unsafe",
            "terminal_environment_contract": terminal_environment_contract(),
        }
    return {
        "ok": True,
        "auto_repaired": True,
        "original_command": raw,
        "repaired_command": repaired,
        "repair_class": classification.command_class,
    }


def _terminal_powershell_body(command: str) -> str:
    raw = str(command or "").strip()
    match = re.search(r"-Command\s+(.+)$", raw, flags=re.IGNORECASE | re.DOTALL)
    if raw.lower().startswith(("powershell ", "pwsh ")) and match:
        body = match.group(1).strip()
        if (body.startswith(chr(34)) and body.endswith(chr(34))) or (
            body.startswith(chr(39)) and body.endswith(chr(39))
        ):
            body = body[1:-1]
        return body
    return raw


def _run_powershell_body(body: str, cwd: Path, timeout: int) -> dict[str, Any]:
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", body],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    stdout = strip_terminal_ansi(completed.stdout)
    stderr = strip_terminal_ansi(completed.stderr)
    return {
        "returncode": completed.returncode,
        "stdout": stdout,
        "stderr": stderr,
        "stdout_tail": stdout[-8000:],
        "stderr_tail": stderr[-8000:],
    }


def terminal_list_files(args: dict[str, Any], root: Path) -> dict[str, Any]:
    directory_arg = args.get("directory", args.get("path", args.get("cwd", None)))
    base = terminal_preferred_cwd()
    path_details = normalize_terminal_path_details(directory_arg, base=base)
    directory = path_details["resolved_path_obj"]
    try:
        limit = _bounded_int_arg(args, ("limit", "max_files"), default=200, minimum=1, maximum=2000)
    except Exception as exc:
        return _terminal_input_error("terminal_list_files", exc)
    recurse = parse_bool(args.get("recurse", args.get("recursive", False)), False)
    pattern = str(args.get("pattern") or args.get("glob") or "*").strip() or "*"

    if not directory.exists():
        return {
            "ok": False,
            "tool": "terminal_list_files",
            "error": "directory_not_found",
            "input_directory": str(directory_arg or ""),
            "resolved_directory": str(directory),
            "terminal_environment_contract": terminal_environment_contract(),
        }
    if not directory.is_dir():
        return {"ok": False, "tool": "terminal_list_files", "error": "not_a_directory", "resolved_directory": str(directory)}

    iterator = directory.rglob(pattern) if recurse else directory.glob(pattern)
    items: list[dict[str, Any]] = []
    for path in iterator:
        try:
            stat = path.stat()
            items.append(
                {
                    "path": str(path),
                    "name": path.name,
                    "kind": "dir" if path.is_dir() else "file",
                    "size_bytes": None if path.is_dir() else stat.st_size,
                    "modified": stat.st_mtime,
                }
            )
        except Exception:
            continue
        if len(items) >= limit:
            break

    items.sort(key=lambda x: (x.get("kind") != "dir", str(x.get("name") or "").lower()))
    payload = {
        "ok": True,
        "tool": "terminal_list_files",
        "input_directory": str(directory_arg or ""),
        "resolved_directory": str(directory),
        "path_normalized": path_details["path_normalized"],
        "normalization_reason": path_details["normalization_reason"],
        "count": len(items),
        "limit": limit,
        "truncated": len(items) >= limit,
        "items": items,
        "items_preview": items[:80],
        "terminal_environment_contract": terminal_environment_contract(),
    }
    write_json(root / "tool-results" / f"{now()}-terminal_list_files.json", payload)
    return payload


def terminal_search_files(args: dict[str, Any], root: Path) -> dict[str, Any]:
    query = str(args.get("query") or args.get("pattern") or args.get("name") or "").strip()
    directory_arg = args.get("directory", args.get("path", args.get("cwd", None)))
    base = terminal_preferred_cwd()
    path_details = normalize_terminal_path_details(directory_arg, base=base)
    directory = path_details["resolved_path_obj"]
    try:
        limit = _bounded_int_arg(args, ("limit", "max_results"), default=200, minimum=1, maximum=2000)
    except Exception:
        return _terminal_input_error("terminal_search_files", exc)
    content = parse_bool(args.get("content", False), False)

    if not query:
        return {"ok": False, "tool": "terminal_search_files", "error": "missing query"}
    if not directory.exists() or not directory.is_dir():
        return {
            "ok": False,
            "tool": "terminal_search_files",
            "error": "directory_not_found",
            "input_directory": str(directory_arg or ""),
            "resolved_directory": str(directory),
            "terminal_environment_contract": terminal_environment_contract(),
        }

    matches: list[dict[str, Any]] = []
    scanned_files = 0
    filename_matches = 0
    content_read_attempts = 0
    content_read_ok = 0
    unreadable_files = 0
    decode_skipped = 0
    skipped_errors_preview: list[dict[str, Any]] = []
    qlow = query.lower()
    excluded = {".git", "__pycache__", "node_modules", ".venv", "venv", ".pytest_cache", ".mypy_cache"}

    def add_match(row: dict[str, Any]) -> None:
        if len(matches) < limit:
            matches.append(row)

    for cur, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs if d not in excluded]
        for fn in files:
            fp = Path(cur) / fn
            scanned_files += 1
            if qlow in fn.lower():
                filename_matches += 1
                add_match({"path": str(fp), "match_type": "filename", "name": fn})
            if content:
                content_read_attempts += 1
                try:
                    text = fp.read_text(encoding="utf-8", errors="ignore")
                    content_read_ok += 1
                    if query in text:
                        line_no = next((i for i, line in enumerate(text.splitlines(), 1) if query in line), None)
                        add_match({"path": str(fp), "match_type": "content", "line": line_no, "name": fn})
                except UnicodeError as exc:
                    decode_skipped += 1
                    unreadable_files += 1
                    if len(skipped_errors_preview) < 10:
                        skipped_errors_preview.append({"path": str(fp), "error_type": type(exc).__name__, "error": str(exc)[:500]})
                except Exception:
                    unreadable_files += 1
                    if len(skipped_errors_preview) < 10:
                        skipped_errors_preview.append({"path": str(fp), "error_type": type(exc).__name__, "error": str(exc)[:500]})
            if len(matches) >= limit:
                break
        if len(matches) >= limit:
            break

    payload = {
        "ok": True,
        "tool": "terminal_search_files",
        "query": query,
        "input_directory": str(directory_arg or ""),
        "resolved_directory": str(directory),
        "path_normalized": path_details["path_normalized"],
        "normalization_reason": path_details["normalization_reason"],
        "count": len(matches),
        "limit": limit,
        "truncated": len(matches) >= limit,
        "search_complete": unreadable_files == 0 and len(matches) < limit,
        "scanned_files": scanned_files,
        "filename_matches": filename_matches,
        "content_read_attempts": content_read_attempts,
        "content_read_ok": content_read_ok,
        "unreadable_files": unreadable_files,
        "decode_skipped": decode_skipped,
        "skipped_errors_preview": skipped_errors_preview,
        "matches": matches,
        "matches_preview": matches[:80],
        "terminal_environment_contract": terminal_environment_contract(),
    }
    payload["search_quality"] = assess_search_quality(payload)
    write_json(root / "tool-results" / f"{now()}-terminal_search_files.json", payload)
    return payload


def terminal_run_command_wait(
    args: dict[str, Any],
    root: Path,
    allow_command: bool,
    user_consent: str,
) -> dict[str, Any]:
    if not allow_command:
        return {"ok": False, "tool": "terminal_run_command_wait", "error": "commands disabled by request"}
    command = str(args.get("command") or "").strip()
    if not command:
        return {"ok": False, "tool": "terminal_run_command_wait", "error": "missing command"}
    repair = _terminal_command_repair(command)
    if repair:
        if repair.get("auto_repaired") is not True:
            repair["tool"] = "terminal_run_command_wait"
            return repair
        command = str(repair.get("repaired_command") or command)

    try:
        timeout = _bounded_int_arg(args, ("timeout_seconds", "timeout"), default=COMMAND_TIMEOUT_SECONDS, minimum=1, maximum=3600)
    except Exception:
        return _terminal_input_error("terminal_run_command_wait", exc)
    cwd_details = normalize_terminal_path_details(args.get("cwd") or args.get("directory") or args.get("path"), base=terminal_preferred_cwd())
    cwd = cwd_details["resolved_path_obj"]
    if not cwd.exists() or not cwd.is_dir():
        return {
            "ok": False,
            "tool": "terminal_run_command_wait",
            "error": "cwd_not_found",
            "resolved_cwd": str(cwd),
            "terminal_environment_contract": terminal_environment_contract(),
        }

    classification = classify_command(command)
    execution_policy = evaluate_command_execution_policy(
        command,
        command_class=classification.command_class,
        cwd=cwd,
        repo_root=LAB_REPO,
        approval_mode=str(args.get("approval_mode") or ""),
        user_consent=user_consent,
    )
    body = _terminal_powershell_body(command)
    if "out-string" not in body.lower():
        body = f"{body} | Out-String"

    if (dangerous_command(command) or classification.consent_required) and (
        "confirm" not in str(user_consent or "").lower()
        and "confermo" not in str(user_consent or "").lower()
    ):
        return {
            "ok": False,
            "tool": "terminal_run_command_wait",
            "needs_consent": True,
            "command": body,
            "error": "command_requires_consent",
            "command_class": classification.command_class,
            "consent_required": classification.consent_required,
            "required_consent": "confirm command execution",
            "policy": classification.reason,
            "command_execution_policy": execution_policy,
            "terminal_environment_contract": terminal_environment_contract(),
        }

    result = _run_powershell_body(body, cwd=cwd, timeout=timeout)
    payload = {
        "ok": result["returncode"] == 0,
        "tool": "terminal_run_command_wait",
        "command": command,
        "powershell_body": body,
        "resolved_cwd": str(cwd),
        "path_normalized": cwd_details["path_normalized"],
        "normalization_reason": cwd_details["normalization_reason"],
        "command_class": classification.command_class,
        "consent_required": classification.consent_required,
        "policy": classification.reason,
        "command_execution_policy": execution_policy,
        "status": "done",
        "returncode": result["returncode"],
        "stdout_text": result["stdout"],
        "stderr_text": result["stderr"],
        "stdout_tail": result["stdout_tail"],
        "stderr_tail": result["stderr_tail"],
        "ansi_stripped": True,
        "terminal_environment_contract": terminal_environment_contract(),
    }
    if "repair" in locals() and isinstance(repair, dict) and repair.get("auto_repaired"):
        payload.update(repair)
    artifact = root / "commands" / f"terminal-command-{now()}.json"
    write_json(artifact, payload)
    payload["artifact"] = str(artifact)
    return payload
