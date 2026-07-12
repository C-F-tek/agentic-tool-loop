#!/usr/bin/env python3
"""Build a read-only inventory of agnostic IA-Carmine tools.

This artifact describes the repository's reusable AI tooling layers: validators,
pipeline/orchestrator scripts, context builders, proposal builders, provider
probes and review helpers. It is designed to be consumed by the megalithic
repository review and by local workflow orchestration.

The tool is report-only:

- no provider execution;
- no patch application;
- no source writes except requested JSON/Markdown outputs;
- no Blender runtime execution;
- no SQLite writes.
"""

from __future__ import annotations

import argparse
import ast
import re
import warnings
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

DEFAULT_OUTPUT = "output/ai_pipeline/agent_agnostic_tool_inventory.json"
DEFAULT_MARKDOWN = "output/ai_pipeline/agent_agnostic_tool_inventory.md"
DEFAULT_ROOTS = (
    "ia_carmine",
    "Tools/validation",
    "Tools/workflow",
    "Tools/npu",
    "Tools/git",
    "Tools/repo_patch_runner",
)
CODE_EXTENSIONS = {".py", ".ps1", ".sh"}
POWERSHELL_FUNC_RE = re.compile(r"(?im)^\s*function\s+([A-Za-z0-9_-]+)\s*(?:\{|$)")
SHELL_FUNC_RE = re.compile(r"(?m)^\s*([A-Za-z_][A-Za-z0-9_]*)\s*\(\)\s*\{")


@dataclass(frozen=True)
class ToolRecord:
    """Compact metadata for one tool-like source file."""

    path: str
    extension: str
    category: str
    owner_lane: str
    consumed_by_lanes: tuple[str, ...]
    provider_execution_default: str
    apply_mode: str
    lines: int
    symbols: tuple[str, ...]
    flags: tuple[str, ...]
    guardrails: tuple[str, ...]


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


def read_text(path: Path, *, max_chars: int = 240_000) -> tuple[str, str | None]:
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError as exc:
        return "", f"{type(exc).__name__}: {exc}"
    if max_chars > 0 and len(text) > max_chars:
        return text[:max_chars], None
    return text, None


def python_symbols(text: str) -> tuple[str, ...]:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SyntaxWarning)
            tree = ast.parse(text)
    except SyntaxError:
        return tuple(
            sorted(set(re.findall(r"(?m)^\s*(?:def|class)\s+([A-Za-z_][A-Za-z0-9_]*)", text)))
        )
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.append(node.name)
    return tuple(sorted(set(names)))


def extract_symbols(path: Path, text: str) -> tuple[str, ...]:
    suffix = path.suffix.lower()
    if suffix == ".py":
        return python_symbols(text)
    if suffix == ".ps1":
        return tuple(sorted(set(POWERSHELL_FUNC_RE.findall(text))))
    if suffix == ".sh":
        return tuple(sorted(set(SHELL_FUNC_RE.findall(text))))
    return ()


def extract_flags(text: str) -> tuple[str, ...]:
    flags = set(re.findall(r"--[A-Za-z0-9][A-Za-z0-9_-]+", text))
    flags.update(re.findall(r"(?<!\w)-[A-Z][A-Za-z0-9]+", text))
    return tuple(sorted(flags)[:80])


def classify_category(rel_path: str, text: str) -> str:
    lower = rel_path.lower()
    content = text.lower()
    if (
        "/validation/" in lower
        or lower.startswith("tools/validation/")
        or lower.startswith("tools/ai/check_")
        or "contract" in lower
    ):
        return "validator"
    if (
        "run_local_ai_core_tool_activation" in lower
        or "run_local_ai_task_via_pipeline" in lower
        or "workflow" in lower
    ):
        return "orchestrator_pipeline"
    if (
        "build_agent" in lower
        or "agent_state" in lower
        or "context_pack" in lower
        or "selected_chunks" in lower
    ):
        return "agent_context_builder"
    if "proposal" in lower or "patch_spec" in lower or "pr_draft" in lower:
        return "proposal_or_review_builder"
    if "npu" in lower or "ollama" in lower or "provider" in lower or "openvino" in content:
        return "provider_probe_or_adapter"
    if "megalithic" in lower or "review" in lower:
        return "review_helper"
    if "git" in lower:
        return "git_helper"
    return "support_tool"


def classify_owner_lane(rel_path: str, text: str, category: str) -> str:
    lower = rel_path.lower()
    content = text.lower()
    if "npu" in lower or "openvino" in content:
        return "npu_explicit_provider_tool"
    if "ollama" in lower or "cuda" in content or "gpu" in content:
        return "gpu_cuda_explicit_provider_tool"
    if category == "validator":
        return "cpu_validation"
    if category == "orchestrator_pipeline":
        return "cpu_orchestration"
    if category == "agent_context_builder":
        return "cpu_context_builder"
    if category == "proposal_or_review_builder":
        return "cpu_proposal_builder"
    return "cpu_support"


def consumed_lanes(rel_path: str, text: str, owner_lane: str) -> tuple[str, ...]:
    lanes = {"cpu"}
    lower = f"{rel_path}\n{text}".lower()
    if "ollama" in lower or "gpu" in lower or "cuda" in lower:
        lanes.add("gpu_cuda")
    if "npu" in lower or "openvino" in lower:
        lanes.add("npu")
    if owner_lane.startswith("npu"):
        lanes.add("npu")
    if owner_lane.startswith("gpu"):
        lanes.add("gpu_cuda")
    return tuple(sorted(lanes))


def provider_execution_default(text: str) -> str:
    lower = text.lower()
    if (
        "--use-ollama" in lower
        or "useexplicitproviders" in lower
        or "run-npu" in lower
        or "run-ollama" in lower
    ):
        return "explicit_only"
    if "provider_execution_performed" in lower:
        return "none_or_reported"
    return "none"


