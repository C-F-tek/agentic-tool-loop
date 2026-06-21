"""Evidence-owned quality checks for repository-analysis final answers."""

from __future__ import annotations

import re
from typing import Any

from aicarmine_broker.application.evidence.audit_guidance import (
    audit_guidance_for_goal,
    final_audit_red_flags,
    goal_requests_semantic_audit,
    pending_read_or_search_actions,
    role_guidance_for_goal,
)
from aicarmine_broker.application.shared.path_tokens import repo_rel_token as _repo_rel_token


def _append_unique(values: list[str], value: Any) -> None:
    text = str(value or "").strip()
    if text and text not in values:
        values.append(text)


def _clip_text(value: Any, limit: int) -> str:
    text = str(value or "")
    if len(text) <= limit:
        return text
    return text[: max(0, limit)] + f"\n...[truncated {len(text) - limit} chars]"


def _compact_list(values: Any, *, limit: int = 12) -> list[Any]:
    if not isinstance(values, list):
        return []
    return values[: max(0, int(limit or 0))]


def _compact_mapping(value: Any, *, text_limit: int = 500, list_limit: int = 8) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if item in (None, "", [], {}):
                continue
            out[str(key)] = _compact_mapping(item, text_limit=text_limit, list_limit=list_limit)
        return out
    if isinstance(value, list):
        return [_compact_mapping(item, text_limit=text_limit, list_limit=list_limit) for item in value[:list_limit]]
    if isinstance(value, str):
        return _clip_text(value, text_limit)
    return value


def _verified_read_summary(contract: dict[str, Any]) -> dict[str, Any]:
    rows = contract.get("verified_content_reads") if isinstance(contract, dict) else []
    rows = rows if isinstance(rows, list) else []
    compact_rows: list[dict[str, Any]] = []
    truncated_paths: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        path = str(row.get("path") or row.get("repo_path") or "").strip()
        if row.get("truncated") or row.get("preview_only"):
            _append_unique(truncated_paths, path)
        item = {
            key: row.get(key)
            for key in (
                "path",
                "repo_path",
                "line_count",
                "content_chars",
                "truncated",
                "preview_only",
                "complete",
                "sha256",
                "source",
            )
            if row.get(key) not in (None, "", [], {})
        }
        if item:
            compact_rows.append(item)
    return {
        "count": len(rows),
        "top": compact_rows[:12],
        "omitted_count": max(0, len(compact_rows) - 12),
        "truncated_paths": truncated_paths[:12],
    }


def _final_quality_rag_tool_surface(contract: dict[str, Any]) -> dict[str, Any]:
    core_status = (
        contract.get("core_discovery_status")
        if isinstance(contract, dict) and isinstance(contract.get("core_discovery_status"), dict)
        else {}
    )
    semantic_paths: list[str] = []
    for path in contract.get("validator_admissible_repo_read_paths") or []:
        if isinstance(path, str):
            _append_unique(semantic_paths, path)
    return {
        "repo_semantic_search_available_as_planner_tool": True,
        "hidden_preplanner_rag_must_not_be_called_by_final_quality": True,
        "route_rule": (
            "If more semantic discovery is needed, request required_next_tool_call.tool="
            "repo_semantic_search with a concrete query; then read returned paths with repo_read."
        ),
        "core_discovery_status": {
            key: core_status.get(key)
            for key in (
                "schema",
                "source",
                "intrinsic_context_rag_status",
                "intrinsic_context_rag_status_scope",
                "rag_status_scope",
                "rag_item_count",
                "repo_semantic_search_available_as_planner_tool",
            )
            if core_status.get(key) not in (None, "", [], {})
        },
        "admissible_repo_read_paths_top": semantic_paths[:12],
    }


def _final_quality_contract_summary(contract: dict[str, Any]) -> dict[str, Any]:
    contract = contract if isinstance(contract, dict) else {}
    final_contract = (
        contract.get("finalization_contract")
        if isinstance(contract.get("finalization_contract"), dict)
        else {}
    )
    coverage = (
        contract.get("minimum_read_coverage")
        if isinstance(contract.get("minimum_read_coverage"), dict)
        else final_contract.get("minimum_read_coverage")
        if isinstance(final_contract.get("minimum_read_coverage"), dict)
        else {}
    )
    return {
        "semantic_goal_classification": _compact_mapping(
            contract.get("semantic_goal_classification"), text_limit=300, list_limit=6
        ),
        "finalization_contract": _compact_mapping(final_contract, text_limit=360, list_limit=8),
        "minimum_read_coverage": _compact_mapping(coverage, text_limit=360, list_limit=12),
        "successful_repo_read_paths": _coalesce_unique_paths(contract.get("successful_repo_read_paths"), limit=24),
        "verified_content_reads": _verified_read_summary(contract),
        "file_memory_paths": [
            _repo_rel_token(row.get("path"))
            for row in _read_note_rows(contract)
            if isinstance(row, dict) and _repo_rel_token(row.get("path"))
        ][:24],
        "candidate_next_actions": _compact_mapping(contract.get("candidate_next_actions"), text_limit=420, list_limit=8),
        "core_discovery_candidates": _compact_mapping(contract.get("core_discovery_candidates"), text_limit=300, list_limit=10),
        "missing_owner_paths": _compact_list(contract.get("missing_owner_paths"), limit=24),
        "candidate_owner_paths": _compact_list(contract.get("candidate_owner_paths"), limit=24),
        "required_next_progress": _clip_text(contract.get("required_next_progress"), 800),
        "required_next_tool_call": _compact_mapping(
            contract.get("required_next_tool_call"),
            text_limit=260,
            list_limit=6,
        ),
        "final_rewrite_latch": str(contract.get("final_rewrite_latch") or "inactive"),
        "required_next_output_sections": _compact_mapping(
            contract.get("required_next_output_sections"),
            text_limit=260,
            list_limit=8,
        ),
        "required_next_missing_evidences": _coalesce_unique_paths(
            contract.get("required_next_missing_evidences"),
            limit=12,
        ),
        "required_next_tool_call_satisfied": _compact_mapping(
            contract.get("required_next_tool_call_satisfied"),
            text_limit=260,
            list_limit=6,
        ),
        "stale_required_next_tool_calls": _compact_mapping(
            contract.get("stale_required_next_tool_calls"),
            text_limit=360,
            list_limit=8,
        ),
        "rag_tool_surface": _final_quality_rag_tool_surface(contract),
        "validation_rejections_tail": _compact_mapping(
            contract.get("validation_rejections_tail"),
            text_limit=500,
            list_limit=6,
        ),
    }


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


