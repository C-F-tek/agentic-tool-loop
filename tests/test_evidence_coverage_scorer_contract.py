from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


from aicarmine_broker import planner  # noqa: E402
from aicarmine_broker.application.evidence.coverage_scorer import score_evidence_coverage  # noqa: E402


def test_coverage_file_goal_missing_read_low_score() -> None:
    score = score_evidence_coverage({
        "target_kind": "file",
        "resolved_goal_file": "README.md",
        "verified_content_reads": [],
        "planner_may_choose_final": False,
    })

    assert score["coverage_score"] <= 0.3
    assert score["final_ready"] is False
    assert "README.md" in score["missing"]


def test_coverage_file_goal_verified_read_final_ready() -> None:
    score = score_evidence_coverage({
        "target_kind": "file",
        "resolved_goal_file": "README.md",
        "verified_content_reads": [{"path": "README.md", "content_chars": 10}],
        "planner_may_choose_final": True,
    })

    assert score["coverage_score"] >= 0.9
    assert score["final_ready"] is True


def test_coverage_repo_goal_docs_only_not_final_ready() -> None:
    score = score_evidence_coverage({
        "repo_concrete_read_required": 5,
        "repo_concrete_read_count": 0,
        "verified_content_read_count": 3,
        "verified_content_reads": [
            {"path": "README.md"},
            {"path": "pyproject.toml"},
            {"path": "services/README.md"},
        ],
        "planner_may_choose_final": False,
    })

    assert score["final_ready"] is False
    assert "no_meaningful_non_root_reads" in score["weaknesses"]


def test_coverage_code_product_requires_complete_payload() -> None:
    score = score_evidence_coverage({
        "verified_content_reads": [{"path": "services/x.py"}],
        "planner_may_choose_final": False,
        "code_product_contract": {
            "required": True,
            "candidate_target_file": "services/x.py",
            "build_state_status": "collecting_source",
            "latest_payload_complete": False,
        },
    })

    assert score["final_ready"] is False
    assert "code_product_payload_incomplete" in score["weaknesses"]


def test_evidence_contract_includes_evidence_coverage() -> None:
    contract = planner.planner_evidence_contract("Read target file README.md", [])

    assert contract["evidence_coverage"]["schema"] == "evidence_coverage_score.v1"
    assert contract["evidence_coverage"]["final_ready"] is False
