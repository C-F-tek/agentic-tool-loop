from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


from aicarmine_broker.application.shared.path_tokens import repo_rel_token  # noqa: E402


def test_repo_rel_token_preserves_dot_directories() -> None:
    assert repo_rel_token("./.github/workflows/test.yml") == ".github/workflows/test.yml"
    assert repo_rel_token(".github/workflows/test.yml") == ".github/workflows/test.yml"


def test_repo_rel_token_normalizes_quotes_and_backslashes() -> None:
    assert repo_rel_token('"services\\aicarmine_broker\\planner.py"') == "services/aicarmine_broker/planner.py"
    assert repo_rel_token("") == "."
