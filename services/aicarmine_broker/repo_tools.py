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
    parse_bool,
)
from .infrastructure.filesystem_repo import repo_rel, safe_rel_path
from .job_store import now, write_json
from .tools.command_safety import dangerous_command
from .tools.powershell_runner import run_ps as _tool_run_ps
from .tools.repo_code_product import repo_propose_code_edit
from .tools.repo_command import repo_command
from .tools.repo_list_files import repo_list_files
from .tools.repo_patch import repo_apply_patch, repo_write_file
from .tools.repo_read import repo_read
from .tools.repo_search import repo_search
from .tools.repo_status import detect_stack, repo_capabilities, repo_status
from .tools.repo_tree import repo_tree
from .tools.repo_validate import repo_validate
from .tools.terminal import (
    normalize_terminal_path,
    strip_terminal_ansi,
    terminal_environment_contract,
    terminal_list_files,
    terminal_preferred_cwd,
    terminal_run_command_wait,
    terminal_search_files,
)


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------


def run_ps(command: str, timeout: int = COMMAND_TIMEOUT_SECONDS) -> dict[str, Any]:
    return _tool_run_ps(command, timeout=timeout)


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