_FINAL_PATH_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9_.@/\\:-])"
    r"(?:[A-Za-z0-9_.@+-]+[\\/])+"
    r"[A-Za-z0-9_.@+-]+(?:\.[A-Za-z0-9_+-]+|[\\/])?"
    r"(?![A-Za-z0-9_.@/\\:-])",
    re.IGNORECASE,
)


def _repoish_path_token(value: Any) -> str:
    text = str(value or "").strip().strip("`'\".,;:)]}")
    text = text.replace("\\", "/").strip("/")
    while "//" in text:
        text = text.replace("//", "/")
    if not text or text in {".", ".."}:
        return ""
    return text


def _path_is_concrete_repo_path(token: Any) -> bool:
    token = _repoish_path_token(token)
    if not token:
        return False
    if token.lower() in {"services", "tools", "cache", "cache_dir", "repo"}:
        return False
    if " " in token:
        return False
    if token in {".", ".."}:
        return False
    if "/" in token or "\\" in token or token.count(".") >= 1:
        return True
    return False


def _contract_read_allowlist(contract: dict[str, Any]) -> set[str]:
    contract = contract if isinstance(contract, dict) else {}
    allowlist: set[str] = set()

    def add(value: Any) -> None:
        token = _repoish_path_token(value)
        if token and _path_is_concrete_repo_path(token):
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
                add(item)
        elif isinstance(values, list):
            for item in values:
                if isinstance(item, dict):
                    add(item.get("path"))
                    add(item.get("repo_path"))
                else:
                    add(item)
    for item in _read_note_rows(contract):
        add(item.get("path"))
        for path in item.get("mentioned_paths") if isinstance(item.get("mentioned_paths"), list) else []:
            add(path)
    return allowlist


def _coalesce_required_next_missing_paths(values: Any) -> list[str]:
    if isinstance(values, tuple):
        values = list(values)
    elif not isinstance(values, list):
        return []
    out: list[str] = []
    for value in values:
        token = _repoish_path_token(value)
        if not token or not _path_is_concrete_repo_path(token):
            continue
        if token not in out:
            out.append(token)
    return out


def _final_path_tokens(final_answer: str) -> list[str]:
    tokens: list[str] = []
    for match in _FINAL_PATH_TOKEN_RE.finditer(str(final_answer or "")):
        token = _repoish_path_token(match.group(0))
        if token and token not in tokens:
            tokens.append(token)
    return tokens


def _coalesce_unique_paths(values: Any, *, limit: int = 10) -> list[str]:
    rows = values if isinstance(values, list) else []
    out: list[str] = []
    for raw in rows:
        token = _repo_rel_token(raw)
        if token and token not in out:
            out.append(token)
    return out[:max(0, int(limit or 0))]


def _path_items(value: Any) -> list[Any]:
    if isinstance(value, dict):
        items = value.get("items")
        return items if isinstance(items, list) else []
    if isinstance(value, list):
        return value
    return []


def _repo_read_completed_paths(contract: dict[str, Any]) -> set[str]:
    contract = contract if isinstance(contract, dict) else {}
    completed: set[str] = set()

    def add(raw: Any) -> None:
        if isinstance(raw, dict):
            raw = raw.get("path") or raw.get("repo_path") or raw.get("source_path")
        token = _repo_rel_token(raw)
        if token and token != ".":
            completed.add(token)

    for key in ("verified_content_reads", "successful_repo_read_paths"):
        for item in _path_items(contract.get(key)):
            add(item)

    for row in _path_items(contract.get("stale_required_next_tool_calls")):
        if not isinstance(row, dict):
            continue
        args = row.get("arguments") if isinstance(row.get("arguments"), dict) else {}
        for item in args.get("paths", []) if isinstance(args.get("paths"), list) else [args.get("path")]:
            add(item)

    return completed


