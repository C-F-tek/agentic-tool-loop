"""Canonical compact summaries for planner evidence contracts."""

from __future__ import annotations

from typing import Any

from .diagnostics import diagnostic_row, safe_text
from .payload_metadata import compact_value, counted_list, stable_json_fingerprint


_CONTRACT_LIST_KEYS = (
    "successful_repo_read_paths",
    "covered_owner_paths",
    "missing_owner_paths",
    "candidate_owner_paths",
    "read_admissible_paths",
    "validator_admissible_repo_read_paths",
    "failed_repo_read_paths",
    "failed_repo_list_files_paths",
)

_COVERAGE_LIST_KEYS = (
    "missing_owner_paths",
    "covered_owner_paths",
    "candidate_owner_paths",
)

_COMPACT_VALUE_KEYS = (
    "semantic_goal_classification",
    "finalization_contract",
    "code_product_contract",
    "core_discovery_status",
    "operational_notes",
    "candidate_next_actions",
    "validation_rejections_tail",
)


def _as_items(value: Any) -> list[Any]:
    if isinstance(value, dict) and isinstance(value.get("items"), list):
        return list(value.get("items") or [])
    return list(value) if isinstance(value, list) else []


def compact_minimum_read_coverage(coverage: Any, *, list_limit: int = 20) -> dict[str, Any]:
    if coverage in (None, "", [], {}):
        return {}
    if not isinstance(coverage, dict):
        return diagnostic_row(
            "coverage_contract_invalid",
            schema="minimum_read_coverage.diagnostic.v1",
            received_type=type(coverage).__name__,
            received_preview=safe_text(coverage, limit=300),
        )
    summary = {
        key: coverage.get(key)
        for key in (
            "required",
            "coverage_satisfied",
            "target_kind",
            "required_count",
            "covered_count",
            "reason",
        )
        if coverage.get(key) not in (None, "", [], {})
    }
    for key in _COVERAGE_LIST_KEYS:
        compact = counted_list(_as_items(coverage.get(key)), limit=list_limit)
        if compact:
            summary[key] = compact
    return summary


def coverage_status_from_contract(contract: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(contract, dict):
        return {
            "schema": "minimum_read_coverage.public_status.v1",
            "coverage_contract_invalid": True,
            "coverage_contract_error": "evidence_contract_not_object",
            "received_type": type(contract).__name__,
        }
    coverage = (
        contract.get("minimum_read_coverage")
        if isinstance(contract.get("minimum_read_coverage"), dict)
        else {}
    )
    compact_coverage = compact_minimum_read_coverage(coverage)
    coverage_invalid = (
        contract.get("minimum_read_coverage") not in (None, "", [], {})
        and not isinstance(contract.get("minimum_read_coverage"), dict)
    )
    return {
        "schema": "minimum_read_coverage.public_status.v1",
        "coverage_contract_invalid": True if coverage_invalid else None,
        "coverage_contract_error": "minimum_read_coverage_not_object" if coverage_invalid else None,
        "coverage_satisfied": (
            coverage.get("coverage_satisfied")
            if coverage else contract.get("coverage_satisfied")
        ),
        "required": coverage.get("required") if coverage else None,
        "target_kind": coverage.get("target_kind") if coverage else None,
        "required_count": coverage.get("required_count") if coverage else None,
        "covered_count": coverage.get("covered_count") if coverage else None,
        "missing_owner_paths": compact_coverage.get("missing_owner_paths", {}).get("items", []),
        "covered_owner_paths": compact_coverage.get("covered_owner_paths", {}).get("items", []),
        "candidate_owner_paths": compact_coverage.get("candidate_owner_paths", {}).get("items", []),
        "minimum_read_coverage": compact_coverage,
    }


def compact_evidence_contract_summary(
    contract: dict[str, Any],
    *,
    schema: str = "planner_evidence_contract_summary.v1",
    list_limit: int = 20,
    text_limit: int = 900,
) -> dict[str, Any]:
    if contract in (None, "", [], {}):
        return {}
    if not isinstance(contract, dict):
        return diagnostic_row(
            "evidence_contract_invalid",
            schema=schema,
            received_type=type(contract).__name__,
            received_preview=safe_text(contract, limit=300),
        )
    try:
        if contract.get("full_contract_not_duplicated_here") is True:
            return dict(contract)
        chars, sha256 = stable_json_fingerprint(contract)
        coverage = (
            contract.get("minimum_read_coverage")
            if isinstance(contract.get("minimum_read_coverage"), dict)
            else {}
        )
        coverage_summary = compact_minimum_read_coverage(contract.get("minimum_read_coverage"), list_limit=list_limit)
        coverage_invalid = (
            contract.get("minimum_read_coverage") not in (None, "", [], {})
            and not isinstance(contract.get("minimum_read_coverage"), dict)
        )
        summary: dict[str, Any] = {
            "schema": schema,
            "full_contract_not_duplicated_here": True,
            "evidence_contract_chars": chars,
            "evidence_contract_sha256": sha256,
            "coverage_contract_invalid": True if coverage_invalid else None,
            "coverage_contract_error": "minimum_read_coverage_not_object" if coverage_invalid else None,
            "coverage_satisfied": coverage.get("coverage_satisfied", contract.get("coverage_satisfied")),
            "minimum_read_coverage": coverage_summary,
            "planner_may_choose_final": contract.get("planner_may_choose_final"),
            "required_next_progress": safe_text(contract.get("required_next_progress"), limit=text_limit),
            "successful_repo_read_count": contract.get("successful_repo_read_count"),
            "verified_content_read_count": contract.get("verified_content_read_count"),
        }
        for key in _CONTRACT_LIST_KEYS:
            compact = counted_list(_as_items(contract.get(key)), limit=list_limit)
            if compact:
                summary[key] = compact
        for key in _COMPACT_VALUE_KEYS:
            value = contract.get(key)
            if value not in (None, "", [], {}):
                summary[key] = compact_value(value, text_limit=text_limit, list_limit=8)
    except Exception as exc:
        return diagnostic_row("evidence_contract_summary_failed", schema=schema, exc=exc)
    return {
        key: value
        for key, value in summary.items()
        if value not in (None, "", [], {})
    }


def evidence_contract_summary_triplet(
    contract: dict[str, Any],
    *,
    schema: str = "planner_evidence_contract_summary.v1",
    list_limit: int = 20,
    text_limit: int = 900,
) -> tuple[dict[str, Any], int, str]:
    summary = compact_evidence_contract_summary(
        contract,
        schema=schema,
        list_limit=list_limit,
        text_limit=text_limit,
    )
    return (
        summary,
        int(summary.get("evidence_contract_chars") or 0),
        str(summary.get("evidence_contract_sha256") or ""),
    )


def validation_without_full_evidence_contract(
    validation: dict[str, Any],
    *,
    schema: str = "planner_evidence_contract_history_summary.v1",
) -> dict[str, Any]:
    if not isinstance(validation, dict):
        return {}
    compact = dict(validation)
    summary, chars, sha256 = evidence_contract_summary_triplet(
        validation.get("evidence_contract") if isinstance(validation.get("evidence_contract"), dict) else {},
        schema=schema,
    )
    compact.pop("evidence_contract", None)
    if summary:
        compact["evidence_contract_summary"] = summary
        compact["evidence_contract_chars"] = chars
        compact["evidence_contract_sha256"] = sha256
    return compact
