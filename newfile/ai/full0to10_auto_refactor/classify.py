"""Candidate classification for auto-refactor planning."""
from __future__ import annotations

from typing import Any

from .constants import CODE_SPLIT_LINE_THRESHOLD, MD_SPLIT_LINE_THRESHOLD


def classify_record(record: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    path = str(record["path"])
    suffix = str(record["suffix"])
    lines = int(record["line_count"])

    if suffix == ".md" and lines > MD_SPLIT_LINE_THRESHOLD:
        candidates.append({"kind": "markdown_split", "path": path, "severity": "high",
                           "reason": f"Markdown file has {lines} lines; split threshold is {MD_SPLIT_LINE_THRESHOLD}."})

    if suffix in {".py", ".ps1"} and lines > CODE_SPLIT_LINE_THRESHOLD:
        candidates.append({"kind": "code_split_candidate", "path": path, "severity": "medium",
                           "reason": f"Code file has {lines} lines; inspect for module extraction."})

    if int(record["trailing_whitespace_lines"]) > 0:
        candidates.append({"kind": "safe_cleanup_trailing_whitespace", "path": path, "severity": "low",
                           "reason": f"{record['trailing_whitespace_lines']} lines have trailing whitespace."})

    if not bool(record["final_newline"]):
        candidates.append({"kind": "safe_cleanup_final_newline", "path": path, "severity": "low",
                           "reason": "File does not end with final newline."})
    return candidates


def classify_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for record in records:
        candidates.extend(classify_record(record))
    order = {"high": 0, "medium": 1, "low": 2}
    return sorted(candidates, key=lambda item: (order.get(str(item["severity"]), 9), str(item["path"])))
