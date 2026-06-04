from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


def test_parse_json_output_accepts_single_and_json_lines() -> None:
    from aicarmine_broker.tools.deterministic_common import parse_json_output

    assert parse_json_output('{"a": 1}') == {"a": 1}
    assert parse_json_output('{"a": 1}\n{"b": 2}\n') == [{"a": 1}, {"b": 2}]
    assert parse_json_output("not-json") is None


def test_bounded_text_marks_truncation() -> None:
    from aicarmine_broker.tools.deterministic_common import bounded_text

    result = bounded_text("abcdef", limit=3)

    assert result.startswith("abc")
    assert "<truncated>" in result


def test_repo_existing_paths_dedupes_and_stays_under_repo(tmp_path: Path, monkeypatch) -> None:
    import aicarmine_broker.tools.deterministic_common as module

    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "a.txt").write_text("a\n", encoding="utf-8")
    monkeypatch.setattr(module, "LAB_REPO", repo_root)

    result = module.repo_existing_paths(["a.txt", "a.txt"])

    assert result == [("a.txt", repo_root / "a.txt")]


def test_write_tool_artifact_roundtrip(tmp_path: Path) -> None:
    from aicarmine_broker.tools.deterministic_common import write_tool_artifact

    artifact = write_tool_artifact(tmp_path, "sample_tool", {"ok": True})

    assert artifact.exists()
    assert artifact.name.endswith("-sample_tool.json")
