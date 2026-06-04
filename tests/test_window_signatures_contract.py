from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


from aicarmine_broker.application.window_signatures import (  # noqa: E402
    decision_paths,
    planner_scratchpad_window_signature,
    repo_read_window_range_for_target,
    repo_read_window_signature,
)


def test_decision_paths_collects_supported_path_fields_and_dedupes() -> None:
    args = {
        "path": "./a.py",
        "target_file": "a.py",
        "items": [{"target_path": ".github/workflows/test.yml"}, "b.py"],
    }

    assert decision_paths(args) == ["a.py", ".github/workflows/test.yml", "b.py"]


def test_repo_read_window_signature_is_stable_and_numeric() -> None:
    signature = repo_read_window_signature({
        "path": "./a.py",
        "line": "10",
        "before": "2",
        "after": 5,
        "max_chars": 1000,
    })

    payload = json.loads(signature)
    assert payload["paths"] == ["a.py"]
    assert payload["window"]["line"] == 10
    assert payload["window"]["before"] == 2


def test_planner_scratchpad_window_signature_normalizes_kind_and_defaults() -> None:
    signature = planner_scratchpad_window_signature({
        "kind": "prompt_context",
        "document_id": "doc-1",
        "offset": "25",
    })

    payload = json.loads(signature)
    assert payload["kind"] == "prompt_context_window"
    assert payload["document_id"] == "doc-1"
    assert payload["offset"] == 25
    assert payload["max_chars"] == 3000


def test_repo_read_window_range_for_target() -> None:
    assert repo_read_window_range_for_target(
        {"target_file": "a.py", "line": 10, "before": 2, "after": 3},
        "a.py",
    ) == (8, 13)
    assert repo_read_window_range_for_target({"path": "b.py", "line": 1}, "a.py") is None
