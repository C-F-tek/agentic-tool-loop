from __future__ import annotations

import json
import re
from typing import Any

from ...planner_core.json_io import (
    _parse_strict_json_object,
    parse_strict_json_object_diagnostics,
)


def _single_embedded_json_decision(text: str) -> dict[str, Any]:
    """Return one embedded planner JSON object, only when unambiguous.
    
    Improved logic for handling multiple curly braces:
    - When multiple valid candidates exist, prefer the one with action field closest to start
    - When no valid candidate exists but multiple dicts found, return empty (let strict parser handle it)
    - Properly handles nested JSON objects in arguments/content fields
    """
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
            candidate["_span_start"] = match.start()  # Track position for disambiguation
            candidates.append(candidate)
    
    # Handle multiple candidates: prefer the one starting earliest (closest to start of text)
    # This reduces false positives when the model emits multiple JSON-like structures
    if len(candidates) >= 1:
        if len(candidates) > 1:
            # Sort by span start position and take the first valid one
            candidates.sort(key=lambda c: c.get("_span_start", 0))
        
        decision = candidates[0]
        span = decision.pop("_embedded_json_span", None)
        span_start = decision.pop("_span_start", None)
        if span:
            decision["raw_planner_text_before_deterministic_strip"] = raw[:4000]
            decision["deterministic_strip"] = {
                "kind": "single_embedded_json_decision" if len(candidates) == 1 else "multi_embedded_json_decision",
                "span": span,
                "rule": f"ignored prose around {'exactly one' if len(candidates) == 1 else 'multiple'} complete planner JSON object(s)",
                "candidates_found": len(candidates),
                "selected_span_start": span_start,
            }
        return decision
    
    return {}


def _native_tool_calls_decision(tool_calls: list[dict[str, Any]], raw_text: str = "") -> dict[str, Any]:
    """Convert Ollama native tool_calls into the existing planner decision shape."""
    from ...tool_contract import normalize_tool_name, parse_tool_call

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


def normalize_planner_decision(
    raw_text: str, goal: str, step: int, state: dict[str, Any]
) -> dict[str, Any]:
    diagnostics = parse_strict_json_object_diagnostics(raw_text)
    decoded = diagnostics.get("decoded") if diagnostics.get("ok") is True else {}
    if decoded:
        # If strict JSON succeeded but contains tool_calls, convert via native tool call path.
        # This handles the case where the model emits valid JSON with {"tool_calls": [...]} format
        # (e.g., Ollama/Qwen native tool calls), which _normalize_terminal_planner_decision cannot handle
        # because it expects action/tool fields, not OpenAI-style tool_calls.
        if isinstance(decoded, dict) and "tool_calls" in decoded:
            tool_calls = decoded["tool_calls"]
            if isinstance(tool_calls, list) and tool_calls:
                native_decision = _native_tool_calls_decision(tool_calls, raw_text)
                if native_decision:
                    normalized = _normalize_terminal_planner_decision(native_decision)
                    normalized["json_extraction_fallback"] = True
                    normalized["json_extraction_source"] = "strict_json_native_conversion"
                    return normalized
        
        normalized = _normalize_terminal_planner_decision(decoded)
        if str(normalized.get("action") or "tool").strip().lower() == "tool" and not normalized.get("tool"):
            for alias in ("name", "tool_name", "function"):
                if normalized.get(alias):
                    normalized["tool"] = normalized.get(alias)
                    break
        return normalized

    raw_response = str(raw_text or "")
    
    # Medium-term fix: Try embedded JSON extraction as fallback when strict JSON parsing fails.
    # This handles cases where the model emits prose around a valid JSON object,
    # or where native tool calls aren't available but embedded JSON decision exists.
    embedded_decision = _single_embedded_json_decision(raw_response)
    if embedded_decision:
        normalized = _normalize_terminal_planner_decision(embedded_decision)
        if str(normalized.get("action") or "tool").strip().lower() == "tool" and not normalized.get("tool"):
            for alias in ("name", "tool_name", "function"):
                if normalized.get(alias):
                    normalized["tool"] = normalized.get(alias)
                    break
        normalized["json_extraction_fallback"] = True
        normalized["json_extraction_source"] = "single_embedded_json_decision"
        return normalized
    
    # Also try native tool calls conversion as fallback.
    # This handles cases where the model emits Ollama native tool_calls format.
    native_decision = _try_native_tool_calls_fallback(raw_response)
    if native_decision:
        normalized = _normalize_terminal_planner_decision(native_decision)
        normalized["json_extraction_fallback"] = True
        normalized["json_extraction_source"] = "native_tool_calls_conversion"
        return normalized

    invalid_decision = {
        "action": "block",
        "reason": "INVALID_PLANNER_OUTPUT_NON_JSON_PURE",
        "final_answer": (
            "Planner 30B emitted output that was not a single pure JSON object. "
            "Controller attempted JSON extraction and native tool calls conversion, "
            "but neither produced a valid decision. The raw model output is preserved in "
            "raw_planner_text. Plain text or mixed prose plus embedded JSON must "
            "be returned to the planner for a pure JSON decision; only malformed "
            "JSON or recognizable invalid tool calls are eligible for Vulkan/GPU0 "
            "11435 repair."
        ),
        "raw_planner_text": raw_response[:12000],
        "json_parse_error_type": diagnostics.get("error_type"),
        "raw_response_chars": diagnostics.get("raw_response_chars", len(raw_response)),
        "raw_response_preview": raw_response[:1000],
        "json_extraction_fallback_attempted": True,
        "json_extraction_fallback_failed": True,
    }
    for key in ("error", "line", "column", "position", "trailing_preview", "start_preview", "decoded_type"):
        if diagnostics.get(key) not in (None, "", [], {}):
            invalid_decision[key if key.startswith("json_") else f"json_parse_{key}"] = diagnostics.get(key)
    return invalid_decision


