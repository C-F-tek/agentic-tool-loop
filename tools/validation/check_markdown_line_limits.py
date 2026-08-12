#!/usr/bin/env python3
"""Validate Markdown line-count budgets for IA-Carmine documentation."""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

DEFAULT_MAX_LINES = 400
DEFAULT_SCOPES = (
    "AGENTS.md",
    "CHATGPT.md",
    "FULL_RUN_UNICA_TUTTO_SU_TUTTO.md",
    "README.md",
    "WORKFLOW.md",
    "docs",
    "CHATGPT",
)
EXCLUDED_DIR_NAMES = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "node_modules",
    "output",
    "renders",
    "venv",
}
EXCLUDED_PREFIXES = (
    "docs/LOCAL_VALIDATION_EVIDENCE/",
    "indexAI/code_chunks/",
    "indexAI/project_code_chunks/",
    "Tools/npu/npu_blender_manual_chunks/",
)


def find_repo_root(start: Path) -> Path:
    current = start.resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate
    raise SystemExit(f"Cannot find repository root from {start}")


def rel(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def should_skip(path: Path, root: Path, include_evidence: bool) -> bool:
    if any(part in EXCLUDED_DIR_NAMES for part in path.parts):
        return True
    prefixes = EXCLUDED_PREFIXES if not include_evidence else tuple(
        p for p in EXCLUDED_PREFIXES if p != "docs/LOCAL_VALIDATION_EVIDENCE/"
    )
    path_rel = rel(path, root)
    return any(path_rel.startswith(prefix) for prefix in prefixes)


def iter_markdown(root: Path, scopes: list[str], include_evidence: bool) -> list[Path]:
    files: dict[str, Path] = {}
    for scope in scopes:
        base = (root / scope).resolve()
        if not base.exists():
            continue
        candidates = [base] if base.is_file() else base.rglob("*.md")
        for path in candidates:
            if path.is_file() and path.suffix.lower() == ".md" and not should_skip(path, root, include_evidence):
                files[rel(path, root)] = path
    return [files[key] for key in sorted(files)]


def render_markdown(report: dict[str, object]) -> str:
    lines = [
        "# Markdown line limit validation",
        "",
        f"- Kind: `{report['kind']}`",
        f"- Passed: `{report['passed']}`",
        f"- Max lines: `{report['max_lines']}`",
        f"- Checked files: `{report['checked_file_count']}`",
        f"- Violation count: `{report['violation_count']}`",
        "",
    ]
    violations = report.get("violations") or []
    if violations:
        lines.extend(["## Violations", ""])
        for item in violations:  # type: ignore[assignment]
            lines.append(f"- `{item['path']}` lines=`{item['line_count']}`")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--max-lines", type=int, default=DEFAULT_MAX_LINES)
    parser.add_argument("--scope", action="append", default=[])
    parser.add_argument("--include-evidence", action="store_true")
    parser.add_argument("--output", default="output/validation/markdown_line_limit_validation.json")
    parser.add_argument("--markdown-output", default="output/validation/markdown_line_limit_validation.md")
    args = parser.parse_args()

    root = find_repo_root(Path(args.repo_root))
    scopes = args.scope or list(DEFAULT_SCOPES)
    files = iter_markdown(root, scopes, args.include_evidence)
    checked = []
    violations = []
    for path in files:
        line_count = len(path.read_text(encoding="utf-8-sig", errors="replace").splitlines())
        item = {"path": rel(path, root), "line_count": line_count}
        checked.append(item)
        if line_count > args.max_lines:
            violations.append(item)

    report = {
        "kind": "ia_carmine_markdown_line_limit_validation",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "passed": not violations,
        "max_lines": args.max_lines,
        "scopes": scopes,
        "include_evidence": bool(args.include_evidence),
        "checked_file_count": len(checked),
        "violation_count": len(violations),
        "violations": violations,
    }
    out = root / args.output
    md = root / args.markdown_output
    out.parent.mkdir(parents=True, exist_ok=True)
    md.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    md.write_text(render_markdown(report), encoding="utf-8")
    print(f"[OK] Checked={len(checked)} violations={len(violations)}")
    print(f"[OK] Report: {rel(out, root)}")
    print(f"[OK] Markdown report: {rel(md, root)}")
    return 0 if not violations else 2


if __name__ == "__main__":
    raise SystemExit(main())
