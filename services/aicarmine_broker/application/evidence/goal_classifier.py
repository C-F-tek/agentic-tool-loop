"""Goal text and deliverable classification helpers for the planner loop."""
from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable, Mapping
from typing import Any

logger = logging.getLogger(__name__)

REPO_ANALYSIS_PREPLANNER_CLASSES = frozenset({
    "repo_analysis",
    "code_security_analysis",
})


def semantic_goal_text(goal: str) -> str:
    """Return the real user-facing goal, never an invented fallback task."""
    raw = str(goal or "").strip()
    if not raw:
        return raw
    try:
        decoded = json.loads(raw)
    except Exception:
        return raw
    if not isinstance(decoded, dict):
        return raw

    for key in ("request", "task", "query", "prompt", "instruction", "command"):
        value = decoded.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    if any(key in decoded for key in ("function", "tool_name", "operation_id", "tool")):
        return (
            "__AICARMINE_INPUT_ERROR_MISSING_USER_REQUEST__ "
            "Planner received a tool envelope without request/task/query/prompt/instruction. "
            f"raw_goal={json.dumps(decoded, ensure_ascii=False, sort_keys=True)[:3000]}"
        )
    return raw


def semantic_goal_low(goal: str) -> str:
    return semantic_goal_text(goal).lower()


def goal_is_tool_envelope(goal: str) -> bool:
    raw = str(goal or "").strip()
    try:
        decoded = json.loads(raw)
    except Exception:
        return False
    return isinstance(decoded, dict) and any(
        key in decoded for key in ("function", "tool_name", "operation_id", "tool")
    )


def input_error_goal(goal: str) -> bool:
    return str(goal or "").strip().startswith("__AICARMINE_INPUT_ERROR_MISSING_USER_REQUEST__")


def has_any(text: str, needles: tuple[str, ...]) -> bool:
    return any(n in text for n in needles)


_NEGATED_OPERATION_PATTERNS = (
    r"do\s+not\s+(?:actually\s+)?(?:apply|modify|change|edit|write|fix|patch)(?:\s+[a-z0-9_.@+/-]+){0,5}",
    r"don't\s+(?:actually\s+)?(?:apply|modify|change|edit|write|fix|patch)(?:\s+[a-z0-9_.@+/-]+){0,5}",
    r"without\s+(?:actually\s+)?(?:applying|modifying|changing|editing|writing|fixing|patching)(?:\s+[a-z0-9_.@+/-]+){0,5}",
    r"no\s+(?:apply|changes?|edits?|writes?|patch(?:es)?|modifications?)(?:\s+[a-z0-9_.@+/-]+){0,5}",
    r"only\s+(?:read|reading|analysis|inspect|review)",
    r"reading\s+only",
    r"read[-\s]?only",
    r"non\s+(?:devi\s+|deve\s+|voglio\s+|serve\s+)?(?:usare|usa|applicare|applica|applico|modificare|modifica|modifico|effettuare\s+modifiche|fare\s+modifiche|cambiare|cambia|editare|edita|scrivere|scrivi|correggere|correggi|patchare|patcha|patch|fixare|fixa)(?:\s+[a-z0-9_.@+/-]+){0,6}",
    r"senza\s+(?:usare|applicare|modificare|toccare|fare\s+modifiche|fare\s+patch|cambiare|editare|scrivere|correggere|patchare|patch|fixare)(?:\s+[a-z0-9_.@+/-]+){0,6}",
    r"solo\s+(?:lettura|analisi|ispezione|review)",
)

_NEGATED_OPERATION_RE = re.compile(
    r"\b(?:" + "|".join(_NEGATED_OPERATION_PATTERNS) + r")\b",
    re.IGNORECASE,
)

_APPLY_REQUEST_PATTERNS = (
    r"\bapplica(?:re)?\b",
    r"\bapplica\s+(?:la\s+)?patch\b",
    r"\bapply\b",
    r"\bapply\s+(?:the\s+)?patch\b",
    r"\b(?:fai|fare)\s+(?:un|una)?\s*patch\b",
    r"\bmodifica(?:re)?\b",
    r"\bscrivi\b",
    r"\bwrite\b",
    r"\bedit\b",
    r"\bchange\b",
    r"\bfix(?:are)?\b",
    r"\brisolvi(?:ere|re)?\b",
    r"\bcorreggi(?:ere|re)?\b",
    r"\brepair\b",
    r"\bhotfix\b",
)

