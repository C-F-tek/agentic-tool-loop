from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


from aicarmine_broker import planner  # noqa: E402
from aicarmine_broker.application.planner.required_progress import (  # noqa: E402
    RequiredNextProgress,
    required_next_progress_from_text,
)


def test_required_progress_model_serializes() -> None:
    progress = RequiredNextProgress(
        kind="code_product_route_shift",
        human_text="Call repo_propose_code_edit with a complete unified_diff.",
        must_not=("prose_only_final",),
        must_choose_one_of=("complete_unified_diff",),
        required_tools=("repo_propose_code_edit",),
        metadata={"candidate_next_actions_count": 1},
    )

    assert progress.to_contract() == {
        "kind": "code_product_route_shift",
        "human_text": "Call repo_propose_code_edit with a complete unified_diff.",
        "must_not": ["prose_only_final"],
        "must_choose_one_of": ["complete_unified_diff"],
        "required_tools": ["repo_propose_code_edit"],
        "forbidden_tools": [],
        "metadata": {"candidate_next_actions_count": 1},
    }


def test_required_progress_model_preserves_human_text() -> None:
    text = (
        "Route shift required after invalid repo_propose_code_edit payload. "
        "Do not repeat repo_read and produce complete structured_operations."
    )

    progress = required_next_progress_from_text(text).to_contract()

    assert progress["kind"] == "code_product_route_shift"
    assert progress["human_text"] == text
    assert "repo_read" in progress["forbidden_tools"]
    assert "complete_structured_operations" in progress["must_choose_one_of"]


def test_evidence_contract_includes_required_progress_model_for_code_product_route_shift() -> None:
    contract = planner.planner_evidence_contract(
        "analizza la repository e proponi diff concreti per il refactoring del codice",
        [],
    )

    progress = contract["required_next_progress_model"]

    assert progress["kind"] == "code_product_route_shift"
    assert progress["human_text"] == contract["required_next_progress"]
    assert "repo_propose_code_edit" in progress["required_tools"]
