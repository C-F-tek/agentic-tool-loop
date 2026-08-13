from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from ..config import COMMAND_TIMEOUT_SECONDS, LAB_REPO
from ..config.env_loader import env_str
from ..infrastructure.filesystem_repo import safe_rel_path
from ..job_store import now, write_json
from .terminal import strip_terminal_ansi


TOOL_RESULT_TEXT_LIMIT = 120_000
TOOL_RESULT_ITEMS_LIMIT = 500


class DeterministicToolInputError(ValueError):
    """Bounded error for deterministic tool input validation failures."""
    def __init__(
        self,
        error: str,
        *,
        argument: str | None = None,
        value: Any = None,
        path: str | None = None,
        detail: str | None = None,
    ) -> None:
        super().__init__(error)
        self.error = error
        self.argument = argument
        self.value = value
        self.path = path
        self.detail = detail

    def payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"error": self.error}
        if self.argument:
            payload["argument"] = self.argument
        if self.value is not None:
            payload["value"] = self.value
        if self.path:
            payload["path"] = self.path
        if self.detail:
            payload["detail"] = self.detail
        return payload


def active_venv_script(name: str) -> Path:
    suffix = ".exe" if os.name == "nt" and not name.lower().endswith(".exe") else ""
    return Path(sys.executable).resolve(strict=False).parent / f"{name}{suffix}"


def winget_package_executable(package_prefix: str, executable_name: str) -> Path | None:
    local = env_str("LOCALAPPDATA", "")
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


def deterministic_input_error(tool: str, exc: Exception) -> dict[str, Any]:
    payload: dict[str, Any] = {"ok": False, "tool": tool}
    if isinstance(exc, DeterministicToolInputError):
        payload.update(exc.payload())
        payload["error_type"] = type(exc).__name__
        return payload
    payload.update({"error": str(exc), "error_type": type(exc).__name__})
    return payload


def bounded_int_arg(
    args: dict[str, Any],
    names: str | tuple[str, ...],
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    keys = (names,) if isinstance(names, str) else names
    label = "/".join(keys)
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
    except (TypeError, ValueError) as exc:
        raise DeterministicToolInputError(
            "invalid_integer_argument",
            argument=label,
            value=selected,
        ) from exc
    return max(minimum, min(parsed, maximum))


def bounded_text(value: Any, limit: int = TOOL_RESULT_TEXT_LIMIT) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    return text[:limit] + ("\n... <truncated>" if len(text) > limit else "")


def subprocess_text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value or "")


def run_argv(
    argv: list[str],
    *,
    cwd: Path | None = None,
    timeout: int = COMMAND_TIMEOUT_SECONDS,
    stdin: str | None = None,
    stdin_bytes: bytes | None = None,
) -> dict[str, Any]:
    if stdin is not None and stdin_bytes is not None:
        return {
            "returncode": None,
            "stdout": "",
            "stderr": "",
            "stdout_tail": "",
            "stderr_tail": "",
            "timed_out": False,
            "error": "stdin and stdin_bytes are mutually exclusive",
            "error_type": "ValueError",
        }
    try:
        common_kwargs: dict[str, Any] = {
            "cwd": str((cwd or LAB_REPO).resolve(strict=False)),
            "capture_output": True,
            "timeout": timeout,
        }
        if stdin_bytes is not None:
            completed = subprocess.run(argv, input=stdin_bytes, **common_kwargs)
        else:
            completed = subprocess.run(
                argv,
                input=stdin,
                text=True,
                encoding="utf-8",
                errors="replace",
                **common_kwargs,
            )
        stdout = strip_terminal_ansi(subprocess_text(completed.stdout))
        stderr = strip_terminal_ansi(subprocess_text(completed.stderr))
        return {
            "returncode": completed.returncode,
            "stdout": bounded_text(stdout),
            "stderr": bounded_text(stderr),
            "stdout_tail": stdout[-8000:],
            "stderr_tail": stderr[-8000:],
            "timed_out": False,
        }
    except subprocess.TimeoutExpired as exc:
        stdout = strip_terminal_ansi(subprocess_text(exc.stdout))
        stderr = strip_terminal_ansi(subprocess_text(exc.stderr))
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
    try:
        rel = "." if raw in {"", "."} else safe_rel_path(raw)
    except ValueError as exc:
        raise DeterministicToolInputError(
            "invalid_repo_path",
            argument="path",
            value=raw,
            detail=str(exc),
        ) from exc
    full = (LAB_REPO / rel).resolve(strict=False)
    try:
        full.relative_to(LAB_REPO)
    except ValueError as exc:
        raise DeterministicToolInputError("path_escapes_repo", argument="path", path=rel) from exc
    if not full.exists():
        raise DeterministicToolInputError("path_not_found", argument="path", path=rel)
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