_TOOL_NAME_NOISE_RE = re.compile(
    r"\b(?:repo_apply_patch|repo_write_file|terminal_run_command_wait|repo_command)\b",
    re.IGNORECASE,
)


def goal_operational_intent_text(goal: str) -> str:
    """Return goal text with negative constraints removed before intent matching."""
    text = semantic_goal_text(goal)
    text = _TOOL_NAME_NOISE_RE.sub(" ", text)
    text = _NEGATED_OPERATION_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def goal_has_negative_write_constraints(goal: str) -> bool:
    text = semantic_goal_text(goal)
    return bool(_TOOL_NAME_NOISE_RE.search(text) or _NEGATED_OPERATION_RE.search(text))


def _positive_code_product_marker(text: str) -> bool:
    low = str(text or "").lower()
    patterns = (
        r"\bunified\s+diff\b",
        r"\bcode\s+diff\b",
        r"\bdetailed\s+code\s+diff\b",
        r"\bcomplete\s+diff\s+patch(?:es)?\b",
        r"\bdiff\s+patch(?:es)?\b",
        r"\bcomplete\s+diff\s+information\b",
        r"\bcomprehensive\s+diff\s+information\b",
        r"\bcomplete\s+diff\s+output(?:s)?\b",
        r"\bcomprehensive\s+diff\s+output(?:s)?\b",
        r"\bdiff\s+completo\b",
        r"\bdiff\s+concret[aoei]\b",
        r"\bdifferenziale(?:\s+di\s+codice)?\b",
        r"\bformato\s+diff\b",
        r"\bin\s+formato\s+diff\b",
        r"\bproposta\s+(?:di\s+)?patch\b",
        r"\bproposte\s+(?:di\s+)?patch\b",
        r"\bproponi(?:mi)?\s+(?:patch|diff)\b",
        r"\bproponi(?:mi)?\s+(?:un|una)\s+(?:patch|diff)\b",
        r"\bpropone\s+(?:patch|diff)\b",
        r"\bproporre\s+(?:patch|diff)\b",
        r"\bgenera(?:re)?\s+(?:un|una)?\s*(?:patch|diff)\b",
        r"\b(?:fai|fare)\s+(?:un|una)?\s*(?:diff)\b",
        r"\bpatch\s+(?:diff|concret[aoei]|complet[aoei])\b",
        r"\bpatch\s+candidate\b",
        r"\bcandidate\s+patch\b",
        r"\bcode\s+product\b",
        r"\bcode\s+edit\s+proposal(?:s)?\b",
        r"\breport[-\s]?only\s+code\s+edit\s+proposal(?:s)?\b",
        r"\breport[-\s]?only\s+(?:diff|patch|code\s+product)\b",
        r"\bproposta\s+(?:di\s+)?refactor(?:ing)?\b",
        r"\bproponi(?:mi)?\s+(?:un\s+)?refactor(?:ing)?(?:\s+concreto)?\b",
        r"\bproporre\s+(?:un\s+)?refactor(?:ing)?(?:\s+concreto)?\b",
        r"\brefactor\s+concreto\b",
        r"\brefactoring\s+concreto\b",
        r"\bgenera(?:re)?\s+(?:un\s+)?diff\b",
        r"\bgenerate\s+(?:a\s+)?patch\b",
        r"\bgenerate\s+(?:a\s+)?(?:detailed\s+)?(?:code\s+)?diff\b",
        r"\bproduce\s+(?:a\s+)?(?:code\s+)?diff\b",
    )
    return any(re.search(pattern, low) for pattern in patterns)


def goal_report_only_code_product_marker(goal: str) -> bool:
    low = semantic_goal_low(goal)
    report_only = re.search(r"\breport[-\s]?only\b", low) or _NEGATED_OPERATION_RE.search(low)
    return bool(report_only and _positive_code_product_marker(goal_operational_intent_text(goal)))


