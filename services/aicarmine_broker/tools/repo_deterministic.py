from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

from aicarmine_broker.config import LAB_REPO
from aicarmine_broker.infrastructure.filesystem_repo import repo_rel
from aicarmine_broker.tools.command_safety import dangerous_command
from aicarmine_broker.tools.deterministic_common import (
    TOOL_RESULT_ITEMS_LIMIT as _TOOL_RESULT_ITEMS_LIMIT,
    bounded_int_arg as _bounded_int_arg,
    deterministic_input_error as _deterministic_input_error,
    deterministic_tool_missing as _deterministic_tool_missing,
    parse_json_output as _parse_json_output,
    repo_existing_path as _repo_existing_path,
    repo_existing_paths as _repo_existing_paths,
    resolve_deterministic_executable as _resolve_deterministic_executable,
    run_argv as _run_argv,
    tool_ok_returncode as _tool_ok_returncode,
    write_tool_artifact as _write_tool_artifact,
)



def repo_fd_files(args: dict[str, Any], root: Path) -> dict[str, Any]:
    exe = _resolve_deterministic_executable("fd")
    if not exe:
        return _deterministic_tool_missing("repo_fd_files", "fd")
    pattern = str(args.get("pattern") or args.get("query") or "").strip()
    extension = str(args.get("extension") or args.get("suffix") or "").strip().lstrip(".")
    try:
        limit = _bounded_int_arg(args, ("limit", "max_results"), default=200, minimum=1, maximum=5000)
        rel, full = _repo_existing_path(args.get("path"), default=".")
    except Exception as exc:
        return _deterministic_input_error("repo_fd_files", exc)
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
    try:
        timeout = _bounded_int_arg(args, "timeout_seconds", default=60, minimum=1, maximum=600)
    except Exception as exc:
        return _deterministic_input_error("repo_fd_files", exc)
    result = _run_argv(argv, timeout=timeout)
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
        return {"ok": False, "tool": "repo_rg_search", "error": "missing_pattern"}
    try:
        limit = _bounded_int_arg(args, ("max_results", "limit"), default=80, minimum=1, maximum=1000)
        context = _bounded_int_arg(args, "context", default=0, minimum=0, maximum=5)
        timeout = _bounded_int_arg(args, "timeout_seconds", default=120, minimum=1, maximum=600)
        rel, full = _repo_existing_path(args.get("path"), default=".")
    except Exception as exc:
        return _deterministic_input_error("repo_rg_search", exc)
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
    result = _run_argv(argv, timeout=timeout)
    matches: list[dict[str, Any]] = []
    for line in result["stdout"].splitlines():
        try:
            row = json.loads(line)
        except Exception:
            continue
        if row.get("type") != "match":
            continue
        data = row.get("data") if isinstance(row.get("data"), dict) else {}
        raw_path_info = data.get("path")
        path_info = raw_path_info if isinstance(raw_path_info, dict) else {}
        raw_lines_info = data.get("lines")
        lines_info = raw_lines_info if isinstance(raw_lines_info, dict) else {}
        matches.append({
            "path": repo_rel(Path(str(path_info.get("text") or "")), LAB_REPO),
            "line_number": data.get("line_number"),
            "absolute_offset": data.get("absolute_offset"),
            "text": lines_info.get("text"),
            "submatches": data.get("submatches") if isinstance(data.get("submatches"), list) else [],
        })
        if len(matches) >= limit:
            break
    ok_value = _tool_ok_returncode(result["returncode"], no_match_ok=True)
    payload = {
        "ok": ok_value,
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
    if not ok_value:
        payload["error"] = "ripgrep_failed"
        payload["diagnostic"] = result.get("stderr_tail") or result.get("error") or ""
        if result.get("timed_out"):
            payload["error"] = "timeout"
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
    try:
        timeout = _bounded_int_arg(args, "timeout_seconds", default=60, minimum=1, maximum=600)
    except Exception as exc:
        return _deterministic_input_error("repo_jq_query", exc)
    argv = [exe, query]
    repo_path = None
    stdin = None
    if isinstance(json_text, str) and json_text.strip():
        stdin = json_text
    else:
        try:
            repo_path, full = _repo_existing_path(args.get("path"))
        except Exception as exc:
            return _deterministic_input_error("repo_jq_query", exc)
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
        timeout = _bounded_int_arg(args, "timeout_seconds", default=120, minimum=1, maximum=600)
        rel, full = _repo_existing_path(args.get("path"), default=".")
    except Exception as exc:
        return _deterministic_input_error("repo_ast_grep_search", exc)
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
    result = _run_argv(argv, timeout=timeout)
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
        tree_sitter = importlib.import_module("tree_sitter")
        tree_sitter_python = importlib.import_module("tree_sitter_python")
        Language = tree_sitter.Language
        Parser = tree_sitter.Parser
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
        return _deterministic_input_error("repo_tree_sitter_parse", exc)
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
    diff_text = diff_text.replace("\r\n", "\n").replace("\r", "\n")
    argv = [exe, "apply", "--check", "--whitespace=error", "-"]
    try:
        timeout = _bounded_int_arg(args, "timeout_seconds", default=120, minimum=1, maximum=600)
    except Exception as exc:
        return _deterministic_input_error("repo_git_apply_check", exc)
    result = _run_argv(
        argv,
        cwd=root,
        timeout=timeout,
        stdin_bytes=diff_text.encode("utf-8"),
    )
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
        timeout = _bounded_int_arg(args, "timeout_seconds", default=180, minimum=1, maximum=1200)
        targets = _repo_existing_paths(args.get("paths") or args.get("path"), default=".")
    except Exception as exc:
        return _deterministic_input_error("repo_ruff_check", exc)
    argv = [exe, "check", "--output-format=json"]
    argv.extend(str(full) for _rel, full in targets)
    result = _run_argv(argv, timeout=timeout)
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
        timeout = _bounded_int_arg(args, "timeout_seconds", default=240, minimum=1, maximum=1200)
        targets = _repo_existing_paths(args.get("paths") or args.get("path"), default=".")
    except Exception as exc:
        return _deterministic_input_error("repo_pyright_check", exc)
    argv = [exe, "--outputjson"]
    argv.extend(str(full) for _rel, full in targets)
    result = _run_argv(argv, timeout=timeout)
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
        maxfail = _bounded_int_arg(args, "maxfail", default=1, minimum=1, maximum=20)
        timeout = _bounded_int_arg(args, "timeout_seconds", default=300, minimum=1, maximum=1800)
        targets = _repo_existing_paths(args.get("paths") or args.get("path"), default=".")
    except Exception as exc:
        return _deterministic_input_error("repo_pytest_run", exc)
    argv = [exe, "-q", "--maxfail", str(maxfail), "--disable-warnings"]
    marker = str(args.get("marker") or "").strip()
    if marker:
        argv.extend(["-m", marker])
    argv.extend(str(full) for _rel, full in targets)
    result = _run_argv(argv, timeout=timeout)
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
        timeout = _bounded_int_arg(args, "timeout_seconds", default=120, minimum=1, maximum=600)
        targets = _repo_existing_paths(args.get("paths") or args.get("path"), default=".")
    except Exception as exc:
        return _deterministic_input_error("repo_shellcheck", exc)
    files = [(rel, full) for rel, full in targets if full.is_file()]
    if not files:
        return {"ok": False, "tool": "repo_shellcheck", "error": "no_files_selected"}
    argv = [exe, "--format=json"]
    argv.extend(str(full) for _rel, full in files)
    result = _run_argv(argv, timeout=timeout)
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
        limit = _bounded_int_arg(args, "limit", default=500, minimum=1, maximum=5000)
        timeout = _bounded_int_arg(args, "timeout_seconds", default=120, minimum=1, maximum=600)
        targets = _repo_existing_paths(args.get("paths") or args.get("path"), default=".")
    except Exception as exc:
        return _deterministic_input_error("repo_ctags_symbols", exc)
    argv = [exe, "--output-format=json", "-f", "-"]
    if any(full.is_dir() for _rel, full in targets):
        argv.append("-R")
    argv.extend(str(full) for _rel, full in targets)
    result = _run_argv(argv, timeout=timeout)
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
        timeout = _bounded_int_arg(args, "timeout_seconds", default=240, minimum=1, maximum=1200)
        targets = _repo_existing_paths(args.get("paths") or args.get("path"), default=".")
    except Exception as exc:
        return _deterministic_input_error("repo_semgrep_scan", exc)
    argv = [exe, "--json", "--disable-version-check"]
    if pattern:
        argv.extend(["--lang", lang, "--pattern", pattern])
    else:
        argv.extend(["--config", config])
    argv.extend(str(full) for _rel, full in targets)
    result = _run_argv(argv, timeout=timeout)
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
    try:
        runs = _bounded_int_arg(args, "runs", default=3, minimum=1, maximum=20)
        warmup = _bounded_int_arg(args, "warmup", default=1, minimum=0, maximum=10)
        timeout = _bounded_int_arg(args, "timeout_seconds", default=600, minimum=1, maximum=3600)
    except Exception as exc:
        return _deterministic_input_error("repo_hyperfine_benchmark", exc)
    argv = [exe, "--runs", str(runs), "--warmup", str(warmup), "--export-json", "-"]
    argv.extend(commands)
    result = _run_argv(argv, timeout=timeout)
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
