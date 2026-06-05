from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


from aicarmine_broker.application.tool_surface.result_compaction import (  # noqa: E402
    compact_tool_result_for_planner,
    python_static_evidence,
)
from aicarmine_broker.infrastructure.result_compaction import compact  # noqa: E402


def test_result_compaction_normalizes_line_endings_and_marks_truncation() -> None:
    text = compact("a\r\nb\r\nc", 4)

    assert text.startswith("a\nb")
    assert "<truncated>" in text


def test_tool_result_compaction_preserves_complete_code_product_diff() -> None:
    result = {
        "tool": "repo_propose_code_edit",
        "ok": True,
        "kind": "code_edit_proposal",
        "target_file": "pkg/a.py",
        "edit_kind": "unified_diff",
        "unified_diff": "--- a/pkg/a.py\n+++ b/pkg/a.py\n@@\n-old\n+new\n",
        "source_writes_performed": False,
        "patch_application_performed": False,
        "manual_review_required": True,
    }

    payload = compact_tool_result_for_planner("repo_propose_code_edit", result, result_compact_chars=500)

    assert payload["kind"] == "code_edit_proposal"
    assert payload["target_file"] == "pkg/a.py"
    assert payload["unified_diff"].startswith("--- a/")
    assert payload["source_writes_performed"] is False
    assert payload["patch_application_performed"] is False


def test_tool_result_compaction_preserves_prompt_context_window_payload() -> None:
    result = {
        "tool": "planner_scratchpad_read",
        "ok": True,
        "mode": "prompt_context_window",
        "items": [{
            "document_id": "doc-1",
            "section": "evidence",
            "window_start": 20,
            "window_end": 50,
            "full_chars": 100,
            "window_chars": 30,
            "complete": False,
            "has_more_before": True,
            "has_more_after": True,
            "sha256": "full-hash",
            "text": "real bounded text",
        }],
    }

    payload = compact_tool_result_for_planner("planner_scratchpad_read", result, result_compact_chars=500)

    item = payload["items"][0]
    assert payload["items_total"] == 1
    assert item["document_id"] == "doc-1"
    assert item["window_end"] == 50
    assert item["text"] == "real bounded text"
    assert item["window_sha256"]


def test_tool_result_compaction_adds_python_static_evidence_for_repo_reads() -> None:
    result = {
        "tool": "repo_read",
        "ok": True,
        "items": [{
            "ok": True,
            "path": "pkg/a.py",
            "content": "import os\n\ndef f():\n    return os.name\n",
            "line_count": 4,
        }],
    }

    payload = compact_tool_result_for_planner("repo_read", result, result_compact_chars=500)

    assert payload["items"][0]["content_preview"].startswith("import os")
    assert payload["python_static_evidence_total"] == 1
    evidence = payload["python_static_evidence"][0]
    assert evidence["parse_ok"] is True
    assert "os" in evidence["imports"]
    assert "f" in evidence["functions"]


def test_python_static_evidence_reports_parse_errors() -> None:
    evidence = python_static_evidence("bad.py", "def broken(:\n")

    assert evidence["parse_ok"] is False
    assert evidence["parse_error_type"]
