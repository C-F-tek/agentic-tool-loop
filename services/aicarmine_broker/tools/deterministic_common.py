from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from aicarmine_broker.config import COMMAND_TIMEOUT_SECONDS, LAB_REPO
from aicarmine_broker.infrastructure.filesystem_repo import safe_rel_path
from aicarmine_broker.job_store import now, write_json
from aicarmine_broker.tools.terminal import strip_terminal_ansi


TOOL_RESULT_TEXT_LIMIT = 120_000
TOOL_RESULT_ITEMS_LIMIT = 500


def active_venv_script(name: str) -> Path:
    suffix = ".exe" if os.name == "nt" and not name.lower().endswith(".exe") else ""
    return Path(sys.executable).resolve(strict=False).parent / f"{name}{suffix}"


def winget_package_executable(package_prefix: str, executable_name: str) -> Path | None:
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


EXE_FALLBACKS: dict[str, list[Path]] = {
    "ctags": [
        candidate
        for candidate in [
            winget_package_executable("UniversalCtags.Ctags", "ctags.exe"),
        ]
        if candidate is not None
    ],
    "shellcheck": [
        candidate
        for candidate in [
            winget_package_executable("koalaman.shellcheck", "shellcheck.exe"),
        ]
        if candidate is not None
    ],
    "hyperfine": [
        candidate
        for candidate in [
            winget_package_executable("sharkdp.hyperfine", "hyperfine.exe"),
        ]
        if candidate is not None
    ],
    "ruff": [active_venv_script("ruff")],
    "pyright": [active_venv_script("pyright")],
    "pytest": [active_venv_script("pytest")],
    "semgrep": [active_venv_script("semgrep")],
}


def resolve_deterministic_executable(name: str) -> str | None:
    normalized = str(name or "").strip()
    if not normalized:
        return None
    for candidate in EXE_FALLBACKS.get(normalized.lower(), []):
        if candidate and candidate.exists():
            return str(candidate)
    found = shutil.which(normalized)
    if found:
        return found
    return None


def deterministic_tool_missing(tool: str, executable: str) -> dict[str, Any]:
    return {
        "ok": False,
        "tool": tool,
        "error": "deterministic_tool_missing",
        "missing_executable": executable,
    }


def bounded_text(value: Any, limit: int = TOOL_RESULT_TEXT_LIMIT) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    return text[:limit] + ("\n... <truncated>" if len(text) > limit else "")


def run_argv(
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
            "stdout": bounded_text(stdout),
            "stderr": bounded_text(stderr),
            "stdout_tail": stdout[-8000:],
            "stderr_tail": stderr[-8000:],
            "timed_out": False,
        }
    except subprocess.TimeoutExpired as exc:
        stdout = strip_terminal_ansi(exc.stdout or "")
        stderr = strip_terminal_ansi(exc.stderr or "")
        return {
            "returncode": None,
            "stdout": bounded_text(stdout),
            "stderr": bounded_text(stderr),
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


def repo_existing_path(value: str | None, *, default: str = ".") -> tuple[str, Path]:
    raw = str(value or default).strip() or default
    rel = "." if raw in {"", "."} else safe_rel_path(raw)
    full = (LAB_REPO / rel).resolve(strict=False)
    full.relative_to(LAB_REPO)
    if not full.exists():
        raise FileNotFoundError(rel)
    return rel, full


def repo_existing_paths(values: Any, *, default: str = ".") -> list[tuple[str, Path]]:
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
        rel, full = repo_existing_path(raw)
        if rel not in seen:
            seen.add(rel)
            out.append((rel, full))
    return out


def parse_json_output(stdout: str) -> Any:
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


def write_tool_artifact(root: Path, tool: str, payload: dict[str, Any]) -> Path:
    artifact = root / "tool-results" / f"{now()}-{tool}.json"
    write_json(artifact, payload)
    return artifact


def tool_ok_returncode(returncode: Any, *, no_match_ok: bool = False) -> bool:
    if returncode == 0:
        return True
    return bool(no_match_ok and returncode == 1)
