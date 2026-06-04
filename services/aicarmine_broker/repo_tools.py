"""
aicarmine_broker.repo_tools
============================
All deterministic local repository tools executed by the 3572 dispatcher:

    repo_capabilities, repo_status, repo_tree, repo_list_files,
    repo_search, repo_read, repo_apply_patch, repo_write_file,
    repo_validate, repo_command, vulkan_helper

Each function takes ``(args: dict, root: Path)`` and returns a result dict.
No HTTP calls are made here.  ``run_ps`` is the only subprocess boundary.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from .config import (
    COMMAND_TIMEOUT_SECONDS,
    LAB_REPO,
    MAX_TOOL_RESULT_CHARS,
    REAL_REPO,
    VALID_INTERNAL_TOOLS,
    parse_bool,
)
from .infrastructure.command_runner import SubprocessCommandRunner
from .infrastructure.filesystem_repo import repo_rel, safe_rel_path
from .job_store import now, write_json
from .tool_registry import capability_map


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------


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


def dangerous_command(command: str) -> bool:
    low = command.lower()
    patterns = [
        r"\bgit\s+reset\b",
        r"\bgit\s+clean\b",
        r"\bgit\s+push\b",
        r"\bgit\s+commit\b",
        r"\bgit\s+merge\b",
        r"\bgit\s+rebase\b",
        r"\bremove-item\b",
        r"\brm\s+-",
        r"\bdel\s+",
        r"\brmdir\b",
        r"\bformat\b",
        r"\bshutdown\b",
    ]
    return any(re.search(p, low) for p in patterns)


def compact(value: Any, limit: int = MAX_TOOL_RESULT_CHARS) -> str:
    text = (
        json.dumps(value, ensure_ascii=False, indent=2, default=str)
        if not isinstance(value, str)
        else value
    )
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text[:limit] + ("\n... <truncated>" if len(text) > limit else "")


_TOOL_RESULT_TEXT_LIMIT = 120_000
_TOOL_RESULT_ITEMS_LIMIT = 500


def _active_venv_script(name: str) -> Path:
    suffix = ".exe" if os.name == "nt" and not name.lower().endswith(".exe") else ""
    return Path(sys.executable).resolve(strict=False).parent / f"{name}{suffix}"


def _winget_package_executable(package_prefix: str, executable_name: str) -> Path | None:
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        return None
    packages = Path(local) / "Microsoft" / "WinGet" / "Packages"
    if not packages.exists():
        return None
    for package_dir in packages.glob(f"{package_prefix}*"):
        if not package_dir.is_dir():
            continue
        for candidate in package_dir.rglob(executable_name):
            if candidate.is_file():
                return candidate.resolve(strict=False)
    return None


_EXE_FALLBACKS: dict[str, list[Path]] = {
    "ctags": [
        p for p in [
            _winget_package_executable("UniversalCtags.Ctags", "ctags.exe"),
        ] if p is not None
    ],
    "shellcheck": [
        p for p in [
            _winget_package_executable("koalaman.shellcheck", "shellcheck.exe"),
        ] if p is not None
    ],
    "hyperfine": [
        p for p in [
            _winget_package_executable("sharkdp.hyperfine", "hyperfine.exe"),
        ] if p is not None
    ],
    "ruff": [_active_venv_script("ruff")],
    "pyright": [_active_venv_script("pyright")],
    "pytest": [_active_venv_script("pytest")],
    "semgrep": [_active_venv_script("semgrep")],
}


def _resolve_deterministic_executable(name: str) -> str | None:
    normalized = str(name or "").strip()
    if not normalized:
        return None
    for candidate in _EXE_FALLBACKS.get(normalized.lower(), []):
        if candidate and candidate.exists():
            return str(candidate)
    found = shutil.which(normalized)
    if found:
        return found
    return None


def _deterministic_tool_missing(tool: str, executable: str) -> dict[str, Any]:
    return {
        "ok": False,
        "tool": tool,
        "error": "deterministic_tool_missing",
        "missing_executable": executable,
    }


def _bounded_text(value: Any, limit: int = _TOOL_RESULT_TEXT_LIMIT) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    return text[:limit] + ("\n... <truncated>" if len(text) > limit else "")


def _run_argv(
    argv: list[str],
    *,
    cwd: Path | None = None,
    timeout: int = COMMAND_TIMEOUT_SECONDS,
    stdin: str | None = None,
) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            argv,
            cwd=str((cwd or LAB_REPO).resolve(strict=False)),
            input=stdin,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        stdout = strip_terminal_ansi(completed.stdout)
        stderr = strip_terminal_ansi(completed.stderr)
        return {
            "returncode": completed.returncode,
            "stdout": _bounded_text(stdout),
            "stderr": _bounded_text(stderr),
            "stdout_tail": stdout[-8000:],
            "stderr_tail": stderr[-8000:],
            "timed_out": False,
        }
    except subprocess.TimeoutExpired as exc:
        stdout = strip_terminal_ansi(exc.stdout or "")
        stderr = strip_terminal_ansi(exc.stderr or "")
        return {
            "returncode": None,
            "stdout": _bounded_text(stdout),
            "stderr": _bounded_text(stderr),
            "stdout_tail": stdout[-8000:],
            "stderr_tail": stderr[-8000:],
            "timed_out": True,
            "error": "timeout",
        }
    except Exception as exc:
        return {
            "returncode": None,
            "stdout": "",
            "stderr": "",
            "stdout_tail": "",
            "stderr_tail": "",
            "timed_out": False,
            "error": str(exc),
            "error_type": type(exc).__name__,
        }


def _repo_existing_path(value: str | None, *, default: str = ".") -> tuple[str, Path]:
    raw = str(value or default).strip() or default
    rel = "." if raw in {"", "."} else safe_rel_path(raw)
    full = (LAB_REPO / rel).resolve(strict=False)
    full.relative_to(LAB_REPO)
    if not full.exists():
        raise FileNotFoundError(rel)
    return rel, full


def _repo_existing_paths(values: Any, *, default: str = ".") -> list[tuple[str, Path]]:
    raw_values: list[str] = []
    if isinstance(values, list):
        raw_values.extend(str(item) for item in values if str(item).strip())
    elif isinstance(values, str) and values.strip():
        raw_values.append(values)
    if not raw_values:
        raw_values.append(default)
    out: list[tuple[str, Path]] = []
    seen: set[str] = set()
    for raw in raw_values:
        rel, full = _repo_existing_path(raw)
        if rel not in seen:
            seen.add(rel)
            out.append((rel, full))
    return out


def _parse_json_output(stdout: str) -> Any:
    text = str(stdout or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        rows = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                return None
        return rows


def _write_tool_artifact(root: Path, tool: str, payload: dict[str, Any]) -> Path:
    artifact = root / "tool-results" / f"{now()}-{tool}.json"
    write_json(artifact, payload)
    return artifact


def _tool_ok_returncode(returncode: Any, *, no_match_ok: bool = False) -> bool:
    if returncode == 0:
        return True
    return bool(no_match_ok and returncode == 1)


# >>> AIC_VULKAN_TERMINAL_ADAPTER_V1
# Windows-aware terminal adapter tools for the Vulkan agent planner.
# Deterministic tool layer: the planner chooses these tools; the controller only validates/dispatches.

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
            p = Path(str(item)).expanduser().resolve(strict=False)
            if p.exists() and p.is_dir():
                return p
        except Exception:
            continue
    return _terminal_user_home()


def normalize_terminal_path(value: str | None = None, *, base: Path | None = None) -> Path:
    # Normalize model-produced Windows paths:
    # C:\Users\..., \Users\..., \\Users\..., /Users/..., or relative paths.
    home = _terminal_user_home()
    base = (base or terminal_preferred_cwd()).resolve(strict=False)
    raw = str(value or "").strip().strip(chr(34) + chr(39))
    if not raw or raw in {".", "./"}:
        return base

    raw = os.path.expandvars(raw).replace("/", "\\")
    no_lead = raw.lstrip("\\")
    # Repair missing drive for \Users\... and \\Users\...
    if no_lead.lower().startswith("users\\"):
        raw = (home.drive or "C:") + "\\" + no_lead

    p = Path(raw)
    if not p.is_absolute():
        p = base / raw
    return p.resolve(strict=False)


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
        repairs.append("Get-ChildItem -Recurse -File -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName | Out-String")
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
    m = re.search(r"-Command\s+(.+)$", raw, flags=re.IGNORECASE | re.DOTALL)
    if raw.lower().startswith(("powershell ", "pwsh ")) and m:
        body = m.group(1).strip()
        if (body.startswith(chr(34)) and body.endswith(chr(34))) or (body.startswith(chr(39)) and body.endswith(chr(39))):
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
        return {
            "ok": False,
            "tool": "terminal_list_files",
            "error": "not_a_directory",
            "resolved_directory": str(directory),
        }

    iterator = directory.rglob(pattern) if recurse else directory.glob(pattern)
    items: list[dict[str, Any]] = []
    for p in iterator:
        try:
            st = p.stat()
            items.append({
                "path": str(p),
                "name": p.name,
                "kind": "dir" if p.is_dir() else "file",
                "size_bytes": None if p.is_dir() else st.st_size,
                "modified": st.st_mtime,
            })
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
# <<< AIC_VULKAN_TERMINAL_ADAPTER_V1

def detect_stack() -> dict[str, Any]:
    excluded = {
        ".git", "__pycache__", ".venv", "node_modules",
        "output", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    }
    py_count = csproj_count = sln_count = 0
    for _, dirs, files in os.walk(LAB_REPO):
        dirs[:] = [d for d in dirs if d not in excluded]
        for f in files:
            low = f.lower()
            if low.endswith(".py"):
                py_count += 1
            elif low.endswith(".csproj"):
                csproj_count += 1
            elif low.endswith(".sln"):
                sln_count += 1
    canonical = ["git status --short --branch", "git diff --check"]
    if py_count:
        canonical.append(
            "python -m compileall -q ia_carmine; python -m compileall -q Tools"
        )
    if csproj_count or sln_count:
        canonical.append("dotnet build")
    if (LAB_REPO / "package.json").exists():
        canonical.append("type package.json")
    return {
        "lab_repo": str(LAB_REPO),
        "real_repo": str(REAL_REPO),
        "python_file_count": py_count,
        "csproj_count": csproj_count,
        "sln_count": sln_count,
        "canonical_commands": canonical,
    }


# ---------------------------------------------------------------------------
# Tool: repo_capabilities
# ---------------------------------------------------------------------------


def repo_capabilities(args: dict[str, Any], root: Path) -> dict[str, Any]:
    registry = capability_map()
    capabilities = [
        {
            "name": "repo_capabilities",
            "risk": "read_only",
            "when_to_use": "Use when the model is unsure which repo/file/tool action to call next.",
            "required_args": [],
        },
        {
            "name": "repo_status",
            "risk": "read_only",
            "when_to_use": "Git status, branch, diff stat, changed files, diff --check and stack.",
            "required_args": [],
        },
        {
            "name": "repo_tree",
            "risk": "read_only",
            "when_to_use": "List files/directories under a repo-relative path.",
            "required_args": ["path"],
        },
        {
            "name": "repo_list_files",
            "risk": "read_only",
            "when_to_use": "List files by suffix/path/limit. Prefer over repo_search for glob-like requests.",
            "required_args": [],
        },
        {
            "name": "repo_search",
            "risk": "read_only",
            "when_to_use": "Find symbols, paths, functions, errors, TODO/FIXME in file content. Accepts query, pattern or symbol.",
            "required_args": ["query|pattern|symbol"],
        },
        {
            "name": "repo_read",
            "risk": "read_only",
            "when_to_use": "Read one or more repo-relative files when the path is known. Accepts path, paths, item or items.",
            "required_args": ["path|paths|items"],
        },
        {
            "name": "repo_apply_patch",
            "risk": "write_safe_guarded",
            "when_to_use": "Replace exact old_text with new_text in a known file.",
            "required_args": ["path", "old_text", "new_text"],
        },
        {
            "name": "repo_write_file",
            "risk": "write_safe_guarded",
            "when_to_use": "Create or overwrite small text files in LAB_REPO.",
            "required_args": ["path", "content"],
        },
        {
            "name": "repo_validate",
            "risk": "diagnostic",
            "when_to_use": "Run git diff --check and Python compile after any edit.",
            "required_args": [],
        },
        {
            "name": "repo_command",
            "risk": "diagnostic_or_write_guarded",
            "when_to_use": "Run safe validation commands. Dangerous commands require user_consent.",
            "required_args": ["command"],
        },
        {
            "name": "vulkan_helper",
            "risk": "composite_read_helper",
            "when_to_use": "Generic repo analysis, problem finding, patch planning.",
            "required_args": ["task"],
        },
    ]
    payload = {
        "ok": True,
        "tool": "repo_capabilities",
        "available_tools": capabilities,
        "valid_internal_tools": sorted(VALID_INTERNAL_TOOLS),
        "registry": registry,
        "contract": registry["runtime_contract"],
        "public_openwebui_surface": registry["surfaces"]["openwebui_public"],
        "internal_planner_surface": registry["surfaces"]["planner_internal"],
        "stack": detect_stack(),
        "input_args": args,
    }
    write_json(root / "tool-results" / f"{now()}-repo_capabilities.json", payload)
    return payload


# ---------------------------------------------------------------------------
# Tool: repo_status
# ---------------------------------------------------------------------------


def repo_status(args: dict[str, Any], root: Path) -> dict[str, Any]:
    commands = {
        "status": "git status --short --branch",
        "diff_stat": "git diff --stat HEAD",
        "diff_name_status": "git diff --name-status HEAD",
        "diff_check": "git diff --check",
        "branch": "git branch --show-current",
    }
    results: dict[str, Any] = {}
    for name, cmd in commands.items():
        result = run_ps(cmd, timeout=120)
        artifact = root / "commands" / f"{name}.json"
        write_json(artifact, {"command": cmd, "result": result})
        results[name] = {
            "command": cmd,
            "returncode": result["returncode"],
            "stdout_tail": result["stdout_tail"],
            "stderr_tail": result["stderr_tail"],
            "artifact": str(artifact),
        }
    payload = {"ok": True, "tool": "repo_status", "stack": detect_stack(), "results": results}
    write_json(root / "tool-results" / f"{now()}-repo_status.json", payload)
    return payload


# ---------------------------------------------------------------------------
# Tool: repo_list_files
# ---------------------------------------------------------------------------

_EXCLUDE_DIRS_DEFAULT = frozenset(
    {
        ".git", ".venv", "venv", "__pycache__", ".pytest_cache",
        ".ruff_cache", ".mypy_cache", "node_modules", "output", "indexAI",
    }
)


def repo_list_files(args: dict[str, Any], root: Path) -> dict[str, Any]:
    path = str(args.get("path") or ".").strip()
    suffix = str(args.get("suffix") or args.get("extension") or "").strip().lower()
    limit = max(1, min(int(args.get("limit") or args.get("max_files") or 20), 1000))
    max_depth = max(0, min(int(args.get("max_depth") or 50), 100))
    core = parse_bool(args.get("core", False), False)

    if core and path in {"", "."}:
        path = "ia_carmine"
    if core and not suffix:
        suffix = ".py"

    exclude_dirs = set(str(d) for d in (args.get("exclude_dirs") or []))
    exclude_dirs |= _EXCLUDE_DIRS_DEFAULT

    try:
        rel = "." if path in {"", "."} else safe_rel_path(path)
        base = (LAB_REPO / rel).resolve(strict=False)
        base.relative_to(LAB_REPO)
    except Exception as exc:
        return {"ok": False, "tool": "repo_list_files", "path": path,
                "error_type": type(exc).__name__, "error": str(exc)}

    if not base.exists():
        return {"ok": False, "tool": "repo_list_files", "path": rel, "error": "path_not_found"}

    def _accept(fp: Path) -> bool:
        return not suffix or fp.suffix.lower() == suffix

    files: list[dict[str, Any]] = []
    if base.is_file():
        if _accept(base):
            files.append({"path": repo_rel(base, LAB_REPO), "size_bytes": base.stat().st_size})
    else:
        base_depth = len(base.relative_to(LAB_REPO).parts)
        for current, dirs, filenames in os.walk(base):
            cp = Path(current)
            depth = len(cp.relative_to(LAB_REPO).parts) - base_depth
            dirs[:] = [d for d in dirs if d not in exclude_dirs]
            if depth > max_depth:
                dirs[:] = []
                continue
            for fn in filenames:
                fp = cp / fn
                if _accept(fp):
                    files.append({"path": repo_rel(fp, LAB_REPO), "size_bytes": fp.stat().st_size})

    files = sorted(files, key=lambda x: str(x.get("path") or "").lower())
    selected = files[:limit]
    payload = {
        "ok": True,
        "tool": "repo_list_files",
        "path": rel if path not in {"", "."} else ".",
        "suffix": suffix,
        "core": core,
        "limit": limit,
        "count": len(selected),
        "total_matches": len(files),
        "files": selected,
        "paths": [str(x["path"]) for x in selected],
        "truncated": len(files) > limit,
    }
    artifact = root / "tool-results" / f"{now()}-repo_list_files.json"
    write_json(artifact, payload)
    payload["artifact"] = str(artifact)
    return payload


# ---------------------------------------------------------------------------
# Tool: repo_tree
# ---------------------------------------------------------------------------


def repo_tree(args: dict[str, Any], root: Path) -> dict[str, Any]:
    path = str(args.get("path") or ".").strip()
    max_files = max(1, min(int(args.get("max_files") or 200), 1000))
    max_depth = max(0, min(int(args.get("max_depth") or 3), 20))
    excluded_dirs = {
        ".git", "__pycache__", ".venv", "node_modules",
        "output", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    }
    try:
        rel = "." if path in {"", "."} else safe_rel_path(path)
        base = (LAB_REPO / rel).resolve(strict=False)
        base.relative_to(LAB_REPO)
    except Exception as exc:
        return {"ok": False, "tool": "repo_tree", "path": path,
                "error_type": type(exc).__name__, "error": str(exc)}

    if not base.exists():
        return {"ok": False, "tool": "repo_tree", "path": rel, "error": "path_not_found"}

    entries: list[dict[str, Any]] = []
    if base.is_file():
        entries.append({"path": repo_rel(base, LAB_REPO), "kind": "file",
                        "size_bytes": base.stat().st_size})
    else:
        base_depth = len(base.relative_to(LAB_REPO).parts)
        for current, dirs, files in os.walk(base):
            cp = Path(current)
            depth = len(cp.relative_to(LAB_REPO).parts) - base_depth
            dirs[:] = [d for d in dirs if d not in excluded_dirs]
            if depth > max_depth:
                dirs[:] = []
                continue
            for dn in dirs:
                entries.append({"path": repo_rel(cp / dn, LAB_REPO), "kind": "dir"})
                if len(entries) >= max_files:
                    break
            for fn in files:
                p = cp / fn
                entries.append({"path": repo_rel(p, LAB_REPO), "kind": "file",
                                 "size_bytes": p.stat().st_size})
                if len(entries) >= max_files:
                    break
            if len(entries) >= max_files:
                break

    payload = {
        "ok": True,
        "tool": "repo_tree",
        "path": rel,
        "count": len(entries),
        "entries": entries,
        "truncated": len(entries) >= max_files,
    }
    artifact = root / "tool-results" / f"{now()}-repo_tree.json"
    write_json(artifact, payload)
    payload["artifact"] = str(artifact)
    return payload


# ---------------------------------------------------------------------------
# Tool: repo_search
# ---------------------------------------------------------------------------


def repo_search(args: dict[str, Any], root: Path) -> dict[str, Any]:
    query = str(args.get("query") or "").strip()
    if re.fullmatch(r"\*\.[A-Za-z0-9_]+", query.strip()):
        return {
            "ok": False,
            "tool": "repo_search",
            "error": "glob_pattern_is_not_text_search",
            "query": query,
            "hint": "Use repo_list_files with suffix instead of repo_search for glob-like file listing.",
            "suggested_tool": "repo_list_files",
            "suggested_arguments": {"path": "ia_carmine", "suffix": query.strip()[1:],
                                     "limit": 20, "core": True},
        }
    if not query:
        return {"ok": False, "tool": "repo_search", "error": "missing query"}

    mode = str(args.get("mode") or "rg").strip()
    path = str(args.get("path") or ".").strip()
    max_results = max(1, min(int(args.get("max_results") or 80), 200))

    q = json.dumps(query)
    target = json.dumps(path)
    if mode == "git_grep":
        command = f"git grep -n -- {q}"
    elif mode == "fd":
        command = f"fd {q} {target}"
    else:
        command = (
            f"rg -n --hidden --glob '!**/__pycache__/**' "
            f"--glob '!output/**' {q} {target}"
        )

    result = run_ps(command, timeout=120)
    payload = {
        "ok": result["returncode"] in (0, 1),
        "tool": "repo_search",
        "mode": mode,
        "query": query,
        "command": command,
        "returncode": result["returncode"],
        "matches": result["stdout"].splitlines()[:max_results],
        "stderr_tail": result["stderr_tail"],
    }
    artifact = root / "tool-results" / f"{now()}-repo_search.json"
    write_json(artifact, payload)
    payload["artifact"] = str(artifact)
    return payload


# ---------------------------------------------------------------------------
# Tool: deterministic external adapters
# ---------------------------------------------------------------------------


def repo_fd_files(args: dict[str, Any], root: Path) -> dict[str, Any]:
    exe = _resolve_deterministic_executable("fd")
    if not exe:
        return _deterministic_tool_missing("repo_fd_files", "fd")
    pattern = str(args.get("pattern") or args.get("query") or "").strip()
    extension = str(args.get("extension") or args.get("suffix") or "").strip().lstrip(".")
    limit = max(1, min(int(args.get("limit") or args.get("max_results") or 200), 5000))
    try:
        rel, full = _repo_existing_path(args.get("path"), default=".")
    except Exception as exc:
        return {"ok": False, "tool": "repo_fd_files", "error": str(exc), "error_type": type(exc).__name__}
    argv = [
        exe,
        "--hidden",
        "--exclude", ".git",
        "--exclude", "__pycache__",
        "--exclude", ".pytest_cache",
        "--exclude", ".mypy_cache",
        "--exclude", ".ruff_cache",
        "--exclude", "node_modules",
        "--exclude", "output",
    ]
    if extension:
        argv.extend(["--extension", extension])
    argv.append(pattern or ".")
    argv.append(str(full))
    result = _run_argv(argv, timeout=int(args.get("timeout_seconds") or 60))
    lines = [line for line in result["stdout"].splitlines() if line.strip()]
    paths = []
    for line in lines[:limit]:
        try:
            paths.append(repo_rel(Path(line), LAB_REPO))
        except Exception:
            paths.append(line.replace("\\", "/"))
    payload = {
        "ok": _tool_ok_returncode(result["returncode"], no_match_ok=True),
        "tool": "repo_fd_files",
        "path": rel,
        "pattern": pattern,
        "extension": extension,
        "limit": limit,
        "count": len(paths),
        "total_output_lines": len(lines),
        "paths": paths,
        "truncated": len(lines) > limit,
        "returncode": result["returncode"],
        "stderr_tail": result["stderr_tail"],
    }
    artifact = _write_tool_artifact(root, "repo_fd_files", payload)
    payload["artifact"] = str(artifact)
    return payload


def repo_rg_search(args: dict[str, Any], root: Path) -> dict[str, Any]:
    exe = _resolve_deterministic_executable("rg")
    if not exe:
        return _deterministic_tool_missing("repo_rg_search", "rg")
    pattern = str(args.get("pattern") or args.get("query") or "").strip()
    if not pattern:
        return {"ok": False, "tool": "repo_rg_search", "error": "missing pattern"}
    limit = max(1, min(int(args.get("max_results") or args.get("limit") or 80), 1000))
    context = max(0, min(int(args.get("context") or 0), 5))
    try:
        rel, full = _repo_existing_path(args.get("path"), default=".")
    except Exception as exc:
        return {"ok": False, "tool": "repo_rg_search", "error": str(exc), "error_type": type(exc).__name__}
    argv = [
        exe,
        "--json",
        "--hidden",
        "--glob", "!**/.git/**",
        "--glob", "!**/__pycache__/**",
        "--glob", "!**/.pytest_cache/**",
        "--glob", "!**/.mypy_cache/**",
        "--glob", "!**/.ruff_cache/**",
        "--glob", "!**/node_modules/**",
        "--glob", "!output/**",
        "-n",
    ]
    if context:
        argv.extend(["-C", str(context)])
    argv.extend([pattern, str(full)])
    result = _run_argv(argv, timeout=int(args.get("timeout_seconds") or 120))
    matches: list[dict[str, Any]] = []
    for line in result["stdout"].splitlines():
        try:
            row = json.loads(line)
        except Exception:
            continue
        if row.get("type") != "match":
            continue
        data = row.get("data") if isinstance(row.get("data"), dict) else {}
        path_info = data.get("path") if isinstance(data.get("path"), dict) else {}
        lines_info = data.get("lines") if isinstance(data.get("lines"), dict) else {}
        matches.append({
            "path": repo_rel(Path(str(path_info.get("text") or "")), LAB_REPO),
            "line_number": data.get("line_number"),
            "absolute_offset": data.get("absolute_offset"),
            "text": lines_info.get("text"),
            "submatches": data.get("submatches") if isinstance(data.get("submatches"), list) else [],
        })
        if len(matches) >= limit:
            break
    payload = {
        "ok": _tool_ok_returncode(result["returncode"], no_match_ok=True),
        "tool": "repo_rg_search",
        "path": rel,
        "pattern": pattern,
        "limit": limit,
        "count": len(matches),
        "matches": matches,
        "truncated": len(matches) >= limit,
        "returncode": result["returncode"],
        "stderr_tail": result["stderr_tail"],
    }
    artifact = _write_tool_artifact(root, "repo_rg_search", payload)
    payload["artifact"] = str(artifact)
    return payload


def repo_jq_query(args: dict[str, Any], root: Path) -> dict[str, Any]:
    exe = _resolve_deterministic_executable("jq")
    if not exe:
        return _deterministic_tool_missing("repo_jq_query", "jq")
    query = str(args.get("query") or args.get("filter") or "").strip()
    if not query:
        return {"ok": False, "tool": "repo_jq_query", "error": "missing query"}
    json_text = args.get("json_text")
    timeout = int(args.get("timeout_seconds") or 60)
    argv = [exe, query]
    repo_path = None
    stdin = None
    if isinstance(json_text, str) and json_text.strip():
        stdin = json_text
    else:
        try:
            repo_path, full = _repo_existing_path(args.get("path"))
        except Exception as exc:
            return {"ok": False, "tool": "repo_jq_query", "error": str(exc), "error_type": type(exc).__name__}
        if not full.is_file():
            return {"ok": False, "tool": "repo_jq_query", "path": repo_path, "error": "path_is_not_file"}
        argv.append(str(full))
    result = _run_argv(argv, timeout=timeout, stdin=stdin)
    parsed = _parse_json_output(result["stdout"])
    payload = {
        "ok": result["returncode"] == 0,
        "tool": "repo_jq_query",
        "query": query,
        "path": repo_path,
        "returncode": result["returncode"],
        "stdout": result["stdout"],
        "parsed_json": parsed,
        "stderr_tail": result["stderr_tail"],
    }
    artifact = _write_tool_artifact(root, "repo_jq_query", payload)
    payload["artifact"] = str(artifact)
    return payload


def repo_ast_grep_search(args: dict[str, Any], root: Path) -> dict[str, Any]:
    exe = _resolve_deterministic_executable("ast-grep") or _resolve_deterministic_executable("sg")
    if not exe:
        return _deterministic_tool_missing("repo_ast_grep_search", "ast-grep")
    pattern = str(args.get("pattern") or "").strip()
    kind = str(args.get("kind") or "").strip()
    lang = str(args.get("lang") or args.get("language") or "python").strip()
    rewrite = str(args.get("rewrite") or "").strip()
    if not pattern and not kind:
        return {"ok": False, "tool": "repo_ast_grep_search", "error": "missing pattern_or_kind"}
    try:
        rel, full = _repo_existing_path(args.get("path"), default=".")
    except Exception as exc:
        return {"ok": False, "tool": "repo_ast_grep_search", "error": str(exc), "error_type": type(exc).__name__}
    argv = [exe, "run", "--json=compact"]
    if pattern:
        argv.extend(["--pattern", pattern])
    if kind:
        argv.extend(["--kind", kind])
    if rewrite:
        argv.extend(["--rewrite", rewrite])
    if lang:
        argv.extend(["--lang", lang])
    argv.append(str(full))
    result = _run_argv(argv, timeout=int(args.get("timeout_seconds") or 120))
    parsed = _parse_json_output(result["stdout"])
    matches = parsed if isinstance(parsed, list) else []
    payload = {
        "ok": _tool_ok_returncode(result["returncode"], no_match_ok=True),
        "tool": "repo_ast_grep_search",
        "path": rel,
        "pattern": pattern,
        "kind": kind,
        "lang": lang,
        "rewrite_dry_run": bool(rewrite),
        "rewrite": rewrite or None,
        "count": len(matches),
        "matches": matches[:_TOOL_RESULT_ITEMS_LIMIT],
        "truncated": len(matches) > _TOOL_RESULT_ITEMS_LIMIT,
        "returncode": result["returncode"],
        "stderr_tail": result["stderr_tail"],
    }
    artifact = _write_tool_artifact(root, "repo_ast_grep_search", payload)
    payload["artifact"] = str(artifact)
    return payload


def repo_ast_grep_dry_run(args: dict[str, Any], root: Path) -> dict[str, Any]:
    payload = repo_ast_grep_search(args, root)
    payload["tool"] = "repo_ast_grep_dry_run"
    payload["dry_run"] = True
    payload["source_writes_performed"] = False
    payload["patch_application_performed"] = False
    artifact = _write_tool_artifact(root, "repo_ast_grep_dry_run", payload)
    payload["artifact"] = str(artifact)
    return payload


def repo_tree_sitter_parse(args: dict[str, Any], root: Path) -> dict[str, Any]:
    try:
        from tree_sitter import Language, Parser
        import tree_sitter_python
    except Exception as exc:
        return {
            "ok": False,
            "tool": "repo_tree_sitter_parse",
            "error": "tree_sitter_dependency_missing",
            "error_type": type(exc).__name__,
            "message": str(exc),
        }
    language = str(args.get("language") or args.get("lang") or "python").strip().lower()
    if language != "python":
        return {"ok": False, "tool": "repo_tree_sitter_parse", "error": "unsupported_tree_sitter_language", "language": language}
    try:
        rel, full = _repo_existing_path(args.get("path"))
    except Exception as exc:
        return {"ok": False, "tool": "repo_tree_sitter_parse", "error": str(exc), "error_type": type(exc).__name__}
    if not full.is_file():
        return {"ok": False, "tool": "repo_tree_sitter_parse", "path": rel, "error": "path_is_not_file"}
    source = full.read_bytes()
    parser = Parser()
    parser.language = Language(tree_sitter_python.language())
    tree = parser.parse(source)
    root_node = tree.root_node
    anchors: list[dict[str, Any]] = []
    wanted = {"function_definition", "class_definition", "import_statement", "import_from_statement"}

    def walk(node: Any) -> None:
        if node.type in wanted:
            name = ""
            child = node.child_by_field_name("name")
            if child is not None:
                name = source[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
            anchors.append({
                "type": node.type,
                "name": name,
                "start_point": list(node.start_point),
                "end_point": list(node.end_point),
                "start_byte": node.start_byte,
                "end_byte": node.end_byte,
            })
        for child in node.children:
            walk(child)

    walk(root_node)
    payload = {
        "ok": not root_node.has_error,
        "tool": "repo_tree_sitter_parse",
        "path": rel,
        "language": language,
        "root_type": root_node.type,
        "has_error": bool(root_node.has_error),
        "anchors": anchors[:_TOOL_RESULT_ITEMS_LIMIT],
        "anchors_total": len(anchors),
        "truncated": len(anchors) > _TOOL_RESULT_ITEMS_LIMIT,
    }
    artifact = _write_tool_artifact(root, "repo_tree_sitter_parse", payload)
    payload["artifact"] = str(artifact)
    return payload


def repo_unidiff_validate(args: dict[str, Any], root: Path) -> dict[str, Any]:
    try:
        from unidiff import PatchSet
    except Exception as exc:
        return {
            "ok": False,
            "tool": "repo_unidiff_validate",
            "error": "unidiff_dependency_missing",
            "error_type": type(exc).__name__,
            "message": str(exc),
        }
    diff_text = args.get("unified_diff") or args.get("diff")
    if not isinstance(diff_text, str) or not diff_text.strip():
        return {"ok": False, "tool": "repo_unidiff_validate", "error": "missing_unified_diff"}
    errors: list[str] = []
    files: list[dict[str, Any]] = []
    try:
        patch = PatchSet(diff_text.splitlines(True))
        for patched in patch:
            files.append({
                "path": patched.path,
                "source_file": patched.source_file,
                "target_file": patched.target_file,
                "is_added_file": patched.is_added_file,
                "is_removed_file": patched.is_removed_file,
                "is_modified_file": patched.is_modified_file,
                "added": patched.added,
                "removed": patched.removed,
                "hunks": len(patched),
            })
    except Exception as exc:
        errors.append(f"unidiff_parse_error:{type(exc).__name__}:{str(exc)[:300]}")
    if "--- " not in diff_text or "+++ " not in diff_text or "@@" not in diff_text:
        errors.append("missing_unified_diff_markers")
    payload = {
        "ok": not errors,
        "tool": "repo_unidiff_validate",
        "file_count": len(files),
        "files": files,
        "errors": errors,
    }
    artifact = _write_tool_artifact(root, "repo_unidiff_validate", payload)
    payload["artifact"] = str(artifact)
    return payload


def repo_git_apply_check(args: dict[str, Any], root: Path) -> dict[str, Any]:
    exe = _resolve_deterministic_executable("git")
    if not exe:
        return _deterministic_tool_missing("repo_git_apply_check", "git")
    diff_text = args.get("unified_diff") or args.get("diff") or args.get("patch")
    if not isinstance(diff_text, str) or not diff_text.strip():
        return {"ok": False, "tool": "repo_git_apply_check", "error": "missing_unified_diff"}
    argv = [exe, "apply", "--check", "--whitespace=error", "-"]
    result = _run_argv(argv, timeout=int(args.get("timeout_seconds") or 120), stdin=diff_text)
    payload = {
        "ok": result["returncode"] == 0,
        "tool": "repo_git_apply_check",
        "returncode": result["returncode"],
        "stdout": result["stdout"],
        "stderr": result["stderr"],
        "stdout_tail": result["stdout_tail"],
        "stderr_tail": result["stderr_tail"],
        "patch_application_performed": False,
        "source_writes_performed": False,
    }
    artifact = _write_tool_artifact(root, "repo_git_apply_check", payload)
    payload["artifact"] = str(artifact)
    return payload


def repo_ruff_check(args: dict[str, Any], root: Path) -> dict[str, Any]:
    exe = _resolve_deterministic_executable("ruff")
    if not exe:
        return _deterministic_tool_missing("repo_ruff_check", "ruff")
    try:
        targets = _repo_existing_paths(args.get("paths") or args.get("path"), default=".")
    except Exception as exc:
        return {"ok": False, "tool": "repo_ruff_check", "error": str(exc), "error_type": type(exc).__name__}
    argv = [exe, "check", "--output-format=json"]
    argv.extend(str(full) for _rel, full in targets)
    result = _run_argv(argv, timeout=int(args.get("timeout_seconds") or 180))
    diagnostics = _parse_json_output(result["stdout"])
    if not isinstance(diagnostics, list):
        diagnostics = []
    payload = {
        "ok": result["returncode"] == 0,
        "tool": "repo_ruff_check",
        "paths": [rel for rel, _full in targets],
        "returncode": result["returncode"],
        "diagnostics": diagnostics[:_TOOL_RESULT_ITEMS_LIMIT],
        "diagnostics_total": len(diagnostics),
        "truncated": len(diagnostics) > _TOOL_RESULT_ITEMS_LIMIT,
        "stderr_tail": result["stderr_tail"],
    }
    artifact = _write_tool_artifact(root, "repo_ruff_check", payload)
    payload["artifact"] = str(artifact)
    return payload


def repo_pyright_check(args: dict[str, Any], root: Path) -> dict[str, Any]:
    exe = _resolve_deterministic_executable("pyright")
    if not exe:
        return _deterministic_tool_missing("repo_pyright_check", "pyright")
    try:
        targets = _repo_existing_paths(args.get("paths") or args.get("path"), default=".")
    except Exception as exc:
        return {"ok": False, "tool": "repo_pyright_check", "error": str(exc), "error_type": type(exc).__name__}
    argv = [exe, "--outputjson"]
    argv.extend(str(full) for _rel, full in targets)
    result = _run_argv(argv, timeout=int(args.get("timeout_seconds") or 240))
    parsed = _parse_json_output(result["stdout"])
    payload = {
        "ok": result["returncode"] == 0,
        "tool": "repo_pyright_check",
        "paths": [rel for rel, _full in targets],
        "returncode": result["returncode"],
        "result": parsed,
        "stderr_tail": result["stderr_tail"],
    }
    artifact = _write_tool_artifact(root, "repo_pyright_check", payload)
    payload["artifact"] = str(artifact)
    return payload


def repo_pytest_run(args: dict[str, Any], root: Path) -> dict[str, Any]:
    exe = _resolve_deterministic_executable("pytest")
    if not exe:
        return _deterministic_tool_missing("repo_pytest_run", "pytest")
    try:
        targets = _repo_existing_paths(args.get("paths") or args.get("path"), default=".")
    except Exception as exc:
        return {"ok": False, "tool": "repo_pytest_run", "error": str(exc), "error_type": type(exc).__name__}
    maxfail = max(1, min(int(args.get("maxfail") or 1), 20))
    argv = [exe, "-q", "--maxfail", str(maxfail), "--disable-warnings"]
    marker = str(args.get("marker") or "").strip()
    if marker:
        argv.extend(["-m", marker])
    argv.extend(str(full) for _rel, full in targets)
    result = _run_argv(argv, timeout=int(args.get("timeout_seconds") or 300))
    payload = {
        "ok": result["returncode"] == 0,
        "tool": "repo_pytest_run",
        "paths": [rel for rel, _full in targets],
        "returncode": result["returncode"],
        "stdout": result["stdout"],
        "stderr": result["stderr"],
        "stdout_tail": result["stdout_tail"],
        "stderr_tail": result["stderr_tail"],
    }
    artifact = _write_tool_artifact(root, "repo_pytest_run", payload)
    payload["artifact"] = str(artifact)
    return payload


def repo_shellcheck(args: dict[str, Any], root: Path) -> dict[str, Any]:
    exe = _resolve_deterministic_executable("shellcheck")
    if not exe:
        return _deterministic_tool_missing("repo_shellcheck", "shellcheck")
    try:
        targets = _repo_existing_paths(args.get("paths") or args.get("path"), default=".")
    except Exception as exc:
        return {"ok": False, "tool": "repo_shellcheck", "error": str(exc), "error_type": type(exc).__name__}
    files = [(rel, full) for rel, full in targets if full.is_file()]
    if not files:
        return {"ok": False, "tool": "repo_shellcheck", "error": "no_files_selected"}
    argv = [exe, "--format=json"]
    argv.extend(str(full) for _rel, full in files)
    result = _run_argv(argv, timeout=int(args.get("timeout_seconds") or 120))
    parsed = _parse_json_output(result["stdout"])
    comments = parsed.get("comments") if isinstance(parsed, dict) else []
    payload = {
        "ok": result["returncode"] == 0,
        "tool": "repo_shellcheck",
        "paths": [rel for rel, _full in files],
        "returncode": result["returncode"],
        "comments": comments if isinstance(comments, list) else [],
        "stderr_tail": result["stderr_tail"],
    }
    artifact = _write_tool_artifact(root, "repo_shellcheck", payload)
    payload["artifact"] = str(artifact)
    return payload


def repo_ctags_symbols(args: dict[str, Any], root: Path) -> dict[str, Any]:
    exe = _resolve_deterministic_executable("ctags")
    if not exe:
        return _deterministic_tool_missing("repo_ctags_symbols", "ctags")
    try:
        targets = _repo_existing_paths(args.get("paths") or args.get("path"), default=".")
    except Exception as exc:
        return {"ok": False, "tool": "repo_ctags_symbols", "error": str(exc), "error_type": type(exc).__name__}
    limit = max(1, min(int(args.get("limit") or 500), 5000))
    argv = [exe, "--output-format=json", "-f", "-"]
    if any(full.is_dir() for _rel, full in targets):
        argv.append("-R")
    argv.extend(str(full) for _rel, full in targets)
    result = _run_argv(argv, timeout=int(args.get("timeout_seconds") or 120))
    symbols = []
    for line in result["stdout"].splitlines():
        try:
            row = json.loads(line)
        except Exception:
            continue
        if isinstance(row, dict) and row.get("_type") == "tag":
            if "path" in row:
                row["path"] = repo_rel(Path(str(row["path"])), LAB_REPO)
            symbols.append(row)
    payload = {
        "ok": result["returncode"] == 0,
        "tool": "repo_ctags_symbols",
        "paths": [rel for rel, _full in targets],
        "returncode": result["returncode"],
        "symbols": symbols[:limit],
        "symbols_total": len(symbols),
        "truncated": len(symbols) > limit,
        "stderr_tail": result["stderr_tail"],
    }
    artifact = _write_tool_artifact(root, "repo_ctags_symbols", payload)
    payload["artifact"] = str(artifact)
    return payload


def repo_semgrep_scan(args: dict[str, Any], root: Path) -> dict[str, Any]:
    exe = _resolve_deterministic_executable("semgrep")
    if not exe:
        return _deterministic_tool_missing("repo_semgrep_scan", "semgrep")
    pattern = str(args.get("pattern") or "").strip()
    config = str(args.get("config") or "").strip()
    lang = str(args.get("lang") or args.get("language") or "python").strip()
    if not pattern and not config:
        return {"ok": False, "tool": "repo_semgrep_scan", "error": "missing_pattern_or_config"}
    try:
        targets = _repo_existing_paths(args.get("paths") or args.get("path"), default=".")
    except Exception as exc:
        return {"ok": False, "tool": "repo_semgrep_scan", "error": str(exc), "error_type": type(exc).__name__}
    argv = [exe, "--json", "--disable-version-check"]
    if pattern:
        argv.extend(["--lang", lang, "--pattern", pattern])
    else:
        argv.extend(["--config", config])
    argv.extend(str(full) for _rel, full in targets)
    result = _run_argv(argv, timeout=int(args.get("timeout_seconds") or 240))
    parsed = _parse_json_output(result["stdout"])
    findings = parsed.get("results") if isinstance(parsed, dict) else []
    payload = {
        "ok": result["returncode"] in (0, 1),
        "tool": "repo_semgrep_scan",
        "paths": [rel for rel, _full in targets],
        "pattern": pattern,
        "config": config or None,
        "lang": lang if pattern else None,
        "returncode": result["returncode"],
        "results": findings[:_TOOL_RESULT_ITEMS_LIMIT] if isinstance(findings, list) else [],
        "results_total": len(findings) if isinstance(findings, list) else 0,
        "truncated": isinstance(findings, list) and len(findings) > _TOOL_RESULT_ITEMS_LIMIT,
        "errors": parsed.get("errors") if isinstance(parsed, dict) else [],
        "stderr_tail": result["stderr_tail"],
    }
    artifact = _write_tool_artifact(root, "repo_semgrep_scan", payload)
    payload["artifact"] = str(artifact)
    return payload


def repo_hyperfine_benchmark(
    args: dict[str, Any],
    root: Path,
    allow_command: bool,
    user_consent: str,
) -> dict[str, Any]:
    exe = _resolve_deterministic_executable("hyperfine")
    if not exe:
        return _deterministic_tool_missing("repo_hyperfine_benchmark", "hyperfine")
    commands = [str(cmd).strip() for cmd in args.get("commands", []) if str(cmd).strip()] if isinstance(args.get("commands"), list) else []
    if not commands:
        return {"ok": False, "tool": "repo_hyperfine_benchmark", "error": "missing_commands"}
    if len(commands) > 4:
        return {"ok": False, "tool": "repo_hyperfine_benchmark", "error": "too_many_commands", "max_commands": 4}
    if not allow_command and (
        "confirm" not in str(user_consent or "").lower()
        and "confermo" not in str(user_consent or "").lower()
    ):
        return {
            "ok": False,
            "tool": "repo_hyperfine_benchmark",
            "needs_consent": True,
            "error": "benchmark commands require explicit consent",
        }
    for command in commands:
        if dangerous_command(command):
            return {
                "ok": False,
                "tool": "repo_hyperfine_benchmark",
                "needs_consent": True,
                "error": "dangerous benchmark command blocked",
                "command": command,
            }
    runs = max(1, min(int(args.get("runs") or 3), 20))
    warmup = max(0, min(int(args.get("warmup") or 1), 10))
    argv = [exe, "--runs", str(runs), "--warmup", str(warmup), "--export-json", "-"]
    argv.extend(commands)
    result = _run_argv(argv, timeout=int(args.get("timeout_seconds") or 600))
    parsed = _parse_json_output(result["stdout"])
    payload = {
        "ok": result["returncode"] == 0,
        "tool": "repo_hyperfine_benchmark",
        "runs": runs,
        "warmup": warmup,
        "commands": commands,
        "returncode": result["returncode"],
        "result": parsed,
        "stdout_tail": result["stdout_tail"],
        "stderr_tail": result["stderr_tail"],
    }
    artifact = _write_tool_artifact(root, "repo_hyperfine_benchmark", payload)
    payload["artifact"] = str(artifact)
    return payload


# ---------------------------------------------------------------------------
# Tool: repo_read
# ---------------------------------------------------------------------------


def _read_paths_from_items(value: object) -> list[str]:
    paths: list[str] = []
    if isinstance(value, dict):
        value = [value]
    if not isinstance(value, list):
        return paths
    for item in value:
        if isinstance(item, str) and item.strip():
            paths.append(item.strip())
        elif isinstance(item, dict):
            for key in ("path", "file", "filename", "name"):
                candidate = item.get(key)
                if isinstance(candidate, str) and candidate.strip():
                    paths.append(candidate.strip())
                    break
            nested = item.get("paths") or item.get("files")
            if isinstance(nested, list):
                paths.extend(str(p).strip() for p in nested if str(p).strip())
    return paths


def repo_read(args: dict[str, Any], root: Path) -> dict[str, Any]:
    paths: list[str] = []
    if isinstance(args.get("paths"), list):
        paths.extend(str(p) for p in args["paths"] if str(p).strip())
    if args.get("path"):
        paths.append(str(args["path"]))
    paths.extend(_read_paths_from_items(args.get("items") or args.get("item")))

    # Preserve order while removing duplicates. Silent count=0 was causing the
    # planner to hallucinate a successful file read.
    deduped: list[str] = []
    for raw_path in paths:
        raw_s = str(raw_path).strip()
        if raw_s and raw_s not in deduped:
            deduped.append(raw_s)
    paths = deduped

    max_chars = int(args.get("max_chars") or 80000)
    max_paths = max(1, min(int(args.get("max_paths") or args.get("limit") or 200), 500))
    line = args.get("line")
    before = int(args.get("before") or 40)
    after = int(args.get("after") or 120)
    items: list[dict[str, Any]] = []

    for raw in paths[:max_paths]:
        try:
            rel = safe_rel_path(raw)
            full = (LAB_REPO / rel).resolve(strict=False)
            full.relative_to(LAB_REPO)
            if not full.exists() or not full.is_file():
                items.append({"ok": False, "path": rel, "error": "file_not_found"})
                continue
            text = full.read_text(encoding="utf-8-sig", errors="replace")
            if line:
                lines = text.splitlines()
                n = max(1, min(int(line), max(1, len(lines))))
                start = max(1, n - before)
                end = min(len(lines), n + after)
                content = "\n".join(
                    f"{i}: {lines[i - 1]}" for i in range(start, end + 1)
                )
            else:
                content = text
            item: dict[str, Any] = {
                "ok": True,
                "path": rel,
                "size_bytes": full.stat().st_size,
                "line_count": len(text.splitlines()),
                "content": content[:max_chars],
                "truncated": len(content) > max_chars,
            }
            safe_name = rel.replace("/", "__").replace("\\", "__")
            artifact = root / "reads" / f"{safe_name}.json"
            artifact_item = dict(item)
            artifact_item["content"] = content
            artifact_item["truncated"] = False
            artifact_item["inline_result_truncated"] = item["truncated"]
            artifact_item["inline_max_chars"] = max_chars
            write_json(artifact, artifact_item)
            item["artifact"] = str(artifact)
            items.append(item)
        except Exception as exc:
            items.append({"ok": False, "path": raw,
                           "error_type": type(exc).__name__, "error": str(exc)})

    if not paths:
        payload = {
            "ok": False,
            "tool": "repo_read",
            "count": 0,
            "items": [],
            "error": "missing path/paths/items",
            "input_keys": sorted(str(k) for k in args.keys()),
        }
    else:
        success_count = sum(1 for item in items if isinstance(item, dict) and item.get("ok") is True)
        failed_count = sum(1 for item in items if isinstance(item, dict) and item.get("ok") is False)
        payload = {
            "ok": success_count > 0,
            "tool": "repo_read",
            "count": len(items),
            "requested_count": len(paths),
            "max_paths": max_paths,
            "success_count": success_count,
            "failed_count": failed_count,
            "all_ok": bool(items) and success_count == len(items),
            "items": items,
        }
    write_json(root / "tool-results" / f"{now()}-repo_read.json", payload)
    return payload


# ---------------------------------------------------------------------------
# Tool: repo_propose_code_edit
# ---------------------------------------------------------------------------


def repo_propose_code_edit(args: dict[str, Any], root: Path) -> dict[str, Any]:
    try:
        from .code_edit_proposal_contract import build_code_edit_proposal
    except Exception as exc:
        return {
            "ok": False,
            "tool": "repo_propose_code_edit",
            "error": "code_edit_proposal_helper_missing",
            "error_type": type(exc).__name__,
            "message": str(exc),
        }

    target_file = str(args.get("target_file") or args.get("path") or "").strip()
    edit_kind = str(args.get("edit_kind") or "").strip()
    rationale = str(args.get("rationale") or args.get("reason") or "").strip()
    validation_commands = (
        [str(cmd) for cmd in args.get("validation_commands") if str(cmd).strip()]
        if isinstance(args.get("validation_commands"), list)
        else None
    )

    tree_sitter_language = str(args.get("tree_sitter_language") or "").strip()
    if not tree_sitter_language and target_file.replace("\\", "/").endswith(".py"):
        tree_sitter_language = "python"

    try:
        proposal = build_code_edit_proposal(
            repo_root=LAB_REPO,
            target_file=target_file,
            edit_kind=edit_kind,
            rationale=rationale,
            unified_diff=args.get("unified_diff"),
            structured_operations=args.get("structured_operations") or args.get("operations"),
            old_text=args.get("old_text") if isinstance(args.get("old_text"), str) else None,
            new_text=args.get("new_text") if isinstance(args.get("new_text"), str) else None,
            validation_commands=validation_commands,
            require_unidiff=parse_bool(args.get("require_unidiff"), default=True),
            ast_anchor=str(args.get("ast_anchor") or "").strip() or None,
            ast_grep_rule=str(args.get("ast_grep_rule") or "").strip() or None,
            tree_sitter_language=tree_sitter_language or None,
        )
    except Exception as exc:
        proposal = {
            "kind": "code_edit_proposal",
            "target_file": target_file,
            "edit_kind": edit_kind,
            "rationale": rationale,
            "source_writes_performed": False,
            "patch_application_performed": False,
            "manual_review_required": True,
            "validation_commands": validation_commands or [],
            "errors": [f"code_edit_proposal_build_failed:{type(exc).__name__}"],
            "warnings": [],
            "message": str(exc),
        }

    payload = {
        "ok": not bool(proposal.get("errors")),
        "tool": "repo_propose_code_edit",
        **proposal,
    }
    artifact = root / "tool-results" / f"{now()}-repo_propose_code_edit.json"
    write_json(artifact, payload)
    payload["artifact"] = str(artifact)
    return payload


# ---------------------------------------------------------------------------
# Tool: repo_apply_patch
# ---------------------------------------------------------------------------


def repo_apply_patch(args: dict[str, Any], root: Path) -> dict[str, Any]:
    path = str(args.get("path") or "").strip()
    old_text = args.get("old_text")
    new_text = args.get("new_text")
    max_replacements = max(1, min(int(args.get("max_replacements") or 1), 20))

    if not path:
        return {"ok": False, "tool": "repo_apply_patch", "error": "missing path"}
    if not isinstance(old_text, str) or old_text == "":
        return {"ok": False, "tool": "repo_apply_patch", "error": "missing old_text"}
    if not isinstance(new_text, str):
        return {"ok": False, "tool": "repo_apply_patch", "error": "missing new_text"}

    try:
        rel = safe_rel_path(path)
        full = (LAB_REPO / rel).resolve(strict=False)
        full.relative_to(LAB_REPO)
    except Exception as exc:
        return {"ok": False, "tool": "repo_apply_patch", "path": path,
                "error_type": type(exc).__name__, "error": str(exc)}

    if not full.exists() or not full.is_file():
        return {"ok": False, "tool": "repo_apply_patch", "path": rel, "error": "file_not_found"}

    original = full.read_text(encoding="utf-8-sig", errors="replace")
    occurrences = original.count(old_text)
    if occurrences < 1:
        return {"ok": False, "tool": "repo_apply_patch", "path": rel,
                "error": "old_text_not_found", "old_text_preview": old_text[:1000]}

    replacements = min(occurrences, max_replacements)
    updated = original.replace(old_text, new_text, replacements)

    safe_name = rel.replace("/", "__").replace("\\", "__")
    backup = root / "artifacts" / f"{safe_name}.{now()}.before.txt"
    backup.parent.mkdir(parents=True, exist_ok=True)
    backup.write_text(original, encoding="utf-8")
    full.write_text(updated, encoding="utf-8")

    payload = {
        "ok": True,
        "tool": "repo_apply_patch",
        "path": rel,
        "changed": updated != original,
        "occurrences_found": occurrences,
        "replacements": replacements,
        "line_count_before": len(original.splitlines()),
        "line_count_after": len(updated.splitlines()),
        "backup_artifact": str(backup),
    }
    write_json(root / "tool-results" / f"{now()}-repo_apply_patch.json", payload)
    return payload


# ---------------------------------------------------------------------------
# Tool: repo_write_file
# ---------------------------------------------------------------------------


def repo_write_file(args: dict[str, Any], root: Path) -> dict[str, Any]:
    path = str(args.get("path") or "").strip()
    content = args.get("content")
    mode = str(args.get("mode") or "overwrite").strip().lower()
    encoding = str(args.get("encoding") or "utf-8").strip() or "utf-8"

    if not path:
        return {"ok": False, "tool": "repo_write_file", "error": "missing path"}
    if not isinstance(content, str):
        return {"ok": False, "tool": "repo_write_file", "path": path,
                "error": "missing string content"}
    if mode not in {"overwrite", "create", "append"}:
        return {"ok": False, "tool": "repo_write_file", "path": path,
                "error": "mode must be overwrite, create or append"}

    try:
        rel = safe_rel_path(path)
        full = (LAB_REPO / rel).resolve(strict=False)
        full.relative_to(LAB_REPO)
    except Exception as exc:
        return {"ok": False, "tool": "repo_write_file", "path": path,
                "error_type": type(exc).__name__, "error": str(exc)}

    if full.exists() and full.is_dir():
        return {"ok": False, "tool": "repo_write_file", "path": rel,
                "error": "target_is_directory"}
    if mode == "create" and full.exists():
        return {"ok": False, "tool": "repo_write_file", "path": rel, "error": "file_exists"}

    backup_path = before_sha256 = ""
    before_size = 0
    if full.exists() and full.is_file():
        old_bytes = full.read_bytes()
        before_size = len(old_bytes)
        before_sha256 = hashlib.sha256(old_bytes).hexdigest()
        safe_name = rel.replace("/", "__").replace("\\", "__")
        backup = root / "backups" / f"{now()}-{safe_name}.bak"
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.write_bytes(old_bytes)
        backup_path = str(backup)

    full.parent.mkdir(parents=True, exist_ok=True)
    if mode == "append":
        with full.open("a", encoding=encoding, errors="replace", newline="") as f:
            f.write(content)
    else:
        full.write_text(content, encoding=encoding, errors="replace", newline="")

    after_bytes = full.read_bytes()
    after_sha256 = hashlib.sha256(after_bytes).hexdigest()

    payload = {
        "ok": True,
        "tool": "repo_write_file",
        "path": rel,
        "mode": mode,
        "backup_path": backup_path,
        "before_size": before_size,
        "after_size": len(after_bytes),
        "before_sha256": before_sha256,
        "after_sha256": after_sha256,
        "line_count_after": len(
            full.read_text(encoding=encoding, errors="replace").splitlines()
        ),
    }
    artifact = root / "tool-results" / f"{now()}-repo_write_file.json"
    write_json(artifact, payload)
    payload["artifact"] = str(artifact)
    return payload


# ---------------------------------------------------------------------------
# Tool: repo_validate
# ---------------------------------------------------------------------------


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
        r = run_ps(cmd, timeout=timeout)
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


# ---------------------------------------------------------------------------
# Tool: repo_command
# ---------------------------------------------------------------------------


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
