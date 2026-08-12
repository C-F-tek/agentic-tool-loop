#!/usr/bin/env python3
"""Build a repository-wide Markdown inventory for IA-Carmine documentation pruning.

The script is report-only. It does not rewrite source files and does not execute
providers, Blender, GPU, NPU or external commands.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


IGNORED_DIR_NAMES = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    "output",
    "renders",
}

CANONICAL_INDEX_FILES = [
    "AGENTS.md",
    "README.md",
    "WORKFLOW.md",
    "docs/README.md",
    "docs/LOCAL_AI_TASKS/README.md",
    "docs/MODULE_MAP.md",
    "Tools/validation/README.md",
    "Tools/npu/pipeline/README.md",
]

ROOT_COMMUNITY_DOCS = {
    "CODE_OF_CONDUCT.md",
    "CONTRIBUTING.md",
    "LICENSE.md",
    "SECURITY.md",
    "SUPPORT.md",
}

ROOT_POLICY_DOCS = {
    "AGENTS.md",
    "README.md",
    "WORKFLOW.md",
    "CHANGELOG.md",
    "AI_PATCH_BUNDLE_TECHNICAL_GOTCHAS.md",
}

EVIDENCE_PREFIX = "docs/LOCAL_VALIDATION_EVIDENCE/"
TASK_PREFIX = "docs/LOCAL_AI_TASKS/"
EXECUTION_PLAN_PREFIX = "docs/EXECUTION_PLANS/"
GENERATED_INDEX_PREFIXES = (
    "indexAI/",
    "Tools/npu/npu_code_",
    "Tools/npu/npu_music_chunks/",
)
GENERATED_NPU_DOCS = {
    "Tools/npu/generated_implementation_notes.md",
    "Tools/npu/npu_music_context.md",
    "Tools/npu/ollama_music_insights.md",
}
GITHUB_TEMPLATE_PREFIXES = (
    ".github/ISSUE_TEMPLATE/",
)
GITHUB_TEMPLATE_FILES = {
    ".github/PULL_REQUEST_TEMPLATE.md",
}


def repo_relative(path: Path, repo_root: Path) -> str:
    return path.resolve().relative_to(repo_root.resolve()).as_posix()


def is_under_ignored_dir(path: Path, repo_root: Path) -> bool:
    rel_parts = path.resolve().relative_to(repo_root.resolve()).parts
    return any(part in IGNORED_DIR_NAMES for part in rel_parts)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="replace")


def first_heading(text: str) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip() or None
    return None


def is_github_template(rel_path: str) -> bool:
    return rel_path in GITHUB_TEMPLATE_FILES or any(rel_path.startswith(prefix) for prefix in GITHUB_TEMPLATE_PREFIXES)


def classify_markdown(rel_path: str) -> str:
    if rel_path in ROOT_POLICY_DOCS:
        return "root_policy_or_entrypoint"
    if rel_path in ROOT_COMMUNITY_DOCS:
        return "root_community_doc"
    if is_github_template(rel_path):
        return "github_template"
    if rel_path == ".aider.chat.history.md":
        return "local_tool_history"
    if rel_path.startswith(EVIDENCE_PREFIX):
        return "compact_evidence"
    if rel_path.startswith(TASK_PREFIX):
        return "local_ai_task_entrypoint"
    if rel_path.startswith(EXECUTION_PLAN_PREFIX):
        return "execution_plan"
    if rel_path in GENERATED_NPU_DOCS or any(rel_path.startswith(prefix) for prefix in GENERATED_INDEX_PREFIXES):
        return "generated_or_index_context"
    if rel_path.endswith("/README.md") and rel_path.startswith("Tools/"):
        return "tool_readme"
    if rel_path.startswith("Tools/npu/"):
        return "npu_tool_context_doc"
    if rel_path.startswith("Scripting/"):
        return "blender_application_doc"
    if rel_path.startswith("docs/"):
        return "stable_project_doc"
    if rel_path.startswith("Tools/"):
        return "tool_or_runtime_doc"
    return "misc_markdown"


def lifecycle_for(category: str, rel_path: str) -> str:
    if rel_path in {"AGENTS.md", "README.md", "WORKFLOW.md", "docs/README.md", "docs/LOCAL_AI_TASKS/README.md"}:
        return "canonical_entrypoint"
    if category in {"root_community_doc", "github_template"}:
        return "repository_community_control"
    if category == "local_tool_history":
        return "local_history_delete_candidate"
    if category == "compact_evidence":
        return "evidence_snapshot"
    if category == "local_ai_task_entrypoint":
        return "current_or_historical_task"
    if category == "execution_plan":
        return "state_record"
    if category == "generated_or_index_context":
        return "generated_context"
    if category == "npu_tool_context_doc":
        return "tool_context_review"
    if category in {"stable_project_doc", "root_policy_or_entrypoint", "tool_readme"}:
        return "maintained_source_doc"
    return "review_needed"


def build_index_text(repo_root: Path) -> dict[str, str]:
    texts: dict[str, str] = {}
    for rel in CANONICAL_INDEX_FILES:
        path = repo_root / rel
        if path.exists() and path.is_file():
            texts[rel] = read_text(path)
    return texts


def indexed_by(rel_path: str, index_texts: dict[str, str]) -> list[str]:
    hits: list[str] = []
    basename = Path(rel_path).name
    for index_path, text in index_texts.items():
        if rel_path in text or f"`{rel_path}`" in text or basename in text:
            hits.append(index_path)
    return hits


def collect_markdown(repo_root: Path) -> list[Path]:
    files: list[Path] = []
    for path in repo_root.rglob("*.md"):
        if path.is_file() and not is_under_ignored_dir(path, repo_root):
            files.append(path)
    return sorted(files, key=lambda item: repo_relative(item, repo_root).lower())


def is_prune_candidate(category: str, lifecycle: str, index_hits: list[str]) -> bool:
    if index_hits:
        return False
    return lifecycle == "local_history_delete_candidate" or category == "misc_markdown"


def requires_index_review(category: str, index_hits: list[str]) -> bool:
    if index_hits:
        return False
    return category in {"stable_project_doc", "tool_readme", "local_ai_task_entrypoint", "npu_tool_context_doc"}


def inventory_item(path: Path, repo_root: Path, index_texts: dict[str, str]) -> dict[str, Any]:
    rel = repo_relative(path, repo_root)
    text = read_text(path)
    category = classify_markdown(rel)
    lifecycle = lifecycle_for(category, rel)
    index_hits = indexed_by(rel, index_texts)
    return {
        "path": rel,
        "category": category,
        "lifecycle": lifecycle,
        "heading": first_heading(text),
        "lines": len(text.splitlines()),
        "size_bytes": path.stat().st_size,
        "indexed_by": index_hits,
        "indexed": bool(index_hits) or rel in CANONICAL_INDEX_FILES,
        "prune_candidate": is_prune_candidate(category, lifecycle, index_hits),
        "requires_index_review": requires_index_review(category, index_hits),
    }


def build_report(repo_root: Path) -> dict[str, Any]:
    index_texts = build_index_text(repo_root)
    items = [inventory_item(path, repo_root, index_texts) for path in collect_markdown(repo_root)]

    by_category: dict[str, int] = {}
    by_lifecycle: dict[str, int] = {}
    for item in items:
        by_category[item["category"]] = by_category.get(item["category"], 0) + 1
        by_lifecycle[item["lifecycle"]] = by_lifecycle.get(item["lifecycle"], 0) + 1

    missing_index = [item for item in items if item["requires_index_review"]]
    prune_candidates = [item for item in items if item["prune_candidate"]]

    return {
        "schema_version": 1,
        "kind": "markdown_inventory",
        "repo_root": str(repo_root),
        "passed": True,
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": False,
        "markdown_count": len(items),
        "indexed_source_files": sorted(index_texts),
        "category_counts": by_category,
        "lifecycle_counts": by_lifecycle,
        "missing_index_count": len(missing_index),
        "prune_candidate_count": len(prune_candidates),
        "missing_index": missing_index,
        "prune_candidates": prune_candidates,
        "items": items,
        "errors": [],
        "warnings": [
            "This inventory is evidence for review. It does not delete or rewrite Markdown files.",
            "A missing index reference is not automatically obsolete; it means the file needs owner/lifecycle review.",
            "GitHub templates and root community docs are repository controls, not prune candidates.",
        ],
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Markdown Documentation Inventory")
    lines.append("")
    lines.append(f"- Kind: `{report['kind']}`")
    lines.append(f"- Markdown files: `{report['markdown_count']}`")
    lines.append(f"- Missing index review count: `{report['missing_index_count']}`")
    lines.append(f"- Prune candidate count: `{report['prune_candidate_count']}`")
    lines.append("- Provider execution performed: `False`")
    lines.append("- Patch application performed: `False`")
    lines.append("")
    lines.append("## Category counts")
    lines.append("")
    lines.append("| Category | Count |")
    lines.append("|---|---:|")
    for category, count in sorted(report["category_counts"].items()):
        lines.append(f"| `{category}` | {count} |")
    lines.append("")
    lines.append("## Missing index review")
    lines.append("")
    if report["missing_index"]:
        lines.append("| Path | Category | Lifecycle | Lines | Heading |")
        lines.append("|---|---|---|---:|---|")
        for item in report["missing_index"]:
            heading = (item.get("heading") or "").replace("|", "\\|")
            lines.append(
                f"| `{item['path']}` | `{item['category']}` | `{item['lifecycle']}` | "
                f"{item['lines']} | {heading} |"
            )
    else:
        lines.append("No missing index review candidates.")
    lines.append("")
    lines.append("## Prune candidates")
    lines.append("")
    if report["prune_candidates"]:
        lines.append("| Path | Category | Lifecycle | Lines | Heading |")
        lines.append("|---|---|---|---:|---|")
        for item in report["prune_candidates"]:
            heading = (item.get("heading") or "").replace("|", "\\|")
            lines.append(
                f"| `{item['path']}` | `{item['category']}` | `{item['lifecycle']}` | "
                f"{item['lines']} | {heading} |"
            )
    else:
        lines.append("No prune candidates.")
    lines.append("")
    lines.append("## Full Markdown map")
    lines.append("")
    lines.append("| Path | Category | Lifecycle | Indexed | Lines |")
    lines.append("|---|---|---|---|---:|")
    for item in report["items"]:
        lines.append(
            f"| `{item['path']}` | `{item['category']}` | `{item['lifecycle']}` | "
            f"`{item['indexed']}` | {item['lines']} |"
        )
    lines.append("")
    return "\n".join(lines)


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a report-only Markdown documentation inventory.")
    parser.add_argument("--repo-root", default=".", help="Repository root.")
    parser.add_argument("--output", default="output/validation/markdown_inventory.json", help="JSON report output.")
    parser.add_argument("--markdown-output", default=None, help="Optional Markdown report output.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    report = build_report(repo_root)
    write_json(Path(args.output), report)
    if args.markdown_output:
        write_text(Path(args.markdown_output), render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
