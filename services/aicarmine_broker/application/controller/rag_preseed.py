"""Loop-start Codex RAG reindex and ranked controller preseed helpers."""

from __future__ import annotations

import hashlib
import importlib
import json
import logging
import os
import re
import sqlite3
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from ..evidence.goal_classifier import (
    goal_operational_intent_text,
    semantic_goal_classification,
)
from ..evidence.audit_guidance import (
    audit_guidance_for_goal,
    audit_owner_targets,
    role_guidance_for_goal,
)
from ..evidence.repo_path_policy import (
    repo_doc_or_config,
    repo_existing_file,
    repo_readable_evidence_file,
    read_candidate_sort_key,
)
from ..shared.path_tokens import repo_rel_token


SafeRelPath = Callable[[str], str]
PostJson = Callable[[str, dict[str, Any], int], dict[str, Any]]

logger = logging.getLogger(__name__)

_STOPWORDS = {
    "a", "ad", "ai", "al", "alla", "anche", "and", "are", "che", "con",
    "da", "del", "della", "di", "do", "e", "for", "il", "in", "is",
    "la", "le", "lo", "nel", "non", "of", "on", "or", "per", "repo",
    "repository", "su", "the", "to", "un", "una", "what",
}

_ANCHOR_CANDIDATES = (
    "AGENTS.md",
    "README.md",
    "pyproject.toml",
    "package.json",
    "requirements.txt",
)

_CODE_SUFFIXES = (
    ".py", ".ps1", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".cpp", ".c",
    ".h", ".cs", ".java", ".kt", ".swift", ".sh", ".bat", ".cmd",
)

_CONFIG_SUFFIXES = (".toml", ".json", ".yaml", ".yml", ".ini", ".cfg")
_DOC_SUFFIXES = (".md", ".txt", ".rst")
_EXPLICIT_PATH_SUFFIXES = tuple(sorted(set((*_CODE_SUFFIXES, *_CONFIG_SUFFIXES, *_DOC_SUFFIXES))))
_EXPLICIT_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9_./\\:-])"
    r"(?:[A-Za-z]:[\\/])?"
    r"(?:[A-Za-z0-9_.@+-]+[\\/])*"
    r"[A-Za-z0-9_.@+-]+"
    r"\.(?:" + "|".join(re.escape(suffix.lstrip(".")) for suffix in _EXPLICIT_PATH_SUFFIXES) + r")"
    r"(?![A-Za-z0-9_./\\:-])",
    re.IGNORECASE,
)
_DEFAULT_RERANK_URL = "http://127.0.0.1:3550/v3/rerank"
_DEFAULT_RERANK_MODEL = "BAAI/bge-reranker-v2-m3"
_RERANK_RESPONSE_BYTES = 64_000
_CODE_SECURITY_EXPANSION_TERMS = (
    "def", "class", "import", "config", "settings", "validate", "validation",
    "error", "exception", "request", "response", "service", "provider",
    "client", "database", "security", "auth",
)


class ControllerRagHTTPError(RuntimeError):
    """Typed HTTP error from the optional controller RAG reranker."""

    def __init__(self, *, status: int, reason: str, body_preview: str) -> None:
        super().__init__(f"controller RAG reranker HTTP {status}: {reason}")
        self.status = status
        self.reason = reason
        self.body_preview = body_preview


class ControllerRagIndexerLoadError(ImportError):
    """Typed indexer load failure with operator-facing diagnostics."""

    def __init__(self, message: str, *, diagnostics: list[dict[str, Any]]) -> None:
        super().__init__(message)
        self.diagnostics = diagnostics

def _low_signal_ranked_path(path: str) -> bool:
    low = repo_rel_token(path).lower()
    name = low.rsplit("/", 1)[-1]
    return (
        "/__pycache__/" in low
        or "/backup/" in low
        or "/backups/" in low
        or "backup" in name
        or name.endswith((".bak", ".orig", ".tmp"))
    )


def _top_dir(path: str) -> str:
    p = repo_rel_token(path).strip("/")
    return p.split("/", 1)[0] if "/" in p else p


def _path_family(path: str) -> str:
    parts = [part for part in repo_rel_token(path).strip("/").split("/") if part]
    return "/".join(parts[:2]) if len(parts) >= 2 else (parts[0] if parts else "")


def _code_security_analysis_goal(goal: str) -> bool:
    low = goal_operational_intent_text(goal).lower()
    code_terms = (
        "codice", "code", "sorgente", "source", "semantiche", "semantic",
        "antipattern", "anti-pattern", "code smell", "qualit",
    )
    critique_terms = (
        "critic", "vulnerabil", "sicurezza", "security", "bug", "errori",
        "violazioni", "best practice", "audit", "review", "analisi", "analizza",
    )
    code_match = any(
        bool(re.search(r"(?<![a-z0-9_])code(?![a-z0-9_])", low))
        if term == "code"
        else term in low
        for term in code_terms
    )
    return code_match and any(term in low for term in critique_terms)


def _preplanner_goal_class(goal: str) -> str:
    classification = semantic_goal_classification(
        goal,
        repo_analysis=_code_security_analysis_goal(goal),
    )
    deliverable_class = str(classification.get("class") or "").strip()
    if deliverable_class == "apply_write":
        return "apply_write"
    if deliverable_class == "code_product_report":
        return "code_product_report"
    if classification.get("requires_code_security_coverage") or _code_security_analysis_goal(goal):
        return "code_security_analysis"
    low = goal_operational_intent_text(goal).lower()
    if any(term in low for term in (
        "analizza", "analisi", "analysis", "review", "audit", "critic",
        "ricerca", "cerca", "trova", "find", "search",
    )):
        return "repo_analysis"
    return "generic"


def _preplanner_goal_class_from_intent(value: Any, *, fallback_goal_class: str) -> str | None:
    raw = re.sub(r"[^a-z0-9_ -]+", " ", str(value or "").strip().lower())
    normalized = re.sub(r"[\s-]+", "_", raw).strip("_")
    if not normalized:
        return None
    if normalized in {
        "apply",
        "apply_patch",
        "apply_write",
        "edit",
        "modify",
        "write",
        "write_apply",
        "fix_apply",
    }:
        return "apply_write"
    if normalized in {
        "code_product",
        "code_product_report",
        "diff",
        "diff_report",
        "patch_report",
        "proposal",
        "report_only_code_product",
        "unified_diff",
    }:
        return "code_product_report"
    if normalized in {"code_security", "code_security_analysis", "security_analysis"}:
        return "code_security_analysis"
    if normalized in {"analysis", "analysis_only", "read", "read_only", "review"}:
        return "analysis_only"
    if normalized == "repo_analysis":
        return "repo_analysis"
    if normalized in {"generic", "unknown", "unspecified"}:
        return "generic"
    return None


def _boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on", "si", "sì"}


def _optional_boolish(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "y", "on", "si", "sì"}:
        return True
    if normalized in {"0", "false", "no", "n", "off", "non", "none"}:
        return False
    return None


