from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


def _seed_repo(tmp_path: Path) -> Path:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "target.txt").write_text("old\nold\n", encoding="utf-8")
    return repo_root


def test_repo_apply_patch_replaces_exact_text_and_writes_backup(tmp_path: Path, monkeypatch) -> None:
    module = import_module("aicarmine_broker.tools.repo_patch")
    repo_root = _seed_repo(tmp_path)
    monkeypatch.setattr(module, "LAB_REPO", repo_root)

    result = module.repo_apply_patch(
        {"path": "target.txt", "old_text": "old", "new_text": "new", "max_replacements": 1},
        tmp_path / "job",
    )

    assert result["ok"] is True
    assert result["changed"] is True
    assert result["occurrences_found"] == 2
    assert result["replacements"] == 1
    assert (repo_root / "target.txt").read_text(encoding="utf-8") == "new\nold\n"
    assert Path(result["backup_artifact"]).exists()


def test_repo_apply_patch_requires_existing_old_text(tmp_path: Path, monkeypatch) -> None:
    module = import_module("aicarmine_broker.tools.repo_patch")
    repo_root = _seed_repo(tmp_path)
    monkeypatch.setattr(module, "LAB_REPO", repo_root)

    result = module.repo_apply_patch(
        {"path": "target.txt", "old_text": "missing", "new_text": "new"},
        tmp_path / "job",
    )

    assert result["ok"] is False
    assert result["error"] == "old_text_not_found"
    assert (repo_root / "target.txt").read_text(encoding="utf-8") == "old\nold\n"


def test_repo_write_file_create_and_append(tmp_path: Path, monkeypatch) -> None:
    module = import_module("aicarmine_broker.tools.repo_patch")
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    monkeypatch.setattr(module, "LAB_REPO", repo_root)

    created = module.repo_write_file(
        {"path": "notes.txt", "content": "a\n", "mode": "create"},
        tmp_path / "job",
    )
    appended = module.repo_write_file(
        {"path": "notes.txt", "content": "b\n", "mode": "append"},
        tmp_path / "job",
    )

    assert created["ok"] is True
    assert appended["ok"] is True
    assert (repo_root / "notes.txt").read_text(encoding="utf-8") == "a\nb\n"
    assert Path(appended["backup_path"]).exists()


def test_repo_tools_facade_exports_patch_tools() -> None:
    from aicarmine_broker.repo_tools import repo_apply_patch, repo_write_file
    from aicarmine_broker.tools.repo_patch import repo_apply_patch as split_apply_patch
    from aicarmine_broker.tools.repo_patch import repo_write_file as split_write_file

    assert repo_apply_patch is split_apply_patch
    assert repo_write_file is split_write_file