def goal_diff_output_not_apply_marker(goal: str) -> bool:
    low = str(goal or "").lower()
    diff_output = re.search(
        r"\b("
        r"generate\s+(?:complete\s+)?diff\s+patch(?:es)?|"
        r"provide\s+(?:the\s+)?(?:full\s+)?diff\s+output|"
        r"full\s+diff\s+output|"
        r"comprehensive\s+diff\s+output(?:s)?|"
        r"diff\s+output(?:s)?"
        r")\b",
        low,
    )
    apply_descriptor = re.search(
        r"\b("
        r"ready\s+to\s+apply|"
        r"ready[-\s]?to[-\s]?apply|"
        r"can\s+be\s+applied|"
        r"patch(?:es)?\s+that\s+can\s+be\s+applied"
        r")\b",
        low,
    )
    explicit_apply_command = re.search(
        r"\b("
        r"apply\s+(?:the\s+)?patch|"
        r"apply\s+(?:these\s+)?changes|"
        r"actually\s+apply|"
        r"applica(?:re)?\s+(?:la\s+)?patch"
        r")\b",
        low,
    )
    return bool(diff_output and apply_descriptor and not explicit_apply_command)


def goal_requests_code_product(goal: str) -> bool:
    return (
        goal_report_only_code_product_marker(goal)
        or _positive_code_product_marker(goal_operational_intent_text(goal))
    )


def goal_requires_code_security_coverage(goal: str) -> bool:
    low = semantic_goal_low(goal)
    code_markers = (
        "codice", "code", "sorgente", "source", "semantiche", "semantic",
        "anti-pattern", "antipattern", "code smell", "refactoring",
    )
    critical_markers = (
        "criticità", "criticita", "vulnerabil", "sicurezza", "security",
        "xss", "sql injection", "authentication", "auth", "race condition",
        "resource leak", "memory leak", "input validation", "hardcoded",
        "segreti", "secrets", "cve", "gdpr",
    )
    review_markers = (
        "cerca", "ricerca", "trova", "analizza", "analisi", "scan",
        "review", "audit", "ispeziona", "inspect",
    )
    return (
        any(marker in low for marker in critical_markers)
        and any(marker in low for marker in review_markers)
        and (any(marker in low for marker in code_markers) or "repo" in low or "repository" in low)
    )


def goal_requests_apply(goal: str) -> bool:
    low = goal_operational_intent_text(goal).lower()
    if goal_report_only_code_product_marker(goal) or goal_diff_output_not_apply_marker(goal):
        return False
    low = _NEGATED_OPERATION_RE.sub(" ", low)
    low = re.sub(r"\breport[-\s]?only\b", " ", low)
    low = re.sub(r"\bcode\s+edit\s+proposal(?:s)?\b", " ", low)
    if goal_requests_code_product(goal) and (
        goal_diff_output_not_apply_marker(goal)
        or re.search(r"\breport[-\s]?only\b", semantic_goal_low(goal))
        or _NEGATED_OPERATION_RE.search(semantic_goal_low(goal))
    ):
        return False
    return any(re.search(pattern, low) for pattern in _APPLY_REQUEST_PATTERNS)


def final_answer_has_inline_code_product(text: str) -> bool:
    value = str(text or "")
    return (
        "```diff" in value
        or "diff --git" in value
        or "\n--- a/" in value
        or "\n+++ b/" in value
        or ("\n@@ " in value and "\n---" in value and "\n+++" in value)
    )


def final_answer_is_action_plan_without_code_product(text: str) -> bool:
    value = str(text or "").strip()
    if not value or final_answer_has_inline_code_product(value):
        return False
    low = value.lower()
    markers = (
        "recommendations", "recommendation", "next steps", "potential areas",
        "potential areas for refactoring", "refactoring recommendations",
        "areas for refactoring", "recommendations:", "next steps:",
        "raccomandazioni", "consigli", "prossimi passi", "miglioramenti",
        "aree di miglioramento", "possibili refactor", "potenziali refactor",
        "review the", "begin by", "start with", "consider consolidating",
    )
    return any(marker in low for marker in markers)


