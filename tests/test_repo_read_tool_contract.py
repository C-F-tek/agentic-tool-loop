from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


def test_repo_read_content_real(tmp_path: Path, monkeypatch) -> None:
    repo_read_module = import_module("aicarmine_broker.tools.repo_read")

    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "AGENTS.md").write_text(
        "AICARMINE_NON_NEGOTIABLE_CONTRACT_START\nreal content\n",
        encoding="utf-8",
    )
    output_root = tmp_path / "job"
    monkeypatch.setattr(repo_read_module, "LAB_REPO", repo_root)

    result = repo_read_module.repo_read({"path": "AGENTS.md", "max_chars": 2000}, output_root)

    assert result["ok"] is True
    assert result["tool"] == "repo_read"
    assert result["items"][0]["ok"] is True
    assert "AICARMINE_NON_NEGOTIABLE_CONTRACT_START" in result["items"][0]["content"]
    assert Path(result["items"][0]["artifact"]).exists()


def test_repo_read_missing_path_typed_error(tmp_path: Path) -> None:
    from aicarmine_broker.tools.repo_read import repo_read

    result = repo_read({}, tmp_path)

    assert result["ok"] is False
    assert result["error"] == "missing path/paths/items"


def test_repo_tools_facade_exports_repo_read() -> None:
    from aicarmine_broker.repo_tools import repo_read as facade_repo_read
    from aicarmine_broker.tools.repo_read import repo_read

    assert facade_repo_read is repo_read
