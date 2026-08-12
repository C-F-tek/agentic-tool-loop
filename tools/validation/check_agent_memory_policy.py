#!/usr/bin/env python3
"""Validate the generic agent memory retention and promotion policy."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def import_memory_modules(repo_root: Path) -> dict[str, Any]:
    tools_ai = repo_root / "Tools" / "ai"
    for value in (str(repo_root), str(tools_ai)):
        if value not in sys.path:
            sys.path.insert(0, value)
    from agent_memory_policy import evaluate_memory_records, load_records
    from agent_state import MemoryRecord

    return {
        "evaluate_memory_records": evaluate_memory_records,
        "load_records": load_records,
        "MemoryRecord": MemoryRecord,
    }


def check_policy(repo_root: Path, memory_db: Path | None) -> dict[str, Any]:
    modules = import_memory_modules(repo_root)
    MemoryRecord = modules["MemoryRecord"]
    now = datetime(2026, 4, 29, tzinfo=timezone.utc)
    records = [
        MemoryRecord.from_text(
            kind="validation_result",
            scope="project",
            source="synthetic_pass",
            text="Validated NPU guardrail packet and Blender audio smoke policy.",
            tags=("validated", "guardrail"),
            confidence=0.95,
        ),
        MemoryRecord.from_text(
            kind="operator_note",
            scope="task",
            source="synthetic_secret",
            text="api_key=sk-this-is-a-synthetic-blocked-example",
            tags=("recent",),
            confidence=0.9,
        ),
        MemoryRecord(
            record_id="synthetic_stale",
            kind="operator_note",
            scope="task",
            source="synthetic_stale",
            summary="Old transient note.",
            content="Old transient note.",
            tags=("recent",),
            confidence=0.9,
            created_at=(now - timedelta(days=90)).isoformat(),
        ),
    ]
    synthetic = modules["evaluate_memory_records"](records, now=now)
    errors: list[str] = []
    actions = {item["source"]: item["action"] for item in synthetic["reviews"]}
    if actions.get("synthetic_pass") != "promote_candidate":
        errors.append("validated synthetic record was not marked as promote_candidate")
    if actions.get("synthetic_secret") != "quarantine":
        errors.append("synthetic secret record was not quarantined")
    if actions.get("synthetic_stale") != "expire_review":
        errors.append("stale synthetic record was not marked for expire_review")

    actual_report = None
    if memory_db is not None and memory_db.exists():
        actual_records = modules["load_records"](memory_db=memory_db, limit=1000)
        actual_report = modules["evaluate_memory_records"](actual_records)
        if actual_report["risk_count"]:
            errors.append(f"actual memory DB has {actual_report['risk_count']} quarantined records")

    return {
        "schema_version": 1,
        "kind": "agent_memory_policy",
        "repo_root": str(repo_root),
        "memory_db": str(memory_db) if memory_db else None,
        "memory_db_exists": bool(memory_db and memory_db.exists()),
        "passed": not errors,
        "errors": errors,
        "warnings": [],
        "synthetic": {
            "record_count": synthetic["record_count"],
            "promotion_candidate_count": synthetic["promotion_candidate_count"],
            "risk_count": synthetic["risk_count"],
            "action_counts": synthetic["action_counts"],
        },
        "actual": None if actual_report is None else {
            "record_count": actual_report["record_count"],
            "promotion_candidate_count": actual_report["promotion_candidate_count"],
            "review_count": actual_report["review_count"],
            "risk_count": actual_report["risk_count"],
            "action_counts": actual_report["action_counts"],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--memory-db", default="indexAI/agent_memory/agent_memory.sqlite")
    parser.add_argument("--output", help="Optional JSON report path.")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    memory_db = Path(args.memory_db)
    if not memory_db.is_absolute():
        memory_db = repo_root / memory_db
    report = check_policy(repo_root, memory_db)
    text = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        output = Path(args.output).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
