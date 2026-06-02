#!/usr/bin/env python3
"""Build a read-only inventory for generic IA-Carmine agent memory.

This tool is the first agnostic memory-observability layer. It reads the
existing local SQLite/JSONL memory contracts and emits reviewable JSON/Markdown
artifacts that other tools can consume.

It is intentionally report-only:

- no SQLite writes;
- no schema creation or migration;
- no memory promotion;
- no provider execution;
- no patch application;
- no Blender runtime execution.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from collections import Counter
from pathlib import Path
from typing import Any

REPO_ROOT_FOR_IMPORTS = Path(__file__).resolve().parents[3]
if str(REPO_ROOT_FOR_IMPORTS) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT_FOR_IMPORTS))

from ia_carmine.memory.agent_memory.policy import evaluate_memory_records, load_records
from ia_carmine.memory.agent_memory.state import MemoryRecord, keywords, select_memory

DEFAULT_MEMORY_DB = "indexAI/agent_memory/agent_memory.sqlite"
DEFAULT_OUTPUT = "output/ai_pipeline/agent_memory_inventory.json"
DEFAULT_MARKDOWN = "output/ai_pipeline/agent_memory_inventory.md"


def resolve_path(repo_root: Path, value: str) -> Path:
    """Resolve a path relative to the repository root."""
    path = Path(value)
    if not path.is_absolute():
        path = repo_root / path
    return path.resolve()


def safe_rel(path: Path, repo_root: Path) -> str:
    """Return a repo-relative path when possible."""
    try:
        return path.resolve(strict=False).relative_to(repo_root.resolve(strict=False)).as_posix()
    except ValueError:
        return str(path)


def quote_identifier(name: str) -> str:
    """Return a SQLite identifier quoted with double quotes."""
    return '"' + str(name).replace('"', '""') + '"'


def read_sqlite_metadata(memory_db: Path, repo_root: Path, *, max_tables: int) -> dict[str, Any]:
    """Inspect a SQLite memory DB in read-only mode."""
    meta: dict[str, Any] = {
        "path": safe_rel(memory_db, repo_root),
        "exists": memory_db.exists(),
        "read_only": True,
        "opened": False,
        "schema_version": None,
        "tables": [],
        "indexes": [],
        "errors": [],
    }
    if not memory_db.exists():
        return meta

    try:
        uri = f"file:{memory_db.as_posix()}?mode=ro"
        with sqlite3.connect(uri, uri=True) as conn:
            conn.row_factory = sqlite3.Row
            meta["opened"] = True
            table_rows = conn.execute(
                "select name from sqlite_master where type='table' order by name"
            ).fetchall()
            for row in table_rows[:max_tables]:
                table_name = str(row["name"])
                quoted = quote_identifier(table_name)
                table_info: dict[str, Any] = {
                    "name": table_name,
                    "row_count": None,
                    "columns": [],
                }
                try:
                    table_info["row_count"] = conn.execute(
                        f"select count(*) from {quoted}"
                    ).fetchone()[0]
                    cols = conn.execute(f"pragma table_info({quoted})").fetchall()
                    table_info["columns"] = [
                        {
                            "name": str(col["name"]),
                            "type": str(col["type"]),
                            "notnull": bool(col["notnull"]),
                            "pk": bool(col["pk"]),
                        }
                        for col in cols
                    ]
                except Exception as exc:  # noqa: BLE001 - report-only inventory.
                    table_info["error"] = f"{type(exc).__name__}: {exc}"
                meta["tables"].append(table_info)

            index_rows = conn.execute(
                "select name, tbl_name from sqlite_master where type='index' order by name"
            ).fetchall()
            meta["indexes"] = [
                {"name": str(row["name"]), "table": str(row["tbl_name"])}
                for row in index_rows[: max_tables * 2]
            ]

            if any(item["name"] == "memory_meta" for item in meta["tables"]):
                try:
                    row = conn.execute(
                        "select value from memory_meta where key='schema_version'"
                    ).fetchone()
                    if row:
                        meta["schema_version"] = str(row["value"])
                except Exception as exc:  # noqa: BLE001
                    meta["errors"].append(
                        f"memory_meta schema_version read failed: {type(exc).__name__}: {exc}"
                    )
    except Exception as exc:  # noqa: BLE001
        meta["errors"].append(f"{type(exc).__name__}: {exc}")
    return meta


def summarize_records(records: list[MemoryRecord]) -> dict[str, Any]:
    """Return distribution counters for loaded memory records."""
    kind_counts: Counter[str] = Counter()
    scope_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    tag_counts: Counter[str] = Counter()
    confidence_buckets: Counter[str] = Counter()
    total_content_chars = 0

    for record in records:
        kind_counts[record.kind] += 1
        scope_counts[record.scope] += 1
        source_counts[record.source] += 1
        total_content_chars += len(record.content)
        for tag in record.tags:
            tag_counts[str(tag)] += 1
        confidence = float(record.confidence)
        if confidence >= 0.9:
            confidence_buckets["0.90-1.00"] += 1
        elif confidence >= 0.75:
            confidence_buckets["0.75-0.89"] += 1
        elif confidence >= 0.5:
            confidence_buckets["0.50-0.74"] += 1
        else:
            confidence_buckets["0.00-0.49"] += 1

    return {
        "record_count": len(records),
        "total_content_chars": total_content_chars,
        "kind_counts": dict(kind_counts.most_common()),
        "scope_counts": dict(scope_counts.most_common()),
        "top_sources": dict(source_counts.most_common(30)),
        "tag_counts": dict(tag_counts.most_common(60)),
        "confidence_buckets": dict(confidence_buckets),
    }


def selected_memory_preview(
    *,
    records: list[MemoryRecord],
    objective: str,
    max_memory_chars: int,
    max_items: int,
) -> list[dict[str, Any]]:
    """Return a compact selected-memory preview under the existing ranking contract."""
    selected = select_memory(records, objective, max_memory_chars)
    preview: list[dict[str, Any]] = []
    for item in selected[:max_items]:
        preview.append(
            {
                "record_id": item.get("record_id"),
                "kind": item.get("kind"),
                "scope": item.get("scope"),
                "source": item.get("source"),
                "tags": item.get("tags", []),
                "confidence": item.get("confidence"),
                "rank_score": item.get("rank_score"),
                "summary": item.get("summary"),
            }
        )
    return preview


def build_inventory(args: argparse.Namespace) -> dict[str, Any]:
    """Build the memory inventory report."""
    repo_root = Path(args.repo_root).resolve()
    memory_db = resolve_path(repo_root, args.memory_db) if args.memory_db else None
    memory_jsonl = [resolve_path(repo_root, item) for item in args.memory_jsonl]

    records = load_records(
        memory_jsonl=memory_jsonl,
        memory_db=memory_db,
        limit=args.memory_db_limit,
    )
    policy_report = evaluate_memory_records(records)
    sqlite_meta = (
        read_sqlite_metadata(memory_db, repo_root, max_tables=args.max_sqlite_tables)
        if memory_db is not None
        else {
            "path": None,
            "exists": False,
            "read_only": True,
            "opened": False,
            "tables": [],
            "indexes": [],
            "errors": [],
        }
    )
    record_summary = summarize_records(records)
    selected_preview = selected_memory_preview(
        records=records,
        objective=args.objective,
        max_memory_chars=args.max_memory_chars,
        max_items=args.max_preview_records,
    )
    objective_keywords = list(keywords(args.objective, 40))

    errors: list[str] = []
    warnings: list[str] = []
    if memory_db is not None and not memory_db.exists():
        warnings.append(f"memory DB not found: {safe_rel(memory_db, repo_root)}")
    if sqlite_meta.get("errors"):
        warnings.extend(str(item) for item in sqlite_meta["errors"])

    return {
        "schema_version": 1,
        "kind": "agent_memory_inventory",
        "repo_root": str(repo_root),
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": False,
        "apply_mode": "report_only_read_only_inventory",
        "objective": args.objective,
        "objective_keywords": objective_keywords,
        "inputs": {
            "memory_db": safe_rel(memory_db, repo_root) if memory_db else None,
            "memory_db_exists": bool(memory_db and memory_db.exists()),
            "memory_jsonl": [safe_rel(path, repo_root) for path in memory_jsonl],
            "memory_db_limit": args.memory_db_limit,
            "max_memory_chars": args.max_memory_chars,
        },
        "sqlite": sqlite_meta,
        "records": record_summary,
        "policy_report": {
            "kind": policy_report.get("kind"),
            "passed": policy_report.get("passed"),
            "record_count": policy_report.get("record_count"),
            "promotion_candidate_count": policy_report.get("promotion_candidate_count"),
            "review_count": policy_report.get("review_count"),
            "risk_count": policy_report.get("risk_count"),
            "duplicate_group_count": policy_report.get("duplicate_group_count"),
            "action_counts": policy_report.get("action_counts", {}),
            "promotion_candidates": policy_report.get("promotion_candidates", [])[
                : args.max_policy_items
            ],
            "risks": [
                item
                for item in policy_report.get("reviews", [])
                if item.get("action") == "quarantine"
            ][: args.max_policy_items],
        },
        "selected_memory_preview": selected_preview,
        "integration": {
            "compatible_with_agent_state_packet": True,
            "compatible_with_megalithic_review": True,
            "recommended_consumer_artifacts": [
                "run_megalithic_repo_review.py",
                "refine_megalithic_review_signals.py",
                "build_megalithic_review_pr_draft.py",
                "run_local_ai_core_tool_activation.ps1",
            ],
        },
        "guardrails": {
            "sqlite_read_only": True,
            "sqlite_db_committed": False,
            "memory_promotion_performed": False,
            "memory_delete_performed": False,
            "provider_execution_performed": False,
            "patch_application_performed": False,
            "blender_runtime_touched": False,
        },
    }


def main() -> int:
    try:
        from ia_carmine._shared.agent_memory_inventory_cli import main as cli_main
    except ModuleNotFoundError:
        from ia_carmine._shared.agent_memory_inventory_cli import main as cli_main
    return cli_main()


if __name__ == "__main__":
    raise SystemExit(main())
