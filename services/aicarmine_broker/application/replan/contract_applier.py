"""Unverified old-text replan applier."""

from __future__ import annotations

import json
from typing import Any


class UnverifiedOldTextReplanApplier:
    """Applica replan con old_text/new_text non verificato."""

    def apply(
        self,
        result: dict[str, Any],
        contract: dict[str, Any],
    ) -> dict[str, Any]:
        """Applica il replan al risultato."""
        if result.get("ok") is not True:
            return result

        required_call = result.get("required_next_tool_call") if isinstance(result.get("required_next_tool_call"), dict) else {}
        tool = str(required_call.get("tool") or "").strip().lower()

        if tool in ("repo_propose_code_edit", "repo_apply_patch"):
            return self._apply_code_edit_replan(result, required_call, contract)

        return result

    def _apply_code_edit_replan(
        self,
        result: dict[str, Any],
        required_call: dict[str, Any],
        contract: dict[str, Any],
    ) -> dict[str, Any]:
        """Applica code edit replan."""
        rationale = str(result.get("rationale") or "").strip()
        decision = str(result.get("decision") or "").strip().lower()

        if "rewrite" in rationale.lower() or "patch" in rationale.lower():
            result["replan_strategy"] = "unverified_old_text_rewrite"
            result["replan_rationale"] = rationale
            result["replan_decision"] = decision
            return result

        result["replan_strategy"] = "none"
        result["replan_rationale"] = ""
        result["replan_decision"] = decision
        return result

    def apply_unverified_old_text_replan_contract(
        self,
        contract: dict[str, Any],
        *,
        target_file: str,
        violation: str,
        history: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Apply unverified old-text replan contract logic extracted from planner.py _apply_unverified_old_text_replan_contract."""
        from ...planner import (
            _repo_rel_token,
            _agentic_v2_decision_paths,
            _code_product_build_state_parse,
            _code_product_build_state_has_collecting_progress,
            _code_product_build_state_ready_payload,
            _code_product_source_window_candidate,
        )

        target = _repo_rel_token(target_file)

        def admissible_replan_candidate(item: Any) -> bool:
            if not isinstance(item, dict):
                return False
            tool_name = str(item.get("tool") or "")
            arguments = item.get("arguments") if isinstance(item.get("arguments"), dict) else {}
            if tool_name == "planner_scratchpad_read":
                return True
            if tool_name == "repo_read":
                return target in {
                    _repo_rel_token(path)
                    for path in _agentic_v2_decision_paths(tool_name, arguments)
                }
            if tool_name == "planner_scratchpad_write" and arguments.get("kind") == "code_product_build_state":
                text = str(arguments.get("text") or arguments.get("content") or "")
                state = _code_product_build_state_parse(text)
                return bool(
                    state
                    and (
                        _code_product_build_state_has_collecting_progress(state)
                        or _code_product_build_state_ready_payload(state)
                        or (
                            str(state.get("status") or "") == "blocked_incomplete"
                            and str(state.get("blocker") or "").strip()
                        )
                    )
                )
            if item.get("action") == "block":
                return True
            return False

        existing = [
            item for item in (contract.get("candidate_next_actions") or [])
            if admissible_replan_candidate(item)
        ]
        preferred: list[dict[str, Any]] = []
        for item in existing:
            tool_name = str(item.get("tool") or "")
            if tool_name == "planner_scratchpad_read":
                preferred.append(item)
            elif tool_name == "repo_read" and target in {
                _repo_rel_token(path)
                for path in _agentic_v2_decision_paths(
                    tool_name,
                    item.get("arguments") if isinstance(item.get("arguments"), dict) else {},
                )
            }:
                preferred.append(item)
        route_candidate = _code_product_source_window_candidate(target, history=history)
        if route_candidate:
            preferred.insert(0, route_candidate)
        if not preferred:
            preferred.append(
                {
                    "action": "block",
                    "reason": "code_product_old_text_not_verifiable",
                    "final_answer": (
                        f"{violation}: old_text is not verified in repo_read content for {target}. "
                        "No further source window is available; cannot build a valid diff."
                    ),
                }
            )
        merged: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in [*preferred, *existing]:
            key = json.dumps(item, ensure_ascii=False, sort_keys=True, default=str)
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
        contract["candidate_next_actions"] = merged[:15]
        contract["required_next_progress"] = (
            f"{violation}. Change decision now: use a real planner_scratchpad_read window from "
            "required_working_set/candidate_next_actions if available, otherwise read a useful target "
            "window or return a typed block. Do not repeat placeholder old_text/new_text."
        )
        return contract