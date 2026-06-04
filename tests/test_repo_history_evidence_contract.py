from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


from aicarmine_broker.application.repo_history_evidence import (  # noqa: E402
    append_unique,
    extract_headings,
    extract_key_lines,
    extract_mentioned_paths,
    failed_repo_list_files_paths,
    file_memory_from_history,
    rank_core_candidates,
    read_items_from_history,
    repo_list_evidence,
)


def _safe_rel(path: str) -> str:
    raw = str(path or "").replace("\\", "/")
    if raw.startswith("/") or ".." in raw.split("/"):
        raise ValueError("unsafe")
    return raw


def test_read_items_rehydrates_same_tool_payload_content() -> None:
    history = [{
        "step": 3,
        "tool_result": {
            "tool": "repo_read",
            "ok": True,
            "items": [{"path": "./docs/PROJECT.md", "ok": True, "content_preview": "# preview"}],
        },
    }]

    items = read_items_from_history(
        history,
        same_tool_artifact_payload=lambda _result: {
            "items": [{"path": "docs/PROJECT.md", "content": "# Project\nruntime tool contract\n"}],
        },
    )

    assert items == [{
        "path": "docs/PROJECT.md",
        "ok": True,
        "content_preview": "# preview",
        "artifact": None,
        "content": "# Project\nruntime tool contract\n",
        "step": 3,
    }]


def test_text_extractors_build_repo_memory_from_real_content() -> None:
    content = "# Runtime\nThe canonical tool workflow is in services/app.py\nignore very long line " + ("x" * 260)

    assert extract_headings(content) == ["Runtime"]
    assert extract_key_lines(content) == [
        "# Runtime",
        "The canonical tool workflow is in services/app.py",
    ]
    assert extract_mentioned_paths(content) == ["services/app.py"]

    memory = file_memory_from_history(
        [{
            "tool_result": {
                "tool": "repo_read",
                "ok": True,
                "items": [{"path": "AGENTS.md", "ok": True, "content": content, "line_count": 3}],
            },
        }],
        same_tool_artifact_payload=lambda result: result,
    )

    assert memory[0]["path"] == "AGENTS.md"
    assert memory[0]["headings"] == ["Runtime"]
    assert memory[0]["mentioned_paths"] == ["services/app.py"]


def test_repo_list_evidence_uses_raw_payload_and_failed_paths() -> None:
    history = [
        {
            "step": 1,
            "tool_result": {
                "tool": "repo_tree",
                "ok": True,
                "path": ".",
                "entries_preview": [{"path": "README.md"}],
                "count": 1,
            },
        },
        {
            "step": 2,
            "tool_result": {
                "tool": "repo_list_files",
                "ok": False,
                "path": "docs",
                "error": "missing",
            },
        },
    ]

    rows = repo_list_evidence(
        history,
        same_tool_artifact_payload=lambda result: {
            "entries": [{"path": "ia_carmine"}, {"path": "services/app.py"}],
        } if result.get("tool") == "repo_tree" else {},
    )

    assert rows == [{
        "step": 1,
        "tool": "repo_tree",
        "path": ".",
        "total_matches": 1,
        "limit": None,
        "truncated": None,
        "paths_preview": ["README.md", "ia_carmine", "services/app.py"],
    }]
    assert failed_repo_list_files_paths(history) == ["docs"]


def test_rank_core_candidates_requires_existing_non_low_signal_top_dirs(tmp_path: Path) -> None:
    (tmp_path / "ia_carmine").mkdir()
    (tmp_path / "docs").mkdir()
    file_memory = [{
        "mentioned_paths": ["ia_carmine/_shared/runtime.py", "missing/path.py", "docs/guide.md"],
        "key_lines": ["core module: ia_carmine/cli.py"],
    }]
    list_rows = [{
        "path": ".",
        "paths_preview": ["ia_carmine/_shared/runtime.py", "docs/guide.md", "missing/path.py"],
    }]

    ranked = rank_core_candidates(
        file_memory,
        list_rows,
        repo_root=tmp_path,
        safe_rel_path=_safe_rel,
    )

    assert ranked[0]["path"] == "ia_carmine"
    assert ranked[0]["score"] > 0
    assert all(row["path"] != "docs" for row in ranked)
    assert all(row["path"] != "missing" for row in ranked)


def test_append_unique_normalizes_repo_tokens() -> None:
    values: list[str] = []
    append_unique(values, "./.github/workflows/test.yml")
    append_unique(values, ".github/workflows/test.yml")
    append_unique(values, "")

    assert values == [".github/workflows/test.yml"]
