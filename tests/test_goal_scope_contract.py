from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


from aicarmine_broker.application.evidence.goal_scope import (  # noqa: E402
    extract_existing_goal_path,
    goal_requested_repo_scope,
    requested_file_limit_from_goal,
)


def _safe_rel(path: str) -> str:
    raw = str(path or "").replace("\\", "/")
    if raw.startswith("/") or ".." in raw.split("/"):
        raise ValueError("unsafe")
    return raw


def test_extract_existing_goal_path_requires_real_file(tmp_path: Path) -> None:
    target = tmp_path / "ia_carmine" / "_shared" / "x.py"
    target.parent.mkdir(parents=True)
    target.write_text("print('x')\n", encoding="utf-8")

    assert extract_existing_goal_path(
        "refactor ia_carmine/_shared/x.py",
        repo_root=tmp_path,
        safe_rel_path=_safe_rel,
    ) == "ia_carmine/_shared/x.py"
    assert extract_existing_goal_path(
        "refactor ia_carmine/_shared/missing.py",
        repo_root=tmp_path,
        safe_rel_path=_safe_rel,
    ) == ""


def test_goal_requested_repo_scope_resolves_existing_dir_and_alias(tmp_path: Path) -> None:
    (tmp_path / "ia_carmine").mkdir()

    assert goal_requested_repo_scope(
        "analizza in ia_carmine",
        repo_root=tmp_path,
        safe_rel_path=_safe_rel,
    ) == "ia_carmine"
    assert goal_requested_repo_scope(
        "analizza ai_carmine",
        repo_root=tmp_path,
        safe_rel_path=_safe_rel,
    ) == "ia_carmine"


def test_requested_file_limit_from_goal_bounds_and_defaults() -> None:
    assert requested_file_limit_from_goal("leggi i primi 50 file python") == 50
    assert requested_file_limit_from_goal("read top 5000 files") == 1000
    assert requested_file_limit_from_goal("analizza repo", default=7) == 7
