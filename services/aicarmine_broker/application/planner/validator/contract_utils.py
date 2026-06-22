"""
contract_utils.py
=================
Read-only helpers that extract structured information from the evidence
contract dict.  No mutations here; callers are responsible for assigning
the return values back into the contract where needed.
"""

from __future__ import annotations

from typing import Any

from aicarmine_broker.application.shared.path_tokens import repo_path_token

from .path_utilis import collect_repo_paths, is_concrete_repo_path, is_concrete_search_query, is_prose_or_metric_token


# ---------------------------------------------------------------------------
# Known paths / dirs
# ---------------------------------------------------------------------------

def known_contract_repo_paths(contract: dict[str, Any]) -> set[str]:
    """
    Collect every path token that the contract already knows about, drawn
    from all canonical path-bearing keys plus coverage and finalization
    sub-contracts.
    """
    contract = contract if isinstance(contract, dict) else {}
    paths: set[str] = set()

    for key in (
        "validator_admissible_repo_read_paths",
        "read_admissible_paths",
        "successful_repo_read_paths",
        "verified_content_reads",
        "covered_owner_paths",
        "candidate_owner_paths",
        "missing_owner_paths",
    ):
        paths.update(collect_repo_paths(contract.get(key)))

    for coverage_source in _iter_coverage_dicts(contract):
        for key in ("covered_owner_paths", "candidate_owner_paths", "missing_owner_paths"):
            paths.update(collect_repo_paths(coverage_source.get(key)))

    return {p for p in paths if p and p != "."}


def known_contract_repo_dirs(contract: dict[str, Any]) -> set[str]:
    """
    Derive every ancestor directory implied by *known_contract_repo_paths*.
    Always includes "." (root).
    """
    dirs = {"."}
    for path in known_contract_repo_paths(contract):
        parts = [part for part in path.split("/") if part]
        for index in range(1, len(parts)):
            dirs.add("/".join(parts[:index]))
    return dirs


def _iter_coverage_dicts(contract: dict[str, Any]):
    """Yield minimum_read_coverage dicts from contract and finalization_contract."""
    coverage = contract.get("minimum_read_coverage")
    if isinstance(coverage, dict):
        yield coverage
    final_contract = contract.get("finalization_contract")
    if isinstance(final_contract, dict):
        fc_coverage = final_contract.get("minimum_read_coverage")
        if isinstance(fc_coverage, dict):
            yield fc_coverage


# ---------------------------------------------------------------------------
# Final quality repo-read allowlist
# ---------------------------------------------------------------------------

def final_quality_repo_read_allowlist(contract: dict[str, Any]) -> set[str]:
    """
    Build the set of paths that *may* appear in a repo_read required by the
    final-quality gate, drawn from file_memory, read_notes, and all the
    standard path-bearing keys.
    """
    contract = contract if isinstance(contract, dict) else {}
    allowlist: set[str] = set()

    def _add(raw: Any) -> None:
        token = repo_path_token(raw)
        if token and is_concrete_repo_path(token):
            allowlist.add(token)

    for key in (
        "validator_admissible_repo_read_paths",
        "read_admissible_paths",
        "successful_repo_read_paths",
        "covered_owner_paths",
        "candidate_owner_paths",
        "missing_owner_paths",
    ):
        values = contract.get(key)
        if isinstance(values, dict):
            for item in values.values():
                if isinstance(item, dict):
                    _add(item.get("path"))
                    _add(item.get("repo_path"))
                else:
                    _add(item)
        elif isinstance(values, list):
            for item in values:
                if isinstance(item, dict):
                    _add(item.get("path"))
                    _add(item.get("repo_path"))
                else:
                    _add(item)

    verified_reads = contract.get("verified_content_reads")
    if isinstance(verified_reads, list):
        for read in verified_reads:
            if isinstance(read, dict):
                _add(read.get("path") or read.get("repo_path"))

    memory = contract.get("file_memory") if isinstance(contract.get("file_memory"), list) else []
    operational = contract.get("operational_notes") if isinstance(contract.get("operational_notes"), dict) else {}
    read_notes = operational.get("read_notes") if isinstance(operational.get("read_notes"), list) else []
    rows: list[dict[str, Any]] = [r for r in memory if isinstance(r, dict)] + [
        r for r in read_notes if isinstance(r, dict)
    ]
    for row in rows:
        _add(row.get("path"))
        for path in row.get("mentioned_paths") if isinstance(row.get("mentioned_paths"), list) else []:
            _add(path)

    return allowlist


# ---------------------------------------------------------------------------
# Coverage helpers (read-only)
# ---------------------------------------------------------------------------

def minimum_read_coverage_contract(contract: dict[str, Any]) -> dict[str, Any]:
    coverage = contract.get("minimum_read_coverage")
    if isinstance(coverage, dict):
        return coverage
    final_contract = contract.get("finalization_contract")
    if isinstance(final_contract, dict):
        coverage = final_contract.get("minimum_read_coverage")
        if isinstance(coverage, dict):
            return coverage
    return {}


def is_coverage_required(contract: dict[str, Any]) -> bool:
    coverage = minimum_read_coverage_contract(contract)
    if coverage:
        return coverage.get("required") is True
    return contract.get("coverage_satisfied") is not True


def is_coverage_satisfied(contract: dict[str, Any]) -> bool:
    coverage = minimum_read_coverage_contract(contract)
    if coverage:
        return coverage.get("coverage_satisfied") is True
    return contract.get("coverage_satisfied") is True


def missing_coverage_owner_paths(contract: dict[str, Any]) -> list[str]:
    coverage = minimum_read_coverage_contract(contract)
    raw = coverage.get("missing_owner_paths") if coverage else contract.get("missing_owner_paths")
    return [str(p) for p in raw] if isinstance(raw, list) else []


# ---------------------------------------------------------------------------
# Route proof check
# ---------------------------------------------------------------------------

def required_next_route_has_deterministic_proof(
    required_call: dict[str, Any],
    contract: dict[str, Any],
) -> bool:
    """
    Return True only when the proposed *required_call* can be verified
    deterministically against the existing contract evidence (no guessing).
    """
    required_call = required_call if isinstance(required_call, dict) else {}
    tool = str(required_call.get("tool") or "").strip()
    args = required_call.get("arguments") if isinstance(required_call.get("arguments"), dict) else {}

    if tool == "repo_read":
        return True

    if tool == "repo_list_files":
        path = repo_path_token(args.get("path") or ".") or "."
        if path == ".":
            return True
        return (
            not is_prose_or_metric_token(path)
            and path in known_contract_repo_dirs(contract)
        )

    if tool in {"repo_semantic_search", "repo_rg_search", "repo_search"}:
        query = (
            args.get("query")
            or args.get("pattern")
            or args.get("symbol")
            or args.get("needle")
            or args.get("text")
        )
        if not is_concrete_search_query(query):
            return False
        path = repo_path_token(args.get("path")) if args.get("path") else ""
        if path and (
            path not in known_contract_repo_paths(contract)
            and path not in known_contract_repo_dirs(contract)
        ):
            return False
        return True

    if tool == "planner_scratchpad_read":
        document_id = str(args.get("document_id") or "").strip()
        target_file = repo_path_token(args.get("target_file")) if args.get("target_file") else ""
        if document_id and not is_prose_or_metric_token(document_id):
            return True
        return bool(target_file and target_file in known_contract_repo_paths(contract))

    return False