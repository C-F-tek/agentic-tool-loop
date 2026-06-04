from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


from aicarmine_broker.application.evidence.execution_digest import (  # noqa: E402
    execution_evidence_digest_text,
    repo_read_content_views,
)


def _repo_read_full_content(item: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    return str(item.get("full_content") or item.get("content") or ""), {"source": "test"}


def _key_lines(content: str) -> list[str]:
    return [line.strip() for line in str(content).splitlines() if line.strip()]


def test_repo_read_content_views_rehydrates_artifact_content(tmp_path: Path) -> None:
    artifact = tmp_path / "read.json"
    artifact.write_text(
        json.dumps({
            "tool": "repo_read",
            "items": [{
                "ok": True,
                "path": "pkg/a.py",
                "line_count": 2,
                "truncated": True,
                "content": "abcdef",
            }],
        }),
        encoding="utf-8",
    )

    views = repo_read_content_views(
        [{"tool_result": {"tool": "repo_read", "artifact": str(artifact)}}],
        repo_read_item_full_content=_repo_read_full_content,
        per_item_limit=3,
        total_limit=10,
    )

    assert views == [{
        "path": "pkg/a.py",
        "line_count": 2,
        "tool_truncated": True,
        "content_chars": 6,
        "content_view_chars": 3,
        "content_view_truncated_by_wrapper": True,
        "content_view": "abc",
    }]


def test_execution_evidence_digest_text_includes_lists_reads_guards_and_repairs() -> None:
    digest = execution_evidence_digest_text(
        {
            "history": [
                {"tool_result": {"tool": "repo_tree", "path": ".", "entries_total": 5, "truncated": True}},
                {
                    "decision": {"tool": "repo_read"},
                    "tool_result": {
                        "tool": "repo_read",
                        "items": [{"ok": True, "path": "pkg/a.py", "line_count": 1, "content": "def f(): pass\n"}],
                    },
                },
                {
                    "tool_result": {
                        "tool": "controller_guard",
                        "summary": "invalid final",
                        "raw_planner_text_preview": "raw\n output",
                        "vulkan_repair": {"ok": False, "error": "timeout", "raw_planner_text_preview": "repair raw"},
                    },
                },
            ]
        },
        repo_read_item_full_content=_repo_read_full_content,
        extract_key_lines=_key_lines,
    )

    assert "agentic_steps_recorded=3" in digest
    assert "repo_tree:. total=5 truncated=true" in digest
    assert "successful repo_read paths: pkg/a.py" in digest
    assert "pkg/a.py: def f(): pass" in digest
    assert "repo_read content_view:" in digest
    assert "invalid final" in digest
    assert "ok=False error=timeout" in digest
    assert "raw output" in digest
    assert "repair raw" in digest


def test_execution_evidence_digest_text_respects_limit() -> None:
    digest = execution_evidence_digest_text(
        {"history": [{"tool_result": {"tool": "repo_read", "path": "a.py"}}]},
        repo_read_item_full_content=_repo_read_full_content,
        extract_key_lines=_key_lines,
        limit=20,
    )

    assert len(digest) == 20
