#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

GENERATED_DOCS = {
    "tool_index": "docs/LOCAL_AI_TASKS/code-aware-tool-index.md",
    "current_state": "docs/LOCAL_AI_TASKS/md-code-coherence-current-state.md",
    "command_contract": "docs/LOCAL_AI_TASKS/code-aware-command-contract.md",
}


def repo_root_from(start: Path) -> Path:
    cur = start.resolve()
    for candidate in (cur, *cur.parents):
        if (candidate / ".git").exists():
            return candidate
    raise SystemExit(f"[FAIL] Repository root not found from {start}")


def rel(path: Path, repo: Path) -> str:
    return path.resolve().relative_to(repo.resolve()).as_posix()


def limited_text(lines: list[str], limit: int) -> str:
    if len(lines) <= limit:
        return "\n".join(lines).rstrip() + "\n"
    head = lines[: max(0, limit - 7)]
    head.extend([
        "",
        "## Troncato",
        "",
        f"Documento limitato a {limit} righe.",
        "Rigenerare `output/validation/md_code_coherence_report.json` per il dettaglio completo.",
    ])
    return "\n".join(head).rstrip() + "\n"


def load_or_build_report(repo: Path, report_arg: str, max_lines: int) -> dict[str, Any]:
    report_path = repo / report_arg
    if not report_path.exists():
        builder = repo / "Tools" / "docs" / "build_code_aware_md_coherence.py"
        if not builder.exists():
            raise SystemExit(f"[FAIL] Missing report and builder: {report_path}")
        subprocess.run([
            sys.executable,
            str(builder),
            "--repo-root",
            str(repo),
            "--max-lines",
            str(max_lines),
            "--output",
            report_arg,
            "--markdown-output",
            "output/validation/md_code_coherence_report.md",
        ], cwd=repo, check=True)
    return json.loads(report_path.read_text(encoding="utf-8-sig"))


def top_scripts(scripts: dict[str, Any], key: str, limit: int) -> list[dict[str, Any]]:
    items = list(scripts.get(key, {}).values())
    return sorted(items, key=lambda x: (-int(x.get("line_count") or 0), x.get("path") or ""))[:limit]


def render_tool_index(report: dict[str, Any], max_doc_lines: int) -> str:
    scripts = report.get("scripts", {})
    lines = [
        "# Code-aware tool index",
        "",
        "Generated from current repository code by `Tools/docs/build_code_aware_md_coherence.py`.",
        "Do not edit by hand when code changes; regenerate from the report.",
        "",
        "## Python scripts",
        "",
        "| Path | Lines | Args | Functions | Classes |",
        "|---|---:|---|---:|---:|",
    ]
    for item in top_scripts(scripts, "python", 120):
        args = ", ".join(item.get("args") or []) or "-"
        if len(args) > 180:
            args = args[:177] + "..."
        lines.append(
            f"| `{item['path']}` | {item.get('line_count')} | `{args}` | {item.get('functions')} | {item.get('classes')} |"
        )
    lines.extend(["", "## PowerShell workflows", "", "| Path | Lines | Parameters |", "|---|---:|---|"])
    for item in top_scripts(scripts, "powershell", 80):
        params = ", ".join(item.get("params") or []) or "-"
        if len(params) > 200:
            params = params[:197] + "..."
        lines.append(f"| `{item['path']}` | {item.get('line_count')} | `{params}` |")
    return limited_text(lines, max_doc_lines)


