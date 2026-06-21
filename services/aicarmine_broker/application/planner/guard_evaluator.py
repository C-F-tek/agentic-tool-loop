"""Guard evaluator for planner decision validation.

This module extracts all guard logic from the main planner loop into a
separate, testable class. Each guard method returns a guard_result dict
that the loop can emit as an event and append to history.

Design:
- Pure functions where possible (no state mutation)
- Event emission handled by caller
- History append handled by caller
- Only business logic lives in this module
"""

from __future__ import annotations

import logging
from typing import Any, Mapping

logger = logging.getLogger(__name__)


class GuardEvaluator:
    """Evaluates guards and returns guard_result dicts.

    Each method evaluates a specific guard condition and returns:
    - None if the decision is valid (no guard triggered)
    - dict with guard_result if a guard triggered
    """

    def __init__(self, deps: Mapping[str, Any], config: Mapping[str, Any]) -> None:
        """Initialize with dependencies and config.

        Args:
            deps: Dependency injections from loop.
            config: Configuration dictionary.
        """
        self.deps = deps
        self.config = config

        # Extract frequently used deps for performance
        self._controller_guard_result_for_validation = deps["controller_guard_result_for_validation"]
        self._controller_guard_rejection_signature = deps["controller_guard_rejection_signature"]
        self._controller_guard_rejection_signature_count = deps["controller_guard_rejection_signature_count"]
        self._controller_guard_count = deps["controller_guard_count"]
        self._planner_incomprehensible_retry_count = deps["planner_incomprehensible_retry_count"]
        self._planner_memory_false_unavailable_claim = deps["planner_memory_false_unavailable_claim"]
        self._raw_planner_text_classification = deps["raw_planner_text_classification"]
        self._should_retry_incomprehensible_planner_output = deps["should_retry_incomprehensible_planner_output"]
        self._is_unrecoverable_plain_text_planner_output = deps["is_unrecoverable_plain_text_planner_output"]
        self._should_attempt_vulkan_repair = deps["should_attempt_vulkan_repair"]
        self._vulkan_repair_invalid_planner_decision = deps["vulkan_repair_invalid_planner_decision"]
        self._normalize_terminal_planner_decision = deps["normalize_terminal_planner_decision"]
        self._native_required_repaired_tool_decision_disallowed = deps["native_required_repaired_tool_decision_disallowed"]
        self._specialist_route_audit = deps["specialist_route_audit"]
        self._planner_replan_specialist_for_validation = deps["planner_replan_specialist_for_validation"]

    def evaluate_support_subturn_guard(
        self,
        decision: dict[str, Any],
        validation: dict[str, Any],
        history: list[dict[str, Any]],
        step: int,
        semantic_step: int,
        support_subturns_used: int,
        job_id: str,
        goal: str,
    ) -> dict[str, Any] | None:
        """Evaluate support subturn validation guard.

        Returns guard_result if rejected, None if valid.
        """
        rejection_signature = self._controller_guard_rejection_signature(validation, decision)
        repeated_rejection_count = self._controller_guard_rejection_signature_count(
            history,
            rejection_signature,
        )
        retry_limit = max(1, int(self.config.get("AGENTIC_PLANNER_INCOMPREHENSIBLE_RETRIES", 0)))
        repeated_rejection_limit = max(1, int(retry_limit or 0))

        guard_result = self._controller_guard_result_for_validation(
            validation,
            decision,
            job_id=job_id,
            step=step,
            goal=goal,
        )
        guard_result["guard_type"] = "support_subturn_validation_failed"
        guard_result["summary"] = "support_subturn_validation_failed"
        guard_result["support_subturn"] = True
        guard_result["semantic_step"] = semantic_step
        guard_result["support_subturn_index"] = support_subturns_used + 1
        guard_result["invalid_decision_signature"] = rejection_signature
        guard_result["invalid_decision_repeat_count"] = repeated_rejection_count + 1
        guard_result["retry_limit"] = repeated_rejection_limit

        return {
            "guard_result": guard_result,
            "should_continue": True,
            "should_finalize": False,
            "max_rejections": repeated_rejection_limit,
            "current_rejections": repeated_rejection_count + 1,
        }

    def evaluate_native_tool_call_guard(
        self,
        validation: dict[str, Any],
        decision: dict[str, Any],
        history: list[dict[str, Any]],
        step: int,
        job_id: str,
        goal: str,
        planner_memory_snapshot: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Evaluate native tool call required guard.

        Returns guard_result if rejected, None if valid.
        """
        violations = {str(v) for v in (validation.get("violations") if isinstance(validation.get("violations"), list) else [])}
        if "planner_native_tool_call_required" not in violations:
            return None

        prior_native_empty_guards = self._controller_guard_count(
            history,
            "planner_native_tool_call_required",
        )
        retry_limit = int(self.config.get("AGENTIC_PLANNER_INCOMPREHENSIBLE_RETRIES", 0))

        if prior_native_empty_guards >= retry_limit:
            return {
                "guard_result": None,
                "should_continue": False,
                "should_finalize": True,
                "final_status": "blocked_needs_attention",
                "final_reason": (
                    "planner_native_tool_call_required_repeated: planner native tool mode "
                    "was active, tools were provided to Ollama, but the planner repeatedly "
                    "returned no message.tool_calls. Controller did not fall back to JSON-text "
                    "tool execution."
                ),
                "final_extra": {
                    "history": history,
                    "planner_decision": decision,
                    "blocked_by": "planner_native_tool_call_required_repeated",
                    "validation": validation,
                },
            }

        guard_result = self._controller_guard_result_for_validation(
            validation,
            decision,
            job_id=job_id,
            step=step,
            goal=goal,
        )
        guard_result["guard_type"] = "planner_native_tool_call_required"
        guard_result["summary"] = "planner_native_tool_call_required"
        guard_result["retry_count"] = prior_native_empty_guards
        guard_result["retry_limit"] = retry_limit

        return {
            "guard_result": guard_result,
            "should_continue": True,
            "should_finalize": False,
        }

    def evaluate_memory_claim_guard(
        self,
        memory_claim_text: str,
        decision: dict[str, Any],
        validation: dict[str, Any],
        history: list[dict[str, Any]],
        step: int,
        job_id: str,
        goal: str,
        planner_memory_snapshot: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Evaluate planner memory false unavailable claim guard.

        Returns guard_result if triggered, None if valid.
        """
        retry_limit = int(self.config.get("AGENTIC_PLANNER_INCOMPREHENSIBLE_RETRIES", 0))
        if not (
            self._planner_memory_false_unavailable_claim(memory_claim_text, planner_memory_snapshot)
            and int(retry_limit or 0) > 0
            and self._planner_incomprehensible_retry_count(history) < int(retry_limit)
        ):
            return None

        retry_count = self._planner_incomprehensible_retry_count(history)
        guard_result = {
            "tool": "controller_guard",
            "ok": True,
            "guard_type": "planner_memory_false_unavailable_claim",
            "summary": "planner_memory_available_but_planner_claimed_unavailable",
            "classification": "plain_text_non_json_retryable",
            "retry_count": retry_count,
            "retry_limit": int(retry_limit or 0),
            "violations": validation.get("violations"),
            "raw_planner_text_preview": memory_claim_text[:4000],
            "planner_memory": {
                "available": True,
                "record_count": planner_memory_snapshot.get("record_count", 0),
                "source": planner_memory_snapshot.get("source"),
            },
            "next_instruction": (
                "planner_memory is available; do not claim long-term memory is unavailable; "
                "repeat as one pure JSON object and either use planner_memory, call a memory tool, "
                "or choose another evidence-bound action"
            ),
            "rejected_decision": {
                k: decision.get(k)
                for k in ("action", "tool", "arguments", "reason", "final_answer")
                if decision.get(k) not in (None, "", [], {})
            },
        }

        return {
            "guard_result": guard_result,
            "should_continue": True,
            "should_finalize": False,
        }

    def evaluate_incomprehensible_output_guard(
        self,
        decision: dict[str, Any],
        validation: dict[str, Any],
        history: list[dict[str, Any]],
        step: int,
        job_id: str,
        goal: str,
        planner_memory_snapshot: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Evaluate incomprehensible planner output guard.

        Returns guard_result if triggered, None if valid.
        """
        retry_limit = int(self.config.get("AGENTIC_PLANNER_INCOMPREHENSIBLE_RETRIES", 0))
        if not self._should_retry_incomprehensible_planner_output(decision, history, retry_limit):
            return None

        raw_planner_text = str(decision.get("raw_planner_text") or "")
        output_classification = self._raw_planner_text_classification(raw_planner_text)
        retry_count = self._planner_incomprehensible_retry_count(history)

        guard_result = {
            "tool": "controller_guard",
            "ok": True,
            "guard_type": "planner_retry_required",
            "summary": "planner_output_incomprehensible_repeat_required",
            "classification": f"{output_classification}_retryable",
            "retry_count": retry_count,
            "retry_limit": int(retry_limit or 0),
            "violations": validation.get("violations"),
            "raw_planner_text_preview": raw_planner_text[:4000],
            "next_instruction": (
                "repeat as one pure JSON object; no prose before or after; "
                "choose from candidate_next_actions; do not answer unrelated "
                "questions"
            ),
            "rejected_decision": {
                k: decision.get(k)
                for k in ("action", "tool", "arguments", "reason", "final_answer")
                if decision.get(k) not in (None, "", [], {})
            },
        }

        return {
            "guard_result": guard_result,
            "should_continue": True,
            "should_finalize": False,
        }

    def evaluate_repeated_code_product_guard(
        self,
        validation: dict[str, Any],
        decision: dict[str, Any],
        history: list[dict[str, Any]],
        step: int,
        job_id: str,
        goal: str,
        planner_memory_snapshot: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Evaluate repeated invalid code product decision guard.

        Returns finalize_result if triggered, None if valid.
        """
        violations = {str(v) for v in (validation.get("violations") if isinstance(validation.get("violations"), list) else [])}
        if "planner_repeated_invalid_code_product_decision" not in violations:
            return None

        guard_result = self._controller_guard_result_for_validation(
            validation,
            decision,
            job_id=job_id,
            step=step,
            goal=goal,
        )
        guard_result["guard_type"] = "planner_repeated_invalid_code_product_decision"
        guard_result["summary"] = "planner_repeated_invalid_code_product_decision"

        return {
            "guard_result": guard_result,
            "should_continue": False,
            "should_finalize": True,
            "final_status": "blocked_needs_attention",
            "final_reason": (
                "planner_repeated_invalid_code_product_decision: planner repeated the same invalid "
                "repo_propose_code_edit placeholder/missing-payload decision after the validator "
                "already required a route shift. Controller did not synthesize a patch or hidden tool call."
            ),
            "final_extra": {
                "history": history,
                "blocked_by": "planner_repeated_invalid_code_product_decision",
                "planner_decision": decision,
                "invalid_decision_signature": validation.get("invalid_decision_signature"),
                "invalid_decision_repeat_count": validation.get("invalid_decision_repeat_count"),
            },
        }

    def evaluate_repeated_rejection_guard(
        self,
        validation: dict[str, Any],
        decision: dict[str, Any],
        history: list[dict[str, Any]],
        step: int,
        job_id: str,
        goal: str,
        planner_memory_snapshot: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Evaluate repeated identical planner rejection guard.

        Returns guard_result if triggered, None if valid.
        """
        rejection_signature = self._controller_guard_rejection_signature(validation, decision)
        repeated_rejection_count = self._controller_guard_rejection_signature_count(
            history,
            rejection_signature,
        )
        retry_limit = int(self.config.get("AGENTIC_PLANNER_INCOMPREHENSIBLE_RETRIES", 0))
        repeated_rejection_limit = max(1, int(retry_limit or 0))

        if repeated_rejection_count < repeated_rejection_limit:
            return None

        guard_result = self._controller_guard_result_for_validation(
            validation,
            decision,
            job_id=job_id,
            step=step,
            goal=goal,
        )
        guard_result["guard_type"] = "repeated_identical_planner_rejection"
        guard_result["summary"] = "repeated_identical_planner_rejection"
        guard_result["invalid_decision_signature"] = rejection_signature
        guard_result["invalid_decision_repeat_count"] = repeated_rejection_count + 1
        guard_result["retry_limit"] = repeated_rejection_limit

        return {
            "guard_result": guard_result,
            "should_continue": False,
            "should_finalize": True,
            "final_status": "blocked_needs_attention",
            "final_reason": (
                "repeated_identical_planner_rejection: planner repeated the same "
                "validator-rejected decision after controller feedback. Controller "
                "stopped the loop and preserved available payloads instead of "
                "consuming max_steps."
            ),
            "final_extra": {
                "history": history,
                "blocked_by": "repeated_identical_planner_rejection",
                "planner_decision": decision,
                "validation": validation,
                "invalid_decision_signature": rejection_signature,
                "invalid_decision_repeat_count": repeated_rejection_count + 1,
            },
        }

    def evaluate_unrecoverable_output_guard(
        self,
        decision: dict[str, Any],
        history: list[dict[str, Any]],
        retry_limit: int,
        step: int,
        job_id: str,
        goal: str,
    ) -> dict[str, Any] | None:
        """Evaluate unrecoverable plain text planner output guard.

        Returns finalize_result if triggered, None if valid.
        """
        if not self._is_unrecoverable_plain_text_planner_output(decision, history, retry_limit):
            return None

        final_answer = str(decision.get("final_answer") or decision.get("reason") or "")
        raw_text = str(decision.get("raw_planner_text") or "")
        output_classification = self._raw_planner_text_classification(raw_text)
        repair_reason = f"{output_classification}_not_gpu0_repairable"

        if raw_text:
            final_answer += (
                "\n\nRaw planner output surfaced, first 4000 chars:\n"
                + raw_text[:4000]
            )

        return {
            "guard_result": None,
            "should_continue": False,
            "should_finalize": True,
            "final_status": "blocked_needs_attention",
            "final_reason": final_answer,
            "final_extra": {
                "history": history,
                "planner_decision": decision,
                "blocked_by": decision.get("reason"),
                "classification": f"planner_output_{output_classification}_unrecoverable",
                "raw_planner_text": decision.get("raw_planner_text"),
                "vulkan_repair": {
                    "attempted": False,
                    "reason": repair_reason,
                },
            },
        }

    def evaluate_vulkan_repair(
        self,
        decision: dict[str, Any],
        validation: dict[str, Any],
        history: list[dict[str, Any]],
        step: int,
        job_id: str,
        goal: str,
        state: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Evaluate and perform Vulkan repair for invalid decisions.

        Returns repair_result dict, or None if repair not applicable.
        """
        should_attempt = self._should_attempt_vulkan_repair(decision, validation, history)
        if not should_attempt:
            return None

        repair_result = self._vulkan_repair_invalid_planner_decision(
            goal=goal,
            step=step,
            decision=decision,
            validation=validation,
            history=history,
            state=state,
        )

        if not (repair_result.get("ok") and isinstance(repair_result.get("repaired_decision"), dict)):
            return {
                "guard_result": None,
                "should_continue": True,
                "should_finalize": False,
                "vulkan_repair_attempted": True,
                "vulkan_repair_ok": False,
            }

        repaired_decision = self._normalize_terminal_planner_decision(
            repair_result["repaired_decision"]
        )

        if self._native_required_repaired_tool_decision_disallowed(repaired_decision):
            repaired_validation = {
                "ok": False,
                "violations": ["vulkan_repair_tool_decision_disallowed_in_native_mode"],
                "evidence_contract": {},
            }
        else:
            # Note: validate_planner_decision_against_evidence is called by caller via deps
            repaired_validation = {"ok": True, "violations": []}

        return {
            "guard_result": None,
            "should_continue": True,
            "should_finalize": False,
            "vulkan_repair_attempted": True,
            "vulkan_repair_ok": True,
            "repaired_decision": repaired_decision,
            "repaired_validation": repaired_validation,
        }

    def evaluate_final_guard(
        self,
        decision: dict[str, Any],
        validation: dict[str, Any],
        history: list[dict[str, Any]],
        step: int,
        job_id: str,
        goal: str,
        planner_memory_snapshot: dict[str, Any],
        should_attempt_vulkan: bool,
        repair_result: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Evaluate final guard (default case when no other guard triggered).

        Returns guard_result for the default rejection case.
        """
        guard_result = self._controller_guard_result_for_validation(
            validation,
            decision,
            job_id=job_id,
            step=step,
            goal=goal,
        )

        if should_attempt_vulkan:
            guard_result["vulkan_repair"] = {
                k: repair_result.get(k)
                for k in (
                    "ok", "error", "raw_text_preview", "raw_planner_text_preview",
                    "repair_cache_key", "repair_cache_hit", "cached_from_step",
                )
                if repair_result.get(k) not in (None, "", [], {})
            }

        return {
            "guard_result": guard_result,
            "should_continue": True,
            "should_finalize": False,
        }