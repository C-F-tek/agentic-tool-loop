from __future__ import annotations

import json
import re
import logging
from typing import Any

from aicarmine_broker.error_handling import (
    BrokerError,
    ErrorCategory,
    ErrorSeverity,
    ErrorReport,
    ErrorSummary,
)

from aicarmine_broker.planner_core.json_io import (
    _parse_strict_json_object,
    parse_strict_json_object_diagnostics,
)

logger = logging.getLogger(__name__)


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
        tool_name = str(call.get("tool") or "").strip().lower()
        if tool_name in {"final_answer", "final", "answer", "block", "blocked", "tool_block"}:
            answer = _final_answer_from_content_field(call["arguments"])
            if answer:
                return {
                    "action": "block" if tool_name in {"block", "blocked", "tool_block"} else "final",
                    "final_answer": answer,
                    "reason": "native_terminal_alias_tool_call",
                    "terminal_alias_normalized": tool_name,
                    "native_tool_call": True,
                    "raw_native_tool_call": call["raw_tool_call"],
                    "raw_planner_text": raw_text[:4000],
                }
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
    normalized = _normalize_final_answer_from_content(_normalize_final_answer_lines(decision))
    action = str(normalized.get("action") or "").strip().lower()
    tool = str(
        normalized.get("tool")
        or normalized.get("name")
        or normalized.get("tool_name")
        or normalized.get("function")
        or ""
    ).strip().lower()
    if action == "tool" and tool in {"final_answer", "final", "answer"}:
        answer = str(
            normalized.get("final_answer")
            or normalized.get("answer")
            or normalized.get("summary")
            or _final_answer_from_content_field(normalized.get("content"))
            or ""
        ).strip()
        if answer:
            out = dict(normalized)
            out["action"] = "final"
            out.pop("tool", None)
            out["final_answer"] = answer
            out["terminal_alias_normalized"] = tool
            return out
    if action == "tool" and tool in {"block", "blocked", "tool_block", "need_user", "needs_user"}:
        answer = str(
            normalized.get("final_answer")
            or normalized.get("answer")
            or normalized.get("summary")
            or _final_answer_from_content_field(normalized.get("content"))
            or ""
        ).strip()
        if answer:
            out = dict(normalized)
            out["action"] = "block"
            out.pop("tool", None)
            out["final_answer"] = answer
            out["terminal_alias_normalized"] = tool
            return out
    return normalized


def parse_json_text_tool_call(content: str) -> dict[str, Any] | None:
    """
    Parse JSON-text tool call from planner response content.
    Expected format: {"action": "tool", "tool": "repo_read", "arguments": {...}}
    Alternative format: {"tool": "repo_read", "arguments": {...}}
    Returns decision dict or None if not parseable.
    """
    if not content or not content.strip():
        return None
    
    stripped = content.strip()
    
    # Try direct JSON parsing first
    try:
        data = json.loads(stripped)
        if not isinstance(data, dict):
            return None
        
        # Check for action-based format
        if data.get("action") == "tool":
            tool_name = str(data.get("tool") or "").strip()
            if tool_name:
                return {
                    "action": "tool",
                    "tool": tool_name,
                    "arguments": data.get("arguments", {}),
                    "source": "json_text_tool_call",
                    "raw_content": content[:2000],
                }
        
        # Check for direct tool format (no action field)
        elif data.get("tool"):
            tool_name = str(data.get("tool") or "").strip()
            if tool_name:
                return {
                    "action": "tool",
                    "tool": tool_name,
                    "arguments": data.get("arguments", {}),
                    "source": "json_text_tool_call_direct",
                    "raw_content": content[:2000],
                }
        
        # Check for function call format (OpenAI style)
        func_data = data.get("function_call") or data.get("function")
        if isinstance(func_data, dict):
            tool_name = str(func_data.get("name") or "").strip()
            if tool_name:
                args = func_data.get("arguments", {})
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                return {
                    "action": "tool",
                    "tool": tool_name,
                    "arguments": args,
                    "source": "json_text_function_call",
                    "raw_content": content[:2000],
                }
        
        return None
        
    except json.JSONDecodeError as e:
        logger.debug(f"JSON parse error in tool call fallback: {e}")
    
    # Try to find embedded JSON in prose text
    # Look for JSON-like structures
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", stripped):
        try:
            decoded, end = decoder.raw_decode(stripped[match.start():])
            if not isinstance(decoded, dict):
                continue
            
            action = str(decoded.get("action") or "").strip().lower()
            if action == "tool":
                tool_name = str(decoded.get("tool") or "").strip()
                if tool_name:
                    return {
                        "action": "tool",
                        "tool": tool_name,
                        "arguments": decoded.get("arguments", {}),
                        "source": "json_text_embedded",
                        "raw_content": content[:2000],
                    }
            
            # Check for direct tool format
            if decoded.get("tool"):
                tool_name = str(decoded.get("tool") or "").strip()
                if tool_name:
                    return {
                        "action": "tool",
                        "tool": tool_name,
                        "arguments": decoded.get("arguments", {}),
                        "source": "json_text_embedded_direct",
                        "raw_content": content[:2000],
                    }
        except json.JSONDecodeError:
            continue
    
    return None


