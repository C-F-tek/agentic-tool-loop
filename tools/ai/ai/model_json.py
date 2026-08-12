"""Helpers for parsing JSON-like model responses.

This module is intentionally scoped to AI/model output. It is not a replacement
for strict project-file JSON helpers such as ``Scripting/shared/json_io.py``.
"""
from __future__ import annotations

import json
import re
from typing import Any


class ModelJsonParseError(ValueError):
    """Raised when a model response cannot be parsed as JSON."""


def strip_markdown_json_fence(text: str) -> str:
    """Strip a surrounding Markdown code fence from a model response."""
    stripped = text.strip().replace("\ufeff", "")
    if not stripped.startswith("```"):
        return stripped

    lines = stripped.splitlines()
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _matching_close(open_char: str) -> str:
    if open_char == "{":
        return "}"
    if open_char == "[":
        return "]"
    raise ValueError(f"Unsupported JSON opener: {open_char!r}")


def _balanced_json_candidate(text: str, start: int) -> str | None:
    """Return a balanced JSON object/array candidate starting at ``start``."""
    opener = text[start]
    closer = _matching_close(opener)
    stack = [closer]
    in_string = False
    escaped = False

    for index in range(start + 1, len(text)):
        char = text[index]
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
        if char in "[{":
            stack.append(_matching_close(char))
            continue
        if stack and char == stack[-1]:
            stack.pop()
            if not stack:
                return text[start : index + 1].strip()
            continue
        if char in "]}" and (not stack or char != stack[-1]):
            return None

    return None


def extract_json_candidate(text: str) -> str:
    """Extract the largest balanced JSON object or array from model output."""
    stripped = strip_markdown_json_fence(text)
    if not stripped:
        return stripped

    if stripped[0] in "[{" and stripped[-1] in "]}":
        return stripped

    candidates: list[str] = []
    for index, char in enumerate(stripped):
        if char not in "[{":
            continue
        candidate = _balanced_json_candidate(stripped, index)
        if candidate:
            candidates.append(candidate)

    if not candidates:
        return stripped
    return max(candidates, key=len)


def repair_common_model_json(text: str) -> str:
    """Apply conservative repairs commonly needed for model JSON output."""
    repaired = text.strip().replace("\ufeff", "")
    repaired = re.sub(r"(?m)^\s*//.*$", "", repaired)
    repaired = re.sub(r",\s*([}\]])", r"\1", repaired)
    return repaired.strip()


def parse_model_json(text: str, *, allow_repair: bool = True) -> Any:
    """Parse JSON from a model response.

    The parser tolerates Markdown fences, surrounding prose and a small set of
    conservative syntax repairs. It never invents missing fields and never
    returns an empty object on failure.
    """
    candidate = extract_json_candidate(text)
    try:
        return json.loads(candidate)
    except json.JSONDecodeError as first_error:
        if not allow_repair:
            raise ModelJsonParseError(str(first_error)) from first_error

        repaired = repair_common_model_json(candidate)
        try:
            return json.loads(repaired)
        except json.JSONDecodeError as second_error:
            raise ModelJsonParseError(f"Unable to parse model JSON: {second_error}") from second_error


def parse_model_json_object(text: str, *, allow_repair: bool = True) -> dict[str, Any]:
    """Parse a JSON object from a model response."""
    parsed = parse_model_json(text, allow_repair=allow_repair)
    if not isinstance(parsed, dict):
        raise ModelJsonParseError(f"Expected JSON object, got {type(parsed).__name__}")
    return parsed
