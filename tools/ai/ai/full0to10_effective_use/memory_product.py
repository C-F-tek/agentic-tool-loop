"""SQLite FTS5 backed quality product generation."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from full0to10_sqlite_memory.db import connect
from full0to10_sqlite_memory.ingest import memory_add_text
from full0to10_sqlite_memory.manifest import build_memory_manifest
from full0to10_sqlite_memory.search import memory_search

from .constants import CONTEXT_FACTS, MEMORY_NAMESPACE
from .paths import repo_relative


def init_memory(db_path: Path) -> sqlite3.Connection:
    return connect(db_path)


def seed_effective_context(conn: sqlite3.Connection, request: str) -> list[dict[str, Any]]:
    reports: list[dict[str, Any]] = []
    reports.append(memory_add_text(conn, MEMORY_NAMESPACE, request, title="operator_request"))
    for index, fact in enumerate(CONTEXT_FACTS, start=1):
        reports.append(memory_add_text(conn, MEMORY_NAMESPACE, fact, title=f"context_fact_{index:02d}"))
    return reports


def search_effective_context(conn: sqlite3.Connection, request: str) -> dict[str, Any]:
    query_terms = "SQLite OR GPU OR NPU OR Ollama OR tool OR quality OR Full0To10"
    report = memory_search(
        conn,
        MEMORY_NAMESPACE,
        query_terms,
        limit=12,
        mode="hybrid",
        embedding_provider="hash",
        embedding_model="hash-local-v1",
    )
    if report.get("result_count", 0) == 0:
        report = memory_search(conn, MEMORY_NAMESPACE, "Full0To10", limit=12, mode="fts")
    return report


def product_markdown(
    request: str,
    db_path: Path,
    repo_root: Path,
    search_report: dict[str, Any],
    provider_contracts: dict[str, Any],
    optimization: dict[str, Any],
) -> str:
    lines = [
        "# Full0To10 effective use quality product",
        "",
        "## Request",
        "",
        request,
        "",
        "## Evidence source",
        "",
        f"- SQLite memory DB: `{repo_relative(db_path, repo_root)}`",
        f"- Namespace: `{MEMORY_NAMESPACE}`",
        f"- Search results: `{search_report.get('result_count')}`",
        "",
        "## Operational answer",
        "",
        "1. Keep SQLite FTS5 as the first local context lane for deterministic memory.",
        "2. Use runtime tools through the registry, not direct monolithic calls.",
        "3. Treat Ollama/GPU as explicit primary advisory only after quality preflight.",
        "4. Keep NPU/OpenVINO as sampled auditor/diagnostic until promotion is reviewed.",
        "5. Keep OpenVINO GPU.0 secondary unless a patch explicitly promotes it.",
        "6. Require quality stack evidence before any Full0To10 real run.",
        "",
        "## Retrieved context",
        "",
    ]
    for item in search_report.get("results", [])[:8]:
        preview = str(item.get("text_preview", "")).replace("\n", " ").strip()
        lines.append(f"- score=`{item.get('hybrid_score')}` heading=`{item.get('heading_path')}` — {preview}")
    lines.extend(
        [
            "",
            "## Provider hardening summary",
            "",
            f"- GPU/Ollama ready contract: `{provider_contracts['lanes']['ollama_gpu']['role']}`",
            f"- NPU contract: `{provider_contracts['lanes']['openvino_npu']['role']}`",
            f"- OpenVINO GPU.0 contract: `{provider_contracts['lanes']['openvino_gpu0']['role']}`",
            "",
            "## Next actions",
            "",
        ]
    )
    for action in optimization.get("next_actions", []):
        lines.append(f"- {action}")
    lines.append("")
    return "\n".join(lines)


def build_memory_product(
    repo_root: Path,
    db_path: Path,
    request: str,
    provider_contracts: dict[str, Any],
    optimization: dict[str, Any],
) -> tuple[dict[str, Any], str, list[dict[str, Any]]]:
    conn = init_memory(db_path)
    seed_reports = seed_effective_context(conn, request)
    search_report = search_effective_context(conn, request)
    manifest = build_memory_manifest(conn, db_path)
    markdown = product_markdown(request, db_path, repo_root, search_report, provider_contracts, optimization)
    memory_report = {
        "kind": "full0to10_effective_use_memory_product",
        "passed": True,
        "db_path": str(db_path),
        "namespace": MEMORY_NAMESPACE,
        "seed_count": len(seed_reports),
        "search": search_report,
        "manifest": manifest,
        "provider_execution_performed": False,
        "patch_application_performed": False,
    }
    return memory_report, markdown, seed_reports