def semantic_goal_classification(goal: str, *, repo_analysis: bool = False) -> dict[str, Any]:
    """Classify the requested deliverable without changing planner ownership."""
    text = semantic_goal_text(goal)
    intent_text = goal_operational_intent_text(goal)
    low = intent_text.lower()
    explicit_apply = goal_requests_apply(goal)
    explicit_code_product = goal_requests_code_product(goal)
    negative_constraints = goal_has_negative_write_constraints(goal)
    if negative_constraints and any(re.search(pattern, text.lower()) for pattern in _APPLY_REQUEST_PATTERNS):
        logger.debug(
            "Goal classification saw apply markers with negative write constraints; text_chars=%s",
            len(text),
        )

    refactor_terms = (
        "refactor", "refactoring", "ristruttura", "ristrutturazione",
        "migliora il codice", "migliorare il codice",
    )
    proposal_verbs = (
        "proponi", "proporre", "proposta", "proposte", "suggerisci",
        "suggerire", "produce", "produci", "genera", "generate",
    )
    concrete_terms = (
        "concreto", "concreta", "concreti", "concrete", "operativo",
        "operativa", "codice", "code", "diff", "patch",
    )
    action_plan_markers = (
        "recommendations", "recommendation", "next steps", "potential areas",
        "areas for refactoring", "aree di miglioramento", "aree per",
        "miglioramenti", "prossimi passi", "possibili refactor",
        "potential refactor", "potenziali refactor",
    )

    concrete_refactor_request = (
        any(term in low for term in refactor_terms)
        and any(verb in low for verb in proposal_verbs)
        and any(term in low for term in concrete_terms)
    )
    wants_plan = any(marker in low for marker in action_plan_markers)

    if explicit_apply:
        classification = "apply_write"
        requested = "apply/edit/fix/write"
        must_code_product = False
        confidence = 0.98
        reason = "explicit apply/write/fix intent"
    elif explicit_code_product or concrete_refactor_request:
        classification = "code_product_report"
        requested = "report-only code product"
        must_code_product = True
        confidence = 0.96 if explicit_code_product else 0.86
        reason = (
            "explicit diff/patch/code-product wording"
            if explicit_code_product else
            "semantic concrete refactor proposal request"
        )
    elif wants_plan:
        classification = "action_plan_only"
        requested = "analysis with recommendations/action plan"
        must_code_product = False
        confidence = 0.82
        reason = "recommendations/next-steps wording without concrete diff request"
    elif repo_analysis:
        classification = "analysis_only"
        requested = "repository analysis"
        must_code_product = False
        confidence = 0.80
        reason = "repository analysis wording"
    else:
        classification = "analysis_only"
        requested = "general answer with evidence"
        must_code_product = False
        confidence = 0.55
        reason = "no code-product or apply deliverable detected"

    return {
        "schema": "planner_goal_classification.v1",
        "class": classification,
        "confidence": confidence,
        "reason": reason,
        "requested_deliverable": requested,
        "must_produce_code_product": bool(must_code_product),
        "requires_code_security_coverage": goal_requires_code_security_coverage(goal),
        "regex_code_product_override": bool(explicit_code_product),
        "regex_apply_override": bool(explicit_apply),
        "negative_write_constraints_present": bool(negative_constraints),
        "operational_intent_text_changed": bool(intent_text != text),
    }


def effective_repo_analysis_goal(
    goal: str,
    semantic_classification: Mapping[str, Any] | None,
    *,
    repo_analysis_goal: Callable[[str], bool],
) -> bool:
    """Return the repository-analysis gate decision from the canonical semantics."""
    semantic = semantic_classification if isinstance(semantic_classification, Mapping) else {}
    preplanner_goal_class = str(semantic.get("preplanner_goal_class") or "").strip()
    requested_deliverable = str(semantic.get("requested_deliverable") or "").strip().lower()
    return bool(
        repo_analysis_goal(goal)
        or preplanner_goal_class in REPO_ANALYSIS_PREPLANNER_CLASSES
        or "repository analysis" in requested_deliverable
    )
