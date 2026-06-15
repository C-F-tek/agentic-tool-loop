"""Planner prompt pack builder owner."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping


def _dict_field(mapping: Mapping[str, Any], key: str) -> dict[str, Any]:
    value = mapping.get(key)
    return dict(value) if isinstance(value, dict) else {}


def explicit_request_context_from_state(state: dict[str, Any]) -> dict[str, Any]:
    """Return structured user/operator context saved with a job request.

    This is intentionally separate from ``goal``. The controller preseed logic
    parses the free-form goal for explicit file/scope requests; structured
    request context is planner-visible evidence and must not cause deterministic
    controller reads before the planner turn.
    """
    original_args = _dict_field(state, "original_args")
    raw = original_args.get("context")
    if isinstance(raw, dict):
        parsed = raw
    elif isinstance(raw, str) and raw.strip():
        try:
            loaded = json.loads(raw)
        except Exception:
            loaded = {}
        parsed = loaded if isinstance(loaded, dict) else {}
    else:
        parsed = {}
    if not parsed:
        return {}
    return {
        key: value
        for key, value in parsed.items()
        if key not in {"raw_events", "history", "planner_stream"}
    }


def invocation_context_from_explicit_request_context(context: dict[str, Any]) -> dict[str, Any]:
    """Return caller/audience context that must be visible to the planner.

    Public bridge requests, Codex MCP requests and local diagnostics can all
    reach the same canonical loop. The planner must answer the actual caller,
    not infer the response surface from a router-compatible ``tool_name``.
    """
    for key in ("invocation_context", "caller_context"):
        value = context.get(key)
        if isinstance(value, dict):
            return dict(value)
    if str(context.get("source") or "") == "codex_app_mcp_agentic_loop_client":
        return {
            "schema": "agentic_loop_invocation_context.v1",
            "caller": "codex_app",
            "caller_tool": "aicarmine_agentic_loop_client",
            "source": "codex_app_mcp_agentic_loop_client",
            "entrypoint": "mcp",
            "audience": "operator",
            "response_surface": "codex_app_mcp",
            "repo_root": context.get("codex_mcp_repo_root"),
            "expected_broker_lab_repo": context.get("expected_broker_lab_repo"),
            "router_tool_name": "vulkan_helper",
            "router_tool_name_is_compatibility_only": True,
            "response_contract": (
                "Answer the Codex/operator caller directly. Do not recommend "
                "vulkan_helper, 3571 or OpenWebUI as the caller's next step for "
                "this MCP invocation."
            ),
        }
    return {}


def step_budget_guidance_from_state(state: dict[str, Any]) -> dict[str, Any]:
    guidance = state.get("planner_step_budget_guidance")
    if not isinstance(guidance, dict):
        return {}
    mode = str(guidance.get("mode") or "").strip()
    if mode not in {"prepare_terminal_decision", "force_terminal_decision"}:
        return {}
    return dict(guidance)


@dataclass(frozen=True)
class PromptPackBuilder:
    """Owner for measured planner prompt payload construction."""

    _deps: Mapping[str, Any]
    _config: Mapping[str, Any]

    def build(
        self,
        *,
        job_id: str,
        state: dict[str, Any],
        step: int,
        history: list[dict[str, Any]],
        tool_manifest: list[dict[str, Any]],
        evidence_contract: dict[str, Any],
        planner_memory: dict[str, Any],
        intrinsic_context: dict[str, Any],
        last_tool_result: dict[str, Any],
        native_tools_schema: list[dict[str, Any]] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        deps = self._deps
        config = self._config
        AGENTIC_PLANNER_NATIVE_TOOLS = bool(config["AGENTIC_PLANNER_NATIVE_TOOLS"])
        AGENTIC_PLANNER_NUM_CTX = int(config["AGENTIC_PLANNER_NUM_CTX"])
        AGENTIC_PLANNER_NUM_CTX_CAP = int(config["AGENTIC_PLANNER_NUM_CTX_CAP"])
        AGENTIC_PLANNER_NUM_CTX_REQUESTED = int(config["AGENTIC_PLANNER_NUM_CTX_REQUESTED"])
        AGENTIC_PLANNER_PROMPT_CHAR_BUDGET = int(config["AGENTIC_PLANNER_PROMPT_CHAR_BUDGET"])
        AGENTIC_PLANNER_PROMPT_COMPACT_RATIO = float(config["AGENTIC_PLANNER_PROMPT_COMPACT_RATIO"])
        LAB_REPO = config["LAB_REPO"]

        _available_tools_for_user_payload = deps["available_tools_for_user_payload"]
        _available_tools_window_pack = deps["available_tools_window_pack"]
        _compact_evidence_contract_for_prompt = deps["compact_evidence_contract_for_prompt"]
        _compact_tool_manifest_for_prompt = deps["compact_tool_manifest_for_prompt"]
        _enforce_required_scratchpad_read_continuation_contract = deps[
            "enforce_required_scratchpad_read_continuation_contract"
        ]
        _forbidden_repeated_prompt_window_calls = deps["forbidden_repeated_prompt_window_calls"]
        _hard_budget_evidence_contract_for_prompt = deps["hard_budget_evidence_contract_for_prompt"]
        _hard_budget_tool_shape_examples_for_prompt = deps["hard_budget_tool_shape_examples_for_prompt"]
        _json_char_len = deps["json_char_len"]
        _native_history_message_reserve_chars = deps["native_history_message_reserve_chars"]
        _optional_context_for_prompt = deps["optional_context_for_prompt"]
        _optional_context_window_pack = deps["optional_context_window_pack"]
        _planner_system_for_current_mode = deps["planner_system_for_current_mode"]
        _preserve_required_next_tool_call_for_prompt = deps["preserve_required_next_tool_call_for_prompt"]
        _prompt_budget_report = deps["prompt_budget_report"]
        _prompt_compaction_threshold = deps["prompt_compaction_threshold"]
        _prompt_generation_headroom_char_budget = deps["prompt_generation_headroom_char_budget"]
        _prompt_window_chars = deps["prompt_window_chars"]
        _report_exceeds_generation_headroom = deps["report_exceeds_generation_headroom"]
        _required_working_set_continuation_action = deps["required_working_set_continuation_action"]
        _required_working_set_for_prompt = deps["required_working_set_for_prompt"]
        _tool_shape_examples_for_prompt = deps["tool_shape_examples_for_prompt"]
        _windowed_evidence_contract_for_prompt = deps["windowed_evidence_contract_for_prompt"]
        agent_job_root = deps["agent_job_root"]
        internal_tool_prompt = deps["internal_tool_prompt"]

        goal = str(state.get("goal") or "")
        explicit_request_context = explicit_request_context_from_state(state)
        invocation_context = invocation_context_from_explicit_request_context(explicit_request_context)
        compact_tools = _compact_tool_manifest_for_prompt(tool_manifest)
        available_tools_for_payload = _available_tools_for_user_payload(compact_tools)
        system_prompt_for_budget = _planner_system_for_current_mode()
        extra_prompt_sections = (
            {"native_tools_schema": _json_char_len(native_tools_schema or [])}
            if AGENTIC_PLANNER_NATIVE_TOOLS
            else {}
        )
        native_history_reserve_chars = _native_history_message_reserve_chars(
            history,
            _prompt_window_chars(True, 0),
        )
        if native_history_reserve_chars:
            extra_prompt_sections["native_history_messages_reserve"] = native_history_reserve_chars
        root = agent_job_root(job_id)
        headroom_char_budget = _prompt_generation_headroom_char_budget()
        step_budget_guidance = step_budget_guidance_from_state(state)
        force_terminal_decision = (
            str(step_budget_guidance.get("mode") or "") == "force_terminal_decision"
        )

        def assemble(*, compact_mode: bool, window_chars: int) -> tuple[dict[str, Any], dict[str, Any], int, list[dict[str, Any]]]:
            required_repo_read_window_budget = None
            required_repo_read_item_limit = None
            if compact_mode:
                if headroom_char_budget > 0:
                    required_repo_read_window_budget = max(
                        12000,
                        min(36000, headroom_char_budget // 6),
                    )
                else:
                    required_repo_read_window_budget = max(
                        12000,
                        min(36000, int(window_chars or 3000) * 3),
                    )
                required_repo_read_item_limit = max(
                    1,
                    min(16, required_repo_read_window_budget // 800),
                )
            required_working_set = _required_working_set_for_prompt(
                goal,
                history,
                evidence_contract,
                job_root=root,
                window_chars=window_chars,
                compact_mode=compact_mode,
                max_repo_read_items=required_repo_read_item_limit,
                max_total_repo_read_window_chars=required_repo_read_window_budget,
            )
            required_chars_local = _json_char_len(required_working_set)
            required_errors_local = list(required_working_set.get("errors") or [])
            evidence_for_prompt = (
                _windowed_evidence_contract_for_prompt(
                    root,
                    goal=goal,
                    contract=evidence_contract,
                    window_chars=window_chars,
                    history=history,
                )
                if compact_mode
                else _compact_evidence_contract_for_prompt(evidence_contract)
            )
            continuation_action = _required_working_set_continuation_action(
                required_working_set,
                history=history,
                window_chars=window_chars,
            )
            if continuation_action:
                forbidden_repeated_calls = _forbidden_repeated_prompt_window_calls(
                    history,
                    continuation_action,
                )
                evidence_for_prompt = _enforce_required_scratchpad_read_continuation_contract(
                    evidence_for_prompt,
                    continuation_action,
                )
                if forbidden_repeated_calls:
                    evidence_for_prompt["forbidden_repeated_tool_calls"] = forbidden_repeated_calls
            micro_batch_contract = (
                evidence_for_prompt.get("micro_batch_contract")
                if isinstance(evidence_for_prompt.get("micro_batch_contract"), dict)
                else {}
            )
            micro_batch_allowed = bool(micro_batch_contract.get("allowed"))
            tool_shape_examples = _tool_shape_examples_for_prompt()
            payload_local = {
                "job_id": job_id,
                "goal": goal,
                "approval_mode": state.get("approval_mode"),
                "max_steps": state.get("max_steps"),
                "current_step": step,
                "lab_repo": str(LAB_REPO),
                "prompt_pack_contract": {
                    "schema": "planner_prompt_pack.v1",
                    "num_ctx_requested": AGENTIC_PLANNER_NUM_CTX_REQUESTED,
                    "num_ctx_cap": AGENTIC_PLANNER_NUM_CTX_CAP,
                    "num_ctx_effective": AGENTIC_PLANNER_NUM_CTX,
                    "prompt_char_budget": AGENTIC_PLANNER_PROMPT_CHAR_BUDGET,
                    "generation_headroom_char_budget": headroom_char_budget,
                    "generation_headroom_reserve_chars": max(0, AGENTIC_PLANNER_PROMPT_CHAR_BUDGET - headroom_char_budget),
                    "prompt_compaction_threshold_chars": _prompt_compaction_threshold(),
                    "prompt_compaction_ratio": AGENTIC_PLANNER_PROMPT_COMPACT_RATIO,
                    "compact_mode": compact_mode,
                    "window_chars": window_chars,
                    "native_tools_schema_accounted_in_budget": bool(extra_prompt_sections),
                    "native_tools_schema_chars": extra_prompt_sections.get("native_tools_schema", 0),
                    "native_history_messages_reserve_chars": native_history_reserve_chars,
                    "required_working_set_not_truncated": True,
                    "required_working_set_uses_real_sqlite_windows_when_compacted": True,
                    "required_working_set_repo_read_global_window_budget_chars": required_repo_read_window_budget,
                    "required_working_set_repo_read_item_limit": required_repo_read_item_limit,
                    "optional_context_may_be_omitted_not_used_as_required_payload": True,
                    "step_budget_terminal_guidance_active": bool(step_budget_guidance),
                    "required_window_continuation_suppressed_by_step_budget": False,
                    "step_budget_terminal_guidance_deferred_by_required_window_continuation": bool(
                        force_terminal_decision and continuation_action
                    ),
                },
                "terminal_environment_contract": {
                    "platform": "windows",
                    "shell": "powershell_noninteractive",
                    "important": [
                        "For user filesystem work outside LAB_REPO prefer terminal_list_files or terminal_search_files.",
                        "For diagnostic shell commands prefer terminal_run_command_wait, not repo_command.",
                        "Never use Linux commands such as ls -la, find . -type f, grep, cat or pwd on Windows.",
                        "Native Open Terminal run_command may return status=running and exit_code=null; terminal_run_command_wait returns final output.",
                    ],
                },
                "available_tools": available_tools_for_payload,
                "tool_shape_examples": tool_shape_examples,
                "required_working_set": required_working_set,
                **(
                    {"explicit_request_context": explicit_request_context}
                    if explicit_request_context
                    else {}
                ),
                **(
                    {"invocation_context": invocation_context}
                    if invocation_context
                    else {}
                ),
                "optional_context": _optional_context_for_prompt(
                    root=root,
                    goal=goal,
                    history=history,
                    planner_memory=planner_memory,
                    intrinsic_context=intrinsic_context,
                    last_tool_result=last_tool_result,
                    compact_mode=compact_mode,
                    window_chars=window_chars,
                ),
                "evidence_contract": evidence_for_prompt,
                "required_response_format": (
                    {
                        "native_tool_calls_required_for_tools": True,
                        "content_json_only_for": ["final", "block"],
                        "allowed_content_actions": ["final", "block"],
                        "textual_tool_action_allowed": False,
                        "tool_execution": "message.tool_calls",
                        "native_tool_batch_allowed": micro_batch_allowed,
                        "native_tool_batch_max_size": (
                            micro_batch_contract.get("max_batch_size")
                            if micro_batch_allowed else
                            1
                        ),
                        "native_tool_batch_rule": (
                            "You may emit multiple native message.tool_calls in one turn only when "
                            "evidence_contract.micro_batch_contract.allowed=true and every call exactly "
                            "matches one allowed_batch_actions entry by tool and arguments. Batch only "
                            "read-only actions; do not batch write/apply/command/final/block actions."
                        ),
                        "tool_arguments_rule": (
                            "When choosing a tool, emit a native tool_call using the provided Ollama tools schema. "
                            "Do not emit JSON content with action=tool."
                        ),
                        "final_answer": "required when content JSON action=final or block",
                        "path_rule": (
                            "Choose paths from required_working_set, evidence_contract, "
                            "candidate_next_actions or explicit user input. Do not copy static example paths."
                        ),
                    }
                    if AGENTIC_PLANNER_NATIVE_TOOLS
                    else {
                        "json_only": True,
                        "allowed_actions": ["tool", "final", "block"],
                        "tool": internal_tool_prompt(exclude_vulkan=False),
                        "arguments": {},
                        "reason": "short operational reason",
                        "final_answer": "required when action=final or block",
                        "path_rule": (
                            "Choose paths from required_working_set, evidence_contract, "
                            "candidate_next_actions or explicit user input. Do not copy static example paths."
                        ),
                    }
                ),
            }
            if step_budget_guidance:
                payload_local["planner_step_budget_guidance"] = step_budget_guidance
            if isinstance(evidence_for_prompt.get("required_next_tool_call"), dict):
                payload_local["required_next_tool_call"] = evidence_for_prompt["required_next_tool_call"]
            if isinstance(evidence_for_prompt.get("forbidden_repeated_tool_calls"), list):
                payload_local["forbidden_repeated_tool_calls"] = evidence_for_prompt["forbidden_repeated_tool_calls"]
            report_local = _prompt_budget_report(
                payload_local,
                system_prompt=system_prompt_for_budget,
                extra_prompt_sections=extra_prompt_sections,
            )
            report_local["required_working_set_chars"] = required_chars_local
            report_local["required_working_set_errors"] = required_errors_local
            report_local["compact_mode"] = compact_mode
            report_local["window_chars"] = window_chars
            report_local["native_history_reserve_chars"] = native_history_reserve_chars
            return payload_local, report_local, required_chars_local, required_errors_local

        payload, report, required_chars, required_errors = assemble(
            compact_mode=False,
            window_chars=_prompt_window_chars(False),
        )
        threshold = _prompt_compaction_threshold()
        if threshold and int(report.get("total_prompt_chars") or 0) > threshold:
            for attempt in range(8):
                payload, report, required_chars, required_errors = assemble(
                    compact_mode=True,
                    window_chars=_prompt_window_chars(True, attempt),
                )
                total_for_compaction = int(report.get("total_prompt_chars") or 0)
                if int(report.get("native_history_reserve_chars") or 0) > 0:
                    total_for_compaction = max(
                        0,
                        total_for_compaction - int(report.get("native_history_reserve_chars") or 0),
                    )
                if total_for_compaction <= threshold:
                    break
        if _report_exceeds_generation_headroom(report, headroom_char_budget):
            optional_for_window = _dict_field(payload, "optional_context")
            for hard_window_chars in (1000, 700, 500):
                evidence_before_hard_budget = _dict_field(payload, "evidence_contract")
                payload["optional_context"] = _optional_context_window_pack(
                    root,
                    goal=goal,
                    optional_context=optional_for_window,
                    window_chars=hard_window_chars,
                    reason="planner_prompt_pack_over_budget_after_compact_mode",
                )
                prompt_contract = _dict_field(payload, "prompt_pack_contract")
                prompt_contract["compact_mode"] = True
                prompt_contract["hard_budget_optional_context_windowed"] = True
                prompt_contract["hard_budget_optional_context_window_chars"] = hard_window_chars
                payload["prompt_pack_contract"] = prompt_contract
                payload["evidence_contract"] = _hard_budget_evidence_contract_for_prompt(
                    root,
                    goal=goal,
                    contract=evidence_contract,
                    window_chars=hard_window_chars,
                    history=history,
                    reason="planner_prompt_pack_over_budget_after_compact_mode",
                )
                _preserve_required_next_tool_call_for_prompt(payload, evidence_before_hard_budget)
                payload["tool_shape_examples"] = _hard_budget_tool_shape_examples_for_prompt()
                payload_evidence = _dict_field(payload, "evidence_contract")
                if isinstance(payload_evidence.get("required_next_tool_call"), dict):
                    payload["required_next_tool_call"] = payload_evidence["required_next_tool_call"]
                elif "required_next_tool_call" in payload:
                    payload.pop("required_next_tool_call", None)
                if isinstance(payload_evidence.get("forbidden_repeated_tool_calls"), list):
                    payload["forbidden_repeated_tool_calls"] = payload_evidence["forbidden_repeated_tool_calls"]
                elif "forbidden_repeated_tool_calls" in payload:
                    payload.pop("forbidden_repeated_tool_calls", None)
                report = _prompt_budget_report(
                    payload,
                    system_prompt=system_prompt_for_budget,
                    extra_prompt_sections=extra_prompt_sections,
                )
                report["required_working_set_chars"] = required_chars
                report["required_working_set_errors"] = required_errors
                report["compact_mode"] = True
                report["window_chars"] = hard_window_chars
                report["native_history_reserve_chars"] = native_history_reserve_chars
                if not _report_exceeds_generation_headroom(report, headroom_char_budget):
                    break
        if (
            _report_exceeds_generation_headroom(report, headroom_char_budget)
            and int((report.get("sections") or {}).get("available_tools") or 0) > 2500
            and _dict_field(payload, "available_tools").get("schema") != "planner_available_tools_window.v1"
        ):
            for hard_window_chars in (700, 500):
                payload["available_tools"] = _available_tools_window_pack(
                    root,
                    goal=goal,
                    available_tools=available_tools_for_payload,
                    window_chars=hard_window_chars,
                    reason="planner_prompt_pack_over_budget_available_tools_windowed",
                )
                prompt_contract = _dict_field(payload, "prompt_pack_contract")
                prompt_contract["compact_mode"] = True
                prompt_contract["available_tools_windowed"] = True
                prompt_contract["available_tools_window_chars"] = hard_window_chars
                payload["prompt_pack_contract"] = prompt_contract
                report = _prompt_budget_report(
                    payload,
                    system_prompt=system_prompt_for_budget,
                    extra_prompt_sections=extra_prompt_sections,
                )
                report["required_working_set_chars"] = required_chars
                report["required_working_set_errors"] = required_errors
                report["compact_mode"] = True
                report["window_chars"] = hard_window_chars
                report["native_history_reserve_chars"] = native_history_reserve_chars
                if not _report_exceeds_generation_headroom(report, headroom_char_budget):
                    break
        payload["prompt_budget_report"] = {
            "schema": report.get("schema"),
            "char_budget": report.get("char_budget"),
            "generation_headroom_char_budget": report.get("generation_headroom_char_budget"),
            "generation_headroom_reserve_chars": report.get("generation_headroom_reserve_chars"),
            "total_prompt_chars": report.get("total_prompt_chars"),
            "over_budget": report.get("over_budget"),
            "over_generation_headroom_budget": report.get("over_generation_headroom_budget"),
            "extra_prompt_chars": report.get("extra_prompt_chars"),
            "native_tools_schema_chars": extra_prompt_sections.get("native_tools_schema", 0),
            "native_history_reserve_chars": extra_prompt_sections.get("native_history_messages_reserve", 0),
            "required_working_set_chars": report.get("required_working_set_chars"),
            "compact_mode": report.get("compact_mode"),
            "window_chars": report.get("window_chars"),
        }
        for _ in range(6):
            report = _prompt_budget_report(
                payload,
                system_prompt=system_prompt_for_budget,
                extra_prompt_sections=extra_prompt_sections,
            )
            report["required_working_set_chars"] = required_chars
            report["required_working_set_errors"] = required_errors
            prompt_contract = _dict_field(payload, "prompt_pack_contract")
            report["compact_mode"] = prompt_contract.get("compact_mode")
            report["window_chars"] = prompt_contract.get("window_chars")
            report["native_history_reserve_chars"] = native_history_reserve_chars
            payload["prompt_budget_report"] = {
                "schema": report.get("schema"),
                "char_budget": report.get("char_budget"),
                "generation_headroom_char_budget": report.get("generation_headroom_char_budget"),
                "generation_headroom_reserve_chars": report.get("generation_headroom_reserve_chars"),
                "total_prompt_chars": report.get("total_prompt_chars"),
                "over_budget": report.get("over_budget"),
                "over_generation_headroom_budget": report.get("over_generation_headroom_budget"),
                "extra_prompt_chars": report.get("extra_prompt_chars"),
                "native_tools_schema_chars": extra_prompt_sections.get("native_tools_schema", 0),
                "native_history_reserve_chars": extra_prompt_sections.get("native_history_messages_reserve", 0),
                "required_working_set_chars": report.get("required_working_set_chars"),
                "compact_mode": report.get("compact_mode"),
                "window_chars": report.get("window_chars"),
            }
            actual_total = (
                len(system_prompt_for_budget)
                + _json_char_len(payload)
                + int(report.get("extra_prompt_chars") or 0)
            )
            if int(report.get("total_prompt_chars") or 0) == actual_total:
                break
        if (
            _report_exceeds_generation_headroom(report, headroom_char_budget)
            and isinstance(payload.get("optional_context"), dict)
            and payload["optional_context"].get("schema") != "planner_optional_context_window_pack.v1"
        ):
            optional_for_window = _dict_field(payload, "optional_context")
            for hard_window_chars in (700, 500):
                evidence_before_hard_budget = _dict_field(payload, "evidence_contract")
                payload["optional_context"] = _optional_context_window_pack(
                    root,
                    goal=goal,
                    optional_context=optional_for_window,
                    window_chars=hard_window_chars,
                    reason="planner_prompt_pack_over_budget_after_budget_report",
                )
                prompt_contract = _dict_field(payload, "prompt_pack_contract")
                prompt_contract["compact_mode"] = True
                prompt_contract["hard_budget_optional_context_windowed"] = True
                prompt_contract["hard_budget_optional_context_window_chars"] = hard_window_chars
                payload["prompt_pack_contract"] = prompt_contract
                payload["evidence_contract"] = _hard_budget_evidence_contract_for_prompt(
                    root,
                    goal=goal,
                    contract=evidence_contract,
                    window_chars=hard_window_chars,
                    history=history,
                    reason="planner_prompt_pack_over_budget_after_budget_report",
                )
                _preserve_required_next_tool_call_for_prompt(payload, evidence_before_hard_budget)
                payload["tool_shape_examples"] = _hard_budget_tool_shape_examples_for_prompt()
                payload_evidence = _dict_field(payload, "evidence_contract")
                if isinstance(payload_evidence.get("required_next_tool_call"), dict):
                    payload["required_next_tool_call"] = payload_evidence["required_next_tool_call"]
                elif "required_next_tool_call" in payload:
                    payload.pop("required_next_tool_call", None)
                if isinstance(payload_evidence.get("forbidden_repeated_tool_calls"), list):
                    payload["forbidden_repeated_tool_calls"] = payload_evidence["forbidden_repeated_tool_calls"]
                elif "forbidden_repeated_tool_calls" in payload:
                    payload.pop("forbidden_repeated_tool_calls", None)
                for _ in range(6):
                    report = _prompt_budget_report(
                        payload,
                        system_prompt=system_prompt_for_budget,
                        extra_prompt_sections=extra_prompt_sections,
                    )
                    report["required_working_set_chars"] = required_chars
                    report["required_working_set_errors"] = required_errors
                    report["compact_mode"] = True
                    report["window_chars"] = hard_window_chars
                    report["native_history_reserve_chars"] = native_history_reserve_chars
                    payload["prompt_budget_report"] = {
                        "schema": report.get("schema"),
                        "char_budget": report.get("char_budget"),
                        "generation_headroom_char_budget": report.get("generation_headroom_char_budget"),
                        "generation_headroom_reserve_chars": report.get("generation_headroom_reserve_chars"),
                        "total_prompt_chars": report.get("total_prompt_chars"),
                        "over_budget": report.get("over_budget"),
                        "over_generation_headroom_budget": report.get("over_generation_headroom_budget"),
                        "extra_prompt_chars": report.get("extra_prompt_chars"),
                        "native_tools_schema_chars": extra_prompt_sections.get("native_tools_schema", 0),
                        "native_history_reserve_chars": extra_prompt_sections.get("native_history_messages_reserve", 0),
                        "required_working_set_chars": report.get("required_working_set_chars"),
                        "compact_mode": report.get("compact_mode"),
                        "window_chars": report.get("window_chars"),
                    }
                    actual_total = (
                        len(system_prompt_for_budget)
                        + _json_char_len(payload)
                        + int(report.get("extra_prompt_chars") or 0)
                    )
                    if int(report.get("total_prompt_chars") or 0) == actual_total:
                        break
                if not _report_exceeds_generation_headroom(report, headroom_char_budget):
                    break
        if native_history_reserve_chars:
            total_without_native_history_reserve = max(
                0,
                int(report.get("total_prompt_chars") or 0) - native_history_reserve_chars,
            )
            history_message_char_budget = (
                max(0, headroom_char_budget - total_without_native_history_reserve)
                if headroom_char_budget > 0
                else max(0, AGENTIC_PLANNER_NUM_CTX * 2)
            )
            report["native_history_reserve_is_synthetic"] = True
            report["total_prompt_chars_without_native_history_reserve"] = total_without_native_history_reserve
            report["over_budget_without_native_history_reserve"] = bool(
                AGENTIC_PLANNER_PROMPT_CHAR_BUDGET > 0
                and total_without_native_history_reserve > AGENTIC_PLANNER_PROMPT_CHAR_BUDGET
            )
            report["over_generation_headroom_without_native_history_reserve"] = bool(
                headroom_char_budget > 0
                and total_without_native_history_reserve > headroom_char_budget
            )
            report["history_message_char_budget"] = history_message_char_budget
            payload_report = _dict_field(payload, "prompt_budget_report")
            payload_report["native_history_reserve_is_synthetic"] = True
            payload_report["total_prompt_chars_without_native_history_reserve"] = total_without_native_history_reserve
            payload_report["over_budget_without_native_history_reserve"] = report["over_budget_without_native_history_reserve"]
            payload_report["over_generation_headroom_without_native_history_reserve"] = report["over_generation_headroom_without_native_history_reserve"]
            payload_report["history_message_char_budget"] = history_message_char_budget
            payload["prompt_budget_report"] = payload_report
            if (
                history_message_char_budget < 2500
                and _dict_field(payload, "optional_context").get("schema") == "planner_optional_context_window_pack.v1"
                and isinstance(_dict_field(payload, "optional_context").get("successful_tool_payload_windows"), list)
                and _dict_field(payload, "optional_context").get("successful_tool_payload_windows")
            ):
                optional_context_copy = _dict_field(payload, "optional_context")
                optional_context_copy.pop("successful_tool_payload_windows", None)
                payload["optional_context"] = optional_context_copy
                prompt_contract = _dict_field(payload, "prompt_pack_contract")
                prompt_contract["compact_mode"] = True
                prompt_contract["native_history_headroom_successful_payload_windows_omitted"] = True
                prompt_contract["native_history_headroom_successful_payload_windows_reason"] = (
                    "successful tool payload windows are transported through native history messages; "
                    "duplicating them in optional_context consumed the history budget."
                )
                payload["prompt_pack_contract"] = prompt_contract
                report = _prompt_budget_report(
                    payload,
                    system_prompt=system_prompt_for_budget,
                    extra_prompt_sections=extra_prompt_sections,
                )
                report["required_working_set_chars"] = required_chars
                report["required_working_set_errors"] = required_errors
                report["compact_mode"] = True
                report["window_chars"] = (prompt_contract or {}).get("window_chars")
                report["native_history_reserve_chars"] = native_history_reserve_chars
                total_without_native_history_reserve = max(
                    0,
                    int(report.get("total_prompt_chars") or 0) - native_history_reserve_chars,
                )
                history_message_char_budget = (
                    max(0, headroom_char_budget - total_without_native_history_reserve)
                    if headroom_char_budget > 0
                    else max(0, AGENTIC_PLANNER_NUM_CTX * 2)
                )
                report["native_history_reserve_is_synthetic"] = True
                report["total_prompt_chars_without_native_history_reserve"] = total_without_native_history_reserve
                report["over_budget_without_native_history_reserve"] = bool(
                    AGENTIC_PLANNER_PROMPT_CHAR_BUDGET > 0
                    and total_without_native_history_reserve > AGENTIC_PLANNER_PROMPT_CHAR_BUDGET
                )
                report["over_generation_headroom_without_native_history_reserve"] = bool(
                    headroom_char_budget > 0
                    and total_without_native_history_reserve > headroom_char_budget
                )
                report["history_message_char_budget"] = history_message_char_budget
                payload_report = _dict_field(payload, "prompt_budget_report")
                payload_report["schema"] = report.get("schema")
                payload_report["char_budget"] = report.get("char_budget")
                payload_report["generation_headroom_char_budget"] = report.get("generation_headroom_char_budget")
                payload_report["generation_headroom_reserve_chars"] = report.get("generation_headroom_reserve_chars")
                payload_report["total_prompt_chars"] = report.get("total_prompt_chars")
                payload_report["over_budget"] = report.get("over_budget")
                payload_report["over_generation_headroom_budget"] = report.get("over_generation_headroom_budget")
                payload_report["extra_prompt_chars"] = report.get("extra_prompt_chars")
                payload_report["native_tools_schema_chars"] = extra_prompt_sections.get("native_tools_schema", 0)
                payload_report["native_history_reserve_chars"] = extra_prompt_sections.get("native_history_messages_reserve", 0)
                payload_report["required_working_set_chars"] = report.get("required_working_set_chars")
                payload_report["compact_mode"] = True
                payload_report["window_chars"] = report.get("window_chars")
                payload_report["native_history_reserve_is_synthetic"] = True
                payload_report["total_prompt_chars_without_native_history_reserve"] = total_without_native_history_reserve
                payload_report["over_budget_without_native_history_reserve"] = report["over_budget_without_native_history_reserve"]
                payload_report["over_generation_headroom_without_native_history_reserve"] = report["over_generation_headroom_without_native_history_reserve"]
                payload_report["history_message_char_budget"] = history_message_char_budget
                payload["prompt_budget_report"] = payload_report
            if (
                history_message_char_budget < 2500
                and _dict_field(payload, "optional_context").get("schema") != "planner_optional_context_window_pack.v1"
            ):
                optional_for_window = _dict_field(payload, "optional_context")
                for hard_window_chars in (500,):
                    payload["optional_context"] = _optional_context_window_pack(
                        root,
                        goal=goal,
                        optional_context=optional_for_window,
                        window_chars=hard_window_chars,
                        reason="planner_native_history_message_budget_low",
                    )
                    prompt_contract = _dict_field(payload, "prompt_pack_contract")
                    prompt_contract["compact_mode"] = True
                    prompt_contract["native_history_headroom_optional_context_windowed"] = True
                    prompt_contract["native_history_headroom_optional_context_window_chars"] = hard_window_chars
                    payload["prompt_pack_contract"] = prompt_contract
                    report = _prompt_budget_report(
                        payload,
                        system_prompt=system_prompt_for_budget,
                        extra_prompt_sections=extra_prompt_sections,
                    )
                    report["required_working_set_chars"] = required_chars
                    report["required_working_set_errors"] = required_errors
                    report["compact_mode"] = True
                    report["window_chars"] = hard_window_chars
                    report["native_history_reserve_chars"] = native_history_reserve_chars
                    total_without_native_history_reserve = max(
                        0,
                        int(report.get("total_prompt_chars") or 0) - native_history_reserve_chars,
                    )
                    history_message_char_budget = (
                        max(0, headroom_char_budget - total_without_native_history_reserve)
                        if headroom_char_budget > 0
                        else max(0, AGENTIC_PLANNER_NUM_CTX * 2)
                    )
                    report["native_history_reserve_is_synthetic"] = True
                    report["total_prompt_chars_without_native_history_reserve"] = total_without_native_history_reserve
                    report["over_budget_without_native_history_reserve"] = bool(
                        AGENTIC_PLANNER_PROMPT_CHAR_BUDGET > 0
                        and total_without_native_history_reserve > AGENTIC_PLANNER_PROMPT_CHAR_BUDGET
                    )
                    report["over_generation_headroom_without_native_history_reserve"] = bool(
                        headroom_char_budget > 0
                        and total_without_native_history_reserve > headroom_char_budget
                    )
                    report["history_message_char_budget"] = history_message_char_budget
                    payload_report = _dict_field(payload, "prompt_budget_report")
                    payload_report["schema"] = report.get("schema")
                    payload_report["char_budget"] = report.get("char_budget")
                    payload_report["generation_headroom_char_budget"] = report.get("generation_headroom_char_budget")
                    payload_report["generation_headroom_reserve_chars"] = report.get("generation_headroom_reserve_chars")
                    payload_report["total_prompt_chars"] = report.get("total_prompt_chars")
                    payload_report["over_budget"] = report.get("over_budget")
                    payload_report["over_generation_headroom_budget"] = report.get("over_generation_headroom_budget")
                    payload_report["extra_prompt_chars"] = report.get("extra_prompt_chars")
                    payload_report["native_tools_schema_chars"] = extra_prompt_sections.get("native_tools_schema", 0)
                    payload_report["native_history_reserve_chars"] = extra_prompt_sections.get("native_history_messages_reserve", 0)
                    payload_report["required_working_set_chars"] = report.get("required_working_set_chars")
                    payload_report["compact_mode"] = True
                    payload_report["window_chars"] = hard_window_chars
                    payload_report["native_history_reserve_is_synthetic"] = True
                    payload_report["total_prompt_chars_without_native_history_reserve"] = total_without_native_history_reserve
                    payload_report["over_budget_without_native_history_reserve"] = report["over_budget_without_native_history_reserve"]
                    payload_report["over_generation_headroom_without_native_history_reserve"] = report["over_generation_headroom_without_native_history_reserve"]
                    payload_report["history_message_char_budget"] = history_message_char_budget
                    payload["prompt_budget_report"] = payload_report
                    if history_message_char_budget >= 2500:
                        break
        return payload, report


def build_planner_user_payload(
    *,
    job_id: str,
    state: dict[str, Any],
    step: int,
    history: list[dict[str, Any]],
    tool_manifest: list[dict[str, Any]],
    evidence_contract: dict[str, Any],
    planner_memory: dict[str, Any],
    intrinsic_context: dict[str, Any],
    last_tool_result: dict[str, Any],
    deps: Mapping[str, Any],
    config: Mapping[str, Any],
    native_tools_schema: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Compatibility entrypoint for ``PromptPackBuilder``."""
    return PromptPackBuilder(_deps=deps, _config=config).build(
        job_id=job_id,
        state=state,
        step=step,
        history=history,
        tool_manifest=tool_manifest,
        evidence_contract=evidence_contract,
        planner_memory=planner_memory,
        intrinsic_context=intrinsic_context,
        last_tool_result=last_tool_result,
        native_tools_schema=native_tools_schema,
    )
