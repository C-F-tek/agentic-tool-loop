from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


def test_public_result_digest_keeps_existing_shape() -> None:
    from aicarmine_broker.application.public_payload.history_ledger import build_public_result_digest

    digest = build_public_result_digest(
        {
            "ok": False,
            "status": "blocked_needs_attention",
            "planner_decision": {"action": "tool", "tool": "repo_read", "ignored": "x"},
            "history": [
                {
                    "step": 1,
                    "decision": {"action": "tool", "tool": "repo_read"},
                    "tool_result": {"tool": "repo_read", "ok": True, "path": "AGENTS.md"},
                }
            ],
            "artifact": "tool-results/a.json",
        },
        inline_limit=1000,
    )

    assert digest["ok"] is False
    assert digest["status"] == "blocked_needs_attention"
    assert digest["planner_decision"] == {"action": "tool", "tool": "repo_read"}
    assert digest["history_count"] == 1
    assert digest["history_tail"][0]["tool"] == "repo_read"
    assert digest["artifacts"] == ["tool-results/a.json"]


def test_job_store_public_result_digest_delegates_same_shape() -> None:
    from aicarmine_broker.job_store import public_result_digest

    digest = public_result_digest({"status": "completed"})

    assert digest == {"status": "completed"}
