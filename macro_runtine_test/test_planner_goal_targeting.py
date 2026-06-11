from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVICES = ROOT / "services"
if str(SERVICES) not in sys.path:
    sys.path.insert(0, str(SERVICES))

import aicarmine_broker.planner as planner  # noqa: E402


def _existing_goal_files() -> list[str]:
    preferred = [
        "AGENTS.md",
        "README.md",
        "CONTRIBUTING.md",
        "package.json",
        "pyproject.toml",
    ]
    return [path for path in preferred if (planner.LAB_REPO / path).is_file()]


def test_repo_analysis_with_multiple_file_mentions_keeps_repo_target() -> None:
    existing_files = _existing_goal_files()
    assert len(existing_files) >= 2
    first, second = existing_files[:2]
    goal = (
        "Esplora completamente il repository con focus sui punti core e relazione tecnica. "
        f"Includi anche {first} e {second} nella panoramica dei file principali."
    )

    assert planner._repo_analysis_goal(goal) is True
    assert planner._goal_target_file(goal) == ""
    assert planner._goal_target_kind(goal) == "repository"

    preseed = planner._controller_preseed_plan(goal, {})
    assert preseed is not None
    assert preseed["tool"] == "repo_tree"
    assert preseed["reason"] == "generic_repo_request_needs_root_surface"


def test_explicit_single_file_request_still_keeps_file_target() -> None:
    existing_files = _existing_goal_files()
    assert existing_files
    target_file = existing_files[0]
    goal = f"analizza {target_file} del progetto"

    assert planner._goal_target_file(goal) == target_file
    assert planner._goal_target_kind(goal) == "file"

    preseed = planner._controller_preseed_plan(goal, {})
    assert preseed is not None
    assert preseed["tool"] == "repo_read"
    assert preseed["arguments"]["path"] == target_file
    assert preseed["reason"] == "explicit_file_request_needs_file_surface"
