from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))

from aicarmine_broker.application.job.response_values import (
    compact_json,
    compact_text,
    event_digest,
)


def test_compact_text_preserves_short_text_and_normalizes_newlines() -> None:
    assert compact_text("a\r\nb\rc", 100) == "a\nb\nc"


def test_compact_text_truncates_with_inline_payload_hint() -> None:
    result = compact_text("x" * 100, 60)

    assert result.startswith("x" * 20)
    assert result.endswith("... <full output is available in inline terminal payload when present>")
    assert "final.md/final.json" not in result


def test_compact_text_limit_zero_returns_full_text() -> None:
    assert compact_text("x" * 100, 0) == "x" * 100


def test_compact_json_uses_json_shape_and_falls_back_to_str() -> None:
    assert compact_json({"b": 1}, 100).startswith("{\n")

    class BrokenRepr:
        def __str__(self) -> str:
            return "broken"

    assert compact_json(BrokenRepr(), 100) == '"broken"'


def test_event_digest_keeps_public_status_without_local_pointer_values() -> None:
    digest = event_digest(
        {
            "time": "2026-06-04 12:00:00",
            "step": 2,
            "event_type": "tool_result",
            "message": "ok",
            "payload": {
                "tool": "repo_read",
                "ok": True,
                "status": "completed",
                "path": "AGENTS.md",
                "artifact": "reads/a.json",
                "returncode": 0,
                "count": 1,
                "truncated": False,
                "z": 1,
            },
        }
    )

    assert digest == {
        "time": "2026-06-04 12:00:00",
        "step": 2,
        "event_type": "tool_result",
        "message": "ok",
        "payload_keys": [
            "artifact",
            "count",
            "ok",
            "path",
            "returncode",
            "status",
            "tool",
            "truncated",
            "z",
        ],
        "tool": "repo_read",
        "ok": True,
        "status": "completed",
        "returncode": 0,
        "count": 1,
        "truncated": False,
    }
    assert "path" not in digest
    assert "artifact" not in digest


def test_job_store_reexports_response_value_helpers() -> None:
    from aicarmine_broker import job_store

    assert job_store.compact_text("abc", 10) == "abc"
    assert job_store.event_digest({"event_type": "x"}) == {"event_type": "x"}
