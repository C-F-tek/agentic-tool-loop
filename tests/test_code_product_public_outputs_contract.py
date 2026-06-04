from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


from aicarmine_broker.application.code_product_public_outputs import (  # noqa: E402
    best_partial_product_for_30b,
    code_product_answer_text,
    latest_code_product_payload,
    partial_product_answer_text,
    partial_products_for_30b,
)


BUILD_STATE_KIND = "code_product_build_state"


def test_code_product_answer_text_preserves_complete_unified_diff() -> None:
    diff = "--- a/a.py\n+++ b/a.py\n@@\n-old\n+new\n"
    result = {
        "history": [{
            "tool_result": {
                "tool": "repo_propose_code_edit",
                "ok": True,
                "kind": "code_edit_proposal",
                "target_file": "a.py",
                "edit_kind": "unified_diff",
                "rationale": "real change",
                "validation_commands": ["git apply --check patch.diff"],
                "source_writes_performed": False,
                "patch_application_performed": False,
                "manual_review_required": True,
                "unified_diff": diff,
            },
        }],
    }

    assert latest_code_product_payload(result["history"])["unified_diff"] == diff
    text = code_product_answer_text(result)

    assert "Code edit proposal generated." in text
    assert "- target_file: a.py" in text
    assert "```diff\n" + diff.rstrip("\n") + "\n```" in text


def test_partial_products_for_30b_preserves_rejected_diff_as_unvalidated_product() -> None:
    diff = "--- a/a.py\n+++ b/a.py\n@@\n-old\n+new\n"
    products = partial_products_for_30b(
        [{
            "step": 4,
            "tool_result": {
                "tool": "controller_guard",
                "summary": "invalid_code_product_candidate",
                "violations": ["invalid_code_product_candidate"],
                "rejected_decision": {
                    "tool": "repo_propose_code_edit",
                    "reason": "produce diff",
                    "arguments": {
                        "target_file": "\"a.py\"",
                        "edit_kind": "unified_diff",
                        "rationale": "fix duplication",
                        "unified_diff": diff,
                    },
                },
            },
        }],
        code_product_build_state_kind=BUILD_STATE_KIND,
    )

    stripped_diff = diff.strip()
    assert products == [{
        "kind": "partial_code_product_candidate",
        "source": "validator_rejected_repo_propose_code_edit",
        "step": 4,
        "payload_is_complete": False,
        "validator_accepted": False,
        "rejection_summary": "invalid_code_product_candidate",
        "violations": ["invalid_code_product_candidate"],
        "target_file": "a.py",
        "edit_kind": "unified_diff",
        "rationale": "fix duplication",
        "unified_diff": stripped_diff,
        "reason": "produce diff",
    }]


def test_best_partial_product_prefers_diff_and_answer_text_formats_it() -> None:
    diff = "--- a/a.py\n+++ b/a.py\n@@\n-old\n+new\n"
    history = [
        {"step": 1, "tool_result": {"tool": "controller_guard", "action_plan_candidate": "Plan only"}},
        {
            "step": 2,
            "tool_result": {
                "tool": "controller_guard",
                "rejected_decision": {
                    "tool": "repo_propose_code_edit",
                    "arguments": {"target_file": "a.py", "edit_kind": "unified_diff", "unified_diff": diff},
                },
            },
        },
    ]

    best = best_partial_product_for_30b(history, code_product_build_state_kind=BUILD_STATE_KIND)
    assert best["unified_diff"] == diff.strip()

    text = partial_product_answer_text(
        {"history": history},
        code_product_build_state_kind=BUILD_STATE_KIND,
    )
    assert "validator_accepted: false" in text
    assert "```diff\n" + diff.rstrip("\n") + "\n```" in text


def test_partial_products_for_30b_extracts_build_state_payload() -> None:
    state = '{"payload":{"target_file":"pkg/a.py","status":"collecting","edit_kind":"unified_diff","rationale":"split logic"}}'
    products = partial_products_for_30b(
        [{
            "step": 5,
            "tool_result": {
                "tool": "controller_guard",
                "summary": "duplicate state",
                "rejected_decision": {
                    "tool": "planner_scratchpad_write",
                    "arguments": {"kind": BUILD_STATE_KIND, "text": state},
                },
            },
        }],
        code_product_build_state_kind=BUILD_STATE_KIND,
    )

    assert products[0]["kind"] == "partial_code_product_build_state"
    assert products[0]["target_file"] == "pkg/a.py"
    assert products[0]["status"] == "collecting"
    assert products[0]["rationale"] == "split logic"
