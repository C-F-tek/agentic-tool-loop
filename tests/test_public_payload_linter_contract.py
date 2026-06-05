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
    assert result["violations"] == []


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

    assert result["ok"] is True
    assert result["warnings"][0]["rule"] == "payload_index_references_missing_priority_evidence"
