"""Builder core logic extracted from builder.py.
Handles semantic classification and preplanner intent computation.
"""

from __future__ import annotations
from typing import Any, Mapping
from aicarmine_broker.planner_core.cache import CACHEABLE_READ_TOOLS


_PREPLANNER_GOAL_CLASSES = frozenset({
    "analysis_only",
    "code_security_analysis",
    "repo_analysis",
    "code_product_report",
    "apply_write",
    "generic",
})


def compute_preplanner_intent(
    initial_orientation_surface: Mapping[str, Any],
) -> dict[str, Any]:
    """Extract preplanner semantic intent from initial orientation surface."""
    if not isinstance(initial_orientation_surface, Mapping):
        return {}
    preplanner_rag = initial_orientation_surface.get("preplanner_rag")
    if not isinstance(preplanner_rag, Mapping):
        return {}
    ranking = preplanner_rag.get("ranking")
    if not isinstance(ranking, Mapping):
        return {}
    query_plan = ranking.get("query_plan")
    if not isinstance(query_plan, Mapping):
        return {}
    intent = query_plan.get("semantic_intent")
    if not isinstance(intent, Mapping):
        return {}
    if str(intent.get("schema") or "") != "agentic_loop_preplanner_semantic_intent.v1":
        return {}
    goal_class = str(intent.get("goal_class") or "").strip()
    if goal_class not in _PREPLANNER_GOAL_CLASSES:
        return {}
    return {str(key): value for key, value in intent.items()}


def classify_semantic_with_preplanner(
    fallback: Mapping[str, Any],
    preplanner_intent: Mapping[str, Any],
) -> dict[str, Any]:
    """Classify semantic intent using preplanner intent when available."""
    classification = dict(fallback if isinstance(fallback, Mapping) else {})
    if not isinstance(preplanner_intent, Mapping):
        return classification
    if str(preplanner_intent.get("source") or "") != "planner_query_plan":
        return classification
    goal_class = str(preplanner_intent.get("goal_class") or "").strip()
    if goal_class not in _PREPLANNER_GOAL_CLASSES:
        return classification
    contract_class = goal_class
    if goal_class in {"repo_analysis", "generic"}:
        contract_class = "analysis_only"
    code_product_requested = bool(preplanner_intent.get("code_product_requested"))
    if goal_class == "code_product_report" and not code_product_requested:
        contract_class = "analysis_only"
    must_code_product = goal_class == "code_product_report" and code_product_requested
    requires_security = bool(preplanner_intent.get("requires_code_security_coverage")) or (
        goal_class == "code_security_analysis"
    )
    requested = {
        "apply_write": "apply/edit/fix/write",
        "code_product_report": "report-only code product",
        "code_security_analysis": "code/security repository analysis",
        "repo_analysis": "repository analysis",
        "analysis_only": "general answer with evidence",
        "generic": "general answer with evidence",
    }.get(goal_class, str(classification.get("requested_deliverable") or "general answer with evidence"))
    classification.update({
        "schema": "planner_goal_classification.v1",
        "class": contract_class,
        "confidence": max(float(classification.get("confidence") or 0.0), 0.9),
        "reason": "controlled preplanner semantic intent",
        "requested_deliverable": requested,
        "must_produce_code_product": must_code_product,
        "requires_code_security_coverage": requires_security,
        "regex_code_product_override": False,
        "regex_apply_override": False,
        "code_product_requested": code_product_requested,
        "preplanner_semantic_intent": dict(preplanner_intent),
        "preplanner_goal_class": goal_class,
    })
    return classification


def goal_requests_code_product_from_semantics(
    fallback_value: bool,
    preplanner_intent: Mapping[str, Any],
) -> bool:
    """Determine if goal requests code product from preplanner semantics."""
    if (
        isinstance(preplanner_intent, Mapping)
        and str(preplanner_intent.get("source") or "") == "planner_query_plan"
    ):
        return (
            str(preplanner_intent.get("goal_class") or "").strip() == "code_product_report"
            and preplanner_intent.get("code_product_requested") is True
        )
    return bool(fallback_value)


def goal_requests_apply_from_semantics(
    fallback_value: bool,
    preplanner_intent: Mapping[str, Any],
) -> bool:
    """Determine if goal requests apply from preplanner semantics."""
    if (
        isinstance(preplanner_intent, Mapping)
        and str(preplanner_intent.get("source") or "") == "planner_query_plan"
    ):
        return str(preplanner_intent.get("goal_class") or "").strip() == "apply_write"
    return bool(fallback_value)


def build_micro_batch_contract(
    candidates: list[dict[str, Any]],
    max_actions: int = 8,
) -> dict[str, Any]:
    """Build micro-batch contract from independent read-only candidates."""
    allowed_actions: list[dict[str, Any]] = []
    seen_call_keys: set[str] = set()
    seen_action_ids: set[str] = set()
    
    def _hashable_value(v: Any) -> Any:
        if isinstance(v, dict):
            return frozenset((k, _hashable_value(sub_v)) for k, sub_v in v.items())
        if isinstance(v, list):
            return tuple(_hashable_value(item) for item in v)
        return v

    def canonical_batch_call_key(tool: str, args: dict[str, Any]) -> str:
        hashable_args = frozenset((k, _hashable_value(v)) for k, v in args.items()) if args else ""
        return f"{tool}:{hash(hashable_args) if hashable_args else ''}"
    
    for action in candidates if isinstance(candidates, list) else []:
        if not isinstance(action, dict):
            continue
        tool = str(action.get("tool") or "").strip()
        if tool not in CACHEABLE_READ_TOOLS:
            continue
        args = action.get("arguments") if isinstance(action.get("arguments"), dict) else {}
        call_key = canonical_batch_call_key(tool, args)
        if call_key in seen_call_keys:
            continue
        action_id = str(action.get("action_id") or "").strip()
        if not action_id or action_id in seen_action_ids:
            continue
        seen_call_keys.add(call_key)
        seen_action_ids.add(action_id)
        allowed_actions.append({
            "action_id": action_id,
            "tool": tool,
            "arguments": args,
            "reason": action.get("reason"),
            "source": action.get("source"),
            "independent_read_only": True,
        })
    limit = max(1, int(max_actions or 8))
    visible_actions = allowed_actions[:limit]
    return {
        "schema": "planner_micro_batch_contract.v1",
        "allowed": len(visible_actions) >= 2,
        "mode": "native_message_tool_calls_only",
        "max_batch_size": min(limit, len(visible_actions)) if visible_actions else 0,
        "allowed_tools": sorted({str(action.get("tool") or "") for action in visible_actions}),
        "allowed_batch_actions": visible_actions,
        "candidate_action_count": len(candidates) if isinstance(candidates, list) else 0,
        "batchable_candidate_count": len(visible_actions),
        "guard": (
            "Multiple native message.tool_calls are accepted only when every call "
            "matches one allowed_batch_actions entry by tool and sanitized arguments. "
            "Write/apply/command/validation/final actions remain single-step and separately validated."
        ),
        "writes_allowed": False,
        "validation_tools_allowed": False,
        "reason": (
            "at_least_two_independent_read_only_candidates"
            if len(visible_actions) >= 2 else
            "fewer_than_two_independent_read_only_candidates"
        ),
    }