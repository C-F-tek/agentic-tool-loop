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
