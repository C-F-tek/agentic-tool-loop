#!/usr/bin/env python3
"""Review generic agent memory for retention, risk and promotion candidates."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ia_carmine.memory.agent_memory.policy import (
    evaluate_memory_records,
    load_records,
    write_memory_policy_markdown,
)


def resolve_path(repo_root: Path, value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = repo_root / path
    return path.resolve()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--memory-db", default="indexAI/agent_memory/agent_memory.sqlite")
    parser.add_argument("--memory-jsonl", action="append", default=[])
    parser.add_argument("--memory-db-limit", type=int, default=1000)
    parser.add_argument("--output", default="output/ai_memory/agent_memory_policy_report.json")
    parser.add_argument(
        "--markdown-output", default="output/ai_memory/agent_memory_policy_report.md"
    )
    parser.add_argument("--fail-on-risk", action="store_true")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    memory_db = resolve_path(repo_root, args.memory_db) if args.memory_db else None
    memory_jsonl = [resolve_path(repo_root, item) for item in args.memory_jsonl]
    records = load_records(
        memory_jsonl=memory_jsonl, memory_db=memory_db, limit=args.memory_db_limit
    )
    report = evaluate_memory_records(records)
    report["repo_root"] = str(repo_root)
    report["inputs"] = {
        "memory_db": str(memory_db) if memory_db else None,
        "memory_db_exists": bool(memory_db and memory_db.exists()),
        "memory_jsonl": [str(path) for path in memory_jsonl],
    }
    if not args.fail_on_risk:
        report["passed"] = True

    output = resolve_path(repo_root, args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    markdown_output = resolve_path(repo_root, args.markdown_output)
    write_memory_policy_markdown(report, markdown_output)

    print(
        json.dumps(
            {
                "report": str(output),
                "markdown": str(markdown_output),
                "record_count": report["record_count"],
                "promotion_candidate_count": report["promotion_candidate_count"],
                "review_count": report["review_count"],
                "risk_count": report["risk_count"],
                "passed": report["passed"],
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