def _try_native_tool_calls_fallback(raw_text: str) -> dict[str, Any]:
    """Try to extract a native tool call decision from raw text.
    
    This handles cases where the model emits Ollama native tool_calls format
    instead of pure JSON, which is the common failure mode when
    native tool calls aren't available.
    
    Robust parsing strategy:
    1. Try strict JSON parse on full text first (handles valid {"tool_calls": [...]})
    2. Fall back to regex + raw_decode with context window
    3. Extract JSON boundaries explicitly if needed ({...} nesting)
    """
    # Strategy 1: Strict JSON parse on full text (most reliable for valid JSON output)
    try:
        decoded = json.loads(str(raw_text or "").strip())
        if isinstance(decoded, dict) and "tool_calls" in decoded:
            tool_calls = decoded["tool_calls"]
            if isinstance(tool_calls, list) and tool_calls:
                return _native_tool_calls_decision(tool_calls, raw_text)
    except (json.JSONDecodeError, ValueError):
        pass
    
    # Strategy 2: Regex + raw_decode with context window
    tool_calls_match = re.search(r'"tool_calls"\s*:\s*\[', raw_text)
    if tool_calls_match:
        try:
            decoder = json.JSONDecoder()
            start = max(0, tool_calls_match.start() - 100)
            decoded, end = decoder.raw_decode(raw_text[start:])
            if isinstance(decoded, dict) and "tool_calls" in decoded:
                tool_calls = decoded["tool_calls"]
                if isinstance(tool_calls, list) and tool_calls:
                    return _native_tool_calls_decision(tool_calls, raw_text)
        except Exception:
            pass
    
    # Strategy 3: Extract JSON boundaries explicitly (handles prose-wrapped JSON)
    # Find first { and matching closing }
    first_brace = raw_text.find('{')
    if first_brace >= 0:
        try:
            decoder = json.JSONDecoder()
            decoded, end = decoder.raw_decode(raw_text[first_brace:])
            if isinstance(decoded, dict) and "tool_calls" in decoded:
                tool_calls = decoded["tool_calls"]
                if isinstance(tool_calls, list) and tool_calls:
                    return _native_tool_calls_decision(tool_calls, raw_text)
        except Exception:
            pass
    
    return {}
