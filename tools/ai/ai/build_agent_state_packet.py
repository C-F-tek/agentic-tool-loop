#!/usr/bin/env python3
"""Build a generic agent state packet from source files and memory JSONL."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from agent_state import (
    DEFAULT_MAX_MEMORY_CHARS,
    DEFAULT_MAX_RECORD_CHARS,
    MemoryRecord,
    build_agent_state_packet,
    load_memory_jsonl,
    load_memory_db,
    records_from_files,
    slugify,
    upsert_memory_db,
    write_agent_state_markdown,
)


def resolve_paths(repo_root: Path, values: list[str]) -> list[Path]:
    """Resolve CLI paths relative to the repository root."""
    paths: list[Path] = []
    for value in values:
        path = Path(value)
        if not path.is_absolute():
            path = repo_root / path
        paths.append(path.resolve())
    return paths


def memory_from_cli(values: list[str]) -> list[MemoryRecord]:
    """Create memory records from repeated CLI notes."""
    records: list[MemoryRecord] = []
    for index, value in enumerate(values, start=1):
        records.append(
            MemoryRecord.from_text(
                kind="operator_note",
                scope="task",
                source=f"cli_note_{index}",
                text=value,
                tags=("recent", "operator_note"),
            )
        )
    return records


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--objective", required=True)
    parser.add_argument("--include-file", action="append", default=[])
    parser.add_argument("--memory-jsonl", action="append", default=[])
    parser.add_argument("--memory-db")
    parser.add_argument("--memory-db-limit", type=int, default=1000)
    parser.add_argument("--memory-note", action="append", default=[])
    parser.add_argument("--save-inputs-to-memory-db", action="store_true")
    parser.add_argument("--output-dir", default="output/ai_pipeline/agent_state")
    parser.add_argument("--packet-name")
    parser.add_argument("--max-memory-chars", type=int, default=DEFAULT_MAX_MEMORY_CHARS)
    parser.add_argument("--max-record-chars", type=int, default=DEFAULT_MAX_RECORD_CHARS)
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = repo_root / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    records: list[MemoryRecord] = []
    immediate_records: list[MemoryRecord] = []
    immediate_records.extend(records_from_files(resolve_paths(repo_root, args.include_file), repo_root, args.max_record_chars))
    for memory_path in resolve_paths(repo_root, args.memory_jsonl):
        records.extend(load_memory_jsonl(memory_path))
    if args.memory_db:
        memory_db = Path(args.memory_db)
        if not memory_db.is_absolute():
            memory_db = repo_root / memory_db
        records.extend(load_memory_db(memory_db, limit=args.memory_db_limit))
    else:
        memory_db = None
    immediate_records.extend(memory_from_cli(args.memory_note))
    records.extend(immediate_records)

    memory_db_saved = 0
    if memory_db is not None and args.save_inputs_to_memory_db:
        memory_db_saved = upsert_memory_db(memory_db, immediate_records)

    packet_name = slugify(args.packet_name or args.objective, "agent_state_packet")[:96]
    packet = build_agent_state_packet(
        repo_root=repo_root,
        objective=args.objective,
        records=records,
        max_memory_chars=args.max_memory_chars,
        packet_name=packet_name,
    )

    json_path = output_dir / f"{packet_name}.json"
    md_path = output_dir / f"{packet_name}.md"
    manifest_path = output_dir / f"{packet_name}_memory_manifest.json"

    json_path.write_text(json.dumps(packet, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    manifest_path.write_text(json.dumps(packet["memory_manifest"], indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_agent_state_markdown(packet, md_path)

    print(
        json.dumps(
            {
                "packet": str(json_path),
                "markdown": str(md_path),
                "manifest": str(manifest_path),
                "selected_memory": len(packet["selected_memory"]),
                "microtasks": len(packet["microtasks"]),
                "selected_memory_chars": packet["budgets"]["selected_memory_chars"],
                "memory_db": str(memory_db) if memory_db else None,
                "memory_db_saved": memory_db_saved,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
