from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


from aicarmine_broker.application.public_payload.tool_context import (  # noqa: E402
    failed_tool_turns,
    final_summary_with_ollama_done_reasons,
    planner_turn_memory,
    public_tool_artifact_rows,
    public_tool_context_limits,
    public_tool_response,
    strip_public_local_references,
    successful_tool_turns,
)


def _same_tool_payload(result: dict[str, Any]) -> dict[str, Any]:
    return result


def _repo_read_full_content(item: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    return str(item.get("full_content") or item.get("content") or ""), {"source": "test"}


def test_public_tool_response_repo_read_carries_inline_content() -> None:
    response = public_tool_response(
        {
            "tool": "repo_read",
            "ok": True,
            "items": [{
                "ok": True,
                "path": "pkg/a.py",
                "line_count": 1,
                "truncated": True,
                "content_preview": "preview",
                "full_content": "complete file",
            }],
        },
        same_tool_artifact_payload=_same_tool_payload,
        repo_read_item_full_content=_repo_read_full_content,
        code_product_build_state_kind="code_product_build_state",
    )

    assert response["tool"] == "repo_read"
    assert response["items"][0]["repo_path"] == "pkg/a.py"
    assert response["items"][0]["content"] == "complete file"
    assert response["items"][0]["truncated"] is False


def test_public_tool_response_code_product_preserves_complete_diff() -> None:
    response = public_tool_response(
        {
            "tool": "repo_propose_code_edit",
            "ok": True,
            "kind": "code_edit_proposal",
            "target_file": "pkg/a.py",
            "edit_kind": "unified_diff",
            "unified_diff": "--- a/pkg/a.py\n+++ b/pkg/a.py\n@@\n-old\n+new\n",
            "manual_review_required": True,
        },
        same_tool_artifact_payload=_same_tool_payload,
        repo_read_item_full_content=_repo_read_full_content,
        code_product_build_state_kind="code_product_build_state",
    )

    assert response["target_file"] == "pkg/a.py"
    assert response["unified_diff"].startswith("---")
    assert response["manual_review_required"] is True


def test_public_tool_response_skips_internal_code_product_build_state() -> None:
    response = public_tool_response(
        {
            "tool": "planner_scratchpad_read",
            "ok": True,
            "mode": "code_product_build_state",
            "items": [{"text": "internal"}],
        },
        same_tool_artifact_payload=_same_tool_payload,
        repo_read_item_full_content=_repo_read_full_content,
        code_product_build_state_kind="code_product_build_state",
    )

    assert response == {}


def test_public_tool_artifact_rows_do_not_expose_local_artifact_path() -> None:
    history = [{
        "step": 1,
        "decision": {"tool": "repo_read", "arguments": {"path": "pkg/a.py"}},
        "tool_result": {
            "tool": "repo_read",
            "ok": True,
            "artifact": "reads/a.json",
            "items": [{"ok": True, "path": "pkg/a.py", "content": "file text"}],
        },
    }]

    rows = public_tool_artifact_rows(
        history,
        same_tool_artifact_payload=_same_tool_payload,
        repo_read_item_full_content=_repo_read_full_content,
        code_product_build_state_kind="code_product_build_state",
    )

    artifact = rows[0]["artifact"]
    assert artifact["kind"] == "repo_read"
    assert artifact["content"] == "file text"
    assert "artifact" not in artifact


def test_public_tool_artifact_rows_include_failed_tool_payload_inline() -> None:
    history = [{
        "step": 1,
        "decision": {"tool": "repo_git_apply_check", "arguments": {"patch": "diff --git a/x b/x\n"}},
        "tool_result": {
            "tool": "repo_git_apply_check",
            "ok": False,
            "artifact": "tool-results/repo_git_apply_check.json",
            "error": "patch_does_not_apply",
            "returncode": 1,
            "stderr_tail": "error: patch failed",
        },
    }]

    rows = public_tool_artifact_rows(
        history,
        same_tool_artifact_payload=_same_tool_payload,
        repo_read_item_full_content=_repo_read_full_content,
        code_product_build_state_kind="code_product_build_state",
    )

    assert rows[0]["ok"] is False
    assert rows[0]["artifact"]["kind"] == "diff_validation"
    assert rows[0]["artifact"]["error"] == "patch_does_not_apply"
    assert "artifact" not in rows[0]["artifact"]


def test_failed_tool_turns_index_failed_payload_without_duplicate_inline_copy() -> None:
    history = [{
        "step": 1,
        "decision": {"tool": "repo_git_apply_check", "arguments": {"patch": "diff --git a/x b/x\n"}},
        "tool_result": {
            "tool": "repo_git_apply_check",
            "ok": False,
            "error": "patch_does_not_apply",
            "returncode": 1,
            "stderr_tail": "error: patch failed",
        },
    }]

    success = successful_tool_turns(
        history,
        same_tool_artifact_payload=_same_tool_payload,
        repo_read_item_full_content=_repo_read_full_content,
        code_product_build_state_kind="code_product_build_state",
    )
    failed = failed_tool_turns(
        history,
        same_tool_artifact_payload=_same_tool_payload,
        repo_read_item_full_content=_repo_read_full_content,
        code_product_build_state_kind="code_product_build_state",
    )
    memory = planner_turn_memory(
        history,
        same_tool_artifact_payload=_same_tool_payload,
        repo_read_item_full_content=_repo_read_full_content,
        code_product_build_state_kind="code_product_build_state",
    )

    assert success == []
    assert failed[0]["tool_ok"] is False
    assert "tool_response" not in failed[0]
    assert failed[0]["payload_location"] == "tool_context_for_30b.artifacts[*].artifact matching step/tool"
    assert memory["successful_tool_turns"] == []
    assert "tool_response" not in memory["failed_tool_turns"][0]
    assert memory["failed_tool_turns"][0]["payload_location"] == (
        "tool_context_for_30b.artifacts[*].artifact matching step/tool"
    )


def test_public_tool_context_limits_reports_partial_lists() -> None:
    limits = public_tool_context_limits([{
        "producer_step": 2,
        "tool": "repo_tree",
        "artifact": {"repo_path": ".", "entries_total": 10, "count": 3},
    }])

    assert limits == [{"step": 2, "tool": "repo_tree", "path": ".", "kind": "partial_list", "visible": 3, "total": 10}]


def test_successful_tool_turns_and_turn_memory_include_useful_payloads() -> None:
    history = [{
        "step": 1,
        "decision": {
            "action": "tool",
            "tool": "repo_read",
            "arguments": {"path": "pkg/a.py"},
            "planner_stream_meta": {"ollama_done_reason": "stop"},
        },
        "tool_result": {"tool": "repo_read", "ok": True, "items": [{"ok": True, "path": "pkg/a.py", "content": "x"}]},
    }]

    turns = successful_tool_turns(
        history,
        same_tool_artifact_payload=_same_tool_payload,
        repo_read_item_full_content=_repo_read_full_content,
        code_product_build_state_kind="code_product_build_state",
    )
    memory = planner_turn_memory(
        history,
        same_tool_artifact_payload=_same_tool_payload,
        repo_read_item_full_content=_repo_read_full_content,
        code_product_build_state_kind="code_product_build_state",
    )

    assert turns[0]["tool_response"]["items"][0]["content"] == "x"
    assert memory["successful_tool_turns"][0]["tool_response"]["tool"] == "repo_read"


def test_final_summary_with_ollama_done_reasons_appends_turns() -> None:
    summary = final_summary_with_ollama_done_reasons(
        "max_steps_reached",
        "Summary",
        {
            "history": [{
                "step": 1,
                "decision": {"action": "tool", "tool": "repo_read", "planner_stream_meta": {"ollama_done_reason": "stop"}},
                "tool_result": {"tool": "repo_read", "ok": True},
            }]
        },
    )

    assert "Turni Ollama conclusi:" in summary
    assert "Nota stato:" in summary


def test_strip_public_local_references_removes_internal_pointers() -> None:
    cleaned = strip_public_local_references({
        "artifact": "reads/a.json",
        "operator_error_path": r"C:\Users\carmi\AI\agent-jobs\job-x\error.txt",
        "store": "job_local_sqlite",
        "document_id": "doc",
        "content": {"final_path": "final.json", "text": "visible"},
    })

    assert cleaned == {"content": {"text": "visible"}}