def render_current_state(report: dict[str, Any], max_doc_lines: int) -> str:
    summary = report.get("summary", {})
    findings = report.get("findings", [])
    by_kind = Counter(f.get("kind") for f in findings)
    by_class = Counter(f.get("classification") for f in findings)
    lines = [
        "# MD/code coherence current state",
        "",
        "## Scope",
        "",
        f"- Markdown scanned: `{report.get('inventory', {}).get('markdown_file_count')}`",
        f"- Python scripts scanned: `{report.get('inventory', {}).get('python_script_count')}`",
        f"- PowerShell scripts scanned: `{report.get('inventory', {}).get('powershell_script_count')}`",
        f"- Finding count: `{summary.get('finding_count')}`",
        f"- By severity: `{json.dumps(summary.get('by_severity', {}), ensure_ascii=False)}`",
        "",
        "## Finding classes",
        "",
    ]
    for key, count in by_class.most_common():
        lines.append(f"- `{key}`: `{count}`")
    lines.extend(["", "## Finding kinds", ""])
    for key, count in by_kind.most_common(30):
        lines.append(f"- `{key}`: `{count}`")
    lines.extend([
        "",
        "## Operational decision",
        "",
        "Do not bulk-fix all findings blindly.",
        "Use high findings first for active commands and missing scripts.",
        "Historical/evidence-only references must be demoted or described as historical, not recreated as fake active files.",
        "",
        "## Top high findings",
        "",
        "| Kind | Document | Target | Classification |",
        "|---|---|---|---|",
    ])
    high = [f for f in findings if f.get("severity") == "high"][:80]
    for item in high:
        lines.append(f"| {item.get('kind')} | `{item.get('path')}` | `{item.get('target')}` | {item.get('classification')} |")
    return limited_text(lines, max_doc_lines)


def render_command_contract(report: dict[str, Any], max_doc_lines: int) -> str:
    scripts = report.get("scripts", {})
    lines = [
        "# Code-aware command contract",
        "",
        "This document summarizes executable command contracts visible in current code.",
        "Root docs should link here or to canonical runbooks instead of duplicating long command blocks.",
        "",
        "## Python argparse contracts",
        "",
        "| Script | Args |",
        "|---|---|",
    ]
    py_items = sorted(scripts.get("python", {}).values(), key=lambda x: x.get("path") or "")
    for item in py_items:
        args = item.get("args") or []
        if not args:
            continue
        value = ", ".join(args)
        if len(value) > 220:
            value = value[:217] + "..."
        lines.append(f"| `{item['path']}` | `{value}` |")
        if len(lines) >= max_doc_lines - 40:
            break
    lines.extend(["", "## PowerShell parameter contracts", "", "| Script | Parameters |", "|---|---|"])
    ps_items = sorted(scripts.get("powershell", {}).values(), key=lambda x: x.get("path") or "")
    for item in ps_items:
        params = item.get("params") or []
        if not params:
            continue
        value = ", ".join(params)
        if len(value) > 220:
            value = value[:217] + "..."
        lines.append(f"| `{item['path']}` | `{value}` |")
    return limited_text(lines, max_doc_lines)


def write_if_changed(path: Path, content: str, apply: bool) -> bool:
    old = path.read_text(encoding="utf-8-sig", errors="replace") if path.exists() else None
    if old == content:
        print(f"[SKIP] unchanged {path}")
        return False
    if not apply:
        print(f"[DRY-RUN] would write {path}")
        print(f"[LINES] {path}: {len(content.splitlines())}")
        return True
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
    print(f"[WRITE] {path}")
    print(f"[LINES] {path}: {len(content.splitlines())}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate compact Markdown docs from code-aware coherence report.")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--report", default="output/validation/md_code_coherence_report.json")
    parser.add_argument("--max-lines", type=int, default=400)
    parser.add_argument("--doc-line-limit", type=int, default=390)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    repo = repo_root_from(Path(args.repo_root))
    report = load_or_build_report(repo, args.report, args.max_lines)
    generated = {
        GENERATED_DOCS["tool_index"]: render_tool_index(report, args.doc_line_limit),
        GENERATED_DOCS["current_state"]: render_current_state(report, args.doc_line_limit),
        GENERATED_DOCS["command_contract"]: render_command_contract(report, args.doc_line_limit),
    }
    changed = 0
    for rel_path, content in generated.items():
        if write_if_changed(repo / rel_path, content, args.apply):
            changed += 1
    print(f"[OK] generated_docs_changed={changed} apply={args.apply}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
