from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


from aicarmine_broker.application.code_product.state import (  # noqa: E402
    CODE_PRODUCT_BUILD_STATE_SCHEMA,
    code_product_action_has_complete_payload,
    code_product_build_state_has_collecting_progress,
    code_product_build_state_parse,
    code_product_build_state_ready_payload,
    code_product_build_state_section,
    code_product_payload_violations,
    copyable_example_text,
    goal_exact_text_block,
)


def test_code_product_build_state_parse_and_section() -> None:
    payload = {"schema": CODE_PRODUCT_BUILD_STATE_SCHEMA, "target_file": "./ia_carmine/x.py"}

    assert code_product_build_state_parse(json.dumps(payload)) == payload
    assert code_product_build_state_parse("{}") == {}
    assert code_product_build_state_section("./ia_carmine/x.py") == "code_product_build_state:ia_carmine/x.py"


def test_code_product_ready_payload_accepts_old_new_text() -> None:
    state = {
        "schema": CODE_PRODUCT_BUILD_STATE_SCHEMA,
        "status": "ready_for_propose",
        "target_file": "ia_carmine/x.py",
        "edit_kind": "unified_diff",
        "old_text": "old",
        "new_text": "new",
        "rationale": "report-only refactor",
        "validation_commands": ["git apply --check"],
    }

    args = code_product_build_state_ready_payload(state)

    assert args["target_file"] == "ia_carmine/x.py"
    assert args["old_text"] == "old"
    assert args["new_text"] == "new"
    assert args["validation_commands"] == ["git apply --check"]


def test_code_product_collecting_progress_requires_identity_and_window_marker() -> None:
    assert code_product_build_state_has_collecting_progress({
        "source_windows": [{"sha256": "abc", "window_end": 10}]
    })
    assert not code_product_build_state_has_collecting_progress({
        "source_windows": [{"sha256": "abc"}]
    })


def test_code_product_payload_violations_require_complete_inline_diff_and_read_target() -> None:
    proposal = {
        "tool": "repo_propose_code_edit",
        "ok": True,
        "kind": "code_edit_proposal",
        "target_file": "ia_carmine/x.py",
        "source_writes_performed": False,
        "patch_application_performed": False,
        "manual_review_required": True,
        "errors": [],
        "edit_kind": "unified_diff",
        "unified_diff": "--- a/ia_carmine/x.py\n+++ b/ia_carmine/x.py\n@@ -1 +1 @@\n-a\n+b\n",
    }

    assert code_product_payload_violations(proposal, {"ia_carmine/x.py"}) == []
    assert code_product_payload_violations({**proposal, "unified_diff_preview": "---"}, {"ia_carmine/x.py"}) == [
        "code_product_payload_not_complete"
    ]
    assert "code_product_target_not_read" in code_product_payload_violations(proposal, set())


def test_goal_exact_text_block_stops_at_next_boundary() -> None:
    goal = """Target file: ia_carmine/x.py
Exact old_text:
    old line
Exact new_text:
    new line
Required behavior: produce diff
"""

    assert goal_exact_text_block(goal, "old_text") == "    old line"
    assert goal_exact_text_block(goal, "new_text") == "    new line"


def test_copyable_example_text_and_action_payload_completeness() -> None:
    assert copyable_example_text("<insert old text>")
    assert copyable_example_text("EXAMPLE_ONLY_DO_NOT_COPY")
    assert not copyable_example_text("real code")

    assert code_product_action_has_complete_payload({
        "tool": "repo_propose_code_edit",
        "arguments": {
            "edit_kind": "unified_diff",
            "old_text": "real old",
            "new_text": "real new",
        },
    })
    assert not code_product_action_has_complete_payload({
        "tool": "repo_propose_code_edit",
        "arguments": {
            "edit_kind": "unified_diff",
            "old_text": "old",
            "new_text": "new",
        },
    })