def parse_json_text_terminal_decision(content: str) -> dict[str, Any] | None:
    """
    Parse JSON-text terminal decision (final/block) from planner response content.
    """
    if not content or not content.strip():
        return None
    
    stripped = content.strip()
    
    try:
        data = json.loads(stripped)
        if not isinstance(data, dict):
            return None
        
        action = str(data.get("action") or "").strip().lower()
        
        if action in ("final", "block"):
            final_answer = str(data.get("final_answer") or data.get("answer") or data.get("summary") or "").strip()
            if not final_answer:
                # Try content field
                content_field = data.get("content")
                if isinstance(content_field, str):
                    final_answer = content_field.strip()
                elif isinstance(content_field, dict):
                    for key in ("final_analysis", "final_answer", "answer", "summary", "message", "text"):
                        val = content_field.get(key)
                        if isinstance(val, str) and val.strip():
                            final_answer = val.strip()
                            break
            
            return {
                "action": action,
                "reason": str(data.get("reason") or ""),
                "final_answer": final_answer,
                "source": "json_text_terminal_decision",
                "raw_content": content[:2000],
            }
        
        # Check for legacy format (no action field but has final_answer)
        if data.get("final_answer") and not data.get("action"):
            return {
                "action": "final",
                "final_answer": str(data["final_answer"]).strip(),
                "reason": str(data.get("reason") or ""),
                "source": "json_text_terminal_legacy",
                "raw_content": content[:2000],
            }
        
        return None
        
    except json.JSONDecodeError as e:
        logger.debug(f"JSON parse error in terminal decision fallback: {e}")
    
    # Try embedded JSON in prose
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", stripped):
        try:
            decoded, end = decoder.raw_decode(stripped[match.start():])
            if not isinstance(decoded, dict):
                continue
            
            action = str(decoded.get("action") or "").strip().lower()
            if action in ("final", "block"):
                final_answer = str(decoded.get("final_answer") or decoded.get("answer") or "").strip()
                return {
                    "action": action,
                    "reason": str(decoded.get("reason") or ""),
                    "final_answer": final_answer,
                    "source": "json_text_embedded_terminal",
                    "raw_content": content[:2000],
                }
        except json.JSONDecodeError:
            continue
    
    return None


def normalize_planner_decision(
    raw_text: str, goal: str, step: int, state: dict[str, Any]
) -> dict[str, Any]:
    diagnostics = parse_strict_json_object_diagnostics(raw_text)
    decoded = diagnostics.get("decoded") if diagnostics.get("ok") is True else {}
    if decoded:
        normalized = _normalize_terminal_planner_decision(decoded)
        if str(normalized.get("action") or "tool").strip().lower() == "tool" and not normalized.get("tool"):
            for alias in ("name", "tool_name", "function"):
                if normalized.get(alias):
                    normalized["tool"] = normalized.get(alias)
                    break
        return normalized

    raw_response = str(raw_text or "")
    
    # Try JSON-text tool call parsing first (for models that return JSON text instead of native tool_calls)
    json_tool_result = parse_json_text_tool_call(raw_response)
    if json_tool_result:
        return json_tool_result
    
    # Try JSON-text terminal decision parsing
    json_terminal_result = parse_json_text_terminal_decision(raw_response)
    if json_terminal_result:
        return json_terminal_result

    invalid_decision = {
        "action": "block",
        "reason": "INVALID_PLANNER_OUTPUT_NON_JSON_PURE",
        "final_answer": (
            "Planner 30B emitted output that was not a single pure JSON object. "
            "No controller JSON extraction, plaintext intent recovery, or fallback "
            "normalization was executed. The raw model output is preserved in "
            "raw_planner_text. Plain text or mixed prose plus embedded JSON must "
            "be returned to the planner for a pure JSON decision; only malformed "
            "JSON or recognizable invalid tool calls remain eligible for Vulkan/GPU1 "
            "repair."
        ),
        "raw_planner_text": raw_response[:12000],
        "json_parse_error_type": diagnostics.get("error_type"),
        "raw_response_chars": diagnostics.get("raw_response_chars", len(raw_response)),
        "raw_response_preview": raw_response[:1000],
    }
    for key in ("error", "line", "column", "position", "trailing_preview", "start_preview", "decoded_type"):
        if diagnostics.get(key) not in (None, "", [], {}):
            invalid_decision[key if key.startswith("json_") else f"json_parse_{key}"] = diagnostics.get(key)
    return invalid_decision