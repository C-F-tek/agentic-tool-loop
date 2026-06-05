from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


from aicarmine_broker import planner  # noqa: E402
from aicarmine_broker.application.runtime_debug import build_runtime_debug_packet  # noqa: E402


def _contract() -> dict:
    return {
        "planner_may_choose_final": False,
        "finalization_contract": {"final_allowed": False},
        "verified_content_reads": [{"path": "README.md"}],
        "missing_full_content_reads": [],
        "candidate_next_actions": [
            {
                "tool": "repo_read",
                "arguments": {"paths": ["README.md"]},
                "action_id": "abc",
                "action_proof": {"source": "test", "validator_admissible": True},
            }
        ],
        "required_next_progress_model": {
            "kind": "candidate_hint",
            "human_text": "read README.md",
            "metadata": {"candidate_next_actions_count": 1},
        },
        "evidence_coverage": {
            "schema": "evidence_coverage_score.v1",
            "coverage_score": 0.5,
            "diagnostic_only": True,
        },
        "forbidden_next_actions": [{"tool": "final"}],
    }


def test_runtime_debug_packet_has_schema_and_is_json_serializable() -> None:
    packet = build_runtime_debug_packet(
        job_id="job-test",
        step=4,
        phase="VALIDATE_DECISION",
        goal="read README.md",
        decision={"action": "tool", "tool": "repo_read", "native_tool_call": True},
        validator_result={"ok": False, "violations": ["repo_read_already_successful:README.md"]},
        evidence_contract=_contract(),
    )

    assert packet["schema"] == "runtime_debug_packet.v1"
    assert packet["diagnostic_only"] is True
    assert packet["job_id"] == "job-test"
    assert packet["step"] == 4
    assert packet["phase"] == "VALIDATE_DECISION"
    assert packet["validator_result"]["violations"] == ["repo_read_already_successful:README.md"]
    assert packet["evidence_contract_summary"]["candidate_next_actions_count"] == 1
    json.dumps(packet)


def test_runtime_debug_packet_redacts_large_strings_and_local_paths() -> None:
    packet = build_runtime_debug_packet(
        job_id="job-test",
        step=1,
        phase="FAILED",
        goal="inspect C:\\Users\\carmi\\AI\\repo",
        decision={
            "action": "final",
            "final_answer": "x" * 2000,
            "reason": "y" * 2000,
        },
        validator_result={"ok": False, "violations": ["x" * 2000]},
        evidence_contract={},
        extra={
            "final_path": "C:\\Users\\carmi\\AI\\agent-jobs\\job-test\\final.json",
            "raw_planner_text": "z" * 2000,
            "items": list(range(25)),
        },
    )

    dumped = json.dumps(packet, ensure_ascii=False)
    assert "C:\\Users" not in dumped
    assert "z" * 1001 not in dumped
    assert packet["extra"]["final_path"] == "<redacted:local_operator_path>"
    assert packet["extra"]["raw_planner_text"] == "<redacted:large_runtime_payload>"
    assert packet["extra"]["items"][-1] == {"_truncated_items": 5}


def test_runtime_debug_packet_contains_evidence_coverage_and_required_progress() -> None:
    packet = build_runtime_debug_packet(
        job_id="job-test",
        step=2,
        phase="CONTROLLER_GUARD",
        goal="read README.md",
        decision={"action": "final", "reason": "not enough evidence"},
        validator_result={"ok": False, "violations": ["final_not_allowed_by_evidence_contract"]},
        evidence_contract=_contract(),
    )

    assert packet["required_next_progress_model"]["kind"] == "candidate_hint"
    assert packet["evidence_coverage"]["schema"] == "evidence_coverage_score.v1"
    assert packet["candidate_next_actions_preview"][0]["action_proof"]["source"] == "test"
    assert packet["forbidden_next_actions"] == [{"tool": "final"}]


def test_controller_guard_result_includes_runtime_debug_packet() -> None:
    validation = {
        "ok": False,
        "violations": ["final_not_allowed_by_evidence_contract:missing README.md"],
        "evidence_contract": _contract(),
    }
    decision = {"action": "final", "final_answer": "done", "reason": "complete"}

    guard = planner.controller_guard_result_for_validation(
        validation,
        decision,
        job_id="job-test",
        step=3,
        goal="read README.md",
    )

    packet = guard["runtime_debug_packet"]
    assert guard["tool"] == "controller_guard"
    assert guard["ok"] is True
    assert packet["schema"] == "runtime_debug_packet.v1"
    assert packet["job_id"] == "job-test"
    assert packet["step"] == 3
    assert packet["validator_result"]["violations"] == validation["violations"]
