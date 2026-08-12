#!/usr/bin/env python3
"""Build a request-scoped transient context artifact.

This tool captures memory notes and RAW snippets for the current user request so
orchestrators and review tools can consume them without mutating persistent
memory or source files.

It is intentionally temporary and report-only:

- no SQLite writes;
- no persistent memory promotion;
- no provider execution;
- no patch application;
- no Blender runtime execution;
- no source writes except requested JSON/Markdown outputs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


try:
    from Tools.ai.code_patch_plan_common import read_json_object
    from Tools.validation.report_utils import write_json_report, write_text_report
except ImportError:
    repo_root_for_import = Path(__file__).resolve().parents[2]
    if str(repo_root_for_import) not in sys.path:
        sys.path.insert(0, str(repo_root_for_import))
    from Tools.ai.code_patch_plan_common import read_json_object
    from Tools.validation.report_utils import write_json_report, write_text_report

DEFAULT_OUTPUT = "output/ai_pipeline/agent_transient_request_context.json"
DEFAULT_MARKDOWN = "output/ai_pipeline/agent_transient_request_context.md"
RAW_TEXT_EXTENSIONS = {".md", ".txt", ".json", ".jsonl", ".yaml", ".yml", ".csv", ".log", ".py", ".ps1", ".sh"}


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def resolve_path(repo_root: Path, value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = repo_root / path
    return path.resolve()


def repo_rel(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve(strict=False).relative_to(repo_root.resolve(strict=False)).as_posix()
    except ValueError:
        return str(path)


def split_values(items: list[str]) -> list[str]:
    values: list[str] = []
    for item in items:
        for part in str(item).split(","):
            normalized = part.strip().strip("'\"")
            if normalized:
                values.append(normalized)
    return values


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def read_text(path: Path, *, max_chars: int) -> tuple[str, bool, str | None]:
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError as exc:
        return "", False, f"{type(exc).__name__}: {exc}"
    truncated = len(text) > max_chars if max_chars > 0 else False
    if truncated:
        text = text[:max_chars]
    return text, truncated, None


def collect_raw_files(repo_root: Path, values: list[str], *, max_files: int, max_chars_per_file: int) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    seen: set[Path] = set()
    for value in split_values(values):
        path = resolve_path(repo_root, value)
        candidates: list[Path] = []
        if path.is_dir():
            candidates.extend(sorted(item for item in path.rglob("*") if item.is_file() and item.suffix.lower() in RAW_TEXT_EXTENSIONS))
        elif path.is_file():
            candidates.append(path)
        else:
            files.append({"path": repo_rel(path, repo_root), "exists": False, "error": "missing", "truncated": False})
            continue
        for candidate in candidates:
            if candidate in seen:
                continue
            seen.add(candidate)
            if len(files) >= max_files:
                break
            text, truncated, error = read_text(candidate, max_chars=max_chars_per_file)
            item: dict[str, Any] = {
                "path": repo_rel(candidate, repo_root),
                "exists": True,
                "extension": candidate.suffix.lower(),
                "chars": len(text),
                "lines": len(text.splitlines()),
                "truncated": truncated,
                "sha256": sha256_text(text),
                "error": error or "",
            }
            if error is None:
                item["preview"] = text[: min(len(text), 2000)]
            files.append(item)
        if len(files) >= max_files:
            break
    return files


def build_report_reference(repo_root: Path, value: str) -> dict[str, Any]:
    path = resolve_path(repo_root, value)
    out: dict[str, Any] = {"path": repo_rel(path, repo_root), "exists": path.exists(), "kind": None, "passed": None, "error": "", "summary": {}}
    if not path.exists():
        out["error"] = "missing"
        return out
    data, errors = read_json_object(path)
    if errors:
        out["error"] = "; ".join(errors)
        return out
    out["kind"] = data.get("kind")
    out["passed"] = data.get("passed")
    for key in ("summary", "decision", "guardrails", "inputs"):
        if isinstance(data.get(key), dict):
            out["summary"][key] = data[key]
    return out


def build_context(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = Path(args.repo_root).resolve()
    memory_notes = [item for item in split_values(args.memory_note or [])]
    raw_files = collect_raw_files(repo_root, args.raw_file or [], max_files=args.max_raw_files, max_chars_per_file=args.max_chars_per_file)
    report_refs = [build_report_reference(repo_root, value) for value in split_values(args.report_file or [])]
    warnings: list[str] = []
    for item in raw_files:
        if item.get("error"):
            warnings.append(f"raw: {item.get('path')}: {item.get('error')}")
    for item in report_refs:
        if item.get("error"):
            warnings.append(f"report: {item.get('path')}: {item.get('error')}")

    total_raw_chars = sum(int(item.get("chars") or 0) for item in raw_files if item.get("exists"))
    return {
        "schema_version": 1,
        "kind": "agent_transient_request_context",
        "generated_at": now_iso(),
        "repo_root": str(repo_root),
        "passed": True,
        "errors": [],
        "warnings": warnings,
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": False,
        "apply_mode": "report_only_request_scoped_context",
        "objective": args.objective,
        "scope": "current_request_only",
        "persistence": {
            "persistent_memory_write_performed": False,
            "sqlite_write_performed": False,
            "promotion_performed": False,
            "delete_performed": False,
            "commit_allowed": False,
        },
        "memory_notes": [
            {"id": f"note-{index+1:03d}", "chars": len(note), "sha256": sha256_text(note), "content": note}
            for index, note in enumerate(memory_notes)
        ],
        "raw_context": {
            "file_count": len(raw_files),
            "total_chars": total_raw_chars,
            "max_files": args.max_raw_files,
            "max_chars_per_file": args.max_chars_per_file,
            "files": raw_files,
        },
        "report_context": {
            "file_count": len(report_refs),
            "reports": report_refs,
        },
        "integration": {
            "compatible_with_megalithic_review": True,
            "compatible_with_core_activation": True,
            "recommended_as_report_file": True,
            "request_scoped": True,
        },
        "guardrails": {
            "report_only": True,
            "request_scoped": True,
            "provider_execution_performed": False,
            "patch_application_performed": False,
            "persistent_memory_write_performed": False,
            "sqlite_write_performed": False,
            "blender_runtime_touched": False,
            "real_github_pr_created": False,
            "output_artifacts_should_not_be_committed": True,
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = ["# Agent Transient Request Context", ""]
    lines.append(f"- Scope: `{report['scope']}`")
    lines.append(f"- Passed: `{report['passed']}`")
    lines.append(f"- Provider execution performed: `{report['provider_execution_performed']}`")
    lines.append(f"- Patch application performed: `{report['patch_application_performed']}`")
    lines.append(f"- Persistent memory write: `{report['persistence']['persistent_memory_write_performed']}`")
    lines.append(f"- SQLite write: `{report['persistence']['sqlite_write_performed']}`")
    lines.append(f"- Memory notes: `{len(report['memory_notes'])}`")
    lines.append(f"- Raw files: `{report['raw_context']['file_count']}`")
    lines.append(f"- Report refs: `{report['report_context']['file_count']}`")
    lines.append("")
    if report["memory_notes"]:
        lines.append("## Memory notes")
        lines.append("")
        for note in report["memory_notes"]:
            lines.append(f"### {note['id']}")
            lines.append("")
            lines.append(note["content"])
            lines.append("")
    if report["raw_context"]["files"]:
        lines.append("## RAW context files")
        lines.append("")
        for item in report["raw_context"]["files"]:
            lines.append(f"- `{item.get('path')}` exists=`{item.get('exists')}` chars=`{item.get('chars')}` truncated=`{item.get('truncated')}` error=`{item.get('error')}`")
        lines.append("")
    if report["report_context"]["reports"]:
        lines.append("## Report context")
        lines.append("")
        for item in report["report_context"]["reports"]:
            lines.append(f"- `{item.get('path')}` kind=`{item.get('kind')}` passed=`{item.get('passed')}` error=`{item.get('error')}`")
        lines.append("")
    lines.append("## Guardrails")
    lines.append("")
    for key, value in report["guardrails"].items():
        lines.append(f"- `{key}`: `{value}`")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--objective", default="Capture request-scoped transient context for IA-Carmine orchestration.")
    parser.add_argument("--memory-note", action="append", default=[])
    parser.add_argument("--raw-file", action="append", default=[])
    parser.add_argument("--report-file", action="append", default=[])
    parser.add_argument("--max-raw-files", type=int, default=80)
    parser.add_argument("--max-chars-per-file", type=int, default=12000)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--markdown-output", default=DEFAULT_MARKDOWN)
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    report = build_context(args)
    output = resolve_path(repo_root, args.output)
    markdown_output = resolve_path(repo_root, args.markdown_output)
    write_json_report(report, output)
    write_text_report(render_markdown(report), markdown_output)
    print(
        json.dumps(
            {
                "passed": report["passed"],
                "output": str(output),
                "markdown": str(markdown_output),
                "memory_note_count": len(report["memory_notes"]),
                "raw_file_count": report["raw_context"]["file_count"],
                "report_file_count": report["report_context"]["file_count"],
                "provider_execution_performed": False,
                "patch_application_performed": False,
                "persistent_memory_write_performed": False,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
