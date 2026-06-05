from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


from aicarmine_broker.application.memory.conflict_detector import detect_memory_conflicts


def test_memory_conflict_keeps_valid_record(tmp_path: Path) -> None:
    target = tmp_path / "services" / "a.py"
    target.parent.mkdir(parents=True)
    target.write_text("x = 1\n", encoding="utf-8")
    record = {
        "record_id": 1,
        "text": "valid lesson",
        "metadata": {"referenced_paths": ["services/a.py"], "branch": "main"},
    }

    report = detect_memory_conflicts({"records": [record]}, repo_root=tmp_path, current_branch="main")

    assert report["schema"] == "memory_conflict_report.v1"
    assert report["usable_memory_records"] == [record]
    assert report["ignored_memory_records"] == []
    assert report["diagnostic_only"] is True
    assert report["does_not_mutate_memory"] is True


def test_memory_conflict_ignores_deleted_path_lesson(tmp_path: Path) -> None:
    record = {
        "record_id": 2,
        "metadata": {"referenced_paths": ["services/missing.py"], "branch": "main"},
    }

    report = detect_memory_conflicts([record], repo_root=tmp_path, current_branch="main")

    assert report["usable_memory_records"] == []
    assert report["ignored_memory_records"][0]["record_id"] == "2"
    assert report["ignored_memory_records"][0]["reason"] == "referenced_path_no_longer_exists"
    assert report["ignored_memory_records"][0]["details"]["path"] == "services/missing.py"


def test_memory_conflict_ignores_wrong_branch_record(tmp_path: Path) -> None:
    record = {"id": 3, "metadata": {"branch": "feature/old"}}

    report = detect_memory_conflicts([record], repo_root=tmp_path, current_branch="main")

    assert report["usable_memory_records"] == []
    assert report["ignored_memory_records"][0]["reason"] == "wrong_branch_record"
    assert report["ignored_memory_records"][0]["details"]["record_branch"] == "feature/old"


def test_memory_conflict_marks_hash_mismatch(tmp_path: Path) -> None:
    target = tmp_path / "services" / "a.py"
    target.parent.mkdir(parents=True)
    target.write_text("x = 2\n", encoding="utf-8")
    record = {
        "record_id": "hash-row",
        "metadata": {
            "referenced_paths": ["services/a.py"],
            "file_hashes": {"services/a.py": "oldhash"},
        },
    }

    report = detect_memory_conflicts(
        [record],
        repo_root=tmp_path,
        current_file_hashes={"services/a.py": "newhash"},
    )

    assert report["usable_memory_records"] == []
    assert report["ignored_memory_records"][0]["reason"] == "referenced_file_hash_mismatch"
    assert report["memory_conflicts"][0]["current_hash"] == "newhash"


def test_memory_conflict_ignores_outside_repo_path(tmp_path: Path) -> None:
    record = {"record_id": 4, "metadata": {"referenced_paths": ["../outside.py"]}}

    report = detect_memory_conflicts([record], repo_root=tmp_path)

    assert report["ignored_memory_records"][0]["reason"] == "referenced_path_outside_repo"
    assert report["ignored_memory_records"][0]["severity"] == "high"


def test_memory_conflict_report_is_json_serializable(tmp_path: Path) -> None:
    report = detect_memory_conflicts([], repo_root=tmp_path)

    json.dumps(report, ensure_ascii=False)
