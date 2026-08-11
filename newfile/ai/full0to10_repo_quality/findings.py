"""Quality findings for repo quality packet."""
from __future__ import annotations

from typing import Any


def build_findings(reads: list[dict[str, Any]], inventory: dict[str, Any]) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    py_files = [item for item in reads if item.get("kind") == "python"]
    md_files = [item for item in reads if item.get("kind") == "markdown"]

    parse_errors = [item for item in py_files if not item.get("parse_ok", True)]
    if parse_errors:
        findings.append(finding("python_parse_errors", "P1", f"{len(parse_errors)} Python files failed AST parse"))

    provider_mentions = [item for item in reads if item.get("mentions", {}).get("provider")]
    gpu_mentions = [item for item in reads if item.get("mentions", {}).get("gpu") or item.get("mentions", {}).get("npu")]
    quality_docs = [item for item in md_files if item.get("mentions", {}).get("quality")]

    if provider_mentions:
        findings.append(finding("provider_surface_visible", "INFO", f"{len(provider_mentions)} files mention provider lanes"))
    if gpu_mentions:
        findings.append(finding("gpu_npu_surface_visible", "INFO", f"{len(gpu_mentions)} files mention GPU/NPU"))
    if not quality_docs:
        findings.append(finding("quality_docs_sparse", "P2", "No scanned Markdown file strongly mentions quality"))

    findings.append(finding("inventory_scope", "INFO", f"Scanned {inventory['file_count']} files"))
    return {
        "kind": "full0to10_repo_quality_findings",
        "passed": not any(item["severity"] == "P0" for item in findings),
        "finding_count": len(findings),
        "findings": findings,
    }


def finding(code: str, severity: str, message: str) -> dict[str, str]:
    return {"code": code, "severity": severity, "message": message}