def _first_present(mapping: Mapping[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in mapping:
            return mapping.get(key)
    return None


def _sanitize_preplanner_semantic_intent(value: Any, *, goal: str) -> dict[str, Any]:
    fallback_classification = semantic_goal_classification(
        goal,
        repo_analysis=_code_security_analysis_goal(goal),
    )
    fallback_goal_class = _preplanner_goal_class(goal)
    base: dict[str, Any] = {
        "schema": "agentic_loop_preplanner_semantic_intent.v1",
        "source": "missing_planner_query_plan",
        "accepted": False,
        "goal_class": "",
        "static_goal_class_hint": fallback_goal_class,
        "fallback_goal_class": fallback_goal_class,
        "fallback_semantic_class": str(fallback_classification.get("class") or ""),
        "negative_write_constraints_present": bool(
            fallback_classification.get("negative_write_constraints_present")
        ),
    }
    if not isinstance(value, Mapping):
        return base

    raw_class = (
        value.get("goal_class")
        or value.get("class")
        or value.get("mode")
        or value.get("intent")
        or value.get("operation")
    )
    planner_goal_class = _preplanner_goal_class_from_intent(
        raw_class,
        fallback_goal_class=fallback_goal_class,
    )
    if planner_goal_class is None:
        return {
            **base,
            "source": "planner_query_plan",
            "raw_class": _sanitize_query_text(raw_class),
            "invalid_reasons": ["semantic_intent_class_missing_or_unknown"],
        }

    if planner_goal_class in {"repo_analysis", "generic"} and _boolish(
        value.get("requires_code_security_coverage")
        or value.get("code_security")
        or value.get("security_analysis")
    ):
        planner_goal_class = "code_security_analysis"

    planner_read_only = _boolish(value.get("read_only"))
    planner_write_requested = _boolish(value.get("write_requested") or value.get("requires_write"))
    planner_apply_requested = _boolish(value.get("apply_requested") or value.get("requires_apply"))
    planner_code_product_requested = _optional_boolish(_first_present(
        value,
        (
            "code_product_requested",
            "diff_requested",
            "patch_requested",
            "code_edit_proposal_requested",
            "proposal_output_requested",
        ),
    ))
    planner_declares_no_write = planner_read_only and not planner_write_requested and not planner_apply_requested
    planner_requires_security = _boolish(
        value.get("requires_code_security_coverage")
        or value.get("code_security")
        or value.get("security_analysis")
    )
    guardrails: list[str] = []
    if planner_goal_class in {"analysis_only", "repo_analysis", "generic"} and planner_requires_security:
        planner_goal_class = "code_security_analysis"
        guardrails.append("planner_analysis_intent_promoted_to_code_security_analysis")
    if (
        fallback_goal_class == "apply_write"
        and planner_goal_class != "apply_write"
        and planner_declares_no_write
    ):
        guardrails.append("planner_read_only_intent_overrode_static_apply_fallback")
    if (
        fallback_goal_class == "code_product_report"
        and planner_goal_class != "code_product_report"
        and planner_declares_no_write
        and planner_code_product_requested is False
    ):
        guardrails.append("planner_read_only_intent_overrode_static_code_product_fallback")
    if (
        planner_goal_class == "code_product_report"
        and planner_code_product_requested is None
        and planner_declares_no_write
    ):
        planner_code_product_requested = True
        guardrails.append("planner_code_product_requested_inferred_from_code_product_report_intent")

    invalid_reasons: list[str] = []
    if planner_goal_class == "apply_write" and planner_declares_no_write:
        guardrails.append("planner_apply_write_without_positive_goal_evidence_downgraded")
        invalid_reasons.append("apply_write_conflicts_with_read_only_no_write_flags")
    if planner_goal_class != "apply_write" and (planner_write_requested or planner_apply_requested):
        invalid_reasons.append("non_apply_goal_conflicts_with_write_or_apply_flags")
    if planner_goal_class == "code_product_report" and planner_apply_requested:
        invalid_reasons.append("code_product_report_must_not_request_apply")
    if planner_goal_class == "code_product_report" and planner_code_product_requested is not True:
        invalid_reasons.append("code_product_report_requires_positive_code_product_requested_flag")
    if planner_goal_class != "code_product_report" and planner_code_product_requested is True:
        invalid_reasons.append("non_code_product_goal_conflicts_with_code_product_requested_flag")

    rationale = _sanitize_query_text(value.get("rationale") or value.get("reason"))
    return {
        **base,
        "source": "planner_query_plan",
        "accepted": not invalid_reasons,
        "goal_class": planner_goal_class if not invalid_reasons else "",
        "planner_goal_class": planner_goal_class,
        "raw_class": _sanitize_query_text(raw_class),
        "requires_code_security_coverage": planner_requires_security,
        "read_only": _boolish(value.get("read_only")),
        "write_requested": planner_write_requested,
        "apply_requested": planner_apply_requested,
        "code_product_requested": bool(planner_code_product_requested),
        "code_product_requested_present": planner_code_product_requested is not None,
        "rationale": rationale,
        "invalid_reasons": invalid_reasons,
        "guardrails": guardrails,
    }


def _query_plan_max_queries() -> int:
    return _env_int("AICARMINE_CONTROLLER_RAG_QUERY_PLANNER_MAX_QUERIES", 5, minimum=1, maximum=8)


def _sanitize_query_text(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if not text:
        return ""
    return text[:180]


def _extract_query_plan_response_text(response: Mapping[str, Any]) -> str:
    raw_message = response.get("message")
    message: Mapping[str, Any] = raw_message if isinstance(raw_message, Mapping) else {}
    return str(
        response.get("response")
        or message.get("content")
        or response.get("partial_content")
        or ""
    )


def _parse_json_object_diagnostics(text: str) -> dict[str, Any]:
    raw_input = str(text or "")
    raw = raw_input.strip()
    diagnostics: dict[str, Any] = {
        "schema": "controller_rag_json_object_parse_diagnostics.v1",
        "ok": False,
        "raw_response_chars": len(raw_input),
        "stripped_chars": len(raw),
    }
    if not raw:
        return {**diagnostics, "error_type": "empty"}
    try:
        decoded = json.loads(raw)
        if isinstance(decoded, dict):
            return {**diagnostics, "ok": True, "decoded": decoded, "recovered_from_embedded_object": False}
        return {**diagnostics, "error_type": "not_json_object", "decoded_type": type(decoded).__name__}
    except json.JSONDecodeError as exc:
        full_decode_error = {
            "error_type": "json_decode_error",
            "error": str(exc)[:500],
            "line": exc.lineno,
            "column": exc.colno,
            "position": exc.pos,
        }
    except ValueError as exc:
        full_decode_error = {"error_type": type(exc).__name__, "error": str(exc)[:500]}
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0:
        return {**diagnostics, **full_decode_error, "error_type": "no_json_object"}
    if end <= start:
        return {**diagnostics, **full_decode_error}
    try:
        decoded = json.loads(raw[start:end + 1])
        if isinstance(decoded, dict):
            return {
                **diagnostics,
                "ok": True,
                "decoded": decoded,
                "recovered_from_embedded_object": True,
                "embedded_start": start,
                "embedded_end": end + 1,
            }
        return {**diagnostics, "error_type": "not_json_object", "decoded_type": type(decoded).__name__}
    except json.JSONDecodeError as exc:
        return {
            **diagnostics,
            "error_type": "json_decode_error",
            "error": str(exc)[:500],
            "line": exc.lineno,
            "column": exc.colno,
            "position": exc.pos,
            "full_decode_error": full_decode_error,
        }
    except ValueError as exc:
        return {**diagnostics, "error_type": type(exc).__name__, "error": str(exc)[:500]}


def _parse_json_object(text: str) -> dict[str, Any] | None:
    diagnostics = _parse_json_object_diagnostics(text)
    decoded = diagnostics.get("decoded") if diagnostics.get("ok") is True else None
    return decoded if isinstance(decoded, dict) else None


# Re-export for use in loop.py
def _query_plan_continue_without_model(
    report: Mapping[str, Any],
    *,
    reason: str,
    attempt: int,
    planner_model: str,
    timeout_seconds: int,
    response: Mapping[str, Any] | None = None,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    response = response if isinstance(response, Mapping) else {}
    result: dict[str, Any] = {
        **dict(report),
        "ok": False,
        "status": "unavailable" if "unavailable" in reason or "request_failed" in reason else "failed",
        "reason": reason,
        "planner_model": planner_model,
        "timeout_seconds": timeout_seconds,
        "attempts": attempt,
        "semantic_intent_required": False,
        "semantic_intent_available": False,
        "preplanner_rag_can_continue": True,
        "fallback_scope": "deterministic_rag_preseed_only",
        "controller_did_not_make_semantic_decision": True,
    }
    for key in ("backend_timeout", "backend_unreachable", "error_type", "error", "network_reason_type"):
        if response.get(key) not in (None, "", [], {}):
            result[key] = response.get(key)
    if extra:
        result.update({key: value for key, value in extra.items() if value not in (None, "", [], {})})
    return result


def _repair_preplanner_query_plan_json(
    *,
    post_json: PostJson,
    planner_url: str,
    planner_model: str,
    keep_alive: str,
    raw_response_text: str,
    parse_diagnostics: Mapping[str, Any],
    goal: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    repair_timeout = _env_int(
        "AICARMINE_CONTROLLER_RAG_QUERY_PLANNER_REPAIR_TIMEOUT_SECONDS",
        min(30, max(10, int(timeout_seconds or 10))),
        minimum=3,
        maximum=60,
    )
    repair_payload = {
        "model": planner_model,
        "stream": False,
        "keep_alive": keep_alive,
        "think": False,
        "format": "json",
        "messages": [
            {
                "role": "system",
                "content": (
                    "Repair malformed repository RAG query-plan JSON. Return only strict JSON. "
                    "Do not solve the user's task and do not call tools."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "schema": "agentic_loop_preplanner_rag_query_plan_repair_request.v1",
                        "goal": str(goal or ""),
                        "raw_response": str(raw_response_text or "")[:12000],
                        "parse_diagnostics": {
                            key: parse_diagnostics.get(key)
                            for key in ("error_type", "error", "line", "column", "position", "raw_response_chars")
                            if parse_diagnostics.get(key) not in (None, "", [], {})
                        },
                        "required_json_shape": {
                            "semantic_intent": {
                                "class": (
                                    "analysis_only | code_security_analysis | repo_analysis | "
                                    "code_product_report | apply_write | generic"
                                ),
                                "read_only": True,
                                "write_requested": False,
                                "apply_requested": False,
                                "code_product_requested": False,
                                "requires_code_security_coverage": False,
                                "rationale": "short reason",
                            },
                            "queries": [{
                                "query": "target file, owner symbol, module family, or concrete runtime phrase",
                                "purpose": "why this target family is needed",
                                "target_kind": (
                                    "owner_source | validator | controller | tool_surface | prompt | "
                                    "public_payload | legacy_wrapper | contract_doc | test"
                                ),
                            }],
                        },
                    },
                    ensure_ascii=False,
                    default=str,
                ),
            },
        ],
        "options": {
            "temperature": 0,
            "num_predict": _env_int(
                "AICARMINE_CONTROLLER_RAG_QUERY_PLANNER_REPAIR_NUM_PREDICT",
                700,
                minimum=128,
                maximum=2048,
            ),
        },
    }
    response = post_json(planner_url, repair_payload, repair_timeout)
    if not isinstance(response, Mapping):
        return {
            "ok": False,
            "repair_attempted": True,
            "repair_status": "failed",
            "repair_reason": "non_mapping_response",
            "repair_timeout_seconds": repair_timeout,
        }
    if response.get("backend_unreachable") or response.get("backend_timeout") or response.get("error"):
        return {
            "ok": False,
            "repair_attempted": True,
            "repair_status": "unavailable",
            "repair_reason": "repair_request_failed",
            "repair_error_type": response.get("error_type"),
            "repair_error": response.get("error"),
            "repair_backend_timeout": response.get("backend_timeout"),
            "repair_backend_unreachable": response.get("backend_unreachable"),
            "repair_timeout_seconds": repair_timeout,
        }
    repair_raw_text = _extract_query_plan_response_text(response)
    repair_parse = _parse_json_object_diagnostics(repair_raw_text)
    decoded = repair_parse.get("decoded") if repair_parse.get("ok") is True else None
    sanitized = _sanitize_preplanner_query_plan(decoded, goal=goal)
    sanitized.update({
        "repair_attempted": True,
        "repair_status": "ready" if sanitized.get("ok") else "invalid",
        "repair_timeout_seconds": repair_timeout,
        "repair_raw_response_chars": len(repair_raw_text),
    })
    if not sanitized.get("ok"):
        sanitized["repair_raw_response_preview"] = repair_raw_text[:1000]
        if repair_parse.get("ok") is not True:
            sanitized["repair_json_parse_error_type"] = repair_parse.get("error_type")
            if repair_parse.get("error") not in (None, "", [], {}):
                sanitized["repair_json_parse_error"] = repair_parse.get("error")
    return sanitized


def _sanitize_preplanner_query_plan(value: Mapping[str, Any] | None, *, goal: str) -> dict[str, Any]:
    max_queries = _query_plan_max_queries()
    static_goal_class_hint = _preplanner_goal_class(goal)
    report: dict[str, Any] = {
        "schema": "agentic_loop_preplanner_rag_query_plan.v1",
        "ok": False,
        "status": "unavailable",
        "source": "none",
        "goal_class": "",
        "static_goal_class_hint": static_goal_class_hint,
        "semantic_intent": _sanitize_preplanner_semantic_intent(None, goal=goal),
        "queries": [],
    }
    if not isinstance(value, Mapping):
        return report
    source = str(value.get("source") or "planner")
    semantic_intent = _sanitize_preplanner_semantic_intent(value.get("semantic_intent"), goal=goal)
    goal_class = str(semantic_intent.get("goal_class") or "")
    semantic_intent_usable = bool(
        semantic_intent.get("source") == "planner_query_plan"
        and semantic_intent.get("accepted") is True
        and goal_class
    )
    raw_queries = value.get("queries")
    queries: list[dict[str, str]] = []
    if isinstance(raw_queries, list):
        for item in raw_queries:
            if isinstance(item, Mapping):
                query = _sanitize_query_text(item.get("query") or item.get("text"))
                purpose = _sanitize_query_text(item.get("purpose"))
                target_kind = _sanitize_query_text(item.get("target_kind") or item.get("kind"))
            else:
                query = _sanitize_query_text(item)
                purpose = ""
                target_kind = ""
            if not query:
                continue
            if query.lower() in {q["query"].lower() for q in queries}:
                continue
            query_item = {"query": query, "purpose": purpose}
            if target_kind:
                query_item["target_kind"] = target_kind
            queries.append(query_item)
            if len(queries) >= max_queries:
                break
    if not semantic_intent_usable:
        return {
            **report,
            "status": "invalid_semantic_intent",
            "source": source,
            "semantic_intent": semantic_intent,
            "reason": "planner_query_plan_missing_invalid_or_inconsistent_semantic_intent",
            "queries": queries,
        }
    if not queries:
        return {
            **report,
            "ok": True,
            "status": "empty",
            "source": source,
            "goal_class": goal_class,
            "semantic_intent": semantic_intent,
            "reason": str(value.get("reason") or "no_queries"),
        }
    return {
        **report,
        "ok": True,
        "status": "ready",
        "source": source,
        "goal_class": goal_class,
        "semantic_intent": semantic_intent,
        "queries": queries,
    }


def controller_preplanner_rag_query_plan(
    goal: str,
    *,
    post_json: PostJson,
    planner_url: str,
    planner_model: str,
    keep_alive: str,
    num_ctx: int,
    timeout: int,
) -> dict[str, Any]:
    """Ask the planner for bounded RAG queries before ranking; never dispatch repo tools."""

    report: dict[str, Any] = {
        "schema": "agentic_loop_preplanner_rag_query_plan.v1",
        "ok": False,
        "status": "skipped",
        "source": "planner",
        "semantic_intent_required": True,
        "queries": [],
    }
    if not _env_bool("AICARMINE_CONTROLLER_RAG_QUERY_PLANNER_ENABLED", True):
        return {**report, "status": "failed", "reason": "semantic_intent_preplanner_disabled"}
    query_planner_num_ctx = _env_int_optional(
        "AICARMINE_CONTROLLER_RAG_QUERY_PLANNER_NUM_CTX",
        minimum=2048,
    )
    report["planner_num_ctx"] = query_planner_num_ctx
    report["planner_num_ctx_source"] = (
        "AICARMINE_CONTROLLER_RAG_QUERY_PLANNER_NUM_CTX"
        if query_planner_num_ctx is not None
        else "ollama_default_or_modelfile"
    )

    static_goal_class_hint = _preplanner_goal_class(goal)
    focus = [
        "classify semantic_intent from the goal meaning before choosing queries",
        "prefer concrete owner source modules, validators, dispatchers, prompt builders, and public payload surfaces",
        "include wrappers or legacy mirrors only when they can diverge from an owner implementation",
        "use docs/contracts as secondary evidence unless the goal explicitly asks for documentation contracts",
    ]
    avoid = [
        "copying static_goal_class_hint as the final intent",
        "generic architecture discovery when a semantic/code audit is requested",
        "documentation-only or contract-only searches when source-code owners are needed",
        "abstract search phrases that name concepts but not concrete runtime owners",
        "test-only or fixture-only queries unless they verify a specific suspected owner rule",
    ]
    query_style = "short concrete owner, symbol, module, or target-file phrases"
    strategy_by_semantic_intent = {
        "apply_write": [
            "explicit target file names and likely aliases",
            "patch anchors and old text phrases",
            "owner source files that must be edited",
            "nearby tests or contracts only when they constrain the edit",
        ],
        "code_product_report": [
            "explicit target file names and likely aliases",
            "diff or refactor proposal anchors",
            "owner source files that define the proposed change",
            "nearby tests or contracts only when they constrain the report",
        ],
        "code_security_analysis": [
            "entrypoints and controllers",
            "request/input validation",
            "error and exception handling",
            "security/auth/secrets/database/client code",
            "core services and provider logic",
        ],
        "repo_analysis": [
            "entrypoints and core owners",
            "validator/controller/tool-surface/prompt/public-payload owner modules",
            "legacy wrappers or mirrors that may clone owner behavior",
            "runtime evidence and owner contracts for the audited behavior",
        ],
        "analysis_only": [
            "concrete owner source modules needed to answer the analysis",
            "validator/controller/tool-surface/prompt/public-payload owner modules when loop semantics are involved",
            "legacy wrappers or mirrors only as comparison targets",
        ],
        "generic": [
            "files named directly by the user",
            "project entrypoints and owner contracts",
            "small target-candidate queries for a ranker",
        ],
    }
    semantic_audit_guidance = audit_guidance_for_goal(goal)
    semantic_audit_search_contract = {
        "trigger": (
            "When the goal asks about semantic inconsistencies, regression risk, duplicate logic, "
            "layer drift, hidden guards, or repeated local implementations."
        ),
        "shared_guidance": semantic_audit_guidance,
        "required_targets": [
            "current owner source modules for the loop or feature under review",
            "validator/controller/tool-surface/prompt/public-payload modules when planner semantics are involved",
            "legacy wrapper or compatibility facade only after at least one current owner-source query",
            "runtime evidence contracts and owner modules that would reveal divergence",
        ],
        "invalid_primary_targets": [
            "README/AGENTS as the only evidence",
            "contract protocol stubs as the only source-code evidence",
            "generated or copied legacy files without a current owner comparison",
        ],
        "query_rule": (
            "Each query must be a concrete search phrase for a readable target family. "
            "Attach target_kind so the controller and operator can audit the planned coverage."
        ),
    }

    max_queries = _query_plan_max_queries()
    system = (
        "You are a repository RAG query planner. Return only strict JSON. "
        "Do not call tools. Do not answer the user's task. "
        "Choose small, precise search queries that help a ranker select concrete target files."
    )
    user_payload = {
        "schema": "agentic_loop_preplanner_rag_query_plan_request.v1",
        "goal": str(goal or ""),
        "static_goal_class_hint": static_goal_class_hint,
        "static_hint_is_not_authoritative": True,
        "constraints": {
            "max_queries": max_queries,
            "query_style": query_style,
            "focus": focus,
            "avoid": avoid,
            "strategy_by_semantic_intent": strategy_by_semantic_intent,
            "semantic_audit_guidance": semantic_audit_guidance,
            "preplanner_role_guidance": role_guidance_for_goal("preplanner", goal),
            "semantic_audit_search_contract": semantic_audit_search_contract,
            "semantic_intent_classes": [
                "analysis_only",
                "code_security_analysis",
                "repo_analysis",
                "code_product_report",
                "apply_write",
                "generic",
            ],
            "intent_rules": [
                "Classify the requested operational mode from meaning, not keyword presence.",
                "static_goal_class_hint is diagnostic only; do not copy it unless the goal meaning independently supports it.",
                "Negated or forbidden actions are constraints, not requested actions.",
                "Tool names inside a negative constraint are not evidence that the tool should be used.",
                "Use apply_write only when the user positively asks to modify/apply/write files.",
                "Use code_product_report for requested patch/diff/proposal output that must not be applied.",
                "For code_product_report, semantic_intent.code_product_requested must be true because the user positively asks for a diff, patch, code product, or code edit proposal as output.",
                "If the user forbids or negates code product, patch, diff, or proposal output, use analysis_only or repo_analysis and set code_product_requested=false.",
            ],
        },
        "required_json_shape": {
            "semantic_intent": {
                "class": "analysis_only | code_security_analysis | repo_analysis | code_product_report | apply_write | generic",
                "read_only": True,
                "write_requested": False,
                "apply_requested": False,
                "code_product_requested": False,
                "requires_code_security_coverage": False,
                "rationale": "short reason",
            },
            "queries": [{
                "query": "target file, owner symbol, module family, or concrete runtime phrase",
                "purpose": "why this target family is needed",
                "target_kind": (
                    "owner_source | validator | controller | tool_surface | prompt | "
                    "public_payload | legacy_wrapper | contract_doc | test"
                ),
            }]
        },
    }
    timeout_seconds = _env_int(
        "AICARMINE_CONTROLLER_RAG_QUERY_PLANNER_TIMEOUT_SECONDS",
        min(60, max(20, int(timeout or 60))),
        minimum=3,
        maximum=60,
    )

    def payload_for_attempt(attempt: int, previous: Mapping[str, Any] | None = None) -> dict[str, Any]:
        request_payload = dict(user_payload)
        if previous:
            request_payload["retry_after_invalid_semantic_intent"] = {
                "attempt": attempt,
                "previous_status": previous.get("status"),
                "previous_reason": previous.get("reason"),
                "previous_semantic_intent": previous.get("semantic_intent"),
                "required_fix": (
                    "Return strict JSON with semantic_intent.class, read_only, "
                    "write_requested, apply_requested, code_product_requested and rationale. "
                    "For code_product_report, code_product_requested must be true because the "
                    "user positively requested diff/patch/code-product output. Do not use "
                    "keyword fallbacks. Resolve contradictions from meaning."
                ),
            }
        options: dict[str, Any] = {
            "temperature": 0,
            "num_predict": _env_int(
                "AICARMINE_CONTROLLER_RAG_QUERY_PLANNER_NUM_PREDICT",
                512,
                minimum=128,
                maximum=2048,
            ),
        }
        if query_planner_num_ctx is not None:
            options["num_ctx"] = query_planner_num_ctx
        return {
            "model": planner_model,
            "stream": False,
            "keep_alive": keep_alive,
            "think": False,
            "format": "json",
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(request_payload, ensure_ascii=False, indent=2)},
            ],
            "options": options,
        }

    attempts = _env_int(
        "AICARMINE_CONTROLLER_RAG_QUERY_PLANNER_SEMANTIC_RETRIES",
        2,
        minimum=1,
        maximum=3,
    )
    last_sanitized: dict[str, Any] = {}
    for attempt in range(1, attempts + 1):
        response = post_json(planner_url, payload_for_attempt(attempt, last_sanitized), timeout_seconds)
        if not isinstance(response, Mapping):
            last_sanitized = {**report, "status": "failed", "reason": "non_mapping_response"}
            break
        if response.get("backend_unreachable") or response.get("backend_timeout") or response.get("error"):
            return _query_plan_continue_without_model(
                report,
                reason="planner_query_plan_request_failed",
                attempt=attempt,
                planner_model=planner_model,
                timeout_seconds=timeout_seconds,
                response=response,
            )
        raw_response_text = _extract_query_plan_response_text(response)
        parse_diagnostics = _parse_json_object_diagnostics(raw_response_text)
        decoded = parse_diagnostics.get("decoded") if parse_diagnostics.get("ok") is True else None
        if parse_diagnostics.get("ok") is True:
            sanitized = _sanitize_preplanner_query_plan(decoded, goal=goal)
        else:
            repaired = _repair_preplanner_query_plan_json(
                post_json=post_json,
                planner_url=planner_url,
                planner_model=planner_model,
                keep_alive=keep_alive,
                raw_response_text=raw_response_text,
                parse_diagnostics=parse_diagnostics,
                goal=goal,
                timeout_seconds=timeout_seconds,
            )
            sanitized = repaired if isinstance(repaired, dict) else _sanitize_preplanner_query_plan(None, goal=goal)
            sanitized.setdefault("repair_attempted", True)
            sanitized["original_json_parse_error_type"] = parse_diagnostics.get("error_type")
            if parse_diagnostics.get("error") not in (None, "", [], {}):
                sanitized["original_json_parse_error"] = parse_diagnostics.get("error")
        sanitized.update({
            "planner_model": planner_model,
            "timeout_seconds": timeout_seconds,
            "attempts": attempt,
            "semantic_intent_required": True,
        })
        if not sanitized.get("ok"):
            sanitized["raw_response_preview"] = raw_response_text[:1000]
            sanitized["raw_response_chars"] = len(raw_response_text)
            if parse_diagnostics.get("ok") is not True:
                sanitized["json_parse_error_type"] = parse_diagnostics.get("error_type")
                if parse_diagnostics.get("error") not in (None, "", [], {}):
                    sanitized["json_parse_error"] = parse_diagnostics.get("error")
        last_sanitized = sanitized
        if sanitized.get("ok"):
            return sanitized
    if last_sanitized.get("json_parse_error_type") or last_sanitized.get("original_json_parse_error_type"):
        return _query_plan_continue_without_model(
            report,
            reason="planner_query_plan_invalid_json_after_repair",
            attempt=attempts,
            planner_model=planner_model,
            timeout_seconds=timeout_seconds,
            extra={
                "status": "invalid_json",
                "raw_response_preview": last_sanitized.get("raw_response_preview"),
                "raw_response_chars": last_sanitized.get("raw_response_chars"),
                "json_parse_error_type": (
                    last_sanitized.get("json_parse_error_type")
                    or last_sanitized.get("original_json_parse_error_type")
                ),
                "json_parse_error": (
                    last_sanitized.get("json_parse_error")
                    or last_sanitized.get("original_json_parse_error")
                ),
                "repair_attempted": last_sanitized.get("repair_attempted"),
                "repair_status": last_sanitized.get("repair_status"),
                "repair_reason": last_sanitized.get("repair_reason"),
                "repair_json_parse_error_type": last_sanitized.get("repair_json_parse_error_type"),
                "repair_json_parse_error": last_sanitized.get("repair_json_parse_error"),
            },
        )
    return {
        **last_sanitized,
        "ok": False,
        "status": "failed",
        "reason": "planner_query_plan_semantic_intent_unusable_after_retry",
        "semantic_intent_required": True,
        "attempts": attempts,
    }


def _path_policy_score(path: str, *, goal: str, repo_root: Path) -> int:
    """Lower is better; keeps broad critique preseed on code, not doc/support crawls."""

    p = repo_rel_token(path)
    low = p.lower()
    name = low.rsplit("/", 1)[-1]
    score = 0
    code_security = _code_security_analysis_goal(goal)

    if name in {"__init__.py", "__main__.py"}:
        score += 70
    if "/fixtures/" in low or "/tests/fixtures/" in low or low.endswith("_fixture.json"):
        score += 45
    if (
        low.startswith(("test/", "tests/"))
        or "/test/" in low
        or "/tests/" in low
        or _top_dir(low).startswith("test")
        or name.startswith("test_")
        or name.endswith("_test.py")
    ):
        score += 36
    if any(part in low for part in ("/legacy/", "/archive/", "/generated/")):
        score += 24
    if low.startswith(("docs/", "examples/", "assets/")):
        score += 40
    if "/docs/" in low or "/doc/" in low:
        score += 28
    if "/_shared/" in low:
        score += 10

    if code_security:
        if low.startswith(("tools/", "scripting/")):
            score += 22
        if low.startswith(("ia_carmine/", "services/", "src/", "app/", "lib/")):
            score -= 18
        if low.endswith(_CODE_SUFFIXES):
            score -= 45
        elif low.endswith(_CONFIG_SUFFIXES) or repo_doc_or_config(p, repo_root=repo_root):
            score += 18
        else:
            score += 35
    elif low.endswith(_CODE_SUFFIXES):
        score -= 20

    if any(term in low for term in (
        "auth", "security", "secret", "credential", "token", "database", "db",
        "sql", "api", "route", "handler", "controller", "service", "provider",
        "client", "config", "settings", "validation", "validator", "operations",
        "workflow", "dispatch",
    )):
        score -= 18

    return score


def _select_ranked_paths(
    ranked: list[dict[str, Any]],
    *,
    goal: str,
    candidate_limit: int,
) -> list[dict[str, Any]]:
    if not ranked:
        return []
    code_security = _code_security_analysis_goal(goal)
    selected: list[dict[str, Any]] = []
    selected_keys: set[str] = set()
    top_counts: dict[str, int] = {}
    family_counts: dict[str, int] = {}
    top_limit = 2 if code_security else 3
    family_limit = 1 if code_security else 2

    def add(item: dict[str, Any], *, enforce_diversity: bool) -> None:
        path = str(item.get("path") or "")
        if not path or path in selected_keys or len(selected) >= candidate_limit:
            return
        top = _top_dir(path).lower()
        family = _path_family(path).lower()
        if enforce_diversity:
            effective_top_limit = (
                1
                if code_security and top in {"tools", "scripting"}
                else top_limit
            )
            if top and top_counts.get(top, 0) >= effective_top_limit:
                return
            if family and family_counts.get(family, 0) >= family_limit:
                return
        selected.append(item)
        selected_keys.add(path)
        top_counts[top] = top_counts.get(top, 0) + 1
        family_counts[family] = family_counts.get(family, 0) + 1

    if code_security:
        for item in ranked:
            if (
                str(item.get("path") or "").lower().endswith(_CODE_SUFFIXES)
                and int(item.get("path_policy_score") or 0) <= -20
            ):
                add(item, enforce_diversity=True)
    for item in ranked:
        if code_security and int(item.get("path_policy_score") or 0) > -20:
            continue
        add(item, enforce_diversity=True)
    if not code_security:
        for item in ranked:
            add(item, enforce_diversity=False)
    return selected[:candidate_limit]


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except Exception:
        return default
    return max(minimum, min(maximum, value))


def _env_int_optional(name: str, *, minimum: int) -> int | None:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return None
    try:
        value = int(raw)
    except Exception:
        return None
    return max(minimum, value)


def _env_float(name: str, default: float, *, minimum: float, maximum: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except Exception:
        return default
    return max(minimum, min(maximum, value))


def _default_controller_rag_db(repo_root: Path) -> Path:
    raw = os.environ.get("AICARMINE_CONTROLLER_RAG_DB") or os.environ.get("AICARMINE_RAG_DB")
    if raw:
        return Path(raw).resolve(strict=False)
    home = Path(os.environ.get("USERPROFILE") or Path.home())
    digest = hashlib.sha256(str(repo_root).lower().encode("utf-8", errors="replace")).hexdigest()[:16]
    return home / "AI" / "state" / "controller_rag" / digest / "code_rag.sqlite3"


def _rag_indexer_operator_hint(exc: Exception) -> str:
    if isinstance(exc, ControllerRagIndexerLoadError):
        return "Controller RAG indexer module could not be loaded; verify PYTHONPATH and codex_bridge dependencies."
    return "Controller RAG reindex failed; verify repo path, DB path, permissions and indexer configuration."


def _load_codex_rag_indexer() -> Any:
    errors: list[dict[str, Any]] = []
    required_attrs = (
        "DEFAULT_SUFFIXES",
        "MAX_FILE_BYTES_DEFAULT",
        "CHUNK_LINES_DEFAULT",
        "CHUNK_CHARS_DEFAULT",
        "SOURCE_GIT_DEFAULT",
        "MODE_DELTA",
        "build_index",
    )
    for module_name in ("codex_bridge.rag_index_repo", "services.codex_bridge.rag_index_repo"):
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError as exc:
            missing_name = str(getattr(exc, "name", "") or "")
            target_missing = bool(missing_name and (module_name == missing_name or module_name.startswith(missing_name + ".")))
            errors.append({
                "module": module_name,
                "stage": "import",
                "category": "module_missing" if target_missing else "dependency_missing",
                "missing_name": missing_name,
                "error_type": type(exc).__name__,
                "error": str(exc)[:500],
            })
            continue
        except ImportError as exc:
            errors.append({
                "module": module_name,
                "stage": "import",
                "category": "dependency_import_error",
                "error_type": type(exc).__name__,
                "error": str(exc)[:500],
            })
            continue
        except AttributeError as exc:
            errors.append({
                "module": module_name,
                "stage": "import",
                "category": "module_initialization_attribute_error",
                "error_type": type(exc).__name__,
                "error": str(exc)[:500],
            })
            continue
        missing_attrs = [name for name in required_attrs if not hasattr(module, name)]
        if missing_attrs:
            errors.append({
                "module": module_name,
                "stage": "attribute_validation",
                "category": "missing_required_attributes",
                "missing_attributes": missing_attrs,
                "error_type": "AttributeError",
                "error": "RAG indexer module is missing required attributes.",
            })
            continue
        if errors:
            logger.warning("Controller RAG indexer loaded after earlier module failures: %s", errors)
        return module
    message = "; ".join(
        f"{item.get('module')}:{item.get('category')}:{item.get('error_type')}"
        for item in errors
    )
    logger.warning("Controller RAG indexer failed to load: %s", errors)
    raise ControllerRagIndexerLoadError(message or "Controller RAG indexer unavailable", diagnostics=errors)


def _parse_suffixes(default_suffixes: set[str]) -> set[str]:
    raw = os.environ.get("AICARMINE_CONTROLLER_RAG_SUFFIXES") or os.environ.get("AICARMINE_RAG_SUFFIXES")
    if not raw:
        return set(default_suffixes)
    suffixes: set[str] = set()
    for item in raw.split(","):
        suffix = item.strip().lower()
        if not suffix:
            continue
        suffixes.add(suffix if suffix.startswith(".") else "." + suffix)
    return suffixes or set(default_suffixes)


def _query_terms(goal: str, *, limit: int = 24) -> list[str]:
    terms: list[str] = []
    for raw in re.findall(r"[A-Za-z0-9_]{2,}", goal.lower()):
        if raw in _STOPWORDS or raw.isdigit():
            continue
        if raw not in terms:
            terms.append(raw)
        if len(terms) >= limit:
            break
    if _code_security_analysis_goal(goal):
        for raw in _CODE_SECURITY_EXPANSION_TERMS:
            if raw not in terms:
                terms.append(raw)
            if len(terms) >= max(limit, 40):
                break
    return terms


def _fts_query(terms: Sequence[str]) -> str:
    return " OR ".join(f'"{term}"' for term in terms if term)


def _sqlite_tables(conn: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type IN ('table', 'view')")
    }


def _index_meta(conn: sqlite3.Connection) -> dict[str, str]:
    if "index_meta" not in _sqlite_tables(conn):
        return {}
    return {
        str(key): str(value)
        for key, value in conn.execute("SELECT key, value FROM index_meta")
    }


def _explicit_path_texts(goal: str, query_plan: Mapping[str, Any] | None) -> list[str]:
    texts: list[str] = [str(goal or "")]
    if isinstance(query_plan, Mapping):
        raw_queries = query_plan.get("queries")
        if isinstance(raw_queries, list):
            for item in raw_queries:
                if isinstance(item, Mapping):
                    texts.append(str(item.get("query") or ""))
                    texts.append(str(item.get("purpose") or ""))
                else:
                    texts.append(str(item or ""))
    return texts


def _literal_path_candidates(goal: str, query_plan: Mapping[str, Any] | None) -> list[str]:
    candidates: list[str] = []
    for text in _explicit_path_texts(goal, query_plan):
        for match in _EXPLICIT_PATH_RE.finditer(text):
            path = repo_rel_token(match.group(0).strip("`'\".,;:)]}"))
            if path and path != "." and path not in candidates:
                candidates.append(path)
    return candidates


def _indexed_literal_request_paths(
    *,
    db: Path,
    goal: str,
    query_plan: Mapping[str, Any] | None,
    repo_root: Path,
    safe_rel_path: SafeRelPath,
    generic_readable_suffixes: Sequence[str],
    limit: int,
) -> tuple[list[str], list[dict[str, Any]]]:
    candidates = _literal_path_candidates(goal, query_plan)
    if not candidates:
        return [], []
    diagnostics: list[dict[str, Any]] = []
    normalized: list[str] = []
    for path in candidates:
        if not repo_existing_file(path, repo_root=repo_root, safe_rel_path=safe_rel_path):
            diagnostics.append({"stage": "explicit_path_db_lookup", "candidate": path, "reason": "literal_path_not_existing_file"})
            continue
        if not repo_readable_evidence_file(path, repo_root=repo_root, generic_readable_suffixes=generic_readable_suffixes):
            diagnostics.append({"stage": "explicit_path_db_lookup", "candidate": path, "reason": "literal_path_not_readable_evidence_file"})
            continue
        if path not in normalized:
            normalized.append(path)

    if not normalized:
        return [], diagnostics
    if not db.exists() or not db.is_file():
        return [], [
            *diagnostics,
            {"stage": "explicit_path_db_lookup", "reason": "rag_db_missing", "candidate_count": len(normalized), "db": str(db)},
        ]

    try:
        conn = sqlite3.connect(db)
        try:
            tables = _sqlite_tables(conn)
            if "files" not in tables:
                return [], [
                    *diagnostics,
                    {"stage": "explicit_path_db_lookup", "reason": "files_table_missing", "candidate_count": len(normalized)},
                ]
            placeholders = ",".join("?" for _ in normalized)
            rows = conn.execute(
                f"SELECT path FROM files WHERE path IN ({placeholders})",
                tuple(normalized),
            ).fetchall()
        finally:
            conn.close()
    except Exception as exc:
        return [], [
            *diagnostics,
            {
                "stage": "explicit_path_db_lookup",
                "reason": "db_lookup_failed",
                "error": str(exc),
                "error_type": type(exc).__name__,
            },
        ]

    indexed = {repo_rel_token(row[0]) for row in rows if row and row[0]}
    selected: list[str] = []
    for path in normalized:
        if path in indexed and path not in selected:
            selected.append(path)
            if len(selected) >= limit:
                break
        else:
            diagnostics.append({"stage": "explicit_path_db_lookup", "candidate": path, "reason": "literal_path_not_indexed_in_db"})
    return selected, diagnostics


def _semantic_owner_target_paths(
    *,
    goal: str,
    query_plan: Mapping[str, Any] | None,
    repo_root: Path,
    safe_rel_path: SafeRelPath,
    generic_readable_suffixes: Sequence[str],
    limit: int,
) -> tuple[list[str], list[dict[str, Any]]]:
    texts = "\n".join(_explicit_path_texts(goal, query_plan)).lower().replace("\\", "/")
    if not texts:
        return [], []
    selected: list[str] = []
    diagnostics: list[dict[str, Any]] = []
    for aliases, paths in audit_owner_targets():
        if not any(alias in texts for alias in aliases):
            continue
        for raw_path in paths:
            path = repo_rel_token(raw_path)
            if not path or path in selected:
                continue
            if not repo_existing_file(path, repo_root=repo_root, safe_rel_path=safe_rel_path):
                diagnostics.append({
                    "stage": "semantic_owner_target_lookup",
                    "candidate": path,
                    "reason": "semantic_owner_target_not_existing_file",
                })
                continue
            if not repo_readable_evidence_file(
                path,
                repo_root=repo_root,
                generic_readable_suffixes=generic_readable_suffixes,
            ):
                diagnostics.append({
                    "stage": "semantic_owner_target_lookup",
                    "candidate": path,
                    "reason": "semantic_owner_target_not_readable_evidence_file",
                })
                continue
            selected.append(path)
            if len(selected) >= limit:
                return selected, diagnostics
    return selected, diagnostics


def _http_json_post(url: str, payload: Mapping[str, Any], *, timeout_seconds: float) -> Any:
    body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=max(1, int(timeout_seconds))) as response:
            raw = response.read(_RERANK_RESPONSE_BYTES)
            text = raw.decode("utf-8", errors="replace")
            status = getattr(response, "status", None)
            content_type = (response.headers.get("Content-Type") or "").lower()
    except urllib.error.HTTPError as exc:
        raw = exc.read(_RERANK_RESPONSE_BYTES)
        text = raw.decode("utf-8", errors="replace")
        raise ControllerRagHTTPError(
            status=int(exc.code or 0),
            reason=str(exc.reason or exc),
            body_preview=text[:2000],
        ) from exc
    if not text.strip():
        return {"status": status}
    if "application/json" in content_type or text.strip().startswith(("{", "[")):
        return json.loads(text)
    return {
        "status": status,
        "content_type": content_type,
        "text": text[:2000],
        "non_json_response": True,
    }


def _parse_rerank_results(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, Mapping):
        raw_results = value.get("results") or value.get("data") or []
    elif isinstance(value, list):
        raw_results = value
    else:
        raw_results = []
    parsed: list[dict[str, Any]] = []
    for position, item in enumerate(raw_results):
        if not isinstance(item, Mapping):
            continue
        raw_index = item.get("index", item.get("document_index", item.get("id", position)))
        try:
            index = int(raw_index)
        except Exception:
            index = position
        raw_score = item.get("relevance_score", item.get("score", item.get("logit", 0.0)))
        try:
            score = float(raw_score)
        except Exception:
            score = 0.0
        parsed.append({"index": index, "score": score})
    return parsed


def _rerank_ranked_items(
    *,
    query: str,
    items: list[dict[str, Any]],
    enabled: bool,
) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    url = os.environ.get("AICARMINE_CONTROLLER_RAG_RERANK_URL") or os.environ.get("AICARMINE_RAG_RERANK_URL") or _DEFAULT_RERANK_URL
    model = os.environ.get("AICARMINE_CONTROLLER_RAG_RERANK_MODEL") or os.environ.get("AICARMINE_RAG_RERANK_MODEL") or _DEFAULT_RERANK_MODEL
    candidate_limit = _env_int("AICARMINE_CONTROLLER_RAG_RERANK_CANDIDATE_LIMIT", 48, minimum=1, maximum=100)
    doc_chars = _env_int("AICARMINE_CONTROLLER_RAG_RERANK_DOC_CHARS", 3000, minimum=200, maximum=20000)
    timeout_seconds = _env_float("AICARMINE_CONTROLLER_RAG_RERANK_TIMEOUT_SECONDS", 30.0, minimum=1.0, maximum=30.0)
    meta: dict[str, Any] = {
        "enabled": bool(enabled),
        "url": url,
        "model": model,
        "candidate_limit": candidate_limit,
        "doc_chars": doc_chars,
        "timeout_seconds": timeout_seconds,
    }
    if not enabled:
        return items, {**meta, "status": "skipped_disabled"}, []
    candidates = items[:candidate_limit]
    documents = [str(item.get("content_preview") or item.get("content") or "")[:doc_chars] for item in candidates]
    meta["input_count"] = len(documents)
    if not documents:
        return items, {**meta, "status": "skipped_no_candidates"}, []
    try:
        response = _http_json_post(
            url,
            {"model": model, "query": query, "documents": documents},
            timeout_seconds=timeout_seconds,
        )
        if isinstance(response, Mapping) and response.get("non_json_response"):
            marked = [dict(item, rerank_score=None) for item in items]
            return marked, {
                **meta,
                "status": "error",
                "error": "reranker_non_json_response",
                "error_type": "non_json_response",
                "http_status": response.get("status"),
                "content_type": response.get("content_type"),
                "body_preview": str(response.get("text") or "")[:1000],
            }, [{
                "stage": "preplanner_rag_rerank",
                "reason": "reranker_non_json_response",
                "http_status": response.get("status"),
            }]
        parsed = _parse_rerank_results(response)
    except ControllerRagHTTPError as exc:
        marked = [dict(item, rerank_score=None) for item in items]
        http_status = int(exc.status or 0)
        status = "unavailable" if http_status == 429 or http_status >= 500 else "error"
        return marked, {
            **meta,
            "status": status,
            "error": "reranker_http_error",
            "error_type": type(exc).__name__,
            "http_status": http_status,
            "http_reason": exc.reason[:200],
            "body_preview": exc.body_preview[:1000],
        }, [{
            "stage": "preplanner_rag_rerank",
            "reason": "reranker_http_error",
            "http_status": http_status,
            "error_type": type(exc).__name__,
        }]
    except TimeoutError as exc:
        marked = [dict(item, rerank_score=None) for item in items]
        return marked, {
            **meta,
            "status": "unavailable",
            "error": "reranker_timeout",
            "error_type": type(exc).__name__,
            "details": str(exc)[:500],
        }, [{"stage": "preplanner_rag_rerank", "reason": "reranker_timeout", "error_type": type(exc).__name__, "error": str(exc)[:500]}]
    except urllib.error.URLError as exc:
        marked = [dict(item, rerank_score=None) for item in items]
        reason = getattr(exc, "reason", None)
        is_timeout = isinstance(reason, TimeoutError)
        return marked, {
            **meta,
            "status": "unavailable",
            "error": "reranker_timeout" if is_timeout else "reranker_network_unavailable",
            "error_type": type(exc).__name__,
            "network_reason_type": type(reason).__name__ if reason is not None else None,
            "details": str(exc)[:500],
        }, [{
            "stage": "preplanner_rag_rerank",
            "reason": "reranker_timeout" if is_timeout else "reranker_network_unavailable",
            "error_type": type(exc).__name__,
            "error": str(exc)[:500],
        }]
    except json.JSONDecodeError as exc:
        marked = [dict(item, rerank_score=None) for item in items]
        return marked, {
            **meta,
            "status": "error",
            "error": "reranker_invalid_json",
            "error_type": type(exc).__name__,
            "json_error": str(exc)[:500],
        }, [{"stage": "preplanner_rag_rerank", "reason": "reranker_invalid_json", "error_type": type(exc).__name__}]
    except (OSError, ValueError) as exc:
        marked = [dict(item, rerank_score=None) for item in items]
        return marked, {
            **meta,
            "status": "unavailable",
            "error": "reranker_network_unavailable",
            "error_type": type(exc).__name__,
            "details": str(exc)[:500],
        }, [{"stage": "preplanner_rag_rerank", "reason": "reranker_network_unavailable", "error_type": type(exc).__name__, "error": str(exc)[:500]}]
    except Exception as exc:
        marked = [dict(item, rerank_score=None) for item in items]
        return marked, {
            **meta,
            "status": "error",
            "error": "reranker_response_error",
            "error_type": type(exc).__name__,
            "details": str(exc)[:500],
        }, [{"stage": "preplanner_rag_rerank", "reason": "reranker_response_error", "error_type": type(exc).__name__, "error": str(exc)[:500]}]

    if not parsed:
        marked = [dict(item, rerank_score=None) for item in items]
        return marked, {
            **meta,
            "status": "error",
            "error": "reranker_no_scores",
            "error_type": "no_scores",
            "response_shape": type(response).__name__,
        }, [{"stage": "preplanner_rag_rerank", "reason": "reranker_no_scores"}]

    reranked: list[dict[str, Any]] = []
    seen: set[int] = set()
    for result in parsed:
        index = int(result.get("index") or 0)
        if index < 0 or index >= len(candidates) or index in seen:
            continue
        seen.add(index)
        reranked.append(dict(candidates[index], rerank_score=result.get("score")))
    for index, item in enumerate(candidates):
        if index not in seen:
            reranked.append(dict(item, rerank_score=None))
    for item in items[candidate_limit:]:
        reranked.append(dict(item, rerank_score=None))
    return reranked, {**meta, "status": "ready", "returned_scores": len(parsed), "ranked_count": len(reranked)}, []


def _ranked_paths_from_codex_rag(
    *,
    db: Path,
    repo_root: Path,
    goal: str,
    query_plan: Mapping[str, Any] | None,
    safe_rel_path: SafeRelPath,
    named_read_priority: Mapping[str, int],
    generic_readable_suffixes: Sequence[str],
    candidate_limit: int,
) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    terms = _query_terms(goal)
    sanitized_query_plan = _sanitize_preplanner_query_plan(query_plan, goal=goal)
    goal_class = str(sanitized_query_plan.get("goal_class") or _preplanner_goal_class(goal))
    raw_queries = sanitized_query_plan.get("queries")
    query_items = raw_queries if isinstance(raw_queries, list) else []
    planner_queries: list[str] = []
    for item in query_items:
        if not isinstance(item, Mapping):
            continue
        query = str(item.get("query") or "")
        if query:
            planner_queries.append(query)
    query_specs: list[dict[str, Any]] = []
    for index, planner_query in enumerate(planner_queries, start=1):
        query_terms = _query_terms(planner_query, limit=24)
        fts_query = _fts_query(query_terms)
        if fts_query:
            query_specs.append({
                "source": "planner_query_plan",
                "query_index": index,
                "query": planner_query,
                "query_terms": query_terms,
                "fts_query": fts_query,
            })
    deterministic_query = _fts_query(terms)
    if deterministic_query and (goal_class != "apply_write" or not query_specs):
        query_specs.append({
            "source": "deterministic_goal_terms",
            "query_index": 0,
            "query": str(goal or ""),
            "query_terms": terms,
            "fts_query": deterministic_query,
        })
    report: dict[str, Any] = {
        "schema": "agentic_loop_preplanner_rag_ranking.v1",
        "db": str(db),
        "query_terms": terms,
        "goal_class": goal_class,
        "query_plan": {
            key: sanitized_query_plan.get(key)
            for key in ("schema", "ok", "status", "source", "goal_class", "semantic_intent", "queries", "reason")
            if sanitized_query_plan.get(key) not in (None, "", [], {})
        },
        "query_specs": query_specs,
        "candidate_limit": int(candidate_limit),
    }
    skipped: list[dict[str, Any]] = []
    if not query_specs:
        report.update({"status": "skipped", "reason": "no_query_terms"})
        return [], report, skipped

    if not db.exists() or not db.is_file():
        report.update({"status": "unavailable", "reason": "rag_db_missing"})
        return [], report, [{"stage": "preplanner_rag_ranking", "reason": "rag_db_missing", "candidate": str(db)}]

    analysis_goal = _code_security_analysis_goal(goal)
    row_limit = max(
        40 if analysis_goal else 20,
        int(candidate_limit) * (20 if analysis_goal else 8),
    )
    rows: list[tuple[Any, ...]] = []
    try:
        conn = sqlite3.connect(db)
        try:
            tables = _sqlite_tables(conn)
            missing = [name for name in ("chunks", "chunks_fts") if name not in tables]
            if missing:
                report.update({"status": "unavailable", "reason": "schema_missing", "missing_tables": missing})
                return [], report, [{"stage": "preplanner_rag_ranking", "reason": "schema_missing", "missing_tables": missing}]
            meta = _index_meta(conn)
            report["index_meta"] = {
                key: meta.get(key)
                for key in ("repo_root", "index_source", "index_mode", "selector", "indexed_at")
                if meta.get(key) not in (None, "")
            }
            seen_row_keys: set[tuple[str, Any, Any]] = set()
            for spec in query_specs:
                query = str(spec.get("fts_query") or "")
                spec_rows = conn.execute(
                    """
                    SELECT c.path, c.kind, c.symbol, c.start_line, c.end_line, c.content, bm25(chunks_fts) AS rank_score
                    FROM chunks_fts
                    JOIN chunks AS c ON c.id = chunks_fts.rowid
                    WHERE chunks_fts MATCH ?
                    ORDER BY rank_score
                    LIMIT ?
                    """,
                    (query, row_limit),
                ).fetchall()
                spec["raw_match_count"] = len(spec_rows)
                for row in spec_rows:
                    row_key = (str(row[0] or ""), row[3], row[4])
                    if row_key in seen_row_keys:
                        continue
                    seen_row_keys.add(row_key)
                    rows.append(row)
        finally:
            conn.close()
    except Exception as exc:
        report.update({
            "status": "failed",
            "reason": "fts_query_failed",
            "error": str(exc),
            "error_type": type(exc).__name__,
        })
        return [], report, [{"stage": "preplanner_rag_ranking", "reason": "fts_query_failed", "error": str(exc)}]

    by_path: dict[str, dict[str, Any]] = {}
    for row in rows:
        path = repo_rel_token(row[0])
        if not path:
            continue
        if _low_signal_ranked_path(path):
            skipped.append({"stage": "preplanner_rag_ranking", "candidate": path, "reason": "low_signal_backup_or_temporary_path"})
            continue
        if not repo_existing_file(path, repo_root=repo_root, safe_rel_path=safe_rel_path):
            skipped.append({"stage": "preplanner_rag_ranking", "candidate": path, "reason": "ranked_path_not_existing_file"})
            continue
        if not repo_readable_evidence_file(
            path,
            repo_root=repo_root,
            generic_readable_suffixes=generic_readable_suffixes,
        ):
            skipped.append({"stage": "preplanner_rag_ranking", "candidate": path, "reason": "ranked_path_not_readable_evidence_file"})
            continue
        try:
            score = float(row[6])
        except Exception:
            score = 0.0
        content = str(row[5] or "")
        item = {
            "path": path,
            "kind": str(row[1] or ""),
            "symbol": str(row[2] or ""),
            "start_line": int(row[3] or 0),
            "end_line": int(row[4] or 0),
            "rank_score": score,
            "path_policy_score": _path_policy_score(path, goal=goal, repo_root=repo_root),
            "content_preview": content[:240],
        }
        previous = by_path.get(path)
        if previous is None or score < float(previous.get("rank_score") or 0.0):
            by_path[path] = item

    ranked = sorted(
        by_path.values(),
        key=lambda item: (
            int(item.get("path_policy_score") or 0),
            float(item.get("rank_score") or 0.0),
            read_candidate_sort_key(
                str(item.get("path") or ""),
                repo_root=repo_root,
                named_read_priority=named_read_priority,
            ),
        ),
    )
    rerank_query = "\n".join([str(goal or ""), *planner_queries]).strip()
    ranked, rerank, rerank_skipped = _rerank_ranked_items(
        query=rerank_query,
        items=ranked,
        enabled=_env_bool("AICARMINE_CONTROLLER_RAG_RERANK_ENABLED", True),
    )
    skipped.extend(rerank_skipped)
    selected = _select_ranked_paths(ranked, goal=goal, candidate_limit=candidate_limit)
    for index, item in enumerate(selected, start=1):
        item["rank"] = index
    report.update({
        "status": "ready",
        "fts_queries": [str(spec.get("fts_query") or "") for spec in query_specs],
        "raw_match_count": len(rows),
        "ranked_path_count": len(ranked),
        "selected_path_count": len(selected),
        "selected_paths": [str(item.get("path") or "") for item in selected],
        "rerank": rerank,
    })
    return selected, report, skipped[:40]


def _anchor_paths(
    *,
    repo_root: Path,
    safe_rel_path: SafeRelPath,
    max_anchors: int,
) -> list[str]:
    anchors: list[str] = []
    for candidate in _ANCHOR_CANDIDATES:
        path = repo_rel_token(candidate)
        if repo_existing_file(path, repo_root=repo_root, safe_rel_path=safe_rel_path):
            anchors.append(path)
        if len(anchors) >= max_anchors:
            break
    return anchors


def controller_preplanner_rag_preseed_plan(
    goal: str,
    original_args: Mapping[str, Any] | None,
    *,
    repo_root: Path,
    safe_rel_path: SafeRelPath,
    named_read_priority: Mapping[str, int],
    generic_readable_suffixes: Sequence[str],
    multi_file_prompt_read_chars: int,
) -> tuple[dict[str, Any] | None, dict[str, Any], list[dict[str, Any]]]:
    """Reindex the Codex RAG DB with git-delta semantics and build a precise read preseed."""
    args = dict(original_args or {})
    if args.get("controller_rag_preseed") is False or not _env_bool("AICARMINE_CONTROLLER_PREPLANNER_RAG_ENABLED", True):
        return None, {
            "schema": "agentic_loop_preplanner_rag.v1",
            "ok": False,
            "status": "disabled",
        }, []

    repo_root = Path(repo_root).resolve(strict=False)
    db = _default_controller_rag_db(repo_root)
    report: dict[str, Any] = {
        "schema": "agentic_loop_preplanner_rag.v1",
        "ok": False,
        "db": str(db),
        "repo_root": str(repo_root),
        "reindex_mode": "delta",
        "reindex_source": "git",
        "selector": "git ls-files --cached --others --exclude-standard",
    }
    skipped: list[dict[str, Any]] = []

    if not repo_root.exists() or not repo_root.is_dir():
        report.update({"status": "failed", "reason": "repo_root_missing"})
        return None, report, [{"stage": "preplanner_rag_reindex", "reason": "repo_root_missing", "candidate": str(repo_root)}]

    try:
        indexer = _load_codex_rag_indexer()
    except Exception as exc:
        report.update({
            "status": "failed",
            "reason": "reindex_failed",
            "error_stage": "indexer_load",
            "error": str(exc),
            "error_type": type(exc).__name__,
            "operator_hint": _rag_indexer_operator_hint(exc),
        })
        diagnostics = getattr(exc, "diagnostics", None)
        if isinstance(diagnostics, list):
            report["indexer_load_diagnostics"] = diagnostics[:4]
        return None, report, [{
            "stage": "preplanner_rag_reindex",
            "reason": "reindex_failed",
            "error_stage": "indexer_load",
            "error": str(exc),
            "error_type": type(exc).__name__,
        }]

    try:
        default_suffixes = set(getattr(indexer, "DEFAULT_SUFFIXES"))
        reindex = indexer.build_index(
            repo_root=repo_root,
            db=db,
            suffixes=_parse_suffixes(default_suffixes),
            exclude_dirs=set(),
            max_file_bytes=_env_int(
                "AICARMINE_CONTROLLER_RAG_MAX_FILE_BYTES",
                int(getattr(indexer, "MAX_FILE_BYTES_DEFAULT")),
                minimum=1_000,
                maximum=20_000_000,
            ),
            chunk_lines=_env_int(
                "AICARMINE_CONTROLLER_RAG_CHUNK_LINES",
                int(getattr(indexer, "CHUNK_LINES_DEFAULT")),
                minimum=20,
                maximum=1000,
            ),
            chunk_chars=_env_int(
                "AICARMINE_CONTROLLER_RAG_CHUNK_CHARS",
                int(getattr(indexer, "CHUNK_CHARS_DEFAULT")),
                minimum=1000,
                maximum=120000,
            ),
            source=str(getattr(indexer, "SOURCE_GIT_DEFAULT")),
            mode=str(getattr(indexer, "MODE_DELTA")),
        )
    except Exception as exc:
        report.update({
            "status": "failed",
            "reason": "reindex_failed",
            "error_stage": "build_index",
            "error": str(exc),
            "error_type": type(exc).__name__,
            "operator_hint": _rag_indexer_operator_hint(exc),
        })
        return None, report, [{
            "stage": "preplanner_rag_reindex",
            "reason": "reindex_failed",
            "error_stage": "build_index",
            "error": str(exc),
            "error_type": type(exc).__name__,
        }]

    read_path_limit = _env_int("AICARMINE_CONTROLLER_RAG_PRESEED_PATH_LIMIT", 8, minimum=1, maximum=24)
    query_plan = args.get("controller_rag_query_plan") if isinstance(args.get("controller_rag_query_plan"), Mapping) else None
    sanitized_query_plan = _sanitize_preplanner_query_plan(query_plan, goal=goal) if query_plan else None
    goal_class = str(
        (sanitized_query_plan or {}).get("goal_class")
        or _preplanner_goal_class(goal)
    )
    default_anchor_limit = 0 if goal_class in {"apply_write", "code_product_report"} else 2
    anchor_limit = _env_int("AICARMINE_CONTROLLER_RAG_PRESEED_ANCHOR_LIMIT", default_anchor_limit, minimum=0, maximum=5)
    ranked_limit = max(1, read_path_limit - anchor_limit)
    ranked_items, ranking, ranking_skipped = _ranked_paths_from_codex_rag(
        db=db,
        repo_root=repo_root,
        goal=goal,
        query_plan=sanitized_query_plan or query_plan,
        safe_rel_path=safe_rel_path,
        named_read_priority=named_read_priority,
        generic_readable_suffixes=generic_readable_suffixes,
        candidate_limit=ranked_limit,
    )
    skipped.extend(ranking_skipped)
    literal_target_paths, literal_target_skipped = _indexed_literal_request_paths(
        db=db,
        goal=goal,
        query_plan=sanitized_query_plan or query_plan,
        repo_root=repo_root,
        safe_rel_path=safe_rel_path,
        generic_readable_suffixes=generic_readable_suffixes,
        limit=read_path_limit,
    )
    skipped.extend(literal_target_skipped)
    semantic_target_paths, semantic_target_skipped = _semantic_owner_target_paths(
        goal=goal,
        query_plan=sanitized_query_plan or query_plan,
        repo_root=repo_root,
        safe_rel_path=safe_rel_path,
        generic_readable_suffixes=generic_readable_suffixes,
        limit=read_path_limit,
    )
    skipped.extend(semantic_target_skipped)

    selected_paths: list[str] = []
    for path in [*literal_target_paths, *semantic_target_paths]:
        if len(selected_paths) >= read_path_limit:
            break
        if path not in selected_paths:
            selected_paths.append(path)
    anchor_paths: list[str] = []
    for path in _anchor_paths(repo_root=repo_root, safe_rel_path=safe_rel_path, max_anchors=anchor_limit):
        if len(selected_paths) >= read_path_limit:
            break
        if path not in selected_paths and (
            repo_doc_or_config(path, repo_root=repo_root)
            or repo_readable_evidence_file(path, repo_root=repo_root, generic_readable_suffixes=generic_readable_suffixes)
        ):
            anchor_paths.append(path)
            selected_paths.append(path)
    ranked_preplanner_paths: list[str] = []
    for item in ranked_items:
        path = str(item.get("path") or "")
        if path and path not in selected_paths:
            selected_paths.append(path)
        if path and path not in ranked_preplanner_paths:
            ranked_preplanner_paths.append(path)
        if len(selected_paths) >= read_path_limit:
            break

    report.update({
        "ok": True,
        "status": "ready",
        "reindex": reindex,
        "ranking": ranking,
        "selected_paths": selected_paths,
        "literal_target_paths": literal_target_paths,
        "semantic_target_paths": semantic_target_paths,
        "anchor_paths": anchor_paths,
        "ranked_preplanner_paths": ranked_preplanner_paths,
        "selected_path_count": len(selected_paths),
        "ranked_items": ranked_items[:read_path_limit],
    })
    if not selected_paths:
        skipped.append({
            "stage": "preplanner_rag_read",
            "reason": "no_ranked_or_anchor_paths_selected_after_reindex",
        })
        return None, report, skipped
    total_read_chars = max(2000, int(multi_file_prompt_read_chars or 2000))
    max_chars_per_path = max(
        2000,
        min(total_read_chars, total_read_chars // max(1, len(selected_paths))),
    )

    plan = {
        "event": "controller_preseed_preplanner_rag_ranked_read",
        "result_event": "controller_preseed_preplanner_rag_ranked_read_result",
        "tool": "repo_read",
        "arguments": {
            "paths": selected_paths,
            "max_chars": max_chars_per_path,
            "max_paths": len(selected_paths),
        },
        "reason": "loop_start_delta_rag_reindex_ranked_preplanner_context",
        "artifact_suffix": "preplanner_rag_ranked-repo_read",
        "dynamic_initial_orientation": True,
        "preplanner_rag": {
            "schema": "agentic_loop_preplanner_rag_preseed.v1",
            "db": str(db),
            "reindex": reindex,
            "ranking": ranking,
            "selected_paths": selected_paths,
            "literal_target_paths": literal_target_paths,
            "semantic_target_paths": semantic_target_paths,
            "anchor_paths": anchor_paths,
            "ranked_preplanner_paths": ranked_preplanner_paths,
            "ranked_items": ranked_items[:read_path_limit],
            "read_path_limit": read_path_limit,
            "total_read_chars_budget": total_read_chars,
            "max_chars_per_path": max_chars_per_path,
        },
        "ranked_preplanner_paths": ranked_preplanner_paths,
    }
    return plan, report, skipped
