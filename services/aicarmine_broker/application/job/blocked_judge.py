"""Blocked job judge for job lifecycle."""

from __future__ import annotations

import json
from typing import Any

from ...config import (
    AGENTIC_PLANNER_NUM_CTX,
    AGENTIC_PLANNER_NUM_CTX_CAP,
    AGENTIC_PLANNER_STEP_TIMEOUT,
    OLLAMA_KEEP_ALIVE,
    PLANNER_MODEL,
    PLANNER_URL,
)


def _list_or_empty(value: Any) -> list:
    return value if isinstance(value, list) else []


def _dict_or_empty(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _prompt_clip_value(value: Any, *, text_limit: int = 1600, list_limit: int = 6) -> Any:
    """Clip a value for prompt usage."""
    if isinstance(value, dict):
        return {k: _prompt_clip_value(v, text_limit=text_limit, list_limit=list_limit) for k, v in list(value.items())[:list_limit]}
    if isinstance(value, list):
        return [_prompt_clip_value(item, text_limit=text_limit, list_limit=list_limit) for item in value[:list_limit]]
    if isinstance(value, str):
        return value[:text_limit]
    return value


def _prompt_clip_text(text: str, limit: int = 500) -> str:
    """Clip text to a limit."""
    return text[:limit] if text else ""


class BlockedJobJudge:
    """Judge blocked jobs for terminal response."""

    def __init__(
        self,
        planner_url: str = PLANNER_URL,
        model: str = PLANNER_MODEL,
        timeout: int = AGENTIC_PLANNER_STEP_TIMEOUT,
    ) -> None:
        self.planner_url = planner_url
        self.model = model
        self.timeout = timeout

    def judge(
        self,
        goal: str,
        decision: dict[str, Any],
        validation: dict[str, Any],
        prevalidation_feedback: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Judge blocked job status."""
        violations = _list_or_empty(validation.get("violations"))
        contract = _dict_or_empty(validation.get("evidence_contract"))

        request_payload = {
            "schema": "planner_blocked_job_judge_request.v1",
            "task": "judge_blocked_job_status",
            "goal": str(goal or ""),
            "rejected_decision": _prompt_clip_value(
                {
                    k: decision.get(k)
                    for k in ("action", "tool", "arguments", "reason", "final_answer")
                    if decision.get(k) not in (None, "", [], {})
                },
                text_limit=1600,
                list_limit=6,
            ),
            "validator_violations": violations,
            "evidence_contract": contract,
            "prevalidation_feedback": _prompt_clip_value(prevalidation_feedback, text_limit=900, list_limit=8) if isinstance(prevalidation_feedback, dict) else None,
            "rules": [
                "Return strict JSON only.",
                "Do not execute tools and do not invent payload content.",
                "The next planner turn must still emit the action; validator remains authoritative.",
                "For blocked job, determine if the job is truly blocked or can continue.",
                "If prevalidation_feedback is present, use it to inform the judgment.",
                "Use required_next_tool_call only for a concrete read/search/window route, never for invented code edits.",
            ],
            "allowed_required_next_tools": sorted(self._BLOCKED_JOB_ROUTE_TOOLS),
            "required_json_shape": {
                "decision": "blocked | unblocked | retry_same_context",
                "required_next_progress": "one concise instruction for the next planner turn",
                "required_next_tool_call": {
                    "tool": "repo_read | repo_semantic_search | repo_rg_search | repo_search | repo_list_files | planner_scratchpad_read",
                    "arguments": {"path": "or query/document selector"},
                    "reason": "why this route is required",
                },
                "rationale": "short reason",
                "confidence": 0.0,
            },
        }

        payload = {
            "model": self.model,
            "stream": False,
            "keep_alive": OLLAMA_KEEP_ALIVE,
            "think": False,
            "format": "json",
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a specialized planner blocked job judge. You do not solve the task. "
                        "You determine if a job is truly blocked or can continue. Return strict JSON only."
                    ),
                },
                {"role": "user", "content": json.dumps(request_payload, ensure_ascii=False, default=str)},
            ],
            "options": {
                "temperature": 0,
                "num_predict": 700,
                "num_ctx": max(
                    4096,
                    min(
                        int(AGENTIC_PLANNER_NUM_CTX_CAP or AGENTIC_PLANNER_NUM_CTX or 8192),
                        int(AGENTIC_PLANNER_NUM_CTX or 8192),
                    ),
                ),
            },
        }

        timeout_seconds = min(60, max(15, int(self.timeout or 30)))
        response = self._post_json(self.planner_url, payload, timeout_seconds)

        if response.get("backend_unreachable") or response.get("backend_timeout") or response.get("error"):
            return {
                "schema": "planner_blocked_job_judge_result.v1",
                "available": False,
                "ok": False,
                "decision": "unavailable",
                "error": response.get("error") or response.get("error_type") or "planner_blocked_job_judge_backend_error",
                "planner_model": self.model,
                "planner_url": self.planner_url,
                "timeout_seconds": timeout_seconds,
            }

        message = _dict_or_empty(response.get("message"))
        raw_text = str(message.get("content") or response.get("response") or response.get("partial_content") or "")
        decoded = self._parse_and_repair_json(raw_text, request_payload, timeout_seconds)
        result = self._sanitize_response(decoded)
        result.update({
            "planner_model": self.model,
            "planner_url": self.planner_url,
            "timeout_seconds": timeout_seconds,
        })
        return result

    def _post_json(self, url: str, payload: dict, timeout: int) -> dict:
        """Invia una richiesta POST JSON."""
        try:
            import urllib.request
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            return {"error": str(e), "error_type": "http_error"}

    def _parse_and_repair_json(self, raw_text: str, request_payload: dict, timeout: int) -> dict:
        """Estrae e ripara JSON malformato."""
        from ...planner import parse_strict_json_object_diagnostics
        parse_diagnostics = parse_strict_json_object_diagnostics(raw_text)
        decoded = parse_diagnostics.get("decoded") if parse_diagnostics.get("ok") is True else {}
        if parse_diagnostics.get("ok") is not True and raw_text.strip():
            repair_request_payload = {
                "schema": "planner_blocked_job_judge_json_repair_request.v1",
                "task": "repair_planner_blocked_job_judge_json",
                "original_specialist_request": request_payload,
                "invalid_response_preview": _prompt_clip_text(raw_text, 4000),
                "json_parse_error_type": parse_diagnostics.get("error_type"),
                "json_parse_error": parse_diagnostics.get("error"),
                "rules": [
                    "Return strict JSON only.",
                    "Do not solve the user task.",
                    "Preserve the specialist role: choose only the next planner-turn route.",
                    "Use the same required_json_shape from the original request.",
                ],
            }
            repair_payload = {
                "model": self.model,
                "stream": False,
                "keep_alive": OLLAMA_KEEP_ALIVE,
                "think": False,
                "format": "json",
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You repair malformed JSON from a planner blocked job judge. "
                            "Return one valid JSON object matching the requested schema."
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps(repair_request_payload, ensure_ascii=False, default=str),
                    },
                ],
                "options": {
                    "temperature": 0,
                    "num_predict": 700,
                    "num_ctx": max(
                        4096,
                        min(
                            int(AGENTIC_PLANNER_NUM_CTX_CAP or AGENTIC_PLANNER_NUM_CTX or 8192),
                            int(AGENTIC_PLANNER_NUM_CTX or 8192),
                        ),
                    ),
                },
            }
            repair_response = self._post_json(self.planner_url, repair_payload, timeout)
            if repair_response.get("error"):
                decoded = {}
            else:
                message = _dict_or_empty(repair_response.get("message"))
                repair_raw_text = str(message.get("content") or repair_response.get("response") or "")
                repair_parse_diagnostics = parse_strict_json_object_diagnostics(repair_raw_text)
                if repair_parse_diagnostics.get("ok") is True:
                    decoded = repair_parse_diagnostics.get("decoded")
        return decoded

    def _sanitize_response(self, decoded: Any) -> dict[str, Any]:
        """Sanitizza la risposta del judge."""
        base = {
            "schema": "planner_blocked_job_judge_result.v1",
            "available": False,
            "ok": False,
            "decision": "invalid",
        }
        if not isinstance(decoded, dict):
            return {**base, "error": "invalid_json_object"}
        decision = str(decoded.get("decision") or "").strip().lower()
        if decision not in {"blocked", "unblocked", "retry_same_context"}:
            return {**base, "raw_decision": _prompt_clip_value(decoded, text_limit=500, list_limit=6)}
        required_next_progress = str(decoded.get("required_next_progress") or "").strip()
        if not required_next_progress:
            return {**base, "decision": decision, "error": "missing_required_next_progress"}
        required_next_tool_call = self._sanitize_tool_call(decoded.get("required_next_tool_call"))
        return {
            "schema": "planner_blocked_job_judge_result.v1",
            "available": True,
            "ok": True,
            "decision": decision,
            "required_next_progress": _prompt_clip_text(required_next_progress, 1000),
            "required_next_tool_call": required_next_tool_call,
            "rationale": _prompt_clip_text(decoded.get("rationale"), 600),
            "confidence": decoded.get("confidence"),
        }

    def _sanitize_tool_call(self, value: Any) -> dict[str, Any]:
        """Sanitizza una tool call."""
        if not isinstance(value, dict):
            return {}
        tool = str(value.get("tool") or "").strip()
        allowed_tools = set(self._BLOCKED_JOB_ROUTE_TOOLS)
        if tool not in allowed_tools:
            return {}
        args = {k: v for k, v in value.get("arguments", {}).items() if v not in (None, "", [], {})}
        reason = str(value.get("reason") or "").strip()
        return {
            "tool": tool,
            "arguments": args,
            "reason": _prompt_clip_text(reason, 500) if reason else "blocked_job_judge_required_next_tool_call",
            "source": "planner_blocked_job_judge",
        }

    _BLOCKED_JOB_ROUTE_TOOLS = frozenset([
        "repo_read",
        "repo_list_files",
        "repo_semantic_search",
        "repo_rg_search",
        "repo_search",
        "planner_scratchpad_read",
    ])