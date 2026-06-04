from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


from aicarmine_broker.application.code_product_history import (  # noqa: E402
    code_product_build_state_duplicate_write,
    code_product_build_state_from_result,
    code_product_build_state_propose_action,
    code_product_build_state_read_action,
    code_product_build_state_write_action,
    code_product_candidate_action,
    code_product_source_windows_from_reads,
    latest_code_product_build_state,
)
from aicarmine_broker.application.code_product_state import (  # noqa: E402
    CODE_PRODUCT_BUILD_STATE_KIND,
    CODE_PRODUCT_BUILD_STATE_SCHEMA,
)
from aicarmine_broker.application.prompt_values import text_hash  # noqa: E402


def _identity_artifact(result: dict) -> dict:
    return result


def _full_content(item: dict) -> tuple[str, dict]:
    return str(item.get("content") or ""), {}


def test_duplicate_write_uses_target_and_state_hash() -> None:
    text = json.dumps({
        "schema": CODE_PRODUCT_BUILD_STATE_SCHEMA,
        "target_file": "ia_carmine/x.py",
        "status": "collecting_source",
    })
    history = [{
        "tool_result": {
            "tool": "planner_scratchpad_write",
            "ok": True,
            "mode": CODE_PRODUCT_BUILD_STATE_KIND,
            "target_file": "./ia_carmine/x.py",
            "sha256": text_hash(text),
        }
    }]

    assert code_product_build_state_duplicate_write(history, target_file="ia_carmine/x.py", text=text)
    assert not code_product_build_state_duplicate_write(history, target_file="ia_carmine/y.py", text=text)


def test_read_result_extracts_ready_payload_and_latest_state() -> None:
    state = {
        "schema": CODE_PRODUCT_BUILD_STATE_SCHEMA,
        "status": "ready_for_propose",
        "target_file": "ia_carmine/x.py",
        "edit_kind": "unified_diff",
        "old_text": "old",
        "new_text": "new",
        "rationale": "report-only refactor",
    }
    result = {
        "tool": "planner_scratchpad_read",
        "ok": True,
        "mode": CODE_PRODUCT_BUILD_STATE_KIND,
        "items": [{
            "document_id": "doc-1",
            "section": "code_product_build_state:ia_carmine/x.py",
            "text": json.dumps(state),
            "sha256": "state-hash",
            "window_start": 0,
            "window_end": 100,
            "full_chars": 100,
            "complete": True,
            "has_more_after": False,
            "metadata": {"target_file": "ia_carmine/x.py", "status": "ready_for_propose"},
        }],
    }

    extracted = code_product_build_state_from_result(result)

    assert extracted["payload_loaded"] is True
    assert extracted["complete_payload_ready"] is True
    assert extracted["ready_arguments"]["old_text"] == "old"
    assert latest_code_product_build_state([{"tool_result": result}], "ia_carmine/x.py")["document_id"] == "doc-1"


def test_window_only_read_result_preserves_next_offset_for_continuation() -> None:
    result = {
        "tool": "planner_scratchpad_read",
        "ok": True,
        "mode": CODE_PRODUCT_BUILD_STATE_KIND,
        "items": [{
            "document_id": "doc-2",
            "section": "code_product_build_state:ia_carmine/x.py",
            "text": "{\"schema\":\"code_product_build_state.v1\"",
            "sha256": "window-hash",
            "window_start": 0,
            "window_end": 64,
            "full_chars": 200,
            "complete": False,
            "has_more_after": True,
            "metadata": {"target_file": "ia_carmine/x.py", "status": "collecting_source"},
        }],
    }

    extracted = code_product_build_state_from_result(result)
    action = code_product_build_state_read_action(extracted, "ia_carmine/x.py")

    assert extracted["window_only"] is True
    assert action["tool"] == "planner_scratchpad_read"
    assert action["arguments"]["document_id"] == "doc-2"
    assert action["arguments"]["offset"] == 64


def test_source_windows_and_write_action_use_real_repo_read_content() -> None:
    history = [{
        "tool_result": {
            "tool": "repo_read",
            "ok": True,
            "items": [{
                "path": "ia_carmine/x.py",
                "content": "def f():\n    return 1\n",
                "window_start": 0,
                "window_end": 22,
                "full_chars": 22,
                "complete": True,
            }],
        }
    }]

    windows = code_product_source_windows_from_reads(
        history,
        "ia_carmine/x.py",
        same_tool_artifact_payload=_identity_artifact,
        repo_read_item_full_content=_full_content,
    )
    action = code_product_build_state_write_action(
        "ia_carmine/x.py",
        history,
        same_tool_artifact_payload=_identity_artifact,
        repo_read_item_full_content=_full_content,
    )

    assert windows[0]["target_file"] == "ia_carmine/x.py"
    assert windows[0]["window_sha256"] == text_hash("def f():\n    return 1\n")
    assert action["tool"] == "planner_scratchpad_write"
    state = json.loads(action["arguments"]["text"])
    assert state["source_windows"][0]["sha256"] == windows[0]["sha256"]


def test_propose_and_exact_text_candidate_actions() -> None:
    ready_state = {
        "ready_arguments": {
            "target_file": "ia_carmine/x.py",
            "edit_kind": "unified_diff",
            "old_text": "old",
            "new_text": "new",
            "rationale": "report-only",
        }
    }
    goal = """Target file: ia_carmine/x.py
Exact old_text:
old
Exact new_text:
new
Required behavior: produce diff
"""

    assert code_product_build_state_propose_action(ready_state, ["missing"])["tool"] == "repo_propose_code_edit"
    candidate = code_product_candidate_action(
        target_file="ia_carmine/x.py",
        latest_violations=["missing_code_product_candidate"],
        goal=goal,
    )
    assert candidate["tool"] == "repo_propose_code_edit"
    assert candidate["arguments"]["old_text"] == "old"
    assert candidate["arguments"]["new_text"] == "new"
