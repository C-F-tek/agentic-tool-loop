"""Evidence contract mutation manager and shadow evaluation phase.

Extracted from run_agentic_planner_job inline logic for:
- ContractMutationPhase: handles persist_turn_memory, write_agent_job_state, history row appends
- ShadowEvaluationPhase: handles evaluate_initial_orientation_shadow (~500 lines)
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable, Mapping


class ContractMutationPhase:
    """Manages contract mutation wiring after guard evaluations.

    Extracted from inline patterns in loop.py that handle:
    - append_history_row
    - persist_turn_memory
    - write_agent_job_state
    - finalize_agentic_job returns
    """

    def __init__(
        self,
        job_id: str,
        state: dict,
        history: list,
        deps: dict,
        config: dict,
        root: Any,
        loop_state: Any,
        loop_controller: Any,
        finalize_fn: Callable,
    ) -> None:
        self.job_id = job_id
        self.state = state
        self.history = history
        self.deps = deps
        self.config = config
        self.root = root
        self.loop_state = loop_state
        self.loop_controller = loop_controller
        self._finalize_agentic_job = finalize_fn

    def persist_guard_result(
        self,
        step: int,
        guard_summary: str,
        guard_result: dict,
        decision: dict,
        should_finalize: bool = False,
        final_status: str = "",
        final_reason: str = "",
        final_extra: dict | None = None,
        support_subturn: bool = False,
    ) -> dict | None:
        """Persist a guard result to history and optionally finalize.

        Returns the finalize result if should_finalize is True, otherwise None.
        """
        row = {
            "step": step,
            "decision": {
                "action": "continue_required",
                "reason": guard_summary,
                "rejected_decision": guard_result.get("rejected_decision", decision),
            },
            "tool_result": guard_result,
        }
        if support_subturn:
            self.loop_controller.mark_support_subturn(row, semantic_step=step)
        self.loop_state.append_history_row(row)
        self.loop_controller.persist_turn_memory(row)
        write_fn = self.deps.get("write_agent_job_state")
        if write_fn and isinstance(self.state, dict):
            try:
                write_fn(self.state, {})
            except Exception:
                pass

        if should_finalize:
            return self._finalize_agentic_job(
                self.job_id,
                self.state,
                final_status,
                final_reason,
                final_extra or {
                    "history": self.history,
                    "blocked_by": guard_result.get("guard_type", "unknown_guard"),
                    "planner_decision": decision,
                },
            )
        return None

    def finalize_blocked(
        self,
        status: str,
        reason: str,
        decision: dict,
        validation: dict,
        extra: dict | None = None,
    ) -> dict:
        """Finalize with blocked_needs_attention status."""
        return self._finalize_agentic_job(
            self.job_id,
            self.state,
            status,
            reason,
            {
                "history": self.history,
                "blocked_by": reason.replace(": ", "_"),
                "planner_decision": decision,
                "validation": validation,
                **(extra or {}),
            },
        )


class ShadowEvaluationPhase:
    """Manages initial orientation shadow evaluation.

    Extracted from evaluate_initial_orientation_shadow (~500 lines) in loop.py.
    Pure function without wiring — does not know job_id, state/history,
    execute tools directly, persist artifact, emit events, or modify legacy flow.
    """

    def __init__(
        self,
        requested_mode: Any,
        root_result: Any,
        goal: Any,
        semantic_intent: Any,
        doc_plan: Any,
        area_plans: Any,
        candidate_pool_fn: Callable[[dict], list[dict]],
        selector_fn: Callable[..., dict],
        effective_mode_fn: Callable[[Any], str],
        legacy_selected_ids_fn: Callable[..., list[str]],
        selection_metrics_fn: Callable[..., dict],
    ) -> None:
        self.requested_mode = requested_mode
        self.root_result = root_result
        self.goal = goal
        self.semantic_intent = semantic_intent
        self.doc_plan = doc_plan
        self.area_plans = area_plans
        self.candidate_pool_fn = candidate_pool_fn
        self.selector_fn = selector_fn
        self.effective_mode_fn = effective_mode_fn
        self.legacy_selected_ids_fn = legacy_selected_ids_fn
        self.selection_metrics_fn = selection_metrics_fn

    def evaluate(self) -> dict:
        """Run the full shadow evaluation pipeline."""
        # STAGE 1 — EFFECTIVE MODE
        effective_mode_raw = self.effective_mode_fn(self.requested_mode)
        effective_mode = "shadow" if effective_mode_raw == "shadow" else "legacy"
        requested_mode_bounded = self._bounded_text(self.requested_mode, 32)

        if effective_mode != "shadow":
            return self._build_skipped_result(
                requested_mode_bounded, effective_mode, "mode_not_shadow"
            )

        # STAGE 2 — ROOT RESULT GATE
        if not isinstance(self.root_result, dict) or self.root_result.get("ok") is not True:
            return self._build_skipped_result(
                requested_mode_bounded, "shadow", "root_result_not_ok"
            )

        # STAGE 3 — CANDIDATE POOL
        try:
            raw_pool = self.candidate_pool_fn(deepcopy(self.root_result))
        except Exception as exc:
            return self._build_unavailable_result(
                requested_mode_bounded, "candidate_pool_exception",
                type(exc).__name__, str(exc)[:500],
            )

        valid_candidates_list = self._valid_candidates(raw_pool)
        candidate_count = len(valid_candidates_list)
        allowed_candidate_ids = {
            c["candidate_id"] for c in valid_candidates_list
        }
        candidate_ids = self._bounded_ids(
            [c["candidate_id"] for c in valid_candidates_list],
            limit=32,
        )

        if not valid_candidates_list:
            return self._build_skipped_result(
                requested_mode_bounded, "shadow", "no_candidates"
            )

        # STAGE 4 — LEGACY SELECTED IDS
        try:
            legacy_result = self.legacy_selected_ids_fn(
                candidates=deepcopy(valid_candidates_list),
                doc_plan=deepcopy(self.doc_plan),
                area_plans=deepcopy(self.area_plans),
            )
        except Exception as exc:
            return self._build_unavailable_result(
                requested_mode_bounded, "legacy_selection_exception",
                type(exc).__name__, str(exc)[:500],
                candidate_count, candidate_ids, [],
            )

        legacy_selected_candidate_ids = self._bounded_ids(
            legacy_result,
            allowed_ids=allowed_candidate_ids,
            limit=13,
        )

        # STAGE 5 — SELECTOR
        try:
            goal_bounded = str(self.goal)[:4000] if isinstance(self.goal, str) else str(self.goal)[:4000]
            semantic_intent_copy = deepcopy(self.semantic_intent) if isinstance(self.semantic_intent, Mapping) else {}
            selector_result = self.selector_fn(
                goal=goal_bounded,
                semantic_intent=semantic_intent_copy,
                candidates=deepcopy(valid_candidates_list),
            )
        except Exception as exc:
            return self._build_unavailable_result(
                requested_mode_bounded, "selector_exception",
                type(exc).__name__, str(exc)[:500],
                candidate_count, candidate_ids, legacy_selected_candidate_ids,
            )

        # STAGE 6 — SELECTOR RESULT VALIDATION
        if not isinstance(selector_result, dict):
            return self._build_invalid_result(
                requested_mode_bounded, "selector_result_not_dict",
                candidate_count, candidate_ids, legacy_selected_candidate_ids,
            )

        selector_ok = selector_result.get("ok") is True
        selector_status = self._bounded_text(selector_result.get("status"), 64).lower()
        selector_ready = selector_ok and selector_status == "ready"
        rationale_bounded = self._bounded_text(selector_result.get("rationale"), 1000)
        confidence_raw = selector_result.get("confidence")
        if isinstance(confidence_raw, bool):
            confidence = None
        elif isinstance(confidence_raw, (int, float)) and 0 <= confidence_raw <= 1:
            confidence = confidence_raw
        else:
            confidence = None

        selected_ids_raw = selector_result.get("selected_candidate_ids", [])
        model_selected_candidate_ids = self._bounded_ids(
            selected_ids_raw,
            allowed_ids=allowed_candidate_ids,
            limit=13,
        )

        # STAGE 7 — PROCESS SELECTOR RESULT
        if not selector_ready:
            return self._build_selector_unavailable_result(
                requested_mode_bounded, selector_result,
                candidate_count, candidate_ids, legacy_selected_candidate_ids,
            )

        # STAGE 8 — COMPUTE METRICS
        selection_overlap = list(set(legacy_selected_candidate_ids) & set(model_selected_candidate_ids))
        metrics = {
            "legacy_count": len(legacy_selected_candidate_ids),
            "model_count": len(model_selected_candidate_ids),
            "selection_overlap": selection_overlap,
            "selection_overlap_count": len(selection_overlap),
            "top1_match": model_selected_candidate_ids[0] == legacy_selected_candidate_ids[0] if (
                model_selected_candidate_ids and legacy_selected_candidate_ids
            ) else False,
            "exact_match": model_selected_candidate_ids == legacy_selected_candidate_ids,
            "would_change_selection": model_selected_candidate_ids != legacy_selected_candidate_ids,
        }

        return {
            "schema": "orientation_shadow_evaluation.v1",
            "lane_id": "orientation.initial",
            "requested_mode": requested_mode_bounded,
            "effective_mode": "shadow",
            "diagnostic_only": True,
            "legacy_authoritative": True,
            "status": "ready",
            "selector_called": True,
            "fallback_used": False,
            "candidate_count": candidate_count,
            "candidate_ids": candidate_ids,
            "legacy_selected_candidate_ids": legacy_selected_candidate_ids,
            "model_selected_candidate_ids": model_selected_candidate_ids,
            "selection_metrics": metrics,
            "model_summary": {
                "ok": selector_ok,
                "status": selector_status,
                "rationale": rationale_bounded,
                "confidence": confidence,
                "unknown_candidate_ids": self._bounded_ids(selector_result.get("unknown_candidate_ids", [])),
                "duplicate_candidate_ids": self._bounded_ids(selector_result.get("duplicate_candidate_ids", [])),
                "duplicate_input_candidate_ids": self._bounded_ids(selector_result.get("duplicate_input_candidate_ids", [])),
                "error_type": "",
                "error": "",
            },
        }

    # --- Internal helpers ---

    @staticmethod
    def _bounded_text(value: Any, limit: int = 32) -> str:
        """Convert value to string safely, strip, truncate."""
        text = ""
        if isinstance(value, str):
            text = value.strip()[:limit]
        elif value is None:
            pass
        else:
            try:
                text = str(value).strip()[:limit]
            except Exception:
                pass
        return text

    @staticmethod
    def _bounded_ids(raw_ids: Any, allowed_ids: set | None = None, limit: int = 13) -> list:
        """Sanitize IDs: must be list of strings, strip, ignore empty/oversized, dedupe."""
        if not isinstance(raw_ids, list):
            return []
        result: list[str] = []
        seen: set[str] = set()
        for item in raw_ids:
            if not isinstance(item, str):
                continue
            id_str = item.strip()
            if not id_str or len(id_str) > 500:
                continue
            if allowed_ids is not None and id_str not in allowed_ids:
                continue
            if id_str in seen:
                continue
            if len(result) >= limit:
                break
            seen.add(id_str)
            result.append(id_str)
        return result

    @staticmethod
    def _valid_candidates(pool: Any) -> list:
        """Build private valid candidate list from raw pool."""
        if not isinstance(pool, list):
            return []
        valid: list[dict] = []
        seen_ids: set[str] = set()
        for cand in pool:
            if not isinstance(cand, dict):
                continue
            cid = cand.get("candidate_id", "")
            if not isinstance(cid, str):
                continue
            cid_stripped = cid.strip()
            if not cid_stripped or len(cid_stripped) > 500:
                continue
            if cid_stripped in seen_ids:
                continue
            new_cand = dict(cand)
            new_cand["candidate_id"] = cid_stripped
            valid.append(new_cand)
            seen_ids.add(cid_stripped)
        return valid

    def _build_skipped_result(
        self, requested_mode: str, effective_mode: str, reason: str
    ) -> dict:
        """Build a skipped shadow evaluation result."""
        return {
            "schema": "orientation_shadow_evaluation.v1",
            "lane_id": "orientation.initial",
            "requested_mode": requested_mode,
            "effective_mode": effective_mode,
            "diagnostic_only": True,
            "legacy_authoritative": True,
            "status": "skipped",
            "reason": reason,
            "selector_called": False,
            "fallback_used": False,
            "candidate_count": 0,
            "candidate_ids": [],
            "legacy_selected_candidate_ids": [],
            "model_selected_candidate_ids": [],
            "selection_metrics": {
                "legacy_count": 0,
                "model_count": 0,
                "selection_overlap": [],
                "selection_overlap_count": 0,
                "top1_match": False,
                "exact_match": True,
                "would_change_selection": False,
            },
            "model_summary": {
                "ok": False,
                "status": "",
                "rationale": "",
                "confidence": None,
                "unknown_candidate_ids": [],
                "duplicate_candidate_ids": [],
                "duplicate_input_candidate_ids": [],
                "error_type": "",
                "error": "",
            },
        }

    def _build_unavailable_result(
        self,
        requested_mode: str,
        reason: str,
        error_type: str,
        error: str,
        candidate_count: int = 0,
        candidate_ids: list | None = None,
        legacy_selected_candidate_ids: list | None = None,
    ) -> dict:
        """Build an unavailable shadow evaluation result."""
        return {
            "schema": "orientation_shadow_evaluation.v1",
            "lane_id": "orientation.initial",
            "requested_mode": requested_mode,
            "effective_mode": "shadow",
            "diagnostic_only": True,
            "legacy_authoritative": True,
            "status": "unavailable",
            "reason": reason,
            "selector_called": False if candidate_count == 0 else True,
            "fallback_used": True,
            "candidate_count": candidate_count,
            "candidate_ids": candidate_ids or [],
            "legacy_selected_candidate_ids": legacy_selected_candidate_ids or [],
            "model_selected_candidate_ids": [],
            "selection_metrics": {
                "legacy_count": len(legacy_selected_candidate_ids) if legacy_selected_candidate_ids else 0,
                "model_count": 0,
                "selection_overlap": [],
                "selection_overlap_count": 0,
                "top1_match": False,
                "exact_match": True,
                "would_change_selection": False,
            },
            "model_summary": {
                "ok": False,
                "status": "",
                "rationale": "",
                "confidence": None,
                "unknown_candidate_ids": [],
                "duplicate_candidate_ids": [],
                "duplicate_input_candidate_ids": [],
                "error_type": error_type,
                "error": error,
            },
        }

    def _build_invalid_result(
        self,
        requested_mode: str,
        reason: str,
        candidate_count: int,
        candidate_ids: list,
        legacy_selected_candidate_ids: list,
    ) -> dict:
        """Build an invalid shadow evaluation result."""
        return {
            "schema": "orientation_shadow_evaluation.v1",
            "lane_id": "orientation.initial",
            "requested_mode": requested_mode,
            "effective_mode": "shadow",
            "diagnostic_only": True,
            "legacy_authoritative": True,
            "status": "invalid",
            "reason": reason,
            "selector_called": True,
            "fallback_used": True,
            "candidate_count": candidate_count,
            "candidate_ids": candidate_ids,
            "legacy_selected_candidate_ids": legacy_selected_candidate_ids,
            "model_selected_candidate_ids": [],
            "selection_metrics": {
                "legacy_count": len(legacy_selected_candidate_ids),
                "model_count": 0,
                "selection_overlap": [],
                "selection_overlap_count": 0,
                "top1_match": False,
                "exact_match": True,
                "would_change_selection": False,
            },
            "model_summary": {
                "ok": False,
                "status": "",
                "rationale": "",
                "confidence": None,
                "unknown_candidate_ids": [],
                "duplicate_candidate_ids": [],
                "duplicate_input_candidate_ids": [],
                "error_type": "TypeError",
                "error": "selector returned non-dict",
            },
        }

    def _build_selector_unavailable_result(
        self,
        requested_mode: str,
        selector_result: dict,
        candidate_count: int,
        candidate_ids: list,
        legacy_selected_candidate_ids: list,
    ) -> dict:
        """Build a selector-unavailable shadow evaluation result."""
        rationale_bounded = self._bounded_text(selector_result.get("rationale"), 160)
        return {
            "schema": "orientation_shadow_evaluation.v1",
            "lane_id": "orientation.initial",
            "requested_mode": requested_mode,
            "effective_mode": "shadow",
            "diagnostic_only": True,
            "legacy_authoritative": True,
            "status": "unavailable",
            "reason": rationale_bounded or "selector_unavailable",
            "selector_called": True,
            "fallback_used": True,
            "candidate_count": candidate_count,
            "candidate_ids": candidate_ids,
            "legacy_selected_candidate_ids": legacy_selected_candidate_ids,
            "model_selected_candidate_ids": [],
            "selection_metrics": {
                "legacy_count": len(legacy_selected_candidate_ids),
                "model_count": 0,
                "selection_overlap": [],
                "selection_overlap_count": 0,
                "top1_match": False,
                "exact_match": True,
                "would_change_selection": False,
            },
            "model_summary": {
                "ok": False,
                "status": "",
                "rationale": "",
                "confidence": None,
                "unknown_candidate_ids": [],
                "duplicate_candidate_ids": [],
                "duplicate_input_candidate_ids": [],
                "error_type": "",
                "error": "",
            },
        }


__all__ = [
    "ContractMutationPhase",
    "ShadowEvaluationPhase",
]