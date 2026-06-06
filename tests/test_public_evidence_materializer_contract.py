from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))

from aicarmine_broker.application.public_payload.evidence_materializer import (  # noqa: E402
    materialize_public_evidence,
)


def test_materializer_promotes_repo_read_content_without_copying_into_index() -> None:
    materialized = materialize_public_evidence(
        tool_context={
            "type": "agentic_loop_complete_structured_context",
            "not_a_summary": True,
            "artifacts": [
                {
                    "producer_step": 1,
                    "tool": "repo_read",
                    "ok": True,
                    "artifact": {
                        "kind": "repo_read",
                        "repo_path": "README.md",
                        "truncated": False,
                        "content": "# Demo\n",
                    },
                }
            ],
        },
        evidence_guide="Use the README content.",
        completed=True,
    )

    priority_item = materialized["priority_evidence_for_30b"]["items"][0]
    index_row = materialized["payload_index_for_30b"]["concrete_results"][0]

    assert priority_item["kind"] == "repo_file_full_content"
    assert priority_item["content"] == "# Demo\n"
    assert index_row["primary_location"] == "priority_evidence_for_30b.items[0].content"
    assert index_row["full_context_location"] == "tool_context_for_30b.artifacts[0].artifact.content"
    assert "content" not in index_row
    assert materialized["materialization_report"]["owner"] == "3572_broker"
    assert materialized["materialization_report"]["ok"] is True


def test_materializer_promotes_unified_diff_without_local_paths() -> None:
    diff = "--- a/services/demo.py\n+++ b/services/demo.py\n@@ -1 +1 @@\n-old\n+new\n"

    materialized = materialize_public_evidence(
        tool_context={
            "not_a_summary": True,
            "artifacts": [
                {
                    "producer_step": 2,
                    "tool": "repo_propose_code_edit",
                    "ok": True,
                    "artifact": {
                        "kind": "code_edit_proposal",
                        "target_file": "services/demo.py",
                        "edit_kind": "unified_diff",
                        "manual_review_required": True,
                        "unified_diff": diff,
                    },
                }
            ],
        },
        evidence_guide="Use the proposed diff.",
        completed=True,
    )

    priority_item = materialized["priority_evidence_for_30b"]["items"][0]
    index_row = materialized["payload_index_for_30b"]["concrete_results"][0]
    serialized = json.dumps(materialized, ensure_ascii=False, default=str)

    assert priority_item["kind"] == "code_edit_proposal"
    assert priority_item["unified_diff"] == diff
    assert priority_item["payload_is_complete"] is True
    assert index_row["payload_type"] == "unified_diff"
    assert index_row["primary_location"] == "priority_evidence_for_30b.items[0].unified_diff"
    assert "unified_diff" not in index_row
    assert "artifact_path" not in serialized
    assert "final_path" not in serialized


def test_materializer_indexes_generic_successful_tool_result_without_copying_payload() -> None:
    materialized = materialize_public_evidence(
        tool_context={
            "not_a_summary": True,
            "artifacts": [
                {
                    "producer_step": 1,
                    "tool": "repo_search",
                    "ok": True,
                    "artifact": {
                        "kind": "tool_result",
                        "matches": ["README.md:1:def demo"],
                        "returncode": 0,
                    },
                }
            ],
        },
        evidence_guide="Use the search matches.",
        completed=False,
    )

    priority_item = materialized["priority_evidence_for_30b"]["items"][0]
    index_row = materialized["payload_index_for_30b"]["concrete_results"][0]
    serialized_index = json.dumps(materialized["payload_index_for_30b"], ensure_ascii=False)

    assert priority_item["kind"] == "tool_result_inline"
    assert priority_item["tool"] == "repo_search"
    assert priority_item["payload_is_complete"] is True
    assert index_row["payload_type"] == "tool_result"
    assert index_row["primary_location"] == "tool_context_for_30b.artifacts[0].artifact"
    assert "README.md:1:def demo" not in serialized_index
    assert materialized["materialization_report"]["owner"] == "3572_broker"
    assert materialized["materialization_report"]["ok"] is True
    assert materialized["materialization_report"]["payload_index"]["resolved_count"] > 0


def test_materializer_indexes_failed_tool_result_as_partial_inline_artifact() -> None:
    materialized = materialize_public_evidence(
        tool_context={
            "not_a_summary": True,
            "artifacts": [
                {
                    "producer_step": 1,
                    "tool": "repo_git_apply_check",
                    "ok": False,
                    "artifact": {
                        "kind": "diff_validation",
                        "ok": False,
                        "error": "patch_does_not_apply",
                        "returncode": 1,
                        "stderr_tail": "error: patch failed",
                    },
                }
            ],
        },
        evidence_guide="Use the failed validation payload.",
        completed=False,
    )

    priority_item = materialized["priority_evidence_for_30b"]["items"][0]
    index_row = materialized["payload_index_for_30b"]["partial_results"][0]

    assert priority_item["kind"] == "tool_result_inline"
    assert priority_item["tool"] == "repo_git_apply_check"
    assert priority_item["payload_is_complete"] is False
    assert priority_item["validator_accepted"] is False
    assert index_row["primary_location"] == "tool_context_for_30b.artifacts[0].artifact"
    assert index_row["validator_accepted"] is False
    assert materialized["materialization_report"]["ok"] is True


def test_materializer_partial_code_product_uses_existing_rationale_location() -> None:
    materialized = materialize_public_evidence(
        tool_context={
            "not_a_summary": True,
            "partial_products_for_30b": [
                {
                    "kind": "partial_code_product_candidate",
                    "target_file": "pkg/a.py",
                    "edit_kind": "unified_diff",
                    "payload_is_complete": False,
                    "validator_accepted": False,
                    "rationale": "missing unified diff",
                }
            ],
        },
        evidence_guide="Use partial code-product diagnostics.",
        completed=False,
    )

    index_row = materialized["payload_index_for_30b"]["partial_results"][0]

    assert index_row["primary_location"] == "priority_evidence_for_30b.items[0].rationale"
    assert materialized["materialization_report"]["payload_index"]["unresolved"] == []


def test_materializer_reports_unresolved_payload_index_targets() -> None:
    materialized = materialize_public_evidence(
        tool_context={"not_a_summary": True, "artifacts": []},
        evidence_guide="No concrete payload.",
        completed=False,
    )
    report = materialized["materialization_report"]

    assert report["schema"] == "public_evidence_materialization.v1"
    assert report["owner"] == "3572_broker"
    assert report["inline_json_required"] is True
    assert report["objects_are_not_transport"] is True
    assert report["payload_index"]["unresolved"] == []
