"""Shared guidance for semantic repository audits and final-quality judging."""

from __future__ import annotations

from typing import Any, Mapping


AUDIT_TRIGGER_TERMS: tuple[str, ...] = (
    "audit",
    "analisi approfondita",
    "analizza a fondo",
    "semantic",
    "semant",
    "incongruen",
    "duplicate",
    "duplicat",
    "clone",
    "clonat",
    "drift",
    "regress",
    "rischio",
    "layer",
    "strati",
    "funzioni logiche ripetute",
)

AUDIT_OWNER_TARGETS: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (
        ("final_quality", "final quality", "final-quality", "quality gate", "judge"),
        (
            "services/aicarmine_broker/application/evidence/final_quality.py",
            "services/aicarmine_broker/application/evidence/builder.py",
        ),
    ),
    (
        ("validator", "validation", "finalization gate", "controller valida"),
        ("services/aicarmine_broker/application/planner/validator.py",),
    ),
    (
        ("evidence_contract", "evidence contract", "coverage", "final_allowed", "final allowed"),
        (
            "services/aicarmine_broker/application/evidence/builder.py",
            "services/aicarmine_broker/application/prompt/evidence_contract.py",
        ),
    ),
    (
        ("tool-surface", "tool_surface", "tool surface", "required_next_tool_call", "candidate_next_actions"),
        (
            "services/aicarmine_broker/application/tool_surface/turn_surface_policy.py",
            "services/aicarmine_broker/application/tool_surface/candidate_actions.py",
        ),
    ),
    (
        ("history", "history_ledger", "ledger"),
        ("services/aicarmine_broker/application/shared/history_ledger.py",),
    ),
    (
        ("prompt contract", "prompt_contract", "available_tools", "tool_contract"),
        (
            "services/aicarmine_broker/application/prompt/tool_contract.py",
            "services/aicarmine_broker/application/prompt/pack_builder.py",
        ),
    ),
    (
        ("planner", "final_required", "step budget", "plain text final", "controller_wrapped_plain_text_final"),
        (
            "services/aicarmine_broker/planner.py",
            "services/aicarmine_broker/application/planner/turn.py",
            "services/aicarmine_broker/application/planner/loop.py",
        ),
    ),
    (
        ("controller", "preplanner", "rag preseed", "preseed", "rag status"),
        (
            "services/aicarmine_broker/application/controller/rag_preseed.py",
            "services/aicarmine_broker/application/evidence/goal_classifier.py",
        ),
    ),
    (
        ("public payload", "openwebui", "terminal response", "vulkan_bridge"),
        (
            "services/aicarmine_broker/application/job/terminal_response.py",
            "services/vulkan_bridge/app.py",
        ),
    ),
)

SPECULATIVE_FINAL_TERMS: tuple[str, ...] = (
    "probabilmente",
    "probably",
    "likely",
    "sembra",
    "appears to",
    "potrebbe",
    "may duplicate",
)

FOLLOW_UP_INVITATION_TERMS: tuple[str, ...] = (
    "vuoi che generi",
    "posso emettere",
    "posso generare",
    "want me to generate",
    "should i generate",
)

GENERIC_NO_ISSUE_PHRASES: tuple[str, ...] = (
    "nessuna duplicazione significativa",
    "nessuna incongruenza",
    "senza evidenti incongruenze",
    "no significant duplication",
    "no evident semantic inconsistencies",
    "well isolated",
    "ben isolati",
)


def goal_requests_semantic_audit(goal: Any) -> bool:
    text = str(goal or "").lower()
    return any(term in text for term in AUDIT_TRIGGER_TERMS)


def audit_owner_targets() -> tuple[tuple[tuple[str, ...], tuple[str, ...]], ...]:
    return AUDIT_OWNER_TARGETS