def apply_mode(text: str) -> str:
    lower = text.lower()
    if "manual_review_only" in lower:
        return "manual_review_only"
    if "patch_application_performed" in lower or "report_only" in lower:
        return "report_only"
    if "git push" in lower or "commit" in lower:
        return "explicit_git_operation"
    return "not_declared"


def extract_guardrails(text: str) -> tuple[str, ...]:
    lower = text.lower()
    guardrails = []
    mapping = {
        "provider_execution_performed": "provider_execution_reported",
        "patch_application_performed": "patch_application_reported",
        "manual_review_only": "manual_review_only",
        "sqlite": "sqlite_awareness",
        "read_only": "read_only",
        "no blender": "no_blender_runtime",
        "blender_runtime": "blender_runtime_guardrail",
        "output/**": "output_artifacts_guardrail",
        "openvino gpu primary": "openvino_gpu_primary_guardrail",
        "npu advisory": "npu_advisory_guardrail",
    }
    for term, label in mapping.items():
        if term in lower:
            guardrails.append(label)
    return tuple(sorted(set(guardrails)))


def iter_tool_files(repo_root: Path, roots: Iterable[str]) -> list[Path]:
    paths: list[Path] = []
    for root_value in roots:
        root = resolve_path(repo_root, root_value)
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if path.is_file() and path.suffix.lower() in CODE_EXTENSIONS:
                paths.append(path)
    return paths


def build_records(repo_root: Path, roots: list[str]) -> tuple[list[ToolRecord], list[str]]:
    records: list[ToolRecord] = []
    warnings: list[str] = []
    for path in iter_tool_files(repo_root, roots):
        text, error = read_text(path)
        rel_path = repo_rel(path, repo_root)
        if error:
            warnings.append(f"{rel_path}: {error}")
            continue
        category = classify_category(rel_path, text)
        owner = classify_owner_lane(rel_path, text, category)
        records.append(
            ToolRecord(
                path=rel_path,
                extension=path.suffix.lower(),
                category=category,
                owner_lane=owner,
                consumed_by_lanes=consumed_lanes(rel_path, text, owner),
                provider_execution_default=provider_execution_default(text),
                apply_mode=apply_mode(text),
                lines=len(text.splitlines()),
                symbols=extract_symbols(path, text),
                flags=extract_flags(text),
                guardrails=extract_guardrails(text),
            )
        )
    return records, warnings


def summarize(records: list[ToolRecord]) -> dict[str, Any]:
    category_counts = Counter(record.category for record in records)
    owner_lane_counts = Counter(record.owner_lane for record in records)
    apply_mode_counts = Counter(record.apply_mode for record in records)
    provider_default_counts = Counter(record.provider_execution_default for record in records)
    lane_counts: Counter[str] = Counter()
    for record in records:
        for lane in record.consumed_by_lanes:
            lane_counts[lane] += 1
    return {
        "tool_count": len(records),
        "category_counts": dict(category_counts.most_common()),
        "owner_lane_counts": dict(owner_lane_counts.most_common()),
        "consumed_lane_counts": dict(lane_counts.most_common()),
        "apply_mode_counts": dict(apply_mode_counts.most_common()),
        "provider_execution_default_counts": dict(provider_default_counts.most_common()),
    }


def record_to_dict(record: ToolRecord) -> dict[str, Any]:
    return {
        "path": record.path,
        "extension": record.extension,
        "category": record.category,
        "owner_lane": record.owner_lane,
        "consumed_by_lanes": list(record.consumed_by_lanes),
        "provider_execution_default": record.provider_execution_default,
        "apply_mode": record.apply_mode,
        "lines": record.lines,
        "symbols": list(record.symbols[:60]),
        "flags": list(record.flags[:60]),
        "guardrails": list(record.guardrails),
    }


def build_inventory(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = Path(args.repo_root).resolve()
    roots = args.root or list(DEFAULT_ROOTS)
    records, warnings = build_records(repo_root, roots)
    summary = summarize(records)
    by_category: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        by_category.setdefault(record.category, []).append(record_to_dict(record))
    for category in by_category:
        by_category[category] = by_category[category][: args.max_items_per_category]

    return {
        "schema_version": 1,
        "kind": "agent_agnostic_tool_inventory",
        "generated_at": now_iso(),
        "repo_root": str(repo_root),
        "passed": True,
        "errors": [],
        "warnings": warnings,
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": False,
        "apply_mode": "report_only_read_only_inventory",
        "roots": roots,
        "summary": summary,
        "tools": [record_to_dict(record) for record in records[: args.max_tools]],
        "by_category": by_category,
        "integration": {
            "compatible_with_core_activation": True,
            "compatible_with_megalithic_review": True,
            "compatible_with_smoke_matrix": True,
            "recommended_consumers": [
                "run_local_ai_core_tool_activation.ps1",
                "run_megalithic_repo_review.py",
                "refine_megalithic_review_signals.py",
                "agnostic_ai_tools_smoke_matrix.py",
            ],
        },
        "guardrails": {
            "report_only": True,
            "provider_execution_performed": False,
            "patch_application_performed": False,
            "sqlite_db_touched": False,
            "blender_runtime_touched": False,
            "real_github_pr_created": False,
            "output_artifacts_should_not_be_committed": True,
        },
    }


def main() -> int:
    try:
        from ia_carmine._shared.agent_agnostic_tool_inventory_cli import main as cli_main
    except ModuleNotFoundError:
        from ia_carmine._shared.agent_agnostic_tool_inventory_cli import main as cli_main
    return cli_main()


if __name__ == "__main__":
    raise SystemExit(main())
