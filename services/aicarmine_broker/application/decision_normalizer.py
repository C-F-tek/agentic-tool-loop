from __future__ import annotations

import json
import re
from typing import Any

from aicarmine_broker.planner_core.json_io import _parse_strict_json_object


def _single_embedded_json_decision(text: str) -> dict[str, Any]:
    """Return one embedded planner JSON object, only when unambiguous."""
    raw = str(text or "")
    if not raw.strip():
        return {}
    if _parse_strict_json_object(raw):
        return {}

    candidates: list[dict[str, Any]] = []
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", raw):
        try:
            decoded, end = decoder.raw_decode(raw[match.start() :])
        except json.JSONDecodeError:
            continue
        if not isinstance(decoded, dict):
            continue
        action = str(decoded.get("action") or "").strip().lower()
        if action in {
            "tool",
            "final",
            "done",
            "complete",
            "completed",
            "block",
            "blocked",
            "need_user",
            "needs_user",
        }:
            candidate = dict(decoded)
            candidate["_embedded_json_span"] = [match.start(), match.start() + end]
            candidates.append(candidate)
    if len(candidates) != 1:
        return {}

    decision = candidates[0]
    span = decision.pop("_embedded_json_span", None)
    if span:
        decision["raw_planner_text_before_deterministic_strip"] = raw[:4000]
        decision["deterministic_strip"] = {
            "kind": "single_embedded_json_decision",
            "span": span,
            "rule": "ignored prose around exactly one complete planner JSON object",
        }
    return decision


def _native_tool_calls_decision(tool_calls: list[dict[str, Any]], raw_text: str = "") -> dict[str, Any]:
    """Convert Ollama native tool_calls into the existing planner decision shape."""
    from aicarmine_broker.tool_contract import normalize_tool_name, parse_tool_call

    calls: list[dict[str, Any]] = []
    for index, call in enumerate(tool_calls if isinstance(tool_calls, list) else []):
        if not isinstance(call, dict):
            continue
        name, args = parse_tool_call(call)
        calls.append(
            {
                "index": index,
                "tool": normalize_tool_name(name),
                "arguments": args,
                "raw_tool_call": call,
            }
        )
    if not calls:
        return {}
    if len(calls) == 1:
        call = calls[0]
        return {
            "action": "tool",
            "tool": call["tool"],
            "arguments": call["arguments"],
            "reason": "native_tool_call",
            "native_tool_call": True,
            "raw_native_tool_call": call["raw_tool_call"],
            "raw_planner_text": raw_text[:4000],
        }
    return {
        "action": "tool_batch",
        "tool_calls": calls,
        "reason": "native_tool_call_batch",
        "native_tool_call": True,
        "raw_planner_text": raw_text[:4000],
    }


def _normalize_final_answer_lines(decision: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(decision, dict) or "final_answer_lines" not in decision:
        return decision
    lines = decision.get("final_answer_lines")
    if not isinstance(lines, list):
        return decision
    normalized = dict(decision)
    normalized["final_answer"] = "\n".join(str(line) for line in lines)
    return normalized


def _final_answer_from_content_field(content: Any) -> str:
    if content in (None, "", [], {}):
        return ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, dict):
        for key in (
            "final_analysis",
            "final_answer",
            "answer",
            "summary",
            "message",
            "response",
            "text",
        ):
            value = content.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return json.dumps(content, ensure_ascii=False, indent=2, default=str)
    if isinstance(content, list):
        if all(isinstance(item, str) for item in content):
            return "\n".join(str(item) for item in content if str(item).strip())
        return json.dumps(content, ensure_ascii=False, indent=2, default=str)
    return str(content).strip()


def _normalize_final_answer_from_content(decision: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(decision, dict):
        return decision
    action = str(decision.get("action") or "").strip().lower()
    if action not in {
        "final",
        "done",
        "complete",
        "completed",
        "block",
        "blocked",
        "need_user",
        "needs_user",
    }:
        return decision
    if str(decision.get("final_answer") or "").strip():
        return decision
    content_answer = _final_answer_from_content_field(decision.get("content"))
    if not content_answer.strip():
        return decision
    normalized = dict(decision)
    normalized["final_answer"] = content_answer
    normalized["final_answer_source"] = (
        "content.final_analysis"
        if isinstance(decision.get("content"), dict)
        and isinstance(decision["content"].get("final_analysis"), str)
        and decision["content"].get("final_analysis").strip()
        else "content"
    )
    return normalized


def _normalize_terminal_planner_decision(decision: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(decision, dict):
        return decision
    return _normalize_final_answer_from_content(_normalize_final_answer_lines(decision))


def normalize_planner_decision(
    raw_text: str, goal: str, step: int, state: dict[str, Any]
) -> dict[str, Any]:
    decoded = _parse_strict_json_object(raw_text)
    if decoded:
        normalized = _normalize_terminal_planner_decision(decoded)
        if str(normalized.get("action") or "tool").strip().lower() == "tool" and not normalized.get("tool"):
            for alias in ("name", "tool_name", "function"):
                if normalized.get(alias):
                    normalized["tool"] = normalized.get(alias)
                    break
        return normalized

    return {
        "action": "block",
        "reason": "INVALID_PLANNER_OUTPUT_NON_JSON_PURE",
        "final_answer": (
            "Planner 30B emitted output that was not a single pure JSON object. "
            "No controller JSON extraction, plaintext intent recovery, or fallback "
            "normalization was executed. The raw model output is preserved in "
            "raw_planner_text. Plain text or mixed prose plus embedded JSON must "
            "be returned to the planner for a pure JSON decision; only malformed "
            "JSON or recognizable invalid tool calls are eligible for Vulkan/GPU0 "
            "11435 repair."
        ),
        "raw_planner_text": str(raw_text or "")[:12000],
    }
