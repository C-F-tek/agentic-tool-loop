#!/usr/bin/env python3
"""Validate full-context golden-path proposal coverage.

This validator is intentionally stricter than check_repository_change_proposals.py.
A repository proposal report can be structurally valid while still failing the
full-context golden-path task because it does not include the required strategic
proposal families P1-P6.

The validator is report-only: it reads a proposal JSON file and writes a compact
validation report. It performs no provider execution and no source writes except
the optional validation report output.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

try:
    from report_utils import resolve_output_path, write_json_report
except ImportError:
    from Tools.validation.report_utils import resolve_output_path, write_json_report  # type: ignore

EXPECTED_KIND = "repository_change_proposals"
EXPECTED_APPLY_MODE = "manual_review_only"
REPORT_KIND = "full_context_golden_proposal_contract"

REQUIRED_FAMILIES = (
    {
        "id": "P1",
        "name": "adapter_manifest_validator",
        "description": "adapter manifest validator",
        "terms": ("adapter manifest", "manifest validator", "adapter validator", "enrichment output consistency"),
    },
    {
        "id": "P2",
        "name": "reusable_enrichment_plan_helper",
        "description": "reusable enrichment-plan helper",
        "terms": ("enrichment plan", "enrichment-plan", "helper", "core helper", "reusable"),
    },
    {
        "id": "P3",
        "name": "full_context_golden_docs_contract",
        "description": "full-context golden path docs contract",
        "terms": ("full-context", "golden path", "docs", "documentation contract", "local_ai_workflow"),
    },
    {
        "id": "P4",
        "name": "wrapper_preset_flag",
        "description": "optional wrapper preset flag",
        "terms": ("preset", "wrapper flag", "fullcontextgoldenpath", "full-context preset", "flag"),
    },
    {
        "id": "P5",
        "name": "selected_chunks_standard_validation_block",
        "description": "selected-chunks evidence in standard validation block",
        "terms": ("selected chunks", "selected-chunks", "selected semantic", "standard validation", "evidence block"),
    },
    {
        "id": "P6",
        "name": "npu_knowledge_broker",
        "description": "NPU knowledge-broker / context-oracle prototype",
        "terms": ("npu", "knowledge broker", "knowledge-broker", "context oracle", "context-oracle", "retrieval", "ranking"),
    },
)

FORBIDDEN_TARGET_PREFIXES = (
    "indexAI/",
    "Scripting/ready_to_jazz_wow_youtube_profiles_audio_sync/",
    "output/",
)
FORBIDDEN_TARGET_EXACT = {"Scripting/shared/blender_compat.py"}
FORBIDDEN_TARGET_FRAGMENTS = ("full_analysis", "analysis_full")


def normalize_path(value: Any) -> str:
    return str(value or "").strip().replace("\\", "/")


def repo_relative(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root).as_posix()
    except ValueError:
        return path.as_posix()


def read_json_object(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
    except OSError as exc:
        return None, str(exc)
    if not isinstance(data, dict):
        return None, f"expected JSON object, got {type(data).__name__}"
    return data, None


def text_blob(item: dict[str, Any]) -> str:
    parts: list[str] = []
    for key, value in item.items():
        if isinstance(value, (str, int, float, bool)):
            parts.append(str(value))
        elif isinstance(value, list):
            parts.extend(str(part) for part in value)
        elif isinstance(value, dict):
            parts.append(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return "\n".join(parts).lower()


def proposal_id(item: dict[str, Any], index: int) -> str:
    return str(item.get("id") or item.get("proposal_id") or f"proposals[{index}]")


def get_target_files(item: dict[str, Any]) -> list[str]:
    value = item.get("target_files")
    if isinstance(value, list):
        return [normalize_path(path) for path in value if str(path).strip()]
    return []


def target_path_errors(path: str) -> list[str]:
    errors: list[str] = []
    normalized = normalize_path(path)
    if not normalized:
        errors.append("empty target path")
        return errors
    if Path(normalized).is_absolute():
        errors.append(f"absolute target path is not allowed: {normalized}")
    if normalized in FORBIDDEN_TARGET_EXACT:
        errors.append(f"forbidden exact target path: {normalized}")
    if any(normalized.startswith(prefix) for prefix in FORBIDDEN_TARGET_PREFIXES):
        errors.append(f"forbidden target prefix: {normalized}")
    lower = normalized.lower()
    if any(fragment in lower for fragment in FORBIDDEN_TARGET_FRAGMENTS) and lower.endswith(".json"):
        errors.append(f"forbidden full-analysis JSON target: {normalized}")
    return errors


def is_manual_review_only(item: dict[str, Any]) -> bool:
    values = [
        item.get("apply_mode"),
        item.get("write_policy"),
        item.get("apply_allowed_now"),
    ]
    if item.get("apply_mode") not in (EXPECTED_APPLY_MODE, None):
        return False
    if item.get("write_policy") not in (EXPECTED_APPLY_MODE, None):
        return False
    if item.get("apply_allowed_now") not in (False, None):
        return False
    if item.get("requires_manual_review") not in (True, None):
        return False
    return True


def family_matches(family: dict[str, Any], item: dict[str, Any]) -> bool:
    blob = text_blob(item)
    proposal_key = proposal_id(item, -1).lower()
    if family["id"].lower() in proposal_key:
        return True
    if family["name"].replace("_", " ") in blob:
        return True
    return any(term.lower() in blob for term in family["terms"])


def validate_proposal_shape(item: Any, index: int) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(item, dict):
        return {"id": f"proposals[{index}]", "ok": False, "errors": ["proposal must be an object"], "warnings": []}

    pid = proposal_id(item, index)
    title = str(item.get("title") or "")
    change_type = str(item.get("change_type") or "")
    targets = get_target_files(item)

    if not title:
        errors.append("title is required")
    if not change_type:
        errors.append("change_type is required")
    if not targets:
        errors.append("target_files must contain at least one concrete file")
    for target in targets:
        errors.extend(target_path_errors(target))
    if not is_manual_review_only(item):
        errors.append("proposal must be manual-review-only with apply_allowed_now false")
    if item.get("requires_provider_execution") not in (False, None):
        warnings.append("proposal requires provider execution; prefer false for contract/prototype proposals")

    return {
        "id": pid,
        "title": title,
        "change_type": change_type,
        "target_files": targets,
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
    }


def validate_golden_proposals(repo_root: Path, proposal_path: Path, min_proposals: int) -> dict[str, Any]:
    rel_path = repo_relative(proposal_path, repo_root)
    errors: list[str] = []
    warnings: list[str] = []
    data, parse_error = read_json_object(proposal_path)
    if parse_error or data is None:
        return {
            "path": rel_path,
            "exists": proposal_path.exists(),
            "json_ok": False,
            "ok": False,
            "errors": [parse_error or "unknown JSON parse error"],
            "warnings": warnings,
            "proposal_count": 0,
            "family_checks": [],
            "proposal_checks": [],
        }

    if data.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    if data.get("kind") != EXPECTED_KIND:
        errors.append(f"kind must be {EXPECTED_KIND}")
    if data.get("passed") is not True:
        errors.append("root passed must be true")
    if data.get("apply_mode") not in (EXPECTED_APPLY_MODE, None):
        errors.append("root apply_mode must be manual_review_only when present")
    if data.get("provider_execution_performed") not in (False, None):
        errors.append("root provider_execution_performed must be false or omitted")

    proposals = data.get("proposals")
    if not isinstance(proposals, list):
        errors.append("proposals must be a list")
        proposals = []
    proposal_count = len(proposals)
    if proposal_count < min_proposals:
        errors.append(f"proposal_count {proposal_count} is below required minimum {min_proposals}")

    proposal_checks = [validate_proposal_shape(item, index) for index, item in enumerate(proposals)]
    for check in proposal_checks:
        for error in check.get("errors", []):
            errors.append(f"{check.get('id')}: {error}")
        for warning in check.get("warnings", []):
            warnings.append(f"{check.get('id')}: {warning}")

    family_checks: list[dict[str, Any]] = []
    for family in REQUIRED_FAMILIES:
        matching = [proposal_id(item, index) for index, item in enumerate(proposals) if isinstance(item, dict) and family_matches(family, item)]
        ok = bool(matching)
        family_checks.append({
            "id": family["id"],
            "name": family["name"],
            "description": family["description"],
            "ok": ok,
            "matched_proposals": matching,
        })
        if not ok:
            errors.append(f"missing required golden proposal family {family['id']}: {family['description']}")

    return {
        "path": rel_path,
        "exists": True,
        "json_ok": True,
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "proposal_count": proposal_count,
        "required_family_count": len(REQUIRED_FAMILIES),
        "family_checks": family_checks,
        "proposal_checks": proposal_checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--proposal", required=True)
    parser.add_argument("--output")
    parser.add_argument("--min-proposals", type=int, default=6)
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    proposal_path = Path(args.proposal)
    if not proposal_path.is_absolute():
        proposal_path = (repo_root / proposal_path).resolve()

    result = validate_golden_proposals(repo_root, proposal_path, args.min_proposals)
    errors = [f"{result['path']}: {error}" for error in result.get("errors", [])]
    warnings = [f"{result['path']}: {warning}" for warning in result.get("warnings", [])]
    report = {
        "schema_version": 1,
        "kind": REPORT_KIND,
        "repo_root": repo_root.as_posix(),
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "results": [result],
    }
    output = resolve_output_path(repo_root, args.output) if args.output else None
    print(write_json_report(report, output), end="")
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
