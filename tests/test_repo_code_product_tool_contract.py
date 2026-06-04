from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


def test_repo_propose_code_edit_generates_inline_diff_without_writes(tmp_path: Path, monkeypatch) -> None:
    module = import_module("aicarmine_broker.tools.repo_code_product")
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    target = repo_root / "target.py"
    original = "def value():\n    return 1\n"
    target.write_text(original, encoding="utf-8")
    monkeypatch.setattr(module, "LAB_REPO", repo_root)

    result = module.repo_propose_code_edit(
        {
            "target_file": "target.py",
            "edit_kind": "unified_diff",
            "rationale": "Return a clearer value for the test fixture.",
            "old_text": "    return 1\n",
            "new_text": "    return 2\n",
            "validation_commands": ["python -m compileall -q target.py"],
        },
        tmp_path / "job",
    )

    assert result["ok"] is True
    assert result["kind"] == "code_edit_proposal"
    assert result["tool"] == "repo_propose_code_edit"
    assert result["source_writes_performed"] is False
    assert result["patch_application_performed"] is False
    assert "--- a/target.py" in result["unified_diff"]
    assert "+++ b/target.py" in result["unified_diff"]
    assert "@@" in result["unified_diff"]
    assert target.read_text(encoding="utf-8") == original
    assert Path(result["artifact"]).exists()


def test_repo_propose_code_edit_missing_target_is_typed_error(tmp_path: Path, monkeypatch) -> None:
    module = import_module("aicarmine_broker.tools.repo_code_product")
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    monkeypatch.setattr(module, "LAB_REPO", repo_root)

    result = module.repo_propose_code_edit(
        {
            "target_file": "missing.py",
            "edit_kind": "unified_diff",
            "rationale": "test",
            "old_text": "a",
            "new_text": "b",
        },
        tmp_path / "job",
    )

    assert result["ok"] is False
    assert result["tool"] == "repo_propose_code_edit"
    assert result["source_writes_performed"] is False
    assert result["patch_application_performed"] is False


def test_repo_tools_facade_exports_code_product_tool() -> None:
    from aicarmine_broker.repo_tools import repo_propose_code_edit
    from aicarmine_broker.tools.repo_code_product import repo_propose_code_edit as split_tool

    assert repo_propose_code_edit is split_tool
