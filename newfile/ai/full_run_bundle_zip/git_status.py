from __future__ import annotations

import subprocess
from pathlib import Path


def run_git_status(repo_root: Path) -> tuple[str, str | None]:
    """Return git status text without mutating the repository."""
    try:
        result = subprocess.run(
            ["git", "status", "--short"],
            cwd=repo_root,
            check=False,
            text=True,
            capture_output=True,
            timeout=30,
        )
    except Exception as exc:
        return "", f"{type(exc).__name__}: {exc}"
    if result.returncode != 0:
        return result.stdout, result.stderr.strip() or f"git status exited {result.returncode}"
    return result.stdout, None
