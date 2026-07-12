"""Pure request-payload helpers for the 3571 bridge."""
from __future__ import annotations

from typing import Any


PUBLIC_AGENT_ARGUMENT_KEYS = {
    "request",
    "task",
    "query",
    "prompt",
    "instruction",
    "context",
    "path",
    "paths",
    "file",
    "files",
    "pattern",
    "symbol",
    "command",
    "approval_mode",
    "return_mode",
    "wait_seconds",
    "action",
    "job_action",
    "job_id",
    "user_consent",
    "allow_command",
}


def public_agent_arguments(raw_payload: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in raw_payload.items()
        if key in PUBLIC_AGENT_ARGUMENT_KEYS and value not in (None, "", [], {})
    }


def payload_to_dict(payload: Any) -> dict[str, Any]:
    if payload is None:
        return {}
    if isinstance(payload, dict):
        data = dict(payload)
    elif hasattr(payload, "model_dump"):
        data = payload.model_dump(mode="json", exclude_none=True, exclude_defaults=True)
    else:
        data = {"value": payload}

    cleaned: dict[str, Any] = {}
    for key, value in data.items():
        if value in (None, ""):
            continue
        if isinstance(value, (dict, list)) and not value:
            continue
        cleaned[str(key)] = value
    return cleaned


def first_text(payload: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def first_dict(payload: dict[str, Any], *keys: str) -> dict[str, Any]:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, dict) and value:
            return dict(value)
    return {}