def audit_guidance_for_goal(goal: Any) -> dict[str, Any]:
    requested = goal_requests_semantic_audit(goal)
    return {
        "schema": "semantic_audit_guidance.v1",
        "requested": requested,
        "trigger_terms": list(AUDIT_TRIGGER_TERMS),
        "owner_target_families": [
            {
                "aliases": list(aliases),
                "paths": list(paths),
            }
            for aliases, paths in AUDIT_OWNER_TARGETS
        ],
        "preplanner_rule": (
            "When requested=true, first select concrete owner modules and comparison layers; "
            "README/AGENTS or legacy wrappers alone are not enough."
        ),
        "judge_rule": (
            "Reject final answers that claim no duplication/drift from shallow reads, speculate "
            "with 'probably/probabilmente', ask follow-up questions instead of answering, cite "
            "unverified paths, or ignore pending repo_semantic_search/repo_read suggestions."
        ),
    }


def role_guidance_for_goal(role: str, goal: Any = "") -> dict[str, Any]:
    role_key = str(role or "").strip().lower()
    base = audit_guidance_for_goal(goal)
    role_rules: dict[str, list[str]] = {
        "preplanner": [
            "Classify intent from meaning, not keyword fallback.",
            "For semantic audits, select concrete owner modules before docs or legacy wrappers.",
            "For code-product requests, surface explicitly named target files before large incidental reads.",
        ],
        "final_quality_judge": [
            "The model judge decides accept/reject/continue_required from verified evidence.",
            "If semantic discovery is missing, route to planner repo_semantic_search, not hidden preplanner RAG.",
            "If concrete content is missing, route to repo_read; reject speculative no-issue finals.",
        ],
        "code_product_replan": [
            "After an invalid repo_propose_code_edit payload, do not repeat the same proposal.",
            "If the target was already read, do not repeat repo_read for that target.",
            "Next progress is either a complete inline repo_propose_code_edit payload or a typed block.",
            "planner_scratchpad_write is allowed only for a complete ready_for_propose payload, not for another collecting_source loop.",
        ],
        "planner_replan": [
            "Decide the next planner route from validator evidence, not from a hard-coded controller sequence.",
            "If a required repo_read/search route is already satisfied, do not ask for it again.",
            "For repository analysis, route to final when verified evidence is sufficient; otherwise choose one new concrete read/search gap.",
            "Do not switch repository analysis/audit failures into repo_propose_code_edit or code_product_build_state.",
        ],
        "repair": [
            "Return pure JSON only and preserve the validator's required_next_progress.",
            "Do not invent paths, reads, tool results, or coverage.",
            "For code-product violations, repair to a complete repo_propose_code_edit or action=block.",
            "For unresolved repo-analysis coverage, route to repo_semantic_search or repo_read instead of final.",
        ],
    }
    return {
        "schema": "agentic_loop_role_guidance.v1",
        "role": role_key,
        "semantic_audit": base,
        "rules": role_rules.get(role_key, []),
    }


def role_guidance_text(role: str, goal: Any = "") -> str:
    guidance = role_guidance_for_goal(role, goal)
    rules = guidance.get("rules") if isinstance(guidance, dict) else []
    return " ".join(str(rule).strip() for rule in rules if str(rule).strip())


def final_audit_red_flags(final_answer: Any) -> dict[str, list[str]]:
    text = str(final_answer or "").lower()

    def hits(terms: tuple[str, ...]) -> list[str]:
        return [term for term in terms if term in text]

    return {
        "speculative_terms": hits(SPECULATIVE_FINAL_TERMS),
        "follow_up_invitations": hits(FOLLOW_UP_INVITATION_TERMS),
        "generic_no_issue_phrases": hits(GENERIC_NO_ISSUE_PHRASES),
    }


def pending_read_or_search_actions(contract: Mapping[str, Any]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    if not isinstance(contract, Mapping):
        return actions
    raw_actions = contract.get("candidate_next_actions")
    if isinstance(raw_actions, list):
        for item in raw_actions:
            if not isinstance(item, dict):
                continue
            tool = str(item.get("tool") or "").strip()
            if tool in {"repo_read", "repo_semantic_search", "repo_rg_search", "repo_search"}:
                actions.append(item)
    required = contract.get("required_next_tool_call")
    if isinstance(required, dict):
        tool = str(required.get("tool") or "").strip()
        if tool in {"repo_read", "repo_semantic_search", "repo_rg_search", "repo_search"}:
            actions.insert(0, required)
    return actions
