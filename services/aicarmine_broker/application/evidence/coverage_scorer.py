"""Diagnostic evidence coverage scoring for planner contracts."""

from __future__ import annotations

from typing import Any


DOC_CONFIG_SUFFIXES = (
    ".md",
    ".toml",
    ".json",
    ".yaml",
    ".yml",
    ".ini",
    ".cfg",
)


def _clamp_score(value: float) -> float:
    return max(0.0, min(1.0, round(value, 2)))


def _verified_paths(contract: dict[str, Any]) -> set[str]:
    rows = contract.get("verified_content_reads") if isinstance(contract.get("verified_content_reads"), list) else []
    return {
        str(row.get("path") or "")
        for row in rows
        if isinstance(row, dict) and str(row.get("path") or "")
    }


def score_evidence_coverage(contract: dict[str, Any]) -> dict[str, Any]:
    target_kind = str(contract.get("target_kind") or "")
    verified_paths = _verified_paths(contract)
    missing = [
        str(path)
        for path in contract.get("missing_full_content_reads") or []
        if str(path)
    ]
    weaknesses: list[str] = []
    score = 0.0
    reason = "No coverage rules matched."

    code_contract = contract.get("code_product_contract") if isinstance(contract.get("code_product_contract"), dict) else {}
    if code_contract.get("required"):
        target = str(code_contract.get("candidate_target_file") or code_contract.get("latest_target_file") or "")
        if target and target in verified_paths:
            score += 0.3
        else:
            weaknesses.append("code_product_target_not_read")
        if code_contract.get("build_state_status") or code_contract.get("build_state_payload_loaded"):
            score += 0.2
        else:
            weaknesses.append("code_product_build_state_missing")
        if code_contract.get("latest_payload_complete"):
            score += 0.5
        else:
            weaknesses.append("code_product_payload_incomplete")
        reason = "code product coverage scored from target read, build-state progress and complete proposal payload"
    elif target_kind == "file":
        target = str(contract.get("resolved_goal_file") or "")
        if target and target in verified_paths:
            score = 0.95
            reason = "target file has direct verified repo_read content"
        else:
            score = 0.25
            weaknesses.append("missing_target_file_read")
            if target:
                missing.append(target)
            reason = "target file read is missing"
    elif target_kind == "directory" or contract.get("resolved_goal_scope"):
        if contract.get("scoped_concrete_read_required"):
            score += 0.3
        else:
            weaknesses.append("scope_not_listed")
        required = int(contract.get("scoped_concrete_read_required") or 0)
        count = int(contract.get("scoped_concrete_read_count") or 0)
        if required and count >= required:
            score += 0.5
        else:
            weaknesses.append("insufficient_scope_reads")
        if not missing:
            score += 0.2
        reason = "directory coverage scored from scoped listing and scoped concrete reads"
    elif contract.get("repo_concrete_read_required") is not None:
        rows = contract.get("verified_content_reads") if isinstance(contract.get("verified_content_reads"), list) else []
        doc_reads = [
            row for row in rows
            if isinstance(row, dict)
            and str(row.get("path") or "").lower().endswith(DOC_CONFIG_SUFFIXES)
        ]
        if contract.get("core_discovery_status") or contract.get("ranked_core_candidate_dirs"):
            score += 0.2
        else:
            weaknesses.append("root_surface_or_core_discovery_weak")
        if len(doc_reads) >= 3:
            score += 0.25
        else:
            weaknesses.append("less_than_three_doc_config_reads")
        if contract.get("repo_concrete_read_count"):
            score += 0.2
        else:
            weaknesses.append("no_meaningful_non_root_reads")
        required = int(contract.get("repo_concrete_read_required") or 0)
        total_reads = int(contract.get("verified_content_read_count") or 0)
        if required and total_reads >= required:
            score += 0.25
        else:
            weaknesses.append("verified_content_read_count_below_required")
        if not missing:
            score += 0.1
        reason = "repository coverage scored from core discovery, docs/config reads and concrete content reads"
    else:
        score = 0.5 if verified_paths else 0.0
        if not verified_paths:
            weaknesses.append("no_verified_content_reads")
        reason = "generic coverage scored from verified content presence"

    score = _clamp_score(score)
    return {
        "schema": "evidence_coverage_score.v1",
        "coverage_score": score,
        "coverage_score_ready": score >= 0.9,
        "final_ready": bool(contract.get("planner_may_choose_final")),
        "final_ready_source": "finalization_contract",
        "missing": sorted(set(missing)),
        "weaknesses": weaknesses,
        "reason": reason,
        "diagnostic_only": True,
        "must_not_override_finalization_contract": True,
    }
