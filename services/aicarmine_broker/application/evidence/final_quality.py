"""Evidence-owned quality checks for repository-analysis final answers."""

from __future__ import annotations

import re
from typing import Any


def _append_unique(values: list[str], value: Any) -> None:
    text = str(value or "").strip()
    if text and text not in values:
        values.append(text)


def _read_note_rows(contract: dict[str, Any]) -> list[dict[str, Any]]:
    memory = contract.get("file_memory") if isinstance(contract, dict) else []
    if not isinstance(memory, list):
        memory = []
    rows: list[dict[str, Any]] = [row for row in memory if isinstance(row, dict)]
    operational = contract.get("operational_notes") if isinstance(contract, dict) else {}
    notes = operational.get("read_notes") if isinstance(operational, dict) else []
    for note in notes if isinstance(notes, list) else []:
        if isinstance(note, dict):
            rows.append(note)
    return rows


def _evidence_paths(contract: dict[str, Any]) -> list[str]:
    rows = _read_note_rows(contract)
    paths: list[str] = []
    for row in rows:
        _append_unique(paths, row.get("path"))
        for path in row.get("mentioned_paths") or []:
            _append_unique(paths, path)

    for key in ("successful_repo_read_paths", "validator_admissible_repo_read_paths"):
        values = contract.get(key) if isinstance(contract, dict) else []
        for path in values if isinstance(values, list) else []:
            if isinstance(path, str):
                _append_unique(paths, path)
    return paths


def _path_hit_count(final_answer: str, paths: list[str]) -> int:
    text = str(final_answer or "")
    return sum(1 for path in paths if path and path in text)


def _concept_present(text_low: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text_low) for pattern in patterns)


def _absolute_no_issue_claim(text_low: str) -> bool:
    patterns = (
        r"\bno\s+(?:critical\s+)?(?:security\s+)?(?:issues|vulnerabilities|flaws)\b",
        r"\bno\s+critical\s+(?:issues|flaws)\s+identified\b",
        r"\bno\s+security\s+(?:flaws|issues)\s+detected\b",
        r"\bno\s+critic",
        r"\bnessun[ae]?\s+criticit",
        r"\bnessun[ae]?\s+vulnerabil",
        r"\bnon\s+(?:sono\s+state?|ho)\s+(?:trovat[ei]|rilevat[ei])\s+(?:critic|vulnerabil)",
        r"\brepository\s+(?:is\s+)?secure\b",
        r"\bintrinsecamente\s+sicur",
        r"\bassenza\s+di\s+(?:critic|vulnerabil)",
    )
    return _concept_present(text_low, patterns)


def repo_analysis_final_answer_quality(
    final_answer: str,
    contract: dict[str, Any],
) -> dict[str, Any]:
    """Return deterministic quality evidence for a repository-analysis final."""
    text = str(final_answer or "")
    stripped = text.strip()
    rows = _read_note_rows(contract if isinstance(contract, dict) else {})
    paths = _evidence_paths(contract if isinstance(contract, dict) else {})
    path_hits = _path_hit_count(stripped, paths)
    core_candidates = contract.get("ranked_core_candidate_dirs") if isinstance(contract, dict) else []
    if not isinstance(core_candidates, list):
        core_candidates = []
    core_paths = [
        str(item.get("path") or "")
        for item in core_candidates
        if isinstance(item, dict) and item.get("path")
    ]
    core_hits = _path_hit_count(stripped, core_paths)

    min_chars = 2200 if len(rows) >= 5 else 900
    pathish_evidence = {
        p for p in paths
        if p and ("/" in p or p.endswith((".md", ".py", ".json", ".ps1", ".toml", ".txt")))
    }
    min_path_hits = min(6, max(3, len(pathish_evidence) // 3))
    if len(paths) >= 8:
        min_path_hits = max(min_path_hits, 5)

    text_low = stripped.lower()
    violations: list[str] = []
    if not stripped:
        violations.append("repo_analysis_final_empty")
    if len(stripped) < min_chars:
        violations.append(f"repo_analysis_final_too_short:{len(stripped)}/{min_chars}")
    if path_hits < min_path_hits:
        violations.append(f"repo_analysis_final_missing_concrete_paths:{path_hits}/{min_path_hits}")
    if core_paths and core_hits < min(2, len(core_paths)):
        violations.append(f"repo_analysis_final_missing_core_candidate_paths:{core_hits}/{min(2, len(core_paths))}")
    if not _concept_present(
        text_low,
        (
            r"\bworkflow\b",
            r"\bflow\b",
            r"\bflusso\b",
            r"\bentrypoint\b",
            r"\bpunto\s+di\s+ingresso\b",
            r"\bcomando\s+canonico\b",
            r"\blauncher\b",
        ),
    ):
        violations.append("repo_analysis_final_missing_workflow_or_entrypoint")
    if not _concept_present(
        text_low,
        (
            r"\bproblem",
            r"\bproble",
            r"\bverific",
            r"\bvalidaz",
            r"\blimit",
            r"\bvincol",
            r"\bcopertura\b",
            r"\bcoverage\b",
        ),
    ):
        violations.append("repo_analysis_final_missing_limits_or_validation")

    generic_phrases = (
        "clear separation of concerns",
        "well-structured repository",
        "chiara separazione",
        "struttura mostra una chiara",
    )
    if any(phrase in text_low for phrase in generic_phrases) and len(stripped) < 3200:
        violations.append("repo_analysis_final_generic_template_language")

    code_security_coverage = (
        contract.get("code_security_coverage")
        if isinstance(contract, dict) and isinstance(contract.get("code_security_coverage"), dict)
        else {}
    )
    if (
        code_security_coverage.get("required") is True
        and code_security_coverage.get("verdict_allowed") is not True
        and _absolute_no_issue_claim(text_low)
    ):
        violations.append("repo_analysis_final_absolute_security_verdict_without_code_coverage")

    return {
        "ok": not violations,
        "violations": violations,
        "metrics": {
            "chars": len(stripped),
            "min_chars": min_chars,
            "path_hits": path_hits,
            "min_path_hits": min_path_hits,
            "core_candidate_hits": core_hits,
            "core_candidate_paths": core_paths[:8],
            "evidence_path_count": len(paths),
            "read_note_count": len(rows),
        },
        "required_next_progress": (
            "Final answer rejected as too shallow for repository analysis. Return action=final "
            "with a richer final_answer grounded in operational_notes.read_notes and file_memory: "
            "cover workflow/entrypoint, core candidates, concrete file roles, validation/problems "
            "or limits, and cite concrete repo-relative paths. Do not call tools unless a new "
            "evidence gap is named."
        ),
    }


def repo_analysis_final_answer_too_shallow(
    final_answer: str,
    contract: dict[str, Any],
) -> bool:
    return not repo_analysis_final_answer_quality(final_answer, contract).get("ok")
