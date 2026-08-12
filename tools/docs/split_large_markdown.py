#!/usr/bin/env python3
"""Split large Markdown files into bounded, navigable Markdown folders.

Default policy:
- scan source documentation only;
- keep every processed Markdown file at or below --max-lines;
- preserve the original file path as a short index/stub;
- move long content into a sibling folder with part files;
- write reports under output/validation by default;
- never commit, stage, delete git history, or touch database/runtime artifacts.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

MARKER_INDEX = "<!-- IA-CARMINE-MD-SPLIT: index -->"
MARKER_PART = "<!-- IA-CARMINE-MD-SPLIT: part -->"
MARKER_MANIFEST = "_ia_carmine_md_split_manifest.json"
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
SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")
MD_LINK_RE = re.compile(
    r"(?P<prefix>!?\[[^\]]*\]\()(?P<url><[^>]+>|[^)\s]+)(?P<title>\s+\"[^\"]*\")?(?P<suffix>\))"
)


@dataclass(frozen=True)
class MarkdownFile:
    path: Path
    rel: str
    line_count: int


def repo_relative(path: Path, repo_root: Path) -> str:
    return path.resolve().relative_to(repo_root.resolve()).as_posix()


def find_repo_root(start: Path) -> Path:
    current = start.resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate
    raise SystemExit(f"Cannot find repository root from {start}")


def git_status(repo_root: Path) -> list[str]:
    proc = subprocess.run(
        ["git", "status", "--short"],
        cwd=repo_root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        return [f"git status failed: {proc.stderr.strip()}"]
    return [line for line in proc.stdout.splitlines() if line.strip()]


def is_under_excluded_prefix(path: Path, repo_root: Path, include_evidence: bool) -> bool:
    rel = repo_relative(path, repo_root)
    prefixes = EXCLUDED_PREFIXES if not include_evidence else tuple(
        p for p in EXCLUDED_PREFIXES if p != "docs/LOCAL_VALIDATION_EVIDENCE/"
    )
    return any(rel.startswith(prefix) for prefix in prefixes)


def should_skip_path(path: Path, repo_root: Path, include_evidence: bool) -> bool:
    if any(part in EXCLUDED_DIR_NAMES for part in path.parts):
        return True
    if is_under_excluded_prefix(path, repo_root, include_evidence):
        return True
    return False


def iter_markdown_files(repo_root: Path, scopes: Iterable[str], include_evidence: bool) -> list[MarkdownFile]:
    found: dict[str, MarkdownFile] = {}
    for scope in scopes:
        base = (repo_root / scope).resolve()
        if not base.exists():
            continue
        candidates = [base] if base.is_file() else sorted(base.rglob("*.md"))
        for path in candidates:
            if path.suffix.lower() != ".md" or not path.is_file():
                continue
            if should_skip_path(path, repo_root, include_evidence):
                continue
            text = path.read_text(encoding="utf-8-sig", errors="replace")
            rel = repo_relative(path, repo_root)
            found[rel] = MarkdownFile(path=path, rel=rel, line_count=len(text.splitlines()))
    return [found[key] for key in sorted(found)]


def is_generated_index(lines: list[str]) -> bool:
    return any(MARKER_INDEX in line for line in lines[:10])


def fence_transition(line: str, current: str | None) -> str | None:
    stripped = line.strip()
    if stripped.startswith("```"):
        return None if current is not None else stripped[3:].strip() or "text"
    return current


def split_force(lines: list[str], budget: int) -> list[list[str]]:
    if budget < 40:
        raise ValueError("budget too small for Markdown chunking")
    chunks: list[list[str]] = []
    index = 0
    while index < len(lines):
        chunk: list[str] = []
        fence: str | None = None
        while index < len(lines) and len(chunk) < budget:
            line = lines[index]
            next_fence = fence_transition(line, fence)
            fence = next_fence
            chunk.append(line)
            index += 1
        if fence is not None:
            chunk.append("```")
            if index < len(lines):
                lines.insert(index, f"```{fence}")
        chunks.append(chunk)
    return chunks


def split_by_headings(lines: list[str], budget: int) -> list[list[str]]:
    sections: list[list[str]] = []
    current: list[str] = []
    in_fence: str | None = None
    for line in lines:
        in_fence = fence_transition(line, in_fence)
        starts_heading = in_fence is None and line.startswith("#") and line.lstrip("#").startswith(" ")
        if starts_heading and current:
            sections.append(current)
            current = [line]
        else:
            current.append(line)
    if current:
        sections.append(current)

    chunks: list[list[str]] = []
    current_chunk: list[str] = []
    for section in sections:
        if len(section) > budget:
            if current_chunk:
                chunks.append(current_chunk)
                current_chunk = []
            chunks.extend(split_force(list(section), budget))
            continue
        if current_chunk and len(current_chunk) + len(section) > budget:
            chunks.append(current_chunk)
            current_chunk = list(section)
        else:
            current_chunk.extend(section)
    if current_chunk:
        chunks.append(current_chunk)
    return chunks


def rewrite_relative_links_for_child_dir(lines: list[str]) -> list[str]:
    rewritten: list[str] = []
    in_fence: str | None = None
    for line in lines:
        in_fence = fence_transition(line, in_fence)
        if in_fence is not None:
            rewritten.append(line)
            continue

        def replace(match: re.Match[str]) -> str:
            raw_url = match.group("url")
            bracketed = raw_url.startswith("<") and raw_url.endswith(">")
            url = raw_url[1:-1] if bracketed else raw_url
            if (
                not url
                or url.startswith("#")
                or url.startswith("/")
                or SCHEME_RE.match(url)
            ):
                return match.group(0)
            new_url = "../" + url
            if bracketed:
                new_url = f"<{new_url}>"
            return f"{match.group('prefix')}{new_url}{match.group('title') or ''}{match.group('suffix')}"

        rewritten.append(MD_LINK_RE.sub(replace, line))
    return rewritten


def choose_target_dir(path: Path) -> Path:
    preferred = path.parent / path.stem
    if not preferred.exists() or (preferred / MARKER_MANIFEST).exists():
        return preferred
    fallback = path.parent / f"{path.name}.parts"
    return fallback


def render_stub(original: MarkdownFile, target_dir: Path, part_names: list[str], max_lines: int) -> list[str]:
    dir_name = target_dir.name
    lines = [
        MARKER_INDEX,
        f"# {original.path.stem}",
        "",
        "Questo documento è stato diviso automaticamente per rispettare il budget di righe Markdown.",
        "",
        f"- File originale: `{original.rel}`",
        f"- Limite massimo configurato: `{max_lines}` righe",
        f"- Indice completo: [`{dir_name}/README.md`]({dir_name}/README.md)",
        "",
        "## Parti",
        "",
    ]
    for name in part_names:
        lines.append(f"- [`{dir_name}/{name}`]({dir_name}/{name})")
    lines.extend([
        "",
        "## Nota operativa",
        "",
        "Mantenere questo file come entrypoint stabile per non rompere i riferimenti esistenti.",
    ])
    return lines


def render_index(original: MarkdownFile, part_names: list[str], max_lines: int) -> list[str]:
    lines = [
        MARKER_INDEX,
        f"# Indice — {original.path.name}",
        "",
        f"Documento sorgente: `../{original.path.name}`",
        f"Limite massimo configurato: `{max_lines}` righe per file Markdown.",
        "",
        "## Parti",
        "",
    ]
    for idx, name in enumerate(part_names, 1):
        lines.append(f"{idx}. [`{name}`]({name})")
    lines.extend([
        "",
        "## Regola",
        "",
        "Le parti sono generate per mantenere la documentazione navigabile e compatibile con agenti AI.",
    ])
    return lines


def render_part_header(original: MarkdownFile, index: int, total: int) -> list[str]:
    nav: list[str] = [
        MARKER_PART,
        f"# {original.path.stem} — parte {index:03d} di {total:03d}",
        "",
        f"Sorgente indice: [`../{original.path.name}`](../{original.path.name})",
        "",
        "## Navigazione",
        "",
        "- [Indice](README.md)",
    ]
    if index > 1:
        nav.append(f"- [Parte precedente](part-{index - 1:03d}.md)")
    if index < total:
        nav.append(f"- [Parte successiva](part-{index + 1:03d}.md)")
    nav.append("")
    return nav


def write_text(path: Path, lines: list[str], apply: bool) -> int:
    text = "\n".join(lines).rstrip() + "\n"
    if apply:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
    return len(text.splitlines())


def split_file(item: MarkdownFile, repo_root: Path, max_lines: int, apply: bool) -> dict[str, object]:
    original_lines = item.path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    if is_generated_index(original_lines):
        return {
            "path": item.rel,
            "action": "skip_generated_index",
            "line_count": item.line_count,
        }

    content_budget = max(60, max_lines - 35)
    chunks = split_by_headings(original_lines, content_budget)
    target_dir = choose_target_dir(item.path)
    target_rel = repo_relative(target_dir, repo_root)
    part_names = [f"part-{idx:03d}.md" for idx in range(1, len(chunks) + 1)]

    if apply and target_dir.exists() and (target_dir / MARKER_MANIFEST).exists():
        for old in target_dir.glob("part-*.md"):
            old.unlink()

    part_results: list[dict[str, object]] = []
    for idx, chunk in enumerate(chunks, 1):
        part_name = part_names[idx - 1]
        body = rewrite_relative_links_for_child_dir(chunk)
        part_lines = render_part_header(item, idx, len(chunks)) + body
        if len(part_lines) > max_lines:
            overflow_budget = max(40, max_lines - len(render_part_header(item, idx, len(chunks))) - 5)
            forced = split_force(body, overflow_budget)
            if len(forced) > 1:
                body = forced[0]
                part_lines = render_part_header(item, idx, len(chunks)) + body
        line_count = write_text(target_dir / part_name, part_lines, apply)
        part_results.append({"path": f"{target_rel}/{part_name}", "lines": line_count})

    stub_lines = render_stub(item, target_dir, part_names, max_lines)
    index_lines = render_index(item, part_names, max_lines)
    stub_count = write_text(item.path, stub_lines, apply)
    index_count = write_text(target_dir / "README.md", index_lines, apply)

    manifest = {
        "kind": "ia_carmine_markdown_split_manifest",
        "source_path": item.rel,
        "target_dir": target_rel,
        "max_lines": max_lines,
        "original_line_count": item.line_count,
        "part_count": len(part_names),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "parts": part_results,
    }
    if apply:
        (target_dir / MARKER_MANIFEST).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    return {
        "path": item.rel,
        "action": "split" if apply else "would_split",
        "original_lines": item.line_count,
        "stub_lines": stub_count,
        "index_lines": index_count,
        "target_dir": target_rel,
        "part_count": len(part_names),
        "parts": part_results,
    }


def render_markdown_report(report: dict[str, object]) -> str:
    lines = [
        "# Markdown line budget report",
        "",
        f"- Kind: `{report['kind']}`",
        f"- Apply: `{report['apply']}`",
        f"- Max lines: `{report['max_lines']}`",
        f"- Scanned files: `{report['scanned_file_count']}`",
        f"- Oversized files: `{report['oversized_file_count']}`",
        f"- Split operations: `{report['split_operation_count']}`",
        "",
        "## Results",
        "",
    ]
    for item in report["results"]:  # type: ignore[index]
        lines.append(f"- `{item.get('path')}` action=`{item.get('action')}` lines=`{item.get('original_lines', item.get('line_count'))}`")
    lines.append("")
    return "\n".join(lines)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--max-lines", type=int, default=DEFAULT_MAX_LINES)
    parser.add_argument("--scope", action="append", default=[])
    parser.add_argument("--include-evidence", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--output", default="output/validation/markdown_line_budget_report.json")
    parser.add_argument("--markdown-output", default="output/validation/markdown_line_budget_report.md")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    repo_root = find_repo_root(Path(args.repo_root))
    scopes = tuple(args.scope) if args.scope else DEFAULT_SCOPES
    files = iter_markdown_files(repo_root, scopes, args.include_evidence)
    oversized = [item for item in files if item.line_count > args.max_lines]
    results = [split_file(item, repo_root, args.max_lines, args.apply) for item in oversized]
    report = {
        "kind": "ia_carmine_markdown_line_budget_split",
        "repo_root": str(repo_root),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "apply": bool(args.apply),
        "max_lines": args.max_lines,
        "scopes": list(scopes),
        "include_evidence": bool(args.include_evidence),
        "scanned_file_count": len(files),
        "oversized_file_count": len(oversized),
        "split_operation_count": len(results),
        "results": results,
        "git_status_after": git_status(repo_root) if args.apply else [],
    }
    output = repo_root / args.output
    md_output = repo_root / args.markdown_output
    output.parent.mkdir(parents=True, exist_ok=True)
    md_output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    md_output.write_text(render_markdown_report(report), encoding="utf-8")
    print(f"[OK] Report: {repo_relative(output, repo_root)}")
    print(f"[OK] Markdown report: {repo_relative(md_output, repo_root)}")
    print(f"[OK] Scanned={len(files)} oversized={len(oversized)} apply={args.apply}")
    for result in results:
        print(f"[{result.get('action')}] {result.get('path')} -> {result.get('target_dir', '')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
