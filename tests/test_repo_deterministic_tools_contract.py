from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


def test_repo_tools_facade_exports_deterministic_tools() -> None:
    from aicarmine_broker.repo_tools import repo_git_apply_check, repo_jq_query, repo_ruff_check
    from aicarmine_broker.tools.repo_deterministic import repo_git_apply_check as split_git_apply
    from aicarmine_broker.tools.repo_deterministic import repo_jq_query as split_jq
    from aicarmine_broker.tools.repo_deterministic import repo_ruff_check as split_ruff

    assert repo_git_apply_check is split_git_apply
    assert repo_jq_query is split_jq
    assert repo_ruff_check is split_ruff


def test_repo_unidiff_validate_rejects_missing_markers(tmp_path: Path) -> None:
    from aicarmine_broker.tools.repo_deterministic import repo_unidiff_validate

    result = repo_unidiff_validate({"unified_diff": "not a diff"}, tmp_path)

    assert result["ok"] is False
    assert "missing_unified_diff_markers" in result["errors"]


def test_repo_git_apply_check_requires_diff(tmp_path: Path) -> None:
    from aicarmine_broker.tools.repo_deterministic import repo_git_apply_check

    result = repo_git_apply_check({}, tmp_path)

    assert result["ok"] is False
    assert result["error"] == "missing_unified_diff"
