from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


from aicarmine_broker import planner  # noqa: E402


def test_planner_evidence_contract_file_goal_requires_direct_read() -> None:
    contract = planner.planner_evidence_contract("Read target file README.md", [])

    assert contract["target_kind"] == "file"
    assert contract["resolved_goal_file"] == "README.md"
    assert contract["finalization_contract"]["final_allowed"] is False
    assert "Need direct repo_read evidence" in contract["finalization_contract"]["reason"]


def test_planner_evidence_contract_file_goal_accepts_verified_inline_read() -> None:
    history = [{
        "step": 1,
        "decision": {"action": "tool", "tool": "repo_read", "arguments": {"path": "README.md"}},
        "tool_result": {
            "tool": "repo_read",
            "ok": True,
            "items": [
                {
                    "ok": True,
                    "path": "README.md",
                    "content": "hello",
                    "line_count": 1,
                    "truncated": False,
                }
            ],
        },
    }]

    contract = planner.planner_evidence_contract("Read target file README.md", history)

    assert contract["successful_repo_read_count"] == 1
    assert contract["verified_content_read_count"] == 1
    assert contract["finalization_contract"]["final_allowed"] is True
    assert contract["finalization_contract"]["verified_content_reads"][0]["source"] == "tool_result_inline"


def test_planner_evidence_contract_makes_candidate_repo_reads_validator_admissible(tmp_path, monkeypatch) -> None:
    target = tmp_path / "ia_carmine" / "runtime" / "heap_gate" / "provider_context.py"
    target.parent.mkdir(parents=True)
    target.write_text("def provider_context():\n    return {}\n", encoding="utf-8")
    monkeypatch.setattr(planner, "LAB_REPO", tmp_path)

    intrinsic_context = {
        "retrieved_rag_chunks": {
            "status": "ready",
            "ranking_source": "test",
            "items": [
                {
                    "path": "ia_carmine/runtime/heap_gate/provider_context.py",
                    "score": 1.0,
                }
            ],
        }
    }

    contract = planner.planner_evidence_contract(
        "analizza la repository e proponi diff concreti per il refactoring del codice",
        [],
        intrinsic_context,
    )

    candidate_paths = [
        path
        for action in contract["candidate_next_actions"]
        if action.get("tool") == "repo_read"
        for path in (action.get("arguments") or {}).get("paths", [])
        if isinstance(path, str)
    ]
    assert "ia_carmine/runtime/heap_gate/provider_context.py" in candidate_paths
    assert (
        "ia_carmine/runtime/heap_gate/provider_context.py"
        in contract["validator_admissible_repo_read_paths"]
    )
    repo_read_candidates = [
        action
        for action in contract["candidate_next_actions"]
        if action.get("tool") == "repo_read"
    ]
    assert repo_read_candidates[0]["action_id"]
    assert repo_read_candidates[0]["action_proof"]["path_exists"] is True
    assert repo_read_candidates[0]["action_proof"]["path_readable"] is True
    assert repo_read_candidates[0]["action_proof"]["validator_admissible"] is True


def test_planner_evidence_contract_candidate_actions_have_proof(tmp_path, monkeypatch) -> None:
    target = tmp_path / "ia_carmine" / "runtime" / "heap_gate" / "provider_context.py"
    target.parent.mkdir(parents=True)
    target.write_text("def provider_context():\n    return {}\n", encoding="utf-8")
    monkeypatch.setattr(planner, "LAB_REPO", tmp_path)

    intrinsic_context = {
        "retrieved_rag_chunks": {
            "status": "ready",
            "ranking_source": "test",
            "items": [
                {
                    "path": "ia_carmine/runtime/heap_gate/provider_context.py",
                    "score": 1.0,
                }
            ],
        }
    }

    contract = planner.planner_evidence_contract(
        "analizza la repository e proponi diff concreti per il refactoring del codice",
        [],
        intrinsic_context,
    )

    candidates = contract["candidate_next_actions"]
    assert candidates
    for action in candidates:
        assert "action_id" in action
        assert "action_proof" in action
        assert action["action_proof"]["source"]

    repo_read_actions = [action for action in candidates if action.get("tool") == "repo_read"]
    assert repo_read_actions
    proof = repo_read_actions[0]["action_proof"]
    assert proof["path_exists"] is True
    assert proof["path_readable"] is True
    assert proof["validator_admissible"] is True


def test_planner_evidence_contract_excludes_missing_core_discovery_candidate(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(planner, "LAB_REPO", tmp_path)

    missing = "ia_carmine/runtime/heap_gate/provider_context.py"
    intrinsic_context = {
        "retrieved_rag_chunks": {
            "status": "ready",
            "ranking_source": "test",
            "items": [
                {
                    "path": missing,
                    "score": 1.0,
                }
            ],
        }
    }

    contract = planner.planner_evidence_contract(
        "analizza la repository e proponi diff concreti per il refactoring del codice",
        [],
        intrinsic_context,
    )

    candidate_paths = [
        path
        for action in contract["candidate_next_actions"]
        if action.get("tool") == "repo_read"
        for path in (action.get("arguments") or {}).get("paths", [])
        if isinstance(path, str)
    ]

    assert missing not in candidate_paths
    assert missing not in contract["validator_admissible_repo_read_paths"]
    assert missing not in str(contract.get("required_next_progress", ""))
    assert not any(
        (action.get("action_proof") or {}).get("path_exists") is False
        for action in contract["candidate_next_actions"]
        if isinstance(action, dict)
    )


def test_planner_evidence_contract_includes_required_next_progress_model() -> None:
    contract = planner.planner_evidence_contract("Read target file README.md", [])

    model = contract.get("required_next_progress_model")

    assert isinstance(model, dict)
    assert model["human_text"] == contract["required_next_progress"]
    assert "kind" in model
    assert "metadata" in model
    assert "candidate_next_actions_count" in model["metadata"]
    assert "final_allowed" in model["metadata"]
