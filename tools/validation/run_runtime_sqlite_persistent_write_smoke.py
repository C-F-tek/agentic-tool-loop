#!/usr/bin/env python3
"""Smoke test for controlled persistent SQLite memory writes."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def resolve_path(repo_root: Path, value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = repo_root / path
    return path.resolve()


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", default="output/validation/runtime_sqlite_persistent_write_smoke.json")
    parser.add_argument("--markdown-output", default="output/validation/runtime_sqlite_persistent_write_smoke.md")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    out = resolve_path(repo_root, args.output)
    md = resolve_path(repo_root, args.markdown_output)
    smoke_dir = repo_root / "output" / "validation" / "runtime_sqlite_persistent_write_smoke"
    smoke_dir.mkdir(parents=True, exist_ok=True)
    db_path = smoke_dir / "agent_memory.sqlite"
    memory_report = smoke_dir / "persistent_write_report.json"
    memory_md = smoke_dir / "persistent_write_report.md"
    command = [
        sys.executable, "Tools/ai/agent_runtime_sqlite_memory.py",
        "--repo-root", ".",
        "--action", "remember",
        "--scope", "persistent",
        "--persistent-database", str(db_path),
        "--allow-persistent-write",
        "--confirm", "persistent_write",
        "--request-id", "persistent_write_smoke",
        "--summary", "Controlled persistent SQLite write smoke",
        "--content", "Controlled persistent SQLite write smoke: patch bundles must be used for long patches.",
        "--role", "validation_smoke",
        "--tag", "persistent-write",
        "--tag", "sqlite",
        "--output", str(memory_report),
        "--markdown-output", str(memory_md),
    ]
    completed = subprocess.run(command, cwd=repo_root, text=True, capture_output=True, check=False)
    report_data: dict[str, Any] = {}
    if memory_report.exists():
        report_data = json.loads(memory_report.read_text(encoding="utf-8-sig"))
    passed = (
        completed.returncode == 0
        and report_data.get("passed") is True
        and report_data.get("sqlite_write_performed") is True
        and report_data.get("persistent_memory_write_performed") is True
        and report_data.get("guardrails", {}).get("persistent_memory_write_authorized") is True
        and report_data.get("patch_application_performed") is False
        and report_data.get("provider_execution_performed") is False
    )
    smoke = {
        "schema_version": 1,
        "kind": "runtime_sqlite_persistent_write_smoke",
        "generated_at": now_iso(),
        "repo_root": str(repo_root),
        "passed": passed,
        "errors": [] if passed else ["persistent write smoke invariants failed"],
        "warnings": [],
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "sqlite_write_performed": bool(report_data.get("sqlite_write_performed")),
        "persistent_memory_write_performed": bool(report_data.get("persistent_memory_write_performed")),
        "persistent_memory_write_authorized": bool(report_data.get("guardrails", {}).get("persistent_memory_write_authorized")),
        "memory_report": str(memory_report.relative_to(repo_root)),
        "persistent_database": str(db_path.relative_to(repo_root)),
        "stdout_tail": completed.stdout[-4000:],
        "stderr_tail": completed.stderr[-4000:],
    }
    write_json(out, smoke)
    md.parent.mkdir(parents=True, exist_ok=True)
    md.write_text(
        "# Runtime SQLite Persistent Write Smoke\n\n"
        + f"- passed: `{smoke['passed']}`\n"
        + f"- sqlite_write_performed: `{smoke['sqlite_write_performed']}`\n"
        + f"- persistent_memory_write_performed: `{smoke['persistent_memory_write_performed']}`\n"
        + f"- persistent_memory_write_authorized: `{smoke['persistent_memory_write_authorized']}`\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "passed": smoke["passed"],
        "output": str(out),
        "provider_execution_performed": smoke["provider_execution_performed"],
        "patch_application_performed": smoke["patch_application_performed"],
        "sqlite_write_performed": smoke["sqlite_write_performed"],
        "persistent_memory_write_performed": smoke["persistent_memory_write_performed"],
        "persistent_memory_write_authorized": smoke["persistent_memory_write_authorized"],
    }, indent=2, ensure_ascii=False))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