def _repo_read_path_allowlist(contract: dict[str, Any]) -> set[str]:
    contract = contract if isinstance(contract, dict) else {}
    allowed: set[str] = set()

    def add(raw: Any) -> None:
        if isinstance(raw, dict):
            raw = raw.get("path") or raw.get("repo_path") or raw.get("source_path")
        token = _repo_rel_token(raw)
        if token and token != ".":
            allowed.add(token)

    for key in (
        "validator_admissible_repo_read_paths",
        "read_admissible_paths",
        "covered_owner_paths",
        "candidate_owner_paths",
        "missing_owner_paths",
    ):
        for item in _path_items(contract.get(key)):
            add(item)
    coverage = (
        contract.get("minimum_read_coverage")
        if isinstance(contract.get("minimum_read_coverage"), dict)
        else {}
    )
    for key in ("covered_owner_paths", "candidate_owner_paths", "missing_owner_paths"):
        for item in _path_items(coverage.get(key)):
            add(item)
    final_contract = (
        contract.get("finalization_contract")
        if isinstance(contract.get("finalization_contract"), dict)
        else {}
    )
    final_coverage = (
        final_contract.get("minimum_read_coverage")
        if isinstance(final_contract.get("minimum_read_coverage"), dict)
        else {}
    )
    for key in ("covered_owner_paths", "candidate_owner_paths", "missing_owner_paths"):
        for item in _path_items(final_coverage.get(key)):
            add(item)
    return allowed - _repo_read_completed_paths(contract)


def _known_repo_paths(contract: dict[str, Any]) -> set[str]:
    contract = contract if isinstance(contract, dict) else {}
    known: set[str] = set()

    def add(raw: Any) -> None:
        if isinstance(raw, dict):
            raw = raw.get("path") or raw.get("repo_path") or raw.get("source_path")
        token = _repo_rel_token(raw)
        if token and token != ".":
            known.add(token)

    for key in (
        "validator_admissible_repo_read_paths",
        "read_admissible_paths",
        "successful_repo_read_paths",
        "verified_content_reads",
        "covered_owner_paths",
        "candidate_owner_paths",
        "missing_owner_paths",
    ):
        for item in _path_items(contract.get(key)):
            add(item)

    coverage = contract.get("minimum_read_coverage") if isinstance(contract.get("minimum_read_coverage"), dict) else {}
    for key in ("covered_owner_paths", "candidate_owner_paths", "missing_owner_paths"):
        for item in _path_items(coverage.get(key)):
            add(item)

    final_contract = contract.get("finalization_contract") if isinstance(contract.get("finalization_contract"), dict) else {}
    final_coverage = (
        final_contract.get("minimum_read_coverage")
        if isinstance(final_contract.get("minimum_read_coverage"), dict)
        else {}
    )
    for key in ("covered_owner_paths", "candidate_owner_paths", "missing_owner_paths"):
        for item in _path_items(final_coverage.get(key)):
            add(item)

    return known


def _known_repo_dirs(paths: set[str]) -> set[str]:
    dirs = {"."}
    for path in paths:
        parts = [part for part in str(path or "").split("/") if part]
        for index in range(1, len(parts)):
            dirs.add("/".join(parts[:index]))
    return dirs


def _route_token_is_prose_or_metric(value: Any) -> bool:
    token = str(value or "").strip()
    if not token:
        return True
    lowered = token.lower()
    if lowered in {
        "ridondanze/rischi",
        "docs/config",
        "planner/final-quality",
        "planner/controller rejection paths",
    }:
        return True
    if any(sep in lowered for sep in (":\\", "://")):
        return True
    compact = lowered.replace("/", "").replace(".", "").replace("-", "").replace("_", "")
    if "/" in lowered and compact.isdigit():
        return True
    if " " in token and not any(
        lowered.endswith(suffix)
        for suffix in (".py", ".md", ".json", ".toml", ".yaml", ".yml", ".txt")
    ):
        return True
    return False


def _search_query_is_concrete(value: Any) -> bool:
    text = str(value or "").strip()
    if not text or len(text) > 260:
        return False
    lowered = text.lower()
    if lowered in {
        "docs/config",
        "ridondanze/rischi",
        "8/2",
        "8/8",
        "9/9",
        "planner/controller rejection paths",
    }:
        return False
    compact = lowered.replace("/", "").replace(".", "").replace("-", "").replace("_", "")
    if "/" in lowered and compact.isdigit():
        return False
    useful_tokens = [
        token
        for token in lowered.replace(",", " ").replace(";", " ").split()
        if len(token) >= 3 and "/" not in token and any(ch.isalpha() for ch in token)
    ]
    if "/" in lowered and len(useful_tokens) < 2:
        return False
    return bool(useful_tokens)


def _record_invalid_required_next_tool_call(
    diagnostics: dict[str, Any] | None,
    *,
    reason: str,
    paths: list[str] | None = None,
    query: Any = None,
) -> None:
    if diagnostics is None:
        return
    if paths:
        diagnostics["invalid_required_next_tool_call_paths"] = paths[:12]
    query_text = str(query or "").strip()
    if query_text:
        diagnostics["invalid_required_next_tool_call_query"] = query_text[:260]
    diagnostics["invalid_required_next_tool_call_reason"] = reason


