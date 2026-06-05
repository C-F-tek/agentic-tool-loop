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
