#!/usr/bin/env python3
"""Validate GPU planner JSON output contracts.

The helpers in this module are intentionally report-only. They classify model
responses and parsed recommendation objects without running providers, applying
patches, writing source files, executing Blender, writing SQLite databases or
changing Git state.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

try:
    from Tools.ai.model_json import ModelJsonParseError, parse_model_json_object, strip_markdown_json_fence
    from Tools.ai.runtime_tool_guidance import ALLOWED_RUNTIME_TOOLS
except ImportError:  # Script-style execution from Tools/ai.
    from model_json import ModelJsonParseError, parse_model_json_object, strip_markdown_json_fence  # type: ignore
    from runtime_tool_guidance import ALLOWED_RUNTIME_TOOLS  # type: ignore


ALLOWED_STATUSES = {"ready_for_patch_plan", "needs_more_context", "advisory_only"}
ALLOWED_RISKS = {"low", "medium", "high"}
REQUIRED_RECOMMENDATION_KEYS = {
    "id",
    "area",
    "status",
    "target_files",
    "rationale",
    "proposed_strategy",
    "risk",
    "validation_commands",
    "stop_conditions",
}
# ALLOWED_RUNTIME_TOOLS is imported from Tools.ai.runtime_tool_guidance so GPU,
# NPU and live provider loops share the same broker allowlist.
REQUIRED_TOOL_REQUEST_KEYS = {"id", "tool", "reason", "args"}
CONTEXT_ECHO_TOP_LEVEL_KEYS = {"files", "context_files", "repository_files", "file_previews"}
CONTEXT_ECHO_NESTED_KEYS = {"content_preview", "preview", "raw_response_preview"}
EXPECTED_TOP_LEVEL_KEYS = {"summary", "confidence", "recommendations", "tool_requests", "missing_evidence", "next_best_action"}
OPEN_TO_CLOSE = {"{": "}", "[": "]"}


@dataclass(frozen=True)
class ModelJsonContractResult:
    """Result of parsing and validating one model response."""

    json_ok: bool
    schema_ok: bool
    context_echo_detected: bool
    parse_error: str
    schema_errors: tuple[str, ...]
    raw_response_sha256: str
    raw_response_chars: int
    top_level_keys: tuple[str, ...]
    recommendation_count: int
    valid_recommendation_count: int
    invalid_recommendation_count: int
    tool_request_count: int
    valid_tool_request_count: int
    invalid_tool_request_count: int
    empty_recommendations_reason: str
    parsed: dict[str, Any]


def response_hash(text: str) -> str:
    """Return a stable hash for a raw model response."""

    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def _balanced_outer_json(text: str) -> bool:
    """Return true when the apparent outer JSON document is balanced.

    This is deliberately stricter than ``model_json.extract_json_candidate``.
    Contract validation should not recover a nested object from a visibly
    truncated outer model response and classify that nested object as the
    complete planner answer.
    """

    stripped = strip_markdown_json_fence(text).strip()
    if not stripped or stripped[0] not in OPEN_TO_CLOSE:
        return True

    expected_outer_close = OPEN_TO_CLOSE[stripped[0]]
    if not stripped.endswith(expected_outer_close):
        return False

    stack = [expected_outer_close]
    in_string = False
    escaped = False
    for char in stripped[1:]:
        if escaped:
            escaped = False
            continue
        if char == "\\" and in_string:
            escaped = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char in OPEN_TO_CLOSE:
            stack.append(OPEN_TO_CLOSE[char])
            continue
        if char in "}]":
            if not stack or stack[-1] != char:
                return False
            stack.pop()
    return not stack and not in_string


def _contains_nested_context_echo(value: Any, *, depth: int = 0) -> bool:
    if depth > 8:
        return False
    if isinstance(value, dict):
        if any(key in value for key in CONTEXT_ECHO_NESTED_KEYS):
            return True
        return any(_contains_nested_context_echo(child, depth=depth + 1) for child in value.values())
    if isinstance(value, list):
        return any(_contains_nested_context_echo(child, depth=depth + 1) for child in value[:20])
    return False


def detect_context_echo(parsed: dict[str, Any]) -> bool:
    """Detect outputs that echo input context instead of returning recommendations."""

    keys = set(parsed)
    if keys & CONTEXT_ECHO_TOP_LEVEL_KEYS:
        return True
    if "recommendations" not in parsed and _contains_nested_context_echo(parsed):
        return True
    return False


def validate_recommendation_object(value: Any, index: int) -> list[str]:
    """Return schema errors for a single recommendation object."""

    errors: list[str] = []
    if not isinstance(value, dict):
        return [f"recommendations[{index}] must be an object"]

    missing = sorted(REQUIRED_RECOMMENDATION_KEYS - set(value))
    if missing:
        errors.append(f"recommendations[{index}] missing keys: {', '.join(missing)}")

    status = value.get("status")
    if status not in ALLOWED_STATUSES:
        errors.append(f"recommendations[{index}].status invalid: {status!r}")

    risk = value.get("risk")
    if risk not in ALLOWED_RISKS:
        errors.append(f"recommendations[{index}].risk invalid: {risk!r}")

    target_files = value.get("target_files")
    if not isinstance(target_files, list) or not all(isinstance(item, str) and item for item in target_files):
        errors.append(f"recommendations[{index}].target_files must be a non-empty string list")

    validation_commands = value.get("validation_commands")
    if not isinstance(validation_commands, list) or not all(isinstance(item, str) for item in validation_commands):
        errors.append(f"recommendations[{index}].validation_commands must be a string list")

    stop_conditions = value.get("stop_conditions")
    if not isinstance(stop_conditions, list) or not all(isinstance(item, str) for item in stop_conditions):
        errors.append(f"recommendations[{index}].stop_conditions must be a string list")

    if _contains_nested_context_echo(value):
        errors.append(f"recommendations[{index}] embeds raw context preview data")

    return errors


def validate_recommendations(parsed: dict[str, Any]) -> tuple[int, int, list[str]]:
    """Validate the recommendations array and return counts plus errors."""

    recommendations = parsed.get("recommendations")
    if not isinstance(recommendations, list):
        return 0, 0, ["top-level recommendations must be a list"]

    valid_count = 0
    errors: list[str] = []
    for index, item in enumerate(recommendations):
        item_errors = validate_recommendation_object(item, index)
        if item_errors:
            errors.extend(item_errors)
        else:
            valid_count += 1
    return valid_count, len(recommendations) - valid_count, errors


def validate_tool_request_object(value: Any, index: int) -> list[str]:
    """Return schema errors for one broker-compatible runtime tool request."""

    errors: list[str] = []
    if not isinstance(value, dict):
        return [f"tool_requests[{index}] must be an object"]

    missing = sorted(REQUIRED_TOOL_REQUEST_KEYS - set(value))
    if missing:
        errors.append(f"tool_requests[{index}] missing keys: {', '.join(missing)}")

    request_id = value.get("id")
    if not isinstance(request_id, str) or not request_id.strip():
        errors.append(f"tool_requests[{index}].id must be a non-empty string")

    tool_name = value.get("tool")
    if not isinstance(tool_name, str) or not tool_name.strip():
        errors.append(f"tool_requests[{index}].tool must be a non-empty string")
    elif tool_name not in ALLOWED_RUNTIME_TOOLS:
        errors.append(f"tool_requests[{index}].tool not allowlisted: {tool_name!r}")

    reason = value.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        errors.append(f"tool_requests[{index}].reason must be a non-empty string")

    request_args = value.get("args")
    if not isinstance(request_args, dict):
        errors.append(f"tool_requests[{index}].args must be an object")

    if _contains_nested_context_echo(value):
        errors.append(f"tool_requests[{index}] embeds raw context preview data")

    return errors


def validate_tool_requests(parsed: dict[str, Any]) -> tuple[int, int, list[str]]:
    """Validate optional runtime tool requests for the broker layer."""

    if "tool_requests" not in parsed:
        return 0, 0, []

    tool_requests = parsed.get("tool_requests")
    if not isinstance(tool_requests, list):
        return 0, 0, ["top-level tool_requests must be a list"]

    valid_count = 0
    errors: list[str] = []
    for index, item in enumerate(tool_requests):
        item_errors = validate_tool_request_object(item, index)
        if item_errors:
            errors.extend(item_errors)
        else:
            valid_count += 1
    return valid_count, len(tool_requests) - valid_count, errors


def classify_empty_reason(
    *,
    json_ok: bool,
    schema_ok: bool,
    context_echo_detected: bool,
    valid_recommendation_count: int,
    valid_tool_request_count: int = 0,
    evidence_ready_for_manual_patch_count: int = 0,
) -> str:
    """Classify an empty or unusable recommendation result."""

    if valid_recommendation_count > 0:
        return ""
    if valid_tool_request_count > 0:
        return "tool_requests_pending"
    if context_echo_detected:
        return "context_echo_detected"
    if not json_ok:
        return "json_parse_failure"
    if not schema_ok:
        return "model_output_schema_mismatch"
    if evidence_ready_for_manual_patch_count > 0:
        return "evidence_ready_but_no_tool_requests"
    return "valid_json_empty_recommendations"


def validate_model_response_contract(
    text: str,
    *,
    evidence_ready_for_manual_patch_count: int = 0,
) -> ModelJsonContractResult:
    """Parse and validate one model response against the GPU planner contract."""

    raw_sha = response_hash(text)
    raw_chars = len(text)
    parse_error = ""
    parsed: dict[str, Any] = {}

    if not _balanced_outer_json(text):
        json_ok = False
        parse_error = "outer JSON document appears truncated or unbalanced"
    else:
        try:
            parsed = parse_model_json_object(text)
            json_ok = True
        except ModelJsonParseError as exc:
            parsed = {}
            json_ok = False
            parse_error = f"{type(exc).__name__}: {exc}"

    top_level_keys = tuple(sorted(parsed)) if isinstance(parsed, dict) else ()
    schema_errors: list[str] = []
    context_echo = False
    valid_count = 0
    invalid_count = 0
    valid_tool_count = 0
    invalid_tool_count = 0

    if json_ok:
        context_echo = detect_context_echo(parsed)
        missing_top_level = sorted({"recommendations"} - set(parsed))
        if missing_top_level:
            schema_errors.append(f"missing top-level keys: {', '.join(missing_top_level)}")
        unexpected_context_keys = sorted(set(parsed) & CONTEXT_ECHO_TOP_LEVEL_KEYS)
        if unexpected_context_keys:
            schema_errors.append(f"context echo top-level keys: {', '.join(unexpected_context_keys)}")
        if "recommendations" in parsed:
            valid_count, invalid_count, recommendation_errors = validate_recommendations(parsed)
            schema_errors.extend(recommendation_errors)
        valid_tool_count, invalid_tool_count, tool_errors = validate_tool_requests(parsed)
        schema_errors.extend(tool_errors)

    schema_ok = json_ok and not schema_errors and not context_echo
    recommendation_count = valid_count
    reason = classify_empty_reason(
        json_ok=json_ok,
        schema_ok=schema_ok,
        context_echo_detected=context_echo,
        valid_recommendation_count=valid_count,
        valid_tool_request_count=valid_tool_count,
        evidence_ready_for_manual_patch_count=evidence_ready_for_manual_patch_count,
    )
    return ModelJsonContractResult(
        json_ok=json_ok,
        schema_ok=schema_ok,
        context_echo_detected=context_echo,
        parse_error=parse_error,
        schema_errors=tuple(schema_errors),
        raw_response_sha256=raw_sha,
        raw_response_chars=raw_chars,
        top_level_keys=top_level_keys,
        recommendation_count=recommendation_count,
        valid_recommendation_count=valid_count,
        invalid_recommendation_count=invalid_count,
        tool_request_count=valid_tool_count + invalid_tool_count,
        valid_tool_request_count=valid_tool_count,
        invalid_tool_request_count=invalid_tool_count,
        empty_recommendations_reason=reason,
        parsed=parsed,
    )


def result_to_dict(result: ModelJsonContractResult, *, include_parsed: bool = False) -> dict[str, Any]:
    """Serialize a contract result for reports."""

    data: dict[str, Any] = {
        "json_ok": result.json_ok,
        "schema_ok": result.schema_ok,
        "context_echo_detected": result.context_echo_detected,
        "parse_error": result.parse_error,
        "schema_errors": list(result.schema_errors),
        "raw_response_sha256": result.raw_response_sha256,
        "raw_response_chars": result.raw_response_chars,
        "top_level_keys": list(result.top_level_keys),
        "recommendation_count": result.recommendation_count,
        "valid_recommendation_count": result.valid_recommendation_count,
        "invalid_recommendation_count": result.invalid_recommendation_count,
        "tool_request_count": result.tool_request_count,
        "valid_tool_request_count": result.valid_tool_request_count,
        "invalid_tool_request_count": result.invalid_tool_request_count,
        "empty_recommendations_reason": result.empty_recommendations_reason,
    }
    if include_parsed:
        data["parsed"] = result.parsed
    return data


def json_dumps_report(data: dict[str, Any]) -> str:
    """Dump report JSON with repository-standard formatting."""

    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"
