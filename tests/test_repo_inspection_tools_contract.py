from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


def _seed_repo(tmp_path: Path) -> Path:
    repo_root = tmp_path / "repo"
    (repo_root / "pkg").mkdir(parents=True)
    (repo_root / "pkg" / "alpha.py").write_text("needle = 1\n", encoding="utf-8")
    (repo_root / "pkg" / "notes.md").write_text("notes\n", encoding="utf-8")
    (repo_root / "__pycache__").mkdir()
    (repo_root / "__pycache__" / "skip.py").write_text("skip\n", encoding="utf-8")
    return repo_root


def test_repo_list_files_uses_real_repo_window(tmp_path: Path, monkeypatch) -> None:
    module = import_module("aicarmine_broker.tools.repo_list_files")
    repo_root = _seed_repo(tmp_path)
    monkeypatch.setattr(module, "LAB_REPO", repo_root)

    result = module.repo_list_files({"path": "pkg", "suffix": ".py", "limit": 5}, tmp_path / "job")

    assert result["ok"] is True
    assert result["tool"] == "repo_list_files"
    assert result["paths"] == ["pkg/alpha.py"]
    assert Path(result["artifact"]).exists()


def test_repo_tree_reports_files_and_dirs(tmp_path: Path, monkeypatch) -> None:
    module = import_module("aicarmine_broker.tools.repo_tree")
    repo_root = _seed_repo(tmp_path)
    monkeypatch.setattr(module, "LAB_REPO", repo_root)

    result = module.repo_tree({"path": ".", "max_depth": 2, "max_files": 10}, tmp_path / "job")

    assert result["ok"] is True
    paths = {entry["path"]: entry["kind"] for entry in result["entries"]}
    assert paths["pkg"] == "dir"
    assert paths["pkg/alpha.py"] == "file"
    assert "__pycache__/skip.py" not in paths


def test_repo_search_rejects_glob_and_uses_runner_payload(tmp_path: Path, monkeypatch) -> None:
    module = import_module("aicarmine_broker.tools.repo_search")

    glob_result = module.repo_search({"query": "*.py"}, tmp_path)
    assert glob_result["ok"] is False
    assert glob_result["suggested_tool"] == "repo_list_files"

    def fake_run_ps(command: str, timeout: int = 120) -> dict[str, object]:
        return {
            "returncode": 0,
            "stdout": "pkg/alpha.py:1:needle = 1\n",
            "stderr_tail": "",
        }

    monkeypatch.setattr(module, "_run_ps", fake_run_ps)
    result = module.repo_search({"query": "needle", "path": "pkg", "max_results": 1}, tmp_path / "job")

    assert result["ok"] is True
    assert result["matches"] == ["pkg/alpha.py:1:needle = 1"]
    assert "rg -n" in result["command"]
    assert Path(result["artifact"]).exists()


def test_repo_tools_facade_exports_inspection_tools() -> None:
    from aicarmine_broker.repo_tools import repo_list_files, repo_search, repo_tree
    from aicarmine_broker.tools.repo_list_files import repo_list_files as split_list_files
    from aicarmine_broker.tools.repo_search import repo_search as split_search
    from aicarmine_broker.tools.repo_tree import repo_tree as split_tree

    assert repo_list_files is split_list_files
    assert repo_search is split_search
    assert repo_tree is split_tree
