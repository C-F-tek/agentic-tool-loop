from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Any

from aicarmine_broker.config import COMMAND_TIMEOUT_SECONDS, parse_bool
from aicarmine_broker.job_store import now, write_json
from aicarmine_broker.tools.command_safety import dangerous_command


_ANSI_ESCAPE_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def strip_terminal_ansi(value: str) -> str:
    return _ANSI_ESCAPE_RE.sub("", str(value or ""))


def _terminal_user_home() -> Path:
    return Path(os.environ.get("USERPROFILE") or str(Path.home())).resolve(strict=False)


def terminal_preferred_cwd() -> Path:
    candidates = [
        os.environ.get("AICARMINE_LAB_REPO"),
        os.environ.get("AICARMINE_OPEN_TERMINAL_WORKDIR"),
        os.environ.get("OPEN_TERMINAL_CWD"),
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
    home = _terminal_user_home()
    base = (base or terminal_preferred_cwd()).resolve(strict=False)
    raw = str(value or "").strip().strip(chr(34) + chr(39))
    if not raw or raw in {".", "./"}:
        return base

    raw = os.path.expandvars(raw).replace("/", "\\")
    no_lead = raw.lstrip("\\")
    if no_lead.lower().startswith("users\\"):
        raw = (home.drive or "C:") + "\\" + no_lead

    path = Path(raw)
    if not path.is_absolute():
        path = base / raw
    return path.resolve(strict=False)


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
    repairs = []
    if re.search(r"(^|[;&|]\s*)ls\s+-la\b", low):
        repairs.append("Get-ChildItem -Force | Format-Table -AutoSize | Out-String")
    if re.search(r"(^|[;&|]\s*)find\s+\.\s+-type\s+f\b", low):
        repairs.append(
            "Get-ChildItem -Recurse -File -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName | Out-String"
        )
    if re.search(r"(^|[;&|]\s*)grep\b", low):
        repairs.append("Select-String -Path .\\* -Recurse -Pattern '<pattern>' -ErrorAction SilentlyContinue | Out-String")
    if re.search(r"(^|[;&|]\s*)cat\s+", low):
        repairs.append("Get-Content -Raw '<path>' | Out-String")
    if re.fullmatch(r"pwd", low):
        repairs.append("(Get-Location).Path | Out-String")
    if re.search(r"(^|[;&|]\s*)cd\s+/d\b", low):
        repairs.append("Set-Location '<path>'; (Get-Location).Path | Out-String")
    if "\\\\users\\\\" in low or low.startswith("\\users\\") or low.startswith("/users/"):
        repairs.append("Use an absolute Windows path with drive, e.g. C:\\Users\\carmi\\AI\\services")
    if not repairs:
        return None
    return {
        "ok": False,
        "error_type": "invalid_command_for_windows_shell",
        "bad_command": raw,
        "repairs": repairs,
        "terminal_environment_contract": terminal_environment_contract(),
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
    directory = normalize_terminal_path(directory_arg, base=base)
    limit = max(1, min(int(args.get("limit") or args.get("max_files") or 200), 5000))
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
    directory = normalize_terminal_path(directory_arg, base=base)
    limit = max(1, min(int(args.get("limit") or args.get("max_results") or 200), 5000))
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
    qlow = query.lower()
    excluded = {".git", "__pycache__", "node_modules", ".venv", "venv", ".pytest_cache", ".mypy_cache"}
    for cur, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs if d not in excluded]
        for fn in files:
            fp = Path(cur) / fn
            if qlow in fn.lower():
                matches.append({"path": str(fp), "match_type": "filename", "name": fn})
            elif content:
                try:
                    text = fp.read_text(encoding="utf-8", errors="ignore")
                    if query in text:
                        line_no = next((i for i, line in enumerate(text.splitlines(), 1) if query in line), None)
                        matches.append({"path": str(fp), "match_type": "content", "line": line_no, "name": fn})
                except Exception:
                    pass
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
        "count": len(matches),
        "limit": limit,
        "truncated": len(matches) >= limit,
        "matches": matches,
        "matches_preview": matches[:80],
        "terminal_environment_contract": terminal_environment_contract(),
    }
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
        repair["tool"] = "terminal_run_command_wait"
        return repair

    timeout = max(1, min(int(args.get("timeout_seconds") or args.get("timeout") or COMMAND_TIMEOUT_SECONDS), 900))
    cwd = normalize_terminal_path(args.get("cwd") or args.get("directory") or args.get("path"), base=terminal_preferred_cwd())
    if not cwd.exists() or not cwd.is_dir():
        return {
            "ok": False,
            "tool": "terminal_run_command_wait",
            "error": "cwd_not_found",
            "resolved_cwd": str(cwd),
            "terminal_environment_contract": terminal_environment_contract(),
        }

    body = _terminal_powershell_body(command)
    if "out-string" not in body.lower():
        body = f"{body} | Out-String"

    if dangerous_command(body) and (
        "confirm" not in str(user_consent or "").lower()
        and "confermo" not in str(user_consent or "").lower()
    ):
        return {
            "ok": False,
            "tool": "terminal_run_command_wait",
            "needs_consent": True,
            "command": body,
            "error": "dangerous command blocked without user_consent",
            "terminal_environment_contract": terminal_environment_contract(),
        }

    result = _run_powershell_body(body, cwd=cwd, timeout=timeout)
    payload = {
        "ok": result["returncode"] == 0,
        "tool": "terminal_run_command_wait",
        "command": command,
        "powershell_body": body,
        "resolved_cwd": str(cwd),
        "status": "done",
        "returncode": result["returncode"],
        "stdout_text": result["stdout"],
        "stderr_text": result["stderr"],
        "stdout_tail": result["stdout_tail"],
        "stderr_tail": result["stderr_tail"],
        "ansi_stripped": True,
        "terminal_environment_contract": terminal_environment_contract(),
    }
    artifact = root / "commands" / f"terminal-command-{now()}.json"
    write_json(artifact, payload)
    payload["artifact"] = str(artifact)
    return payload
