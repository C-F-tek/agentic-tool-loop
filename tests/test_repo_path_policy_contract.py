from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


from aicarmine_broker.application.repo_path_policy import (  # noqa: E402
    dynamic_read_candidate_paths,
    low_signal_top_dir,
    meaningful_read_candidates_from_evidence,
    path_under_scope,
    repo_code_file,
    repo_doc_or_config,
    repo_existing_dir,
    repo_existing_file,
    repo_path_kind,
    repo_readable_evidence_file,
    scope_candidate_source_paths,
    scope_read_candidates_from_evidence,
    top_dir,
)


NAMED = {"agents.md": 0, "readme.md": 1}
SUFFIXES = (".md", ".py", ".json", ".txt")


def _safe_rel(path: str) -> str:
    raw = str(path or "").replace("\\", "/")
    if raw.startswith("/") or ".." in raw.split("/"):
        raise ValueError("unsafe")
    return raw


def test_repo_existing_and_kind_are_repo_root_bound(tmp_path: Path) -> None:
    (tmp_path / "ia_carmine").mkdir()
    (tmp_path / "ia_carmine" / "x.py").write_text("print('x')\n", encoding="utf-8")

    assert repo_existing_file("ia_carmine/x.py", repo_root=tmp_path, safe_rel_path=_safe_rel)
    assert repo_existing_dir("ia_carmine", repo_root=tmp_path, safe_rel_path=_safe_rel)
    assert not repo_existing_file("../outside.py", repo_root=tmp_path, safe_rel_path=_safe_rel)
    assert repo_path_kind("ia_carmine/x.py", repo_root=tmp_path) == "file"
    assert repo_path_kind("ia_carmine", repo_root=tmp_path) == "dir"


def test_doc_code_readable_and_scope_policy(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "README.md").write_text("# docs\n", encoding="utf-8")

    assert repo_doc_or_config("docs/README.md", repo_root=tmp_path)
    assert repo_code_file("services/app.ps1")
    assert repo_readable_evidence_file(
        "docs/README.md",
        repo_root=tmp_path,
        generic_readable_suffixes=SUFFIXES,
    )
    assert path_under_scope("ia_carmine/_shared/x.py", "ia_carmine")
    assert not path_under_scope("services/app.py", "ia_carmine")
    assert top_dir("ia_carmine/_shared/x.py") == "ia_carmine"
    assert low_signal_top_dir("docs")


def test_dynamic_read_candidates_rank_named_then_code(tmp_path: Path) -> None:
    for rel in ("README.md", "ia_carmine/_shared/runtime.py", "ia_carmine/data.json", "docs/skip.md"):
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x\n", encoding="utf-8")

    candidates = dynamic_read_candidate_paths(
        ["ia_carmine/data.json", "README.md", "ia_carmine/_shared/runtime.py", "docs/skip.md"],
        read_ok={"docs/skip.md"},
        target_scope="",
        repo_root=tmp_path,
        named_read_priority=NAMED,
        generic_readable_suffixes=SUFFIXES,
    )

    assert candidates[0] == "README.md"
    assert "docs/skip.md" not in candidates
    assert "ia_carmine/_shared/runtime.py" in candidates


def test_scope_candidate_helpers_keep_candidates_inside_scope(tmp_path: Path) -> None:
    for rel in ("ia_carmine/a.py", "ia_carmine/README.md", "services/app.py"):
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x\n", encoding="utf-8")
    rows = [{
        "path": "ia_carmine",
        "paths_preview": ["ia_carmine/a.py", "ia_carmine/README.md", "services/app.py"],
    }]

    assert scope_candidate_source_paths(rows, "ia_carmine") == ["ia_carmine/a.py", "ia_carmine/README.md"]
    scoped = scope_read_candidates_from_evidence(
        rows,
        "ia_carmine",
        repo_root=tmp_path,
        named_read_priority=NAMED,
        generic_readable_suffixes=SUFFIXES,
    )
    meaningful = meaningful_read_candidates_from_evidence(
        rows,
        repo_root=tmp_path,
        named_read_priority=NAMED,
        generic_readable_suffixes=SUFFIXES,
    )

    assert scoped[0] == "ia_carmine/README.md"
    assert "services/app.py" not in scoped
    assert meaningful[0] == "ia_carmine/README.md"
