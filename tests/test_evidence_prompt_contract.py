from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


from aicarmine_broker.application.evidence_prompt_contract import (  # noqa: E402
    EVIDENCE_PROMPT_KEEP_KEYS,
    compact_evidence_contract_for_prompt,
    hard_budget_evidence_contract_summary,
)


def test_compact_evidence_contract_keeps_contract_keys_and_drops_empty_values() -> None:
    contract = {
        "semantic_goal_classification": {"class": "analysis_only"},
        "goal_requests_code_product": False,
        "required_next_progress": "produce final",
        "not_prompt_visible": "drop me",
        "failed_repo_read_paths": [],
    }

    payload = compact_evidence_contract_for_prompt(contract, prompt_preview_chars=1000)

    assert set(payload).issubset(set(EVIDENCE_PROMPT_KEEP_KEYS) | {"file_memory"})
    assert payload["semantic_goal_classification"] == {"class": "analysis_only"}
    assert payload["goal_requests_code_product"] is False
    assert payload["required_next_progress"] == "produce final"
    assert "not_prompt_visible" not in payload
    assert "failed_repo_read_paths" not in payload


def test_compact_evidence_contract_bounds_file_memory() -> None:
    contract = {
        "file_memory": [
            {
                "path": f"file_{idx}.py",
                "line_count": idx,
                "truncated": False,
                "key_lines": [f"line {line}" for line in range(12)],
                "content_excerpt": "x" * 800,
            }
            for idx in range(8)
        ],
    }

    payload = compact_evidence_contract_for_prompt(contract, prompt_preview_chars=1200)

    assert len(payload["file_memory"]) == 6
    first = payload["file_memory"][0]
    assert first["path"] == "file_0.py"
    assert len(first["key_lines"]) == 9
    assert first["key_lines"][-1] == {"omitted_items_for_prompt": "4"}
    assert first["content_excerpt"].endswith("<prompt_preview_truncated>")


def test_compact_evidence_contract_operational_notes_are_bounded() -> None:
    contract = {
        "operational_notes": {
            "final_allowed": True,
            "next_instruction": "y" * 800,
            "candidate_next_actions": [{"tool": f"repo_read_{idx}"} for idx in range(10)],
        },
    }

    payload = compact_evidence_contract_for_prompt(contract, prompt_preview_chars=1600)

    notes = payload["operational_notes"]
    assert notes["final_allowed"] is True
    assert notes["next_instruction"].endswith("<prompt_preview_truncated>")
    assert len(notes["candidate_next_actions"]) == 7
    assert notes["candidate_next_actions"][-1] == {"omitted_items_for_prompt": 4}


def test_hard_budget_evidence_contract_summary_keeps_required_progress() -> None:
    contract = {
        "semantic_goal_classification": {"class": "code_product_report"},
        "goal_requests_code_product": True,
        "successful_repo_read_count": 3,
        "required_next_progress": "call repo_propose_code_edit",
        "finalization_contract": {
            "final_allowed": False,
            "planner_may_choose_final": False,
            "reason": "missing code product",
            "ignored": "drop",
        },
        "code_product_contract": {
            "required": True,
            "required_tool": "repo_propose_code_edit",
            "latest_violations": ["missing_code_product_candidate"],
            "ignored": "drop",
        },
        "candidate_next_actions": [
            {"tool": "repo_read", "arguments": {"path": f"file_{idx}.py"}}
            for idx in range(6)
        ],
        "required_next_tool_call": {"tool": "planner_scratchpad_read"},
        "forbidden_repeated_tool_calls": [{"document_id": "doc", "offset": 0}],
        "successful_repo_read_paths": [f"file_{idx}.py" for idx in range(8)],
    }

    payload = hard_budget_evidence_contract_summary(contract, reason="headroom")

    assert payload["schema"] == "planner_evidence_contract_hard_budget.v1"
    assert payload["hard_budget_reason"] == "headroom"
    assert payload["full_contract_available_from_sqlite_window"] is True
    assert "full_evidence_contract_window" not in payload
    assert payload["finalization_contract"] == {
        "final_allowed": False,
        "planner_may_choose_final": False,
        "reason": "missing code product",
    }
    assert payload["code_product_contract"]["required_tool"] == "repo_propose_code_edit"
    assert len(payload["candidate_next_actions"]) == 4
    assert payload["candidate_next_actions"][-1] == {"omitted_items_for_prompt": 3}
    assert payload["required_next_tool_call"] == {"tool": "planner_scratchpad_read"}
    assert len(payload["successful_repo_read_paths"]) == 6
    assert payload["successful_repo_read_paths"][-1] == {"omitted_items_for_prompt": 3}
