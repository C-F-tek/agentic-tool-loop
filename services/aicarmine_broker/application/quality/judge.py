"""Final quality judge for repo analysis."""

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


class FinalQualityJudge:
    """Judge final quality for repo analysis decisions."""

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
        """Judge final quality for repo analysis."""
        violations = _list_or_empty(validation.get("violations"))
        contract = _dict_or_empty(validation.get("evidence_contract"))
        code_contract = _dict_or_empty(contract.get("code_product_contract"))

        if not code_contract.get("required"):
            return {}

        request_payload = {
            "schema": "planner_final_quality_request.v1",
            "task": "judge_final_quality_for_repo_analysis",
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
                "For repo-analysis replan, never convert duplicate-read/final-quality failures into repo_propose_code_edit or code_product_build_state.",
                "If the rejected required_next_tool_call is already satisfied, set required_next_progress toward final rewrite or one different concrete evidence gap.",
                "If prevalidation_feedback is present, do not repeat the rejected route. Choose one different valid route or omit required_next_tool_call.",
                "Use required_next_tool_call only for a concrete read/search/window route, never for invented code edits.",
                "repo_read_allowlist contains only unread validator-admissible paths; if it is empty, do not choose repo_read.",
                "For repo_read, choose only paths listed in repo_read_allowlist; prose, metrics, headings, concepts, and already-read files must become required_next_progress or a search query.",
            ],
            "allowed_required_next_tools": sorted(self._FINAL_QUALITY_ROUTE_TOOLS),
            "required_json_shape": {
                "decision": "continue_required | block_recommended | retry_same_context",
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
                        "You are a specialized planner final quality judge. You do not solve the task. "
                        "You convert validator rejection evidence into the next instruction for the "
                        "main planner. Return strict JSON only."
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
                "schema": "planner_final_quality_result.v1",
                "available": False,
                "ok": False,
                "decision": "unavailable",
                "error": response.get("error") or response.get("error_type") or "planner_final_quality_backend_error",
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
                "schema": "planner_final_quality_json_repair_request.v1",
                "task": "repair_planner_final_quality_json",
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
                            "You repair malformed JSON from a planner final quality judge. "
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
            "schema": "planner_final_quality_result.v1",
            "available": False,
            "ok": False,
            "decision": "invalid",
        }
        if not isinstance(decoded, dict):
            return {**base, "error": "invalid_json_object"}
        decision = str(decoded.get("decision") or "").strip().lower()
        if decision not in {"continue_required", "block_recommended", "retry_same_context"}:
            return {**base, "raw_decision": _prompt_clip_value(decoded, text_limit=500, list_limit=6)}
        required_next_progress = str(decoded.get("required_next_progress") or "").strip()
        if not required_next_progress:
            return {**base, "decision": decision, "error": "missing_required_next_progress"}
        required_next_tool_call = self._sanitize_tool_call(decoded.get("required_next_tool_call"))
        return {
            "schema": "planner_final_quality_result.v1",
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
        allowed_tools = set(self._FINAL_QUALITY_ROUTE_TOOLS)
        if tool not in allowed_tools:
            return {}
        args = {k: v for k, v in value.get("arguments", {}).items() if v not in (None, "", [], {})}
        reason = str(value.get("reason") or "").strip()
        return {
            "tool": tool,
            "arguments": args,
            "reason": _prompt_clip_text(reason, 500) if reason else "final_quality_judge_required_next_tool_call",
            "source": "planner_final_quality_judge",
        }

    _FINAL_QUALITY_ROUTE_TOOLS = frozenset([
        "repo_read",
        "repo_list_files",
        "repo_semantic_search",
        "repo_rg_search",
        "repo_search",
        "planner_scratchpad_read",
    ])

    def final_answer_model_quality(
        self,
        final_answer: str,
        contract: dict[str, Any],
        *,
        goal: str,
        history: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Wrap _repo_analysis_final_answer_model_quality logic for final answer quality."""
        from ...planner import (
            _repo_analysis_final_answer_model_quality_request,
            _sanitize_repo_analysis_final_model_quality,
            _specialist_route_audit,
            parse_strict_json_object_diagnostics,
            post_json,
            AGENTIC_PLANNER_NUM_CTX_CAP,
            AGENTIC_PLANNER_STEP_TIMEOUT,
            OLLAMA_KEEP_ALIVE,
            PLANNER_MODEL,
            PLANNER_URL,
            _FINAL_QUALITY_ROUTE_TOOLS as FINAL_QUALITY_ROUTE_TOOLS,
        )
        
        request = _repo_analysis_final_answer_model_quality_request(
            final_answer,
            contract,
            goal=goal,
        )
        user_payload = _dict_or_empty(request.get("user_payload"))
        options = {
            "temperature": 0,
            "num_predict": 1000,
            "num_ctx": max(
                4096,
                min(int(AGENTIC_PLANNER_NUM_CTX_CAP or AGENTIC_PLANNER_NUM_CTX or 8192), int(AGENTIC_PLANNER_NUM_CTX or 8192)),
            ),
        }
        payload = {
            "model": PLANNER_MODEL,
            "stream": False,
            "keep_alive": OLLAMA_KEEP_ALIVE,
            "think": False,
            "format": "json",
            "messages": [
                {"role": "system", "content": str(request.get("system") or "")},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False, default=str)},
            ],
            "options": options,
        }
        timeout_seconds = min(90, max(20, int(AGENTIC_PLANNER_STEP_TIMEOUT or 30)))
        response = post_json(PLANNER_URL, payload, timeout_seconds)
        if response.get("backend_unreachable") or response.get("backend_timeout") or response.get("error"):
            quality = _sanitize_repo_analysis_final_model_quality(None, contract)
            quality.update({
                "violations": ["repo_analysis_final_model_quality_unavailable"],
                "required_next_progress": (
                    "Final answer rejected because the model final-quality judge was unavailable. "
                    "Retry final-quality evaluation; do not accept the final through deterministic heuristics."
                ),
                "planner_model": PLANNER_MODEL,
                "planner_url": PLANNER_URL,
                "timeout_seconds": timeout_seconds,
                "backend_error": response.get("error") or response.get("error_type") or "planner_backend_error",
            })
            return quality

        message = _dict_or_empty(response.get("message"))
        raw_text = str(message.get("content") or response.get("response") or response.get("partial_content") or "")
        parse_diagnostics = parse_strict_json_object_diagnostics(raw_text)
        repaired_raw_text = ""
        repair_diagnostics: dict[str, Any] = {}
        decoded = parse_diagnostics.get("decoded") if parse_diagnostics.get("ok") is True else {}
        if (
            not decoded
            or str(decoded.get("decision") or "").strip().lower()
            not in {"accept", "reject", "continue_required"}
        ):
            repair_payload = {
                "model": PLANNER_MODEL,
                "stream": False,
                "keep_alive": OLLAMA_KEEP_ALIVE,
                "think": False,
                "format": "json",
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            str(request.get("system") or "")
                            + "\n\nThe previous final-quality judge response was invalid JSON. "
                            "Re-evaluate the same request now and return exactly one strict JSON object."
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "schema": "repo_analysis_final_model_quality_repair_request.v1",
                                "original_request": user_payload,
                                "invalid_response_preview": raw_text[:2000],
                                "invalid_response_chars": len(raw_text),
                                "json_parse_error_type": parse_diagnostics.get("error_type"),
                                "json_parse_error": parse_diagnostics.get("error"),
                            },
                            ensure_ascii=False,
                            default=str,
                        ),
                    },
                ],
                "options": options,
            }
            repair_response = post_json(PLANNER_URL, repair_payload, timeout_seconds)
            repair_diagnostics = {
                "attempted": True,
                "planner_model": PLANNER_MODEL,
                "planner_url": PLANNER_URL,
                "timeout_seconds": timeout_seconds,
            }
            if (
                repair_response.get("backend_unreachable")
                or repair_response.get("backend_timeout")
                or repair_response.get("error")
            ):
                repair_diagnostics.update({
                    "ok": False,
                    "error": repair_response.get("error") or repair_response.get("error_type") or "planner_backend_error",
                    "error_type": repair_response.get("error_type"),
                })
            else:
                repair_message = _dict_or_empty(repair_response.get("message"))
                repaired_raw_text = str(
                    repair_message.get("content")
                    or repair_response.get("response")
                    or repair_response.get("partial_content")
                    or ""
                )
                repair_parse = parse_strict_json_object_diagnostics(repaired_raw_text)
                repair_diagnostics.update({
                    "ok": repair_parse.get("ok") is True,
                    "raw_response_chars": len(repaired_raw_text),
                })
                if repair_parse.get("ok") is True:
                    decoded = repair_parse.get("decoded") if isinstance(repair_parse.get("decoded"), dict) else {}
                else:
                    repair_diagnostics.update({
                        "json_parse_error_type": repair_parse.get("error_type"),
                        "json_parse_error": repair_parse.get("error"),
                        "raw_response_preview": repaired_raw_text[:2000],
                    })
        quality = _sanitize_repo_analysis_final_model_quality(decoded, contract)
        quality.update({
            "planner_model": PLANNER_MODEL,
            "planner_url": PLANNER_URL,
            "timeout_seconds": timeout_seconds,
        })
        if repair_diagnostics:
            quality["json_repair_attempt"] = repair_diagnostics
            if quality.get("model_decision_available"):
                quality["json_repaired_by_final_quality_model"] = True
        if not quality.get("model_decision_available"):
            quality["raw_response_preview"] = raw_text[:2000]
            quality["raw_response_chars"] = len(raw_text)
            if parse_diagnostics.get("ok") is not True:
                quality["json_parse_error_type"] = parse_diagnostics.get("error_type")
                if parse_diagnostics.get("error") not in (None, "", [], {}):
                    quality["json_parse_error"] = parse_diagnostics.get("error")
            quality["violations"] = ["repo_analysis_final_model_quality_invalid"]
            quality["required_next_progress"] = (
                "Final answer rejected because the model final-quality judge did not return valid JSON. "
                "Retry final-quality evaluation; do not accept the final through deterministic heuristics."
            )
        history_for_audit = history if isinstance(history, list) else []
        required_route = (
            quality.get("required_next_tool_call")
            if isinstance(quality.get("required_next_tool_call"), dict)
            else {}
        )
        if required_route:
            route_audit = _specialist_route_audit(
                required_route,
                history_for_audit,
                source="repo_analysis_final_quality",
                allowed_tools=FINAL_QUALITY_ROUTE_TOOLS,
            )
            if route_audit.get("accepted") is not True:
                retry_user_payload = dict(user_payload)
                retry_rules = retry_user_payload.get("decision_rules")
                retry_rules = list(retry_rules) if isinstance(retry_rules, list) else []
                retry_rules.append(
                    "A previous required_next_tool_call failed prevalidation. Do not repeat it. "
                    "Choose one different valid route, or omit required_next_tool_call and require "
                    "a corrected final answer from existing evidence."
                )
                retry_user_payload["decision_rules"] = retry_rules
                retry_user_payload["prevalidation_feedback"] = _prompt_clip_value(
                    route_audit,
                    text_limit=900,
                    list_limit=8,
                )
                retry_payload = {
                    "model": PLANNER_MODEL,
                    "stream": False,
                    "keep_alive": OLLAMA_KEEP_ALIVE,
                    "think": False,
                    "format": "json",
                    "messages": [
                        {"role": "system", "content": str(request.get("system") or "")},
                        {"role": "user", "content": json.dumps(retry_user_payload, ensure_ascii=False, default=str)},
                    ],
                    "options": options,
                }
                retry_response = post_json(PLANNER_URL, retry_payload, timeout_seconds)
                retry_quality: dict[str, Any]
                retry_audit: dict[str, Any] = {}
                if (
                    retry_response.get("backend_unreachable")
                    or retry_response.get("backend_timeout")
                    or retry_response.get("error")
                ):
                    retry_quality = _sanitize_repo_analysis_final_model_quality(None, contract)
                    retry_quality["backend_error"] = (
                        retry_response.get("error")
                        or retry_response.get("error_type")
                        or "planner_backend_error"
                    )
                else:
                    retry_message = _dict_or_empty(retry_response.get("message"))
                    retry_raw_text = str(
                        retry_message.get("content")
                        or retry_response.get("response")
                        or retry_response.get("partial_content")
                        or ""
                    )
                    retry_parse = parse_strict_json_object_diagnostics(retry_raw_text)
                    retry_decoded = retry_parse.get("decoded") if retry_parse.get("ok") is True else {}
                    retry_quality = _sanitize_repo_analysis_final_model_quality(retry_decoded, contract)
                    retry_quality["raw_response_preview"] = retry_raw_text[:1200]
                    retry_quality["raw_response_chars"] = len(retry_raw_text)
                    if retry_parse.get("ok") is not True:
                        retry_quality["json_parse_error_type"] = retry_parse.get("error_type")
                retry_route = (
                    retry_quality.get("required_next_tool_call")
                    if isinstance(retry_quality.get("required_next_tool_call"), dict)
                    else {}
                )
                if retry_route:
                    retry_audit = _specialist_route_audit(
                        retry_route,
                        history_for_audit,
                        source="repo_analysis_final_quality_retry",
                        allowed_tools=FINAL_QUALITY_ROUTE_TOOLS,
                    )
                if retry_route and retry_audit.get("accepted") is True:
                    quality = retry_quality
                    quality["judge_route_prevalidation_retry"] = {
                        "attempted": True,
                        "first_audit": route_audit,
                        "retry_audit": retry_audit,
                        "accepted": True,
                    }
                else:
                    quality["stale_or_invalid_judge_route"] = {
                        "attempted_retry": True,
                        "first_audit": route_audit,
                        "retry_audit": retry_audit,
                        "retry_quality": _prompt_clip_value(retry_quality, text_limit=700, list_limit=8),
                    }
                    quality.pop("required_next_tool_call", None)
                    quality["required_next_progress"] = (
                        "Final-quality judge route was stale or invalid after one retry. "
                        "Rewrite action=final from existing verified evidence if sufficient, "
                        "choose a different concrete evidence gap, or return a typed action=block."
                    )
        return quality
