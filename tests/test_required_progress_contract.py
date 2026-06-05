from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


from aicarmine_broker import planner  # noqa: E402
from aicarmine_broker.application.planner.required_progress import (  # noqa: E402
    RequiredNextProgress,
    progress_code_product_block_required,
    progress_code_product_route_shift,
    progress_forbidden_repeat_repo_read,
    progress_native_tool_required,
    progress_prompt_context_continuation,
    progress_quality_gate_final_allowed,
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
    assert "repo_propose_code_edit" in progress["required_tools"]


def test_progress_code_product_route_shift_has_expected_kind() -> None:
    progress = progress_code_product_route_shift(
        "Route shift required after invalid repo_propose_code_edit payload.",
        source="test",
    ).to_contract()

    assert progress["kind"] == "code_product_route_shift"
    assert "repo_propose_code_edit" in progress["required_tools"]
    assert "repo_propose_code_edit_complete_payload" in progress["must_choose_one_of"]
    assert progress["metadata"]["source"] == "test"


def test_progress_forbidden_repeat_has_repo_read_forbidden() -> None:
    progress = progress_forbidden_repeat_repo_read(
        "Do not repeat repo_read on README.md.",
        target="README.md",
    ).to_contract()

    assert progress["kind"] == "forbidden_repeat_repo_read"
    assert progress["forbidden_tools"] == ["repo_read"]
    assert progress["metadata"]["target"] == "README.md"


def test_progress_quality_gate_requires_final() -> None:
    progress = progress_quality_gate_final_allowed("Quality gate is satisfied.").to_contract()

    assert progress["kind"] == "quality_gate_final_allowed"
    assert progress["must_choose_one_of"] == ["final"]


def test_progress_factories_preserve_human_text() -> None:
    text = "code_product_build_state blocked_incomplete"

    assert progress_code_product_block_required(text).to_contract()["human_text"] == text
    assert progress_native_tool_required(text).to_contract()["human_text"] == text
    assert progress_prompt_context_continuation(text).to_contract()["human_text"] == text


def test_evidence_contract_includes_required_progress_model_for_code_product_route_shift() -> None:
    contract = planner.planner_evidence_contract(
        "analizza la repository e proponi diff concreti per il refactoring del codice",
        [],
    )

    progress = contract["required_next_progress_model"]

    assert progress["kind"] == "code_product_route_shift"
    assert progress["human_text"] == contract["required_next_progress"]
    assert "repo_propose_code_edit" in progress["required_tools"]
