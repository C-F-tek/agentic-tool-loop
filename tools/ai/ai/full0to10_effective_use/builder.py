"""Build Full0To10 effective use optimization artifacts."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .constants import (
    DEFAULT_DB,
    OPTIMIZATION_NAME,
    PROVIDER_HARDENING_NAME,
    QUALITY_PRODUCT_NAME,
    TELEMETRY_NAME,
    SAFETY_FLAGS,
)
from .memory_product import build_memory_product
from .optimizer import build_optimization
from .paths import ensure_dir, repo_relative, resolve_repo_path
from .provider_contracts import build_provider_contracts
from .render import render_summary_markdown
from .tool_telemetry import build_tool_telemetry, event


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def build_effective_use_optimization(
    repo_root: Path,
    output_dir: Path,
    request: str,
    db_path: Path | None,
    no_external_probes: bool,
    timeout_seconds: int,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    output_dir = ensure_dir(output_dir)
    memory_db = db_path or resolve_repo_path(repo_root, DEFAULT_DB)
    events: list[dict[str, Any]] = []

    provider_contracts = build_provider_contracts(repo_root, timeout_seconds=timeout_seconds, external=not no_external_probes)
    events.append(event("hardware_capability", "build_provider_contracts", provider_contracts["passed"]))

    optimization = build_optimization(provider_contracts, request)
    events.append(event("optimizer", "build_optimization", optimization["passed"]))

    memory_report, product_md, seed_reports = build_memory_product(
        repo_root,
        memory_db,
        request,
        provider_contracts,
        optimization,
    )
    events.append(event("sqlite_memory", "seed_context", all(item.get("passed") for item in seed_reports)))
    events.append(event("sqlite_memory", "search_context", memory_report["search"].get("passed", False)))
    events.append(event("quality_product", "render_markdown", bool(product_md.strip())))

    telemetry = build_tool_telemetry(events)

    provider_path = output_dir / PROVIDER_HARDENING_NAME
    optimization_path = output_dir / OPTIMIZATION_NAME
    telemetry_path = output_dir / TELEMETRY_NAME
    product_path = output_dir / QUALITY_PRODUCT_NAME
    summary_path = output_dir / "full0to10_effective_use_summary.json"
    summary_md_path = output_dir / "full0to10_effective_use_summary.md"

    write_json(provider_path, provider_contracts)
    write_json(optimization_path, optimization)
    write_json(telemetry_path, telemetry)
    product_path.write_text(product_md, encoding="utf-8")

    report = {
        "kind": "full0to10_effective_use_optimization_summary",
        "passed": provider_contracts["passed"] and optimization["passed"] and telemetry["passed"] and memory_report["passed"],
        "request": request,
        "outputs": {
            "quality_product": repo_relative(product_path, repo_root),
            "provider_hardening": repo_relative(provider_path, repo_root),
            "optimization": repo_relative(optimization_path, repo_root),
            "tool_telemetry": repo_relative(telemetry_path, repo_root),
            "memory_db": repo_relative(memory_db, repo_root),
        },
        "provider_contracts": provider_contracts,
        "optimization": optimization,
        "memory_report": memory_report,
        "tool_telemetry": telemetry,
        "errors": [],
        "warnings": optimization["warnings"],
    }
    report.update(SAFETY_FLAGS)
    write_json(summary_path, report)
    summary_md_path.write_text(render_summary_markdown(report), encoding="utf-8")
    report["outputs"]["summary"] = repo_relative(summary_path, repo_root)
    report["outputs"]["summary_markdown"] = repo_relative(summary_md_path, repo_root)
    return report
