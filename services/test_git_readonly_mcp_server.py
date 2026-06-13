from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SERVICES_ROOT = Path(__file__).resolve().parent
CODEX_BRIDGE_ROOT = SERVICES_ROOT / "codex_bridge"
for import_root in (SERVICES_ROOT, CODEX_BRIDGE_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from codex_bridge import git_readonly_mcp_server  # noqa: E402


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True)


@pytest.mark.skipif(shutil.which("git") is None, reason="git executable not available")
def test_git_readonly_log_and_diff_are_read_only(tmp_path) -> None:
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.name", "Codex Test")
    _git(tmp_path, "config", "user.email", "codex@example.test")
    target = tmp_path / "sample.txt"
    target.write_text("one\n", encoding="utf-8")
    _git(tmp_path, "add", "sample.txt")
    _git(tmp_path, "commit", "-m", "initial")
    target.write_text("one\ntwo\n", encoding="utf-8")

    log = git_readonly_mcp_server._log({"max_count": 1}, tmp_path)
    diff = git_readonly_mcp_server._diff({"path": "sample.txt"}, tmp_path)

    assert log["ok"] is True
    assert log["commits"][0]["subject"] == "initial"
    assert diff["ok"] is True
    assert "+two" in diff["git"]["stdout"]
    assert target.read_text(encoding="utf-8") == "one\ntwo\n"


@pytest.mark.skipif(shutil.which("git") is None, reason="git executable not available")
def test_git_readonly_rejects_path_outside_repo(tmp_path) -> None:
    _git(tmp_path, "init")
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("outside\n", encoding="utf-8")

    result = git_readonly_mcp_server._diff({"path": str(outside)}, tmp_path)

    assert result["ok"] is False
    assert result["error"] == "path_not_under_repo"
