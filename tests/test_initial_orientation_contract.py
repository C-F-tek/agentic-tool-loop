from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


from aicarmine_broker.application.evidence.initial_orientation import (  # noqa: E402
    initial_orientation_surface_from_history,
)


def _surface(history: list[dict[str, Any]], skipped: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return initial_orientation_surface_from_history(
        history,
        skipped,
        repo_rel_token=lambda value: str(value).replace("\\", "/").strip("/"),
        repo_doc_or_config=lambda path: str(path).lower().endswith((".md", ".json", ".toml")),
        low_signal_top_dir=lambda path: str(path).startswith("venvs"),
        path_under_scope=lambda path, scope: str(path).startswith(str(scope).rstrip("/") + "/") or str(path) == scope,
    )


def test_initial_orientation_surface_collects_preseed_steps() -> None:
    surface = _surface(
        [
            {
                "step": 0,
                "tool_result": {
                    "controller_preseed": True,
                    "tool": "repo_tree",
                    "path": ".",
                    "ok": True,
                    "entries_total": 4,
                    "truncated": False,
                    "preseed_reason": "root",
                    "artifact": {"entries": []},
                },
            },
            {
                "step": 0,
                "tool_result": {
                    "controller_preseed": True,
                    "tool": "repo_list_files",
                    "path": "services",
                    "ok": True,
                    "preseed_index": 2,
                },
            },
            {
                "step": 0,
                "tool_result": {
                    "controller_preseed": True,
                    "tool": "repo_read",
                    "ok": True,
                    "items": [
                        {"ok": True, "path": "README.md"},
                        {"ok": True, "path": "services/app.py"},
                        {"ok": False, "path": "ignored.md"},
                    ],
                },
            },
            {
                "step": 1,
                "tool_result": {"tool": "repo_read", "ok": True, "items": [{"ok": True, "path": "not-preseed.md"}]},
            },
        ],
        skipped=[{"path": "low-signal"}],
    )

    assert surface["schema"] == "agentic_loop_initial_orientation_surface.v1"
    assert surface["controller_preseed_read_only"] is True
    assert surface["root_tree"]["count"] == 4
    assert surface["docs_read"] == ["README.md"]
    assert surface["areas_listed"] == ["services"]
    assert surface["files_read"] == ["README.md", "services/app.py"]
    assert surface["skipped_candidates"] == [{"path": "low-signal"}]
    assert surface["doc_read_count"] == 1
    assert surface["area_list_count"] == 1
    assert surface["file_read_count"] == 2
    assert surface["useful_area_list_count"] == 1
    assert surface["concrete_useful_file_read_count"] == 1


def test_initial_orientation_surface_accepts_controller_preseed_decision_rows() -> None:
    surface = _surface([
        {
            "step": 0,
            "preseed_index": 1,
            "decision": {"action": "controller_preseed", "tool": "repo_list_files", "reason": "area"},
            "tool_result": {"tool": "repo_list_files", "path": "ia_carmine", "ok": True},
        }
    ])

    assert surface["areas_listed"] == ["ia_carmine"]
    assert surface["preseed_steps"][0]["preseed_index"] == 1
    assert surface["preseed_steps"][0]["reason"] == "area"