def _allowed_concrete_repo_path(value: Any, allowlist: set[str]) -> str:
    if isinstance(value, dict):
        value = value.get("path") or value.get("repo_path") or value.get("source_path")
    token = _repo_rel_token(value)
    if not token or token == "." or token not in allowlist:
        return ""
    if any(ch.isspace() for ch in token):
        return ""
    return token


def _normalize_required_next_tool_call_paths(
    tool: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(arguments, dict):
        return {}
    args = dict(arguments)
    if tool == "repo_read":
        if "paths" in args:
            raw_paths = args.get("paths")
            if isinstance(raw_paths, (list, tuple)):
                normalized = [_repo_rel_token(item) for item in raw_paths if _repo_rel_token(item)]
                if normalized:
                    args["paths"] = _coalesce_unique_paths(normalized, limit=12)
                else:
                    args.pop("paths", None)
            elif raw_paths is not None:
                normalized = _repo_rel_token(raw_paths)
                if normalized:
                    args["paths"] = [normalized]
                else:
                    args.pop("paths", None)
            else:
                args.pop("paths", None)
            args.pop("path", None)
        else:
            normalized_path = _repo_rel_token(args.get("path"))
            if normalized_path:
                args["path"] = normalized_path
            else:
                args.pop("path", None)
        return args

    for key in ("path", "document_id", "target_file", "target_dir", "root"):
        if key in args:
            normalized = _repo_rel_token(args.get(key))
            if normalized:
                args[key] = normalized
            else:
                args.pop(key, None)
    return args


def _required_next_output_sections(violations: list[str], metrics: dict[str, Any]) -> list[str]:
    sections: list[str] = []
    if any(str(v).startswith("repo_analysis_final_missing_concrete_paths") for v in violations):
        _append_unique(sections, "Concrete file-level evidence")
    if any(str(v).startswith("repo_analysis_final_missing_core_candidate_paths") for v in violations):
        _append_unique(sections, "Core ownership candidates and file roles")
    if any("unverified_paths" in str(v) for v in violations):
        _append_unique(sections, "Verified path mentions")
    if any("coverage" in str(v) for v in violations) or str(metrics.get("read_note_count") or ""):
        _append_unique(sections, "Coverage limits and verification status")
    if any("speculative" in str(v) for v in violations):
        _append_unique(sections, "Risk/limitations wording")
    if any("too_short" in str(v) for v in violations):
        _append_unique(sections, "Missing evidence depth and workflow completeness")
    if not sections:
        _append_unique(sections, "Actionable final-rewrite evidence checklist")
    return sections


def _required_next_missing_evidences(
    violations: list[str],
    metrics: dict[str, Any],
    hard_pending_actions: list[dict[str, Any]],
    contract: dict[str, Any],
) -> list[str]:
    missing: list[str] = []
    allowlist = _repo_read_path_allowlist(contract if isinstance(contract, dict) else {})

    def add_path(raw: Any) -> None:
        token = _allowed_concrete_repo_path(raw, allowlist)
        if token:
            _append_unique(missing, token)

    if metrics.get("unverified_path_tokens"):
        for item in metrics.get("unverified_path_tokens") or []:
            add_path(item)
    for row in hard_pending_actions:
        for key in ("path", "paths", "target_file", "path_hint"):
            value = row.get(key)
            if isinstance(value, list):
                for item in value:
                    add_path(item)
            else:
                add_path(value)
    return missing[:24]


def _known_path_tokens(contract: dict[str, Any], paths: list[str], core_paths: list[str]) -> set[str]:
    known: set[str] = set()

    def add(raw: Any) -> None:
        token = _repoish_path_token(raw)
        if not token:
            return
        known.add(token.lower())
        parts = token.split("/")
        for index in range(1, len(parts)):
            known.add("/".join(parts[:index]).lower())

    for path in [*paths, *core_paths]:
        add(path)
    for key in (
        "candidate_owner_paths",
        "missing_owner_paths",
        "read_admissible_paths",
        "validator_admissible_repo_read_paths",
        "successful_repo_read_paths",
    ):
        values = contract.get(key) if isinstance(contract, dict) else []
        for path in values if isinstance(values, list) else []:
            add(path)
    return known


def _unverified_final_path_tokens(
    final_answer: str,
    contract: dict[str, Any],
    *,
    paths: list[str],
    core_paths: list[str],
) -> list[str]:
    known = _known_path_tokens(contract, paths, core_paths)
    unresolved: list[str] = []
    for token in _final_path_tokens(final_answer):
        low = token.lower()
        if low in {"services", "tools", "cache"}:
            continue
        if low not in known:
            unresolved.append(token)
    return unresolved


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


def _absolute_repo_no_issue_claim(text_low: str) -> bool:
    patterns = (
        r"\bno\s+(?:semantic\s+)?(?:drift|duplication|duplicate\s+logic|regression\s+risk)\b",
        r"\bno\s+critical\s+(?:semantic\s+)?(?:issues|findings|risks)\b",
        r"\bnessun[ae]?\s+(?:incongruenza|duplicazione|regressione|drift|rischio)\b",
        r"\bnessun[ae]?\s+critic",
        r"\bniente\s+(?:drift|duplicazioni|incongruenze|cloni)\b",
        r"\bno\s+drift\b",
    )
    return _concept_present(text_low, patterns)


def _declares_partial_or_limited_coverage(text_low: str) -> bool:
    patterns = (
        r"\breview\s+parzial",
        r"\bcopertura\s+parzial",
        r"\blimiti?\s+della\s+copertura\b",
        r"\blimits?\s+of\s+coverage\b",
        r"\bnon\s+ancora\s+(?:esaminat|esplorat|lett)",
        r"\bnot\s+yet\s+(?:examined|explored|read)\b",
        r"\btruncat[oaie]?\b",
        r"\btruncated\b",
    )
    return _concept_present(text_low, patterns)


def _claims_deep_or_complete_review(text_low: str) -> bool:
    patterns = (
        r"\breview\s+(?:locale\s+)?(?:read-only\s+)?approfondit",
        r"\bho\s+completato\s+la\s+review\b",
        r"\breview\s+complet",
        r"\baudit\s+complet",
        r"\bsufficiente\s+per\s+dichiarare\b",
    )
    return _concept_present(text_low, patterns)


def repo_analysis_final_answer_quality(
    final_answer: str,
    contract: dict[str, Any],
) -> dict[str, Any]:
    """Return deterministic quality evidence for a repository-analysis final."""
    text = str(final_answer or "")
    stripped = text.strip()
    pending_actions = pending_read_or_search_actions(contract if isinstance(contract, dict) else {})
    hard_pending_actions = [
        action for action in pending_actions
        if (
            action.get("required") is True
            or str(action.get("source") or "") == "repo_analysis_final_model_quality"
            or str(action.get("action_id") or "").startswith("repo_analysis_final_quality:")
            or "required" in str(action.get("reason") or "").lower()
        )
    ]
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
    
    # ENTRY POINT CHECK: Entry points defined in contract at mount point
    # Extract entry points from contract's minimum_read_coverage.covered_owner_paths
    # If no entry points specified, skip this validation
    entry_points_contract = contract.get("entry_points") if isinstance(contract, dict) else None
    if entry_points_contract and isinstance(entry_points_contract, dict):
        verified_content_reads = (
            contract.get("verified_content_reads")
            if isinstance(contract, dict) and isinstance(contract.get("verified_content_reads"), list)
            else []
        )
        existing_entry_points = set()
        for ep_path in entry_points_contract.values():
            if isinstance(ep_path, str):
                if ep_path in verified_content_reads:
                    existing_entry_points.add(ep_path)
                elif any(ep_path in str(p) for p in paths):
                    existing_entry_points.add(ep_path)
        
        if existing_entry_points:
            missing_entry_points = [
                ep for ep in existing_entry_points
                if ep not in verified_content_reads
            ]
            if missing_entry_points:
                violations.append(f"missing_entry_point:{','.join(missing_entry_points)}")
    
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
    red_flags = final_audit_red_flags(stripped)
    if red_flags.get("follow_up_invitations"):
        violations.append("repo_analysis_final_follow_up_invitation_instead_of_answer")
    # Patch C: distingue evidenza acquisita da evidenza assente.
    if red_flags.get("speculative_terms"):
        verified_content_reads = (
            contract.get("verified_content_reads")
            if isinstance(contract, dict) and isinstance(contract.get("verified_content_reads"), list)
            else []
        )
        read_note_count = max(len(rows), len(verified_content_reads))

        full_context_available = any(
            isinstance(row, dict)
            and (
                row.get("full_context_reconstructed") is True
                or row.get("complete") is True
                or str(row.get("content_source") or "") == "repo_read_artifact_rehydrated_for_prompt"
                or str(row.get("source") or "") == "repo_read_artifact_rehydrated_for_prompt"
            )
            for row in verified_content_reads
        )

        if read_note_count > 0 or full_context_available:
            violations.append("evidence_consumed_but_final_too_short")
        else:
            violations.append("repo_analysis_final_speculative_claims_without_evidence")
    if red_flags.get("generic_no_issue_phrases") and len(rows) < 8:
        violations.append("repo_analysis_final_generic_no_issue_claim_with_shallow_evidence")
    unverified_path_tokens = _unverified_final_path_tokens(
        stripped,
        contract if isinstance(contract, dict) else {},
        paths=paths,
        core_paths=core_paths,
    )
    if unverified_path_tokens:
        violations.append("repo_analysis_final_mentions_unverified_paths:" + ",".join(unverified_path_tokens[:4]))
    if hard_pending_actions and not _declares_partial_or_limited_coverage(text_low):
        violations.append("repo_analysis_final_ignores_required_read_or_search_route")
    if _declares_partial_or_limited_coverage(text_low) and _claims_deep_or_complete_review(text_low):
        violations.append("repo_analysis_final_claims_complete_despite_declared_limits")
    if _declares_partial_or_limited_coverage(text_low) and _absolute_repo_no_issue_claim(text_low):
        violations.append("repo_analysis_final_absolute_no_issue_claim_with_partial_coverage")
    core_status = (
        contract.get("core_discovery_status")
        if isinstance(contract, dict) and isinstance(contract.get("core_discovery_status"), dict)
        else {}
    )
    rag_reported_missing = "rag" in text_low and any(
        term in text_low
        for term in (
            "missing",
            "mancant",
            "assent",
            "non disponibile",
            "not available",
            "unavailable",
        )
    )
    if rag_reported_missing and core_status.get("repo_semantic_search_available_as_planner_tool") is True:
        violations.append("repo_analysis_final_confuses_intrinsic_rag_missing_with_planner_rag")

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

    quality_metrics = {
        "chars": len(stripped),
        "min_chars": min_chars,
        "path_hits": path_hits,
        "min_path_hits": min_path_hits,
        "core_candidate_hits": core_hits,
        "core_candidate_paths": core_paths[:8],
        "evidence_path_count": len(paths),
        "read_note_count": len(rows),
        "unverified_path_tokens": unverified_path_tokens[:8],
        "final_audit_red_flags": red_flags,
        "hard_pending_read_or_search_actions": hard_pending_actions[:4],
    }
    return {
        "ok": not violations,
        "violations": violations,
        "metrics": quality_metrics,
        "required_next_output_sections": _required_next_output_sections(violations, quality_metrics),
        "required_next_missing_evidences": _required_next_missing_evidences(
            violations,
            {
                "unverified_path_tokens": unverified_path_tokens,
                "read_note_count": len(rows),
            },
            hard_pending_actions[:4],
            contract if isinstance(contract, dict) else {},
        ),
        "required_next_progress": (
            "Final answer rejected as too shallow for repository analysis. Return action=final "
            "with a richer final_answer grounded in operational_notes.read_notes and file_memory: "
            "cover workflow/entrypoint, core candidates, concrete file roles, validation/problems "
            "or limits, and cite concrete repo-relative paths. Do not call tools unless a new "
            "evidence gap is named."
        ),
    }


_ALLOWED_FINAL_QUALITY_ROUTE_TOOLS = {
    "repo_read",
    "repo_semantic_search",
    "repo_rg_search",
    "repo_search",
    "repo_list_files",
}

_ALLOWED_FINAL_QUALITY_ROUTE_ARGS = {
    "repo_read": {
        "path",
        "paths",
        "line",
        "line_start",
        "line_count",
        "start_line",
        "end_line",
        "before",
        "after",
        "max_chars",
    },
    "repo_semantic_search": {
        "query",
        "path",
        "limit",
        "top_k",
        "max_results",
        "candidate_limit",
        "rerank",
        "reindex",
        "max_chunk_chars",
    },
    "repo_rg_search": {"query", "pattern", "path", "max_results", "context"},
    "repo_search": {"query", "pattern", "symbol", "path", "max_results"},
    "repo_list_files": {"path", "limit", "suffix", "glob", "max_files"},
}


def repo_analysis_final_answer_model_quality_request(
    final_answer: str,
    contract: dict[str, Any],
    *,
    goal: str,
) -> dict[str, Any]:
    """Build the LLM judge request for repo-analysis final validation."""
    return {
        "system": (
            "You are the final-quality judge for a repository-analysis agentic loop. "
            "Return strict JSON only. You decide whether the proposed final answer is acceptable "
            "or whether the planner must continue. The controller will only enforce your JSON. "
            "Do not call hidden preplanner RAG. If more semantic discovery is needed, route to "
            "the normal planner tool repo_semantic_search. If a concrete file/window is missing, "
            "route to repo_read. Do not invent reads or claim coverage not present in the contract."
        ),
        "user_payload": {
            "schema": "repo_analysis_final_model_quality_request.v1",
            "task": "judge_repo_analysis_final_answer_or_route_next_tool",
            "goal": str(goal or ""),
            "final_answer": _clip_text(final_answer, 16000),
            "contract_summary": _final_quality_contract_summary(contract),
            "semantic_audit_guidance": audit_guidance_for_goal(goal),
            "final_quality_judge_role_guidance": role_guidance_for_goal("final_quality_judge", goal),
            "goal_requests_semantic_audit": goal_requests_semantic_audit(goal),
            "decision_rules": [
                "Accept only if the final answer is grounded in verified repo evidence and answers the goal.",
                "Reject if it declares unread/truncated/missing files that are needed to answer the goal.",
                "Reject if it claims complete analysis while naming unresolved coverage limits.",
                "Reject if it says no duplication, no semantic drift, or no regression risk from shallow owner reads.",
                "Reject if it uses speculative language such as probably/probabilmente for concrete code ownership claims.",
                "Reject if it asks the user whether to generate a final, diff, or patch instead of answering the current request.",
                "Reject if it cites repo-relative paths that are not present in verified reads, admissible read paths, or owner candidates.",
                "Reject if candidate_next_actions or required_next_tool_call still names a required repo_read/repo_semantic_search route and the final does not explicitly state a bounded limitation.",
                "Reject if it reports global RAG missing only because intrinsic_context had no retrieved_rag_chunks; repo_semantic_search is the planner RAG tool.",
                "Do not choose required_next_tool_call for a repo_read/search route already present in verified_content_reads, successful_repo_read_paths, or stale_required_next_tool_calls.",
                "If broad discovery is still needed, choose required_next_tool_call.tool=repo_semantic_search with a concrete query.",
                "If specific unread/truncated paths are named, choose required_next_tool_call.tool=repo_read for those paths or a focused window.",
                "required_next_missing_evidences is path-only: include only concrete repo-relative paths already present in contract_summary path fields.",
                "Do not ask to repo_read files already present in verified_content_reads or successful_repo_read_paths.",
                "For headings, metrics, missing sections, or conceptual gaps, use required_next_progress/required_next_output_sections, or repo_semantic_search with a concrete query.",
                "If enough evidence exists but the prose is inconsistent, reject and require a corrected final without a tool call.",
            ],
            "allowed_required_next_tools": sorted(_ALLOWED_FINAL_QUALITY_ROUTE_TOOLS),
            "required_json_shape": {
                "decision": "accept | reject | continue_required",
                "ok": True,
                "violations": [{"code": "short_machine_code", "reason": "human reason"}],
                "required_next_progress": "short instruction for the next planner turn",
                "required_next_output_sections": ["Concrete file-level evidence", "Coverage limits and validation status"],
                "required_next_missing_evidences": ["repo-relative concrete path"],
                "required_next_tool_call": {
                    "tool": "repo_semantic_search | repo_read | repo_rg_search | repo_search | repo_list_files",
                    "arguments": {"query": "concrete query or path args"},
                    "reason": "why this tool is the next needed step",
                },
                "confidence": 0.0,
            },
        },
    }


def _violation_code(value: Any) -> str:
    if isinstance(value, dict):
        raw = value.get("code") or value.get("violation") or value.get("reason")
    else:
        raw = value
    text = str(raw or "").strip()
    if not text:
        return ""
    text = re.sub(r"[^a-zA-Z0-9_:-]+", "_", text).strip("_").lower()
    return text[:120]


def _sanitize_required_next_tool_call(
    value: Any,
    contract: dict[str, Any],
    diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    tool = str(value.get("tool") or "").strip().lower()
    if tool not in _ALLOWED_FINAL_QUALITY_ROUTE_TOOLS:
        _record_invalid_required_next_tool_call(
            diagnostics,
            reason="final-quality proposed a required_next_tool_call tool outside the allowed route set",
        )
        return {}
    raw_args = value.get("arguments") if isinstance(value.get("arguments"), dict) else {}
    allowed_args = _ALLOWED_FINAL_QUALITY_ROUTE_ARGS.get(tool, set())
    args = {
        key: raw_args.get(key)
        for key in allowed_args
        if raw_args.get(key) not in (None, "", [], {})
    }
    out = {
        "tool": tool,
        "arguments": args,
    }
    invalid_paths: list[str] = []
    if tool in {"repo_semantic_search", "repo_rg_search", "repo_search"} and not (
        args.get("query") or args.get("pattern") or args.get("symbol") or args.get("needle") or args.get("text")
    ):
        _record_invalid_required_next_tool_call(
            diagnostics,
            reason=f"{tool} required_next_tool_call was missing query, pattern, symbol, needle, or text",
        )
        return {}
    if tool in {"repo_semantic_search", "repo_rg_search", "repo_search"}:
        query_value = args.get("query") or args.get("pattern") or args.get("symbol") or args.get("needle") or args.get("text")
        if not _search_query_is_concrete(query_value):
            _record_invalid_required_next_tool_call(
                diagnostics,
                reason=f"{tool} query looked like a heading, metric, violation label, or path token",
                query=query_value,
            )
            return {}
        known_paths = _known_repo_paths(contract if isinstance(contract, dict) else {})
        known_dirs = _known_repo_dirs(known_paths)
        path_token = _repo_rel_token(args.get("path")) if args.get("path") else ""
        if path_token and path_token not in known_paths and path_token not in known_dirs:
            invalid_paths.append(path_token)
            args.pop("path", None)
    if tool == "repo_read" and not (args.get("path") or args.get("paths")):
        _record_invalid_required_next_tool_call(
            diagnostics,
            reason="repo_read required_next_tool_call was missing path or paths",
        )
        return {}
    if tool == "repo_read":
        allowlist = _repo_read_path_allowlist(contract if isinstance(contract, dict) else {})
        raw_paths = args.get("paths") if isinstance(args.get("paths"), list) else [args.get("path")]
        valid_paths: list[str] = []
        invalid_paths: list[str] = []
        for raw_path in raw_paths:
            path = _allowed_concrete_repo_path(raw_path, allowlist)
            if path and path not in valid_paths:
                valid_paths.append(path)
            elif raw_path not in (None, "", [], {}):
                invalid_paths.append(str(raw_path))
        if not valid_paths:
            _record_invalid_required_next_tool_call(
                diagnostics,
                reason="repo_read required_next_tool_call contained no concrete unread admissible repo paths",
                paths=invalid_paths,
            )
            return {}
        args = {"paths": valid_paths[:12]}
        if invalid_paths:
            out["invalid_required_next_tool_call_paths"] = invalid_paths[:12]
    if tool == "repo_list_files":
        known_dirs = _known_repo_dirs(_known_repo_paths(contract if isinstance(contract, dict) else {}))
        path_token = _repo_rel_token(args.get("path") or ".") or "."
        if path_token != "." and (_route_token_is_prose_or_metric(path_token) or path_token not in known_dirs):
            _record_invalid_required_next_tool_call(
                diagnostics,
                reason="repo_list_files path was not a known concrete repo directory",
                paths=[path_token],
            )
            return {}
        args["path"] = path_token
    if invalid_paths and "invalid_required_next_tool_call_paths" not in out:
        out["invalid_required_next_tool_call_paths"] = invalid_paths[:12]
    reason = str(value.get("reason") or "").strip()
    if reason:
        out["reason"] = _clip_text(reason, 500)
    if bool(value.get("allow_only_if_missing_evidence")):
        out["allow_only_if_missing_evidence"] = True
    out["source"] = "repo_analysis_final_model_quality"
    out["arguments"] = _normalize_required_next_tool_call_paths(tool, args)
    return out


def _sanitize_required_next_output_sections(value: Any) -> list[str]:
    sections = value if isinstance(value, list) else []
    out: list[str] = []
    for item in sections:
        text = str(item or "").strip()
        if text and text not in out:
            out.append(text)
    return out[:12]


def _sanitize_required_next_missing_evidences(value: Any, contract: dict[str, Any]) -> list[str]:
    items = value if isinstance(value, list) else []
    allowlist = _repo_read_path_allowlist(contract if isinstance(contract, dict) else {})
    out: list[str] = []
    for item in items:
        if isinstance(item, (list, tuple, dict)):
            continue
        text = _allowed_concrete_repo_path(item, allowlist)
        if text and text not in out:
            out.append(text)
    return out[:24]


def sanitize_repo_analysis_final_model_quality(
    value: Any,
    contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Normalize the model judge response; invalid model output rejects final."""
    base = {
        "schema": "repo_analysis_final_model_quality.v1",
        "model_decision_available": False,
        "ok": False,
        "decision": "invalid",
        "violations": ["repo_analysis_final_model_quality_invalid"],
        "required_next_progress": (
            "Final answer quality requires a valid model judge decision. Retry final quality "
            "or continue with an evidence-bound repo_semantic_search/repo_read if a concrete gap is known."
        ),
    }
    if not isinstance(value, dict):
        return base
    decision = str(value.get("decision") or "").strip().lower()
    if decision not in {"accept", "reject", "continue_required"}:
        return {**base, "raw_decision": _compact_mapping(value, text_limit=500, list_limit=6)}

    raw_violations = value.get("violations")
    violation_items = raw_violations if isinstance(raw_violations, list) else []
    violations = [code for code in (_violation_code(item) for item in violation_items) if code]
    ok = decision == "accept" and value.get("ok") is not False
    if not ok and not violations:
        violations = ["repo_analysis_final_model_rejected"]
    if ok:
        violations = []
    required_next_progress = str(value.get("required_next_progress") or "").strip()
    contract = contract if isinstance(contract, dict) else {}
    invalid_required_next_tool_call: dict[str, Any] = {}
    required_next_tool_call = _sanitize_required_next_tool_call(
        value.get("required_next_tool_call"),
        contract,
        invalid_required_next_tool_call,
    )
    required_next_output_sections = _sanitize_required_next_output_sections(
        value.get("required_next_output_sections")
    )
    if not ok and not required_next_output_sections:
        required_next_output_sections = _required_next_output_sections(
            violations,
            {
                "read_note_count": 0,
                "path_hits": 0,
                "min_path_hits": 0,
                "unverified_path_tokens": [],
                "hard_pending_read_or_search_actions": [],
            },
        )
    required_next_missing_evidences = _sanitize_required_next_missing_evidences(
        value.get("required_next_missing_evidences"),
        contract,
    )
    if not ok and not required_next_missing_evidences:
        required_next_missing_evidences = _required_next_missing_evidences(
            violations,
            {
                "unverified_path_tokens": [],
                "read_note_count": 0,
            },
            [],
            {},
        )
    if not ok and not required_next_progress:
        required_next_progress = (
            "Model final-quality judge rejected the final answer. Continue with the "
            "required_next_tool_call if present; otherwise rewrite the final answer from verified evidence."
        )
    if required_next_tool_call and not required_next_progress:
        required_next_progress = str(required_next_tool_call.get("reason") or "")
    out = {
        "schema": "repo_analysis_final_model_quality.v1",
        "model_decision_available": True,
        "ok": ok,
        "decision": decision,
        "violations": violations,
        "required_next_progress": _clip_text(required_next_progress, 1000),
        "required_next_tool_call": required_next_tool_call,
        "confidence": value.get("confidence"),
        "required_next_output_sections": required_next_output_sections,
        "required_next_missing_evidences": required_next_missing_evidences,
        "raw_decision": _compact_mapping(value, text_limit=500, list_limit=6),
    }
    if not required_next_tool_call:
        out.pop("required_next_tool_call", None)
    for key in (
        "invalid_required_next_tool_call_paths",
        "invalid_required_next_tool_call_query",
        "invalid_required_next_tool_call_reason",
    ):
        if invalid_required_next_tool_call.get(key) not in (None, "", [], {}):
            out[key] = invalid_required_next_tool_call.get(key)
    return out


def repo_analysis_final_answer_too_shallow(
    final_answer: str,
    contract: dict[str, Any],
) -> bool:
    return not repo_analysis_final_answer_quality(final_answer, contract).get("ok")
