#!/usr/bin/env python3
"""Read-only Git MCP server for Codex-side regression diagnostics."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from repo_mcp_common import (
    ToolSpec,
    boolean_prop,
    compact_text_tuple,
    health_payload,
    integer_prop,
    object_schema,
    safe_int,
    self_test,
    serve,
    string_prop,
    path_is_under,
)

SERVER_NAME = "aicarmine-git-readonly-mcp"
SERVER_VERSION = "0.1.0"
REV_RE = re.compile(r"^[A-Za-z0-9_./:@{}^~+-]+$")


# Alias for local callers that expect `_compact_text` name
_compact_text = compact_text_tuple


def _compact_text(text: str, max_chars: int) -> tuple[str, bool]:
    if len(text) <= max_chars:
        return text, False
    return text[: max(0, max_chars - 80)].rstrip() + f"\n...[truncated chars={len(text)}]", True


def _validate_rev(value: Any, *, default: str = "HEAD", name: str = "rev") -> tuple[str | None, dict[str, Any] | None]:
    text = str(value or default).strip()
    if not text:
        return None, {"ok": False, "error": f"missing_{name}"}
    if text.startswith("-") or not REV_RE.fullmatch(text):
        return None, {"ok": False, "error": "invalid_git_revision", name: text}
    return text, None




def _pathspec(value: Any, root: Path) -> tuple[str | None, dict[str, Any] | None]:
    text = str(value or "").strip()
    if not text:
        return None, None
    candidate = Path(text).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        resolved = candidate.resolve()
    except PermissionError as exc:
        return None, {
            "ok": False,
            "error": "path_permission_denied",
            "path": text,
            "error_type": type(exc).__name__,
            "message": str(exc),
        }
    except (OSError, RuntimeError) as exc:
        return None, {
            "ok": False,
            "error": "path_resolve_failed",
            "path": text,
            "error_type": type(exc).__name__,
            "message": str(exc),
        }
    if not path_is_under(resolved, root):
        return None, {"ok": False, "error": "path_not_under_repo", "path": text, "resolved": str(resolved), "repo_root": str(root)}
    try:
        return str(resolved.relative_to(root.resolve())), None
    except ValueError:
        return str(resolved), None


def _run_git(root: Path, args: list[str], *, timeout_seconds: int, max_chars: int) -> dict[str, Any]:
    command = ["git", "-C", str(root), *args]
    try:
        proc = subprocess.run(
            command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        stdout, stdout_truncated = _compact_text(exc.stdout or "", max_chars) if isinstance(exc.stdout, str) else ("", False)
        stderr, stderr_truncated = _compact_text(exc.stderr or "", max_chars) if isinstance(exc.stderr, str) else ("", False)
        return {
            "returncode": -1,
            "stdout": stdout,
            "stderr": stderr,
            "stdout_truncated": stdout_truncated,
            "stderr_truncated": stderr_truncated,
            "command": command,
            "timeout_seconds": timeout_seconds,
            "error": "git_command_timeout",
            "error_type": type(exc).__name__,
        }
    except FileNotFoundError as exc:
        return {
            "returncode": -1,
            "stdout": "",
            "stderr": str(exc)[:max_chars],
            "stdout_truncated": False,
            "stderr_truncated": len(str(exc)) > max_chars,
            "command": command,
            "timeout_seconds": timeout_seconds,
            "error": "git_executable_not_found",
            "error_type": type(exc).__name__,
        }
    except PermissionError as exc:
        return {
            "returncode": -1,
            "stdout": "",
            "stderr": str(exc)[:max_chars],
            "stdout_truncated": False,
            "stderr_truncated": len(str(exc)) > max_chars,
            "command": command,
            "timeout_seconds": timeout_seconds,
            "error": "git_permission_denied",
            "error_type": type(exc).__name__,
        }
    except OSError as exc:
        return {
            "returncode": -1,
            "stdout": "",
            "stderr": str(exc)[:max_chars],
            "stdout_truncated": False,
            "stderr_truncated": len(str(exc)) > max_chars,
            "command": command,
            "timeout_seconds": timeout_seconds,
            "error": "git_os_error",
            "error_type": type(exc).__name__,
        }
    stdout, stdout_truncated = _compact_text(proc.stdout, max_chars)
    stderr, stderr_truncated = _compact_text(proc.stderr, max_chars)
    return {
        "returncode": proc.returncode,
        "stdout": stdout,
        "stderr": stderr,
        "stdout_truncated": stdout_truncated,
        "stderr_truncated": stderr_truncated,
        "command": command,
        "timeout_seconds": timeout_seconds,
        **(
            {
                "error": f"git_command_failed_rc{proc.returncode}",
                "error_type": "CalledProcessError",
                "stderr_preview": (proc.stderr or "")[:500],
            }
            if proc.returncode != 0
            else {}
        ),
    }


def _current_branch(root: Path) -> str:
    result = _run_git(root, ["branch", "--show-current"], timeout_seconds=10, max_chars=2000)
    return str(result.get("stdout") or "").strip()


def _log(args: dict[str, Any], root: Path) -> dict[str, Any]:
    max_count = safe_int(args.get("max_count") or args.get("limit"), 20, 1, 200)
    timeout_seconds = safe_int(args.get("timeout_seconds"), 10, 1, 60)
    rev, problem = _validate_rev(args.get("rev"), default="HEAD", name="rev")
    if problem is not None:
        return problem
    pathspec, path_problem = _pathspec(args.get("path"), root)
    if path_problem is not None:
        return path_problem
    cmd = [
        "log",
        f"--max-count={max_count}",
        "--date=iso-strict",
        "--pretty=format:%H%x00%h%x00%an%x00%ae%x00%at%x00%s",
        rev or "HEAD",
    ]
    if pathspec:
        cmd.extend(["--", pathspec])
    result = _run_git(root, cmd, timeout_seconds=timeout_seconds, max_chars=200000)
    commits: list[dict[str, Any]] = []
    if result["returncode"] == 0:
        for line in str(result["stdout"]).splitlines():
            parts = line.split("\x00", 5)
            if len(parts) == 6:
                commits.append(
                    {
                        "hash": parts[0],
                        "short_hash": parts[1],
                        "author_name": parts[2],
                        "author_email": parts[3],
                        "author_time": parts[4],
                        "subject": parts[5],
                    }
                )
    return {
        "ok": result["returncode"] == 0,
        "tool": "aicarmine_git_readonly_log",
        "commits": commits,
        "count": len(commits),
        "git": result,
        "read_only": True,
    }


def _show(args: dict[str, Any], root: Path) -> dict[str, Any]:
    rev, problem = _validate_rev(args.get("rev"), default="HEAD", name="rev")
    if problem is not None:
        return problem
    include_patch = bool(args.get("include_patch", False))
    max_chars = safe_int(args.get("max_chars"), 60000, 1000, 500000)
    timeout_seconds = safe_int(args.get("timeout_seconds"), 10, 1, 60)
    cmd = ["show", "--no-ext-diff", "--stat", "--format=fuller", rev or "HEAD"]
    if not include_patch:
        cmd.append("--no-patch")
    result = _run_git(root, cmd, timeout_seconds=timeout_seconds, max_chars=max_chars)
    return {"ok": result["returncode"] == 0, "tool": "aicarmine_git_readonly_show", "git": result, "read_only": True}


def _diff(args: dict[str, Any], root: Path) -> dict[str, Any]:
    max_chars = safe_int(args.get("max_chars"), 80000, 1000, 500000)
    timeout_seconds = safe_int(args.get("timeout_seconds"), 10, 1, 60)
    pathspec, path_problem = _pathspec(args.get("path"), root)
    if path_problem is not None:
        return path_problem
    cmd = ["diff", "--no-ext-diff"]
    if bool(args.get("staged", False)):
        cmd.append("--staged")
    base = args.get("base")
    head = args.get("head")
    if base is not None or head is not None:
        base_rev, base_problem = _validate_rev(base, default="HEAD", name="base")
        if base_problem is not None:
            return base_problem
        head_rev, head_problem = _validate_rev(head, default="HEAD", name="head")
        if head_problem is not None:
            return head_problem
        cmd.append(f"{base_rev}..{head_rev}")
    if pathspec:
        cmd.extend(["--", pathspec])
    result = _run_git(root, cmd, timeout_seconds=timeout_seconds, max_chars=max_chars)
    return {"ok": result["returncode"] == 0, "tool": "aicarmine_git_readonly_diff", "git": result, "read_only": True}


def _blame(args: dict[str, Any], root: Path) -> dict[str, Any]:
    pathspec, path_problem = _pathspec(args.get("path"), root)
    if path_problem is not None:
        return path_problem
    if not pathspec:
        return {"ok": False, "error": "missing_path"}
    rev, problem = _validate_rev(args.get("rev"), default="HEAD", name="rev")
    if problem is not None:
        return problem
    start = safe_int(args.get("start_line"), 1, 1, 1_000_000)
    end = safe_int(args.get("end_line"), start, start, 1_000_000)
    max_chars = safe_int(args.get("max_chars"), 80000, 1000, 500000)
    timeout_seconds = safe_int(args.get("timeout_seconds"), 10, 1, 60)
    cmd = ["blame", "--line-porcelain", "-L", f"{start},{end}", rev or "HEAD", "--", pathspec]
    result = _run_git(root, cmd, timeout_seconds=timeout_seconds, max_chars=max_chars)
    return {"ok": result["returncode"] == 0, "tool": "aicarmine_git_readonly_blame", "git": result, "read_only": True}


def _branch_compare(args: dict[str, Any], root: Path) -> dict[str, Any]:
    branch = str(args.get("branch") or _current_branch(root)).strip()
    remote = str(args.get("remote") or "origin").strip()
    if not branch:
        return {"ok": False, "error": "missing_branch"}
    branch_rev, branch_problem = _validate_rev(branch, default=branch, name="branch")
    if branch_problem is not None:
        return branch_problem
    remote_ref, remote_problem = _validate_rev(f"{remote}/{branch}", default=f"{remote}/{branch}", name="remote_ref")
    if remote_problem is not None:
        return remote_problem
    timeout_seconds = safe_int(args.get("timeout_seconds"), 10, 1, 60)
    left_right = _run_git(
        root,
        ["rev-list", "--left-right", "--count", f"{branch_rev}...{remote_ref}"],
        timeout_seconds=timeout_seconds,
        max_chars=4000,
    )
    local_hash = _run_git(root, ["rev-parse", "--short", branch_rev or "HEAD"], timeout_seconds=timeout_seconds, max_chars=4000)
    remote_hash = _run_git(root, ["rev-parse", "--short", remote_ref or "HEAD"], timeout_seconds=timeout_seconds, max_chars=4000)
    ahead = behind = None
    if left_right["returncode"] == 0:
        parts = str(left_right["stdout"]).split()
        if len(parts) >= 2:
            ahead, behind = int(parts[0]), int(parts[1])
    return {
        "ok": left_right["returncode"] == 0,
        "tool": "aicarmine_git_readonly_branch_compare",
        "branch": branch,
        "remote": remote,
        "remote_ref": f"{remote}/{branch}",
        "ahead": ahead,
        "behind": behind,
        "local_hash": str(local_hash.get("stdout") or "").strip(),
        "remote_hash": str(remote_hash.get("stdout") or "").strip(),
        "git": {"left_right": left_right, "local_hash": local_hash, "remote_hash": remote_hash},
        "read_only": True,
    }


def _health(args: dict[str, Any], root: Path, tools: dict[str, ToolSpec]) -> dict[str, Any]:
    payload = health_payload(SERVER_NAME, list(tools))
    payload.update(
        {
            "read_only": True,
            "commands": ["git log", "git show", "git diff", "git blame", "git rev-list", "git rev-parse"],
            "no_git_writes": True,
            "no_shell": True,
        }
    )
    return payload


def _tools() -> dict[str, ToolSpec]:
    tools: dict[str, ToolSpec] = {}

    def health(args: dict[str, Any], root: Path) -> dict[str, Any]:
        return _health(args, root, tools)

    tools["aicarmine_git_readonly_health"] = ToolSpec(
        name="aicarmine_git_readonly_health",
        description="Report Git read-only MCP health and allowed diagnostic commands.",
        input_schema=object_schema(),
        handler=health,
    )
    tools["aicarmine_git_readonly_log"] = ToolSpec(
        name="aicarmine_git_readonly_log",
        description="Read recent commits with a fixed structured format.",
        input_schema=object_schema(
            {
                "rev": string_prop("HEAD"),
                "path": string_prop(),
                "max_count": integer_prop(20, 1, 200),
                "limit": integer_prop(20, 1, 200),
                "timeout_seconds": integer_prop(10, 1, 60),
            }
        ),
        handler=_log,
    )
    tools["aicarmine_git_readonly_show"] = ToolSpec(
        name="aicarmine_git_readonly_show",
        description="Read one commit with stat and optional patch.",
        input_schema=object_schema(
            {
                "rev": string_prop("HEAD"),
                "include_patch": boolean_prop(False),
                "max_chars": integer_prop(60000, 1000, 500000),
                "timeout_seconds": integer_prop(10, 1, 60),
            }
        ),
        handler=_show,
    )
    tools["aicarmine_git_readonly_diff"] = ToolSpec(
        name="aicarmine_git_readonly_diff",
        description="Read a bounded git diff for worktree, staged, or revision range.",
        input_schema=object_schema(
            {
                "base": string_prop(),
                "head": string_prop(),
                "path": string_prop(),
                "staged": boolean_prop(False),
                "max_chars": integer_prop(80000, 1000, 500000),
                "timeout_seconds": integer_prop(10, 1, 60),
            }
        ),
        handler=_diff,
    )
    tools["aicarmine_git_readonly_blame"] = ToolSpec(
        name="aicarmine_git_readonly_blame",
        description="Read line blame for a repo file and bounded line range.",
        input_schema=object_schema(
            {
                "path": string_prop(),
                "rev": string_prop("HEAD"),
                "start_line": integer_prop(1, 1, 1000000),
                "end_line": integer_prop(1, 1, 1000000),
                "max_chars": integer_prop(80000, 1000, 500000),
                "timeout_seconds": integer_prop(10, 1, 60),
            },
            required=["path"],
        ),
        handler=_blame,
    )
    tools["aicarmine_git_readonly_branch_compare"] = ToolSpec(
        name="aicarmine_git_readonly_branch_compare",
        description="Compare a local branch with a remote tracking ref without fetching.",
        input_schema=object_schema(
            {
                "branch": string_prop(),
                "remote": string_prop("origin"),
                "timeout_seconds": integer_prop(10, 1, 60),
            }
        ),
        handler=_branch_compare,
    )
    return tools


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    tools = _tools()
    if "--self-test" in argv:
        result = self_test(
            server_name=SERVER_NAME,
            server_version=SERVER_VERSION,
            tools=tools,
            health_tool="aicarmine_git_readonly_health",
            real_tool="aicarmine_git_readonly_log",
            real_args={"max_count": 1},
        )
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 0 if result.get("ok") else 1
    return serve(SERVER_NAME, SERVER_VERSION, tools)


if __name__ == "__main__":
    raise SystemExit(main())
