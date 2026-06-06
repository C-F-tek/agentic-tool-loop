from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


from vulkan_bridge.application.public_payload_linter import lint_public_payload  # noqa: E402


def test_public_payload_linter_warns_local_path_outside_operator_diagnostics() -> None:
    result = lint_public_payload({
        "ok": True,
        "tool_context_for_30b": "{}",
        "final_path": r"C:\Users\carmi\AI\agent-jobs\job-x\final.json",
    })

    assert result["schema"] == "public_payload_lint.v1"
    assert result["ok"] is False
    assert result["mode"] == "warn"
    assert result["enforcement"] == "warn_only"
    assert result["would_block"] is False
    assert result["violations"][0]["rule"] == "local_pointer_key_outside_operator_diagnostics"
    assert "C:\\Users" not in str(result)


def test_public_payload_linter_allows_operator_diagnostics_path() -> None:
    result = lint_public_payload({
        "ok": True,
        "tool_context_for_30b": "{}",
        "operator_diagnostics": {
            "local_final_path": r"C:\Users\carmi\AI\agent-jobs\job-x\final.json",
        },
    })

    assert result["ok"] is True


def test_public_payload_linter_warns_operator_error_path_outside_diagnostics() -> None:
    result = lint_public_payload(
        {
            "tool_context_for_30b": "{}",
            "operator_error_path": r"C:\Users\carmi\AI\agent-jobs\job-x\error.txt",
        }
    )

    assert result["ok"] is False
    assert result["violations"][0]["rule"] == "local_pointer_key_outside_operator_diagnostics"


def test_public_payload_linter_rejects_artifact_path() -> None:
    result = lint_public_payload({
        "ok": True,
        "tool_context_for_30b": {"artifacts": [{"artifact_path": "tool-results/x.json"}]},
    })

    assert result["ok"] is False
    assert result["violations"][0]["rule"] == "local_pointer_key_outside_operator_diagnostics"


def test_public_payload_linter_accepts_inline_unified_diff() -> None:
    result = lint_public_payload({
        "ok": True,
        "payload_index_for_30b": {
            "concrete_results": [
                {"field": "priority_evidence_for_30b.items[0].unified_diff"}
            ]
        },
        "priority_evidence_for_30b": {
            "items": [{"kind": "code_edit_proposal", "unified_diff": "--- a/x\n+++ b/x\n"}]
        },
        "tool_context_for_30b": {
            "artifacts": [{"artifact": {"unified_diff": "--- a/x\n+++ b/x\n"}}]
        },
    })

    assert result["ok"] is True
    assert result["violations"] == []


def test_public_payload_linter_warns_missing_priority_evidence() -> None:
    result = lint_public_payload({
        "ok": True,
        "payload_index_for_30b": {
            "concrete_results": [
                {"field": "priority_evidence_for_30b.items[0].content"}
            ]
        },
        "tool_context_for_30b": "{}",
    })

    assert result["ok"] is False
    assert result["violations"][0]["rule"] == "payload_index_references_missing_priority_evidence"


def test_public_payload_linter_rejects_tool_context_string_that_is_not_json_object() -> None:
    result = lint_public_payload({
        "ok": True,
        "tool_context_for_30b": "not json",
    })

    assert result["ok"] is False
    assert result["violations"][0]["rule"] == "tool_context_for_30b_string_not_json_object"


def test_public_payload_linter_rejects_payload_index_dangling_reference() -> None:
    result = lint_public_payload({
        "ok": True,
        "payload_index_for_30b": {
            "concrete_results": [
                {"primary_location": "priority_evidence_for_30b.items[0].content"}
            ]
        },
        "priority_evidence_for_30b": {"items": []},
        "tool_context_for_30b": "{}",
    })

    assert result["ok"] is False
    assert result["violations"][0]["rule"] == "payload_index_target_missing"


def test_public_payload_linter_rejects_payload_index_local_pointer_target() -> None:
    result = lint_public_payload({
        "ok": True,
        "payload_index_for_30b": {
            "concrete_results": [
                {"primary_location": "tool-results/proposal.json"}
            ]
        },
        "priority_evidence_for_30b": {"items": [{"content": "inline"}]},
        "tool_context_for_30b": "{}",
    })

    rules = [row["rule"] for row in result["violations"]]
    assert "payload_index_target_points_to_local_pointer" in rules


def test_public_payload_linter_rejects_payload_index_content_copy() -> None:
    result = lint_public_payload({
        "ok": True,
        "payload_index_for_30b": {
            "concrete_results": [
                {
                    "primary_location": "priority_evidence_for_30b.items[0].content",
                    "content": "# duplicated copy\n",
                }
            ]
        },
        "priority_evidence_for_30b": {"items": [{"content": "# duplicated copy\n"}]},
        "tool_context_for_30b": "{}",
    })

    assert result["ok"] is False
    assert result["violations"][0]["rule"] == "payload_index_contains_concrete_payload_copy"


def test_public_payload_linter_rejects_tool_context_root_narrative_alias() -> None:
    result = lint_public_payload({
        "ok": True,
        "tool_context_for_30b": {"answer_for_30b": "duplicate"},
    })

    assert result["ok"] is False
    assert result["violations"][0]["rule"] == "tool_context_root_narrative_alias"


def test_public_payload_linter_rejects_omission_marker_as_payload() -> None:
    result = lint_public_payload({
        "ok": True,
        "tool_context_for_30b": {"artifacts": [{"artifact": {"content": "[local_path_omitted]"}}]},
    })

    assert result["ok"] is False
    assert result["violations"][0]["rule"] == "public_payload_omission_marker"


def test_public_payload_linter_rejects_object_repr_as_payload() -> None:
    result = lint_public_payload({
        "ok": True,
        "tool_context_for_30b": {"artifacts": [{"artifact": {"content": "<object object at 0x1234ABCD>"}}]},
    })

    assert result["ok"] is False
    assert result["violations"][0]["rule"] == "public_payload_object_repr"


def test_public_payload_linter_rejects_completed_payload_without_materialization_report() -> None:
    result = lint_public_payload({
        "ok": True,
        "status": "completed",
        "tool_context_for_30b": {"artifacts": [{"artifact": {"content": "inline"}}]},
        "priority_evidence_for_30b": {"items": [{"content": "inline"}]},
    })

    assert result["ok"] is False
    assert result["violations"][0]["rule"] == "terminal_payload_missing_materialization_report"


def test_public_payload_linter_rejects_completed_summary_as_payload_substitute() -> None:
    result = lint_public_payload({
        "ok": True,
        "status": "completed",
        "evidence_guide_for_30b": "summary only",
        "final_summary": "summary only",
        "payload_index_for_30b": {},
        "priority_evidence_for_30b": {"items": []},
        "tool_context_for_30b": {},
        "materialization_report": {
            "schema": "public_evidence_materialization.v1",
            "ok": False,
        },
    })

    rules = [row["rule"] for row in result["violations"]]
    assert "summary_used_as_payload_substitute" in rules
