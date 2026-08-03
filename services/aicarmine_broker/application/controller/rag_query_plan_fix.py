"""Query plan repair service for controller preplanner RAG.

This module provides:
- RAGQueryPlanRepairService: handles query plan repair with better error handling and fallback strategies.
- build_fallback_query_plan(): builds a deterministic fallback query plan when the planner model is unavailable.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

logger = logging.getLogger(__name__)


class RAGQueryPlanRepairError(RuntimeError):
    """Raised when query plan repair fails with diagnostic information."""

    def __init__(self, *, reason: str, status: str, repair_timeout_seconds: int) -> None:
        super().__init__(f"Query plan repair failed: {reason}")
        self.reason = reason
        self.status = status
        self.repair_timeout_seconds = repair_timeout_seconds


class RAGQueryPlanRepairService:
    """Handles query plan repair with better error handling and fallback strategies.
    
    Attributes:
        planner_url: URL of the Ollama planner endpoint.
        planner_model: Model name for the planner.
        keep_alive: Keep-alive string for Ollama.
        timeout_seconds: Timeout for repair requests.
    """

    def __init__(
        self,
        *,
        planner_url: str,
        planner_model: str,
        keep_alive: str,
        timeout_seconds: int,
    ) -> None:
        self.planner_url = planner_url
        self.planner_model = planner_model
        self.keep_alive = keep_alive
        self.timeout_seconds = timeout_seconds

    def build_fallback_query_plan(self, goal: str) -> dict[str, Any]:
        """Build a deterministic fallback query plan when the planner model is unavailable.
        
        Args:
            goal: The user's goal text.
            
        Returns:
            A minimal valid query plan with deterministic queries.
        """
        max_queries = _env_int(
            "AICARMINE_CONTROLLER_RAG_QUERY_PLANNER_MAX_QUERIES",
            5,
            minimum=1,
            maximum=8,
        )
        
        fallback_semantic_intent = {
            "schema": "agentic_loop_preplanner_semantic_intent.v1",
            "source": "fallback_query_plan",
            "accepted": True,
            "goal_class": "repo_analysis",
            "static_goal_class_hint": "repo_analysis",
            "fallback_goal_class": "repo_analysis",
            "fallback_semantic_class": "repo_analysis",
            "negative_write_constraints_present": True,
            "read_only": True,
            "write_requested": False,
            "apply_requested": False,
            "code_product_requested": False,
            "requires_code_security_coverage": False,
            "rationale": "Deterministic fallback when planner model unavailable",
        }
        
        fallback_queries = [
            {
                "query": "owner source modules",
                "purpose": "Identify current owner implementation files",
                "target_kind": "owner_source",
            },
            {
                "query": "validator modules",
                "purpose": "Identify validator implementations",
                "target_kind": "validator",
            },
        ]
        
        return {
            "schema": "agentic_loop_preplanner_rag_query_plan.v1",
            "ok": True,
            "status": "ready",
            "source": "fallback_query_plan",
            "goal_class": "repo_analysis",
            "semantic_intent": fallback_semantic_intent,
            "queries": fallback_queries[:max_queries],
            "reason": "deterministic_fallback_planner_unavailable",
        }

    def repair_query_plan(
        self,
        *,
        raw_response_text: str,
        parse_diagnostics: Mapping[str, Any],
        goal: str,
    ) -> dict[str, Any]:
        """Repair a malformed query plan response.
        
        Args:
            raw_response_text: The raw response text from the planner.
            parse_diagnostics: Parse diagnostics from the original response.
            goal: The user's goal text.
            
        Returns:
            A repaired query plan or error report.
        """
        repair_timeout = _env_int(
            "AICARMINE_CONTROLLER_RAG_QUERY_PLANNER_REPAIR_TIMEOUT_SECONDS",
            min(30, max(10, int(self.timeout_seconds or 10))),
            minimum=3,
            maximum=60,
        )
        
        repair_payload = {
            "model": self.planner_model,
            "stream": False,
            "keep_alive": self.keep_alive,
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
        
        try:
            response = _http_json_post(
                self.planner_url,
                repair_payload,
                repair_timeout,
            )
        except Exception as exc:
            return {
                "ok": False,
                "status": "unavailable",
                "source": "repair_failed",
                "reason": f"repair_request_failed: {type(exc).__name__}",
                "repair_attempted": True,
                "repair_status": "failed",
                "repair_reason": "repair_request_exception",
                "repair_timeout_seconds": repair_timeout,
                "repair_error_type": type(exc).__name__,
                "repair_error": str(exc)[:2000],
            }
        
        if response.get("backend_unreachable") or response.get("backend_timeout") or response.get("error"):
            return {
                "ok": False,
                "status": "unavailable",
                "source": "repair_failed",
                "reason": "repair_request_failed",
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
        
        if decoded and isinstance(decoded, dict):
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
        
        return {
            "ok": False,
            "status": "unavailable",
            "source": "repair_failed",
            "reason": "repair_json_parse_failed",
            "repair_attempted": True,
            "repair_status": "failed",
            "repair_reason": "repair_json_parse_failed",
            "repair_timeout_seconds": repair_timeout,
            "repair_raw_response_chars": len(repair_raw_text),
            "repair_json_parse_error_type": repair_parse.get("error_type"),
            "repair_json_parse_error": repair_parse.get("error"),
        }


def _env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    """Read an integer environment variable with bounded validation."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, value))


