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
