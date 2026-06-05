from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


from aicarmine_broker.application.planner.validation_rejections import (  # noqa: E402
    canonical_invalid_code_product_decision_signature,
    compact_validation_rejections_tail,
    disallowed_invalid_code_product_signatures,
    invalid_code_product_decision_signature_count,
    invalid_code_product_decision_signature_from_history_item,
    invalid_decision_signature_key,
)


def _invalid_diff_decision() -> dict:
    return {
        "action": "tool",
        "tool": "repo_propose_code_edit",
        "arguments": {
            "target_file": "./a.py",
            "edit_kind": "unified_diff",
            "old_text": "old",
            "new_text": "new",
            "unified_diff": "",
            "rationale": "r",
        },
    }


def test_canonical_invalid_code_product_decision_signature_for_missing_diff() -> None:
    signature = canonical_invalid_code_product_decision_signature(
        _invalid_diff_decision(),
        ["repo_propose_code_edit_missing_unified_diff"],
    )

    assert signature["tool"] == "repo_propose_code_edit"
    assert signature["target_file"] == "a.py"
    assert signature["edit_kind"] == "unified_diff"
    assert signature["payload_class"] == "missing_diff"
    assert signature["args_sha256"]
    assert invalid_decision_signature_key(signature).startswith("{")


def test_invalid_code_product_signature_from_history_and_count() -> None:
    row = {
        "tool_result": {
            "violations": ["repo_propose_code_edit_missing_unified_diff"],
            "rejected_decision": _invalid_diff_decision(),
        }
    }
    signature = invalid_code_product_decision_signature_from_history_item(row)

    assert signature["payload_class"] == "missing_diff"
    assert invalid_code_product_decision_signature_count([row, row], signature) == 2


def test_disallowed_invalid_code_product_signatures_requires_repeat() -> None:
    row = {
        "violations": ["repo_propose_code_edit_missing_unified_diff"],
        "rejected_decision": _invalid_diff_decision(),
    }

    assert disallowed_invalid_code_product_signatures([row]) == []
    repeated = disallowed_invalid_code_product_signatures([row, row])
    assert repeated[0]["payload_class"] == "missing_diff"
    assert repeated[0]["repeat_count"] == 2
    assert repeated[0]["rule"] == "do_not_repeat_invalid_code_product_decision"


def test_compact_validation_rejections_tail_dedupes_and_bounds_payload() -> None:
    row = {
        "step": 1,
        "guard_type": "invalid_code_product_candidate",
        "violations": ["repo_propose_code_edit_missing_unified_diff"],
        "rejected_decision": {
            **_invalid_diff_decision(),
            "arguments": {
                **_invalid_diff_decision()["arguments"],
                "old_text": "o" * 900,
            },
        },
        "action_plan_candidate": "plan" * 1200,
    }
    duplicate = {**row, "step": 2}

    payload = compact_validation_rejections_tail([row, duplicate], limit=5)

    assert len(payload) == 1
    assert payload[0]["repeat_count"] == 2
    assert payload[0]["last_step"] == 2
    old_text = payload[0]["rejected_decision"]["arguments"]["old_text"]
    assert old_text.endswith("...[truncated in rejection digest]")
    assert payload[0]["action_plan_candidate"].endswith("<prompt_preview_truncated>")