def _extract_query_plan_response_text(response: Mapping[str, Any]) -> str:
    """Extract response text from a query plan response."""
    raw_message = response.get("message")
    message: Mapping[str, Any] = raw_message if isinstance(raw_message, Mapping) else {}
    return str(
        response.get("response")
        or message.get("content")
        or response.get("partial_content")
        or ""
    )


def _parse_json_object_diagnostics(text: str) -> dict[str, Any]:
    """Parse JSON with diagnostics, returning decoded object or error info."""
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


def _sanitize_preplanner_query_plan(value: Mapping[str, Any] | None, *, goal: str) -> dict[str, Any]:
    """Sanitize a preplanner query plan, validating semantic intent and queries."""
    max_queries = _env_int(
        "AICARMINE_CONTROLLER_RAG_QUERY_PLANNER_MAX_QUERIES",
        5,
        minimum=1,
        maximum=8,
    )
    
    report: dict[str, Any] = {
        "schema": "agentic_loop_preplanner_rag_query_plan.v1",
        "ok": False,
        "status": "unavailable",
        "source": "none",
        "goal_class": "",
        "static_goal_class_hint": "repo_analysis",
        "semantic_intent": {
            "schema": "agentic_loop_preplanner_semantic_intent.v1",
            "source": "none",
            "accepted": False,
            "goal_class": "",
            "static_goal_class_hint": "repo_analysis",
            "fallback_goal_class": "repo_analysis",
            "fallback_semantic_class": "repo_analysis",
            "negative_write_constraints_present": True,
        },
        "queries": [],
    }
    
    if not isinstance(value, Mapping):
        return report
    
    source = str(value.get("source") or "planner")
    semantic_intent = value.get("semantic_intent")
    goal_class = str((semantic_intent or {}).get("goal_class") or "")
    semantic_intent_usable = bool(
        (semantic_intent or {}).get("source") == "planner_query_plan"
        and (semantic_intent or {}).get("accepted") is True
        and goal_class
    )
    
    raw_queries = value.get("queries")
    queries: list[dict[str, str]] = []
    if isinstance(raw_queries, list):
        for item in raw_queries:
            if isinstance(item, Mapping):
                query = str(item.get("query") or item.get("text") or "")
                purpose = str(item.get("purpose") or "")
                target_kind = str(item.get("target_kind") or item.get("kind") or "")
            else:
                query = str(item or "")
                purpose = ""
                target_kind = ""
            if not query:
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
            "reason": "no_queries",
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


def _http_json_post(url: str, payload: Mapping[str, Any], timeout_seconds: float) -> dict[str, Any]:
    """POST JSON to an HTTP endpoint and parse the response."""
    import urllib.request
    import urllib.error
    
    body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=max(1, int(timeout_seconds))) as response:
            raw = response.read(64000)
            text = raw.decode("utf-8", errors="replace")
            status = getattr(response, "status", None)
            content_type = (response.headers.get("Content-Type") or "").lower()
    except urllib.error.HTTPError as exc:
        raw = exc.read(64000)
        text = raw.decode("utf-8", errors="replace")
        raise RuntimeError(
            f"HTTP {exc.code}: {exc.reason}"
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