from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


from aicarmine_broker.application.controller.preseed import (  # noqa: E402
    controller_initial_area_list_plans,
    controller_initial_area_read_plan,
    controller_initial_doc_preseed_plan,
    list_result_file_paths,
    root_surface_entries,
    root_surface_file_paths,
)


NAMED = {"agents.md": 0, "readme.md": 1}
INITIAL_DOCS = {"AGENTS.md": 0, "README.md": 1}


def _safe_rel(path: str) -> str:
    raw = str(path or "").replace("\\", "/")
    if raw.startswith("/") or ".." in raw.split("/"):
        raise ValueError("unsafe")
    return raw


def test_root_surface_entries_and_file_paths_use_real_repo_files(tmp_path: Path) -> None:
    (tmp_path / "ia_carmine").mkdir()
    (tmp_path / "README.md").write_text("# readme\n", encoding="utf-8")
    result = {
        "entries": [
            {"path": "README.md", "kind": "file"},
            {"path": "ia_carmine", "kind": "dir"},
            {"path": "missing.md", "kind": "file"},
        ]
    }

    assert root_surface_entries(result, repo_root=tmp_path) == [
        {"path": "README.md", "kind": "file"},
        {"path": "ia_carmine", "kind": "dir"},
        {"path": "missing.md", "kind": "file"},
    ]
    assert root_surface_file_paths(result, repo_root=tmp_path, safe_rel_path=_safe_rel) == ["README.md"]


def test_initial_doc_preseed_plan_selects_existing_docs_and_reports_missing_named_docs(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# readme\n", encoding="utf-8")
    root_result = {"entries": [{"path": "README.md", "kind": "file"}]}

    plan, skipped = controller_initial_doc_preseed_plan(
        root_result,
        repo_root=tmp_path,
        safe_rel_path=_safe_rel,
        named_read_priority=NAMED,
        initial_doc_name_priority=INITIAL_DOCS,
        scoped_concrete_read_target=10,
        multi_file_prompt_read_chars=4000,
    )

    assert plan and plan["tool"] == "repo_read"
    assert plan["arguments"] == {"paths": ["README.md"], "max_chars": 4000}
    assert {"candidate": "AGENTS.md", "reason": "not_seen_in_root_surface", "stage": "initial_doc_read"} in skipped


def test_initial_area_list_skips_low_signal_dirs(tmp_path: Path) -> None:
    for rel in ("ia_carmine", "docs", ".git"):
        (tmp_path / rel).mkdir(parents=True)
    root_result = {
        "entries": [
            {"path": "ia_carmine", "kind": "dir"},
            {"path": "docs", "kind": "dir"},
            {"path": ".git", "kind": "dir"},
        ]
    }

    plans, skipped = controller_initial_area_list_plans(
        root_result,
        repo_root=tmp_path,
        safe_rel_path=_safe_rel,
    )

    assert skipped == []
    assert [plan["arguments"]["path"] for plan in plans] == ["ia_carmine"]


def test_initial_area_read_plan_prefers_docs_before_code(tmp_path: Path) -> None:
    for rel in ("ia_carmine/a.py", "ia_carmine/README.md"):
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x\n", encoding="utf-8")
    list_result = {
        "path": "ia_carmine",
        "paths": ["ia_carmine/a.py", "ia_carmine/README.md", "missing.py"],
    }

    assert list_result_file_paths(list_result, repo_root=tmp_path, safe_rel_path=_safe_rel) == [
        "ia_carmine/a.py",
        "ia_carmine/README.md",
    ]
    plan, skipped = controller_initial_area_read_plan(
        list_result,
        repo_root=tmp_path,
        safe_rel_path=_safe_rel,
        named_read_priority=NAMED,
        single_file_prompt_read_chars=3000,
    )

    assert skipped == []
    assert plan and plan["tool"] == "repo_read"
    assert plan["arguments"] == {"path": "ia_carmine/README.md", "max_chars": 3000}
