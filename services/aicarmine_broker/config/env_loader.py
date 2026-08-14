from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from typing import Any


EnvMapping = Mapping[str, str]

_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}
logger = logging.getLogger(__name__)


def _env(env: EnvMapping | None = None) -> EnvMapping:
    return os.environ if env is None else env


def _safe_preview(value: object,  limit: int = 200) -> str:
    try:
        text = str(value)
    except Exception as exc:
        text = f"<unstringifiable:{type(exc).__name__}>"
    return text[: max(0, int(limit or 0))]


def env_error_context(
    name: str,
    
    expected: str,
    value: object,
    exc: Exception | None = None,
) -> dict[str, Any]:
    context: dict[str, Any] = {
        "env_name": str(name),
        "expected": str(expected),
        "received_type": type(value).__name__,
        "received_preview": _safe_preview(value),
    }
    if exc is not None:
        context["error_type"] = type(exc).__name__
        context["error"] = str(exc)[:500]
    return context


def _format_env_error(context: Mapping[str, Any]) -> str:
    return (
        f"{context.get('env_name')} expected {context.get('expected')}; "
        f"received_type={context.get('received_type')}; "
        f"received_preview={context.get('received_preview')!r}; "
        f"error_type={context.get('error_type') or ''}"
    )


def _env_text(name: str, value: object,  expected: str) -> str:
    try:
        return str(value).strip()
    except Exception as exc:
        context = env_error_context(name, expected=expected, value=value, exc=exc)
        raise ValueError(_format_env_error(context)) from exc


def parse_bool(value: object, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    try:
        text = str(value).strip().lower()
    except Exception as exc:
        logger.debug(
            "Boolean parse fallback to default. value_type=%s error_type=%s",
            type(value).__name__,
            type(exc).__name__,
        )
        return default
    if not text:
        return default
    if text in _TRUE_VALUES:
        return True
    if text in _FALSE_VALUES:
        return False
    return bool(value)


def env_str(name: str, default: str, env: EnvMapping | None = None) -> str:
    value = _env(env).get(name)
    return default if value is None else value


def env_first(
    names: tuple[str, ...],
    default: str,
    env: EnvMapping | None = None,
) -> str:
    source = _env(env)
    for name in names:
        value = source.get(name)
        if value is None:
            continue
        text = _env_text(name, value, expected="non-empty string")
        if text:
            return str(value)
    return default



def env_bool(name: str, default: bool, env: EnvMapping | None = None) -> bool:
    value = _env(env).get(name)
    if value is None:
        return default
    if isinstance(value, (bool, int, float)):
        return parse_bool(value, default)
    try:
        str(value)
    except Exception as exc:
        context = env_error_context(name, expected="boolean", value=value, exc=exc)
        logger.debug(
            "Boolean env parse fallback to default. env_name=%s received_type=%s error_type=%s",
            context["env_name"],
            context["received_type"],
            context.get("error_type"),
        )
        return default
    return parse_bool(value, default)


def _parse_int_env(name: str, value: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        context = env_error_context(name, expected="integer", value=value, exc=exc)
        raise ValueError(_format_env_error(context)) from exc


def env_int(name: str, default: int, env: EnvMapping | None = None) -> int:
    value = _env(env).get(name)
    if value is None:
        return default
    text = _env_text(name, value, expected="integer")
    if not text:
        return default
    return _parse_int_env(name, text)


def env_int_any(
    names: tuple[str, ...],
    default: int,
    env: EnvMapping | None = None,
) -> int:
    source = _env(env)
    for name in names:
        value = source.get(name)
        if value is None:
            continue
        text = _env_text(name, value, expected="integer")
        if text:
            return _parse_int_env(name, text)
    return default


def env_float(name: str, default: float, env: EnvMapping | None = None) -> float:
    value = _env(env).get(name)
    if value is None:
        return default
    text = _env_text(name, value, expected="float")
    if not text:
        return default
    try:
        return float(text)
    except (TypeError, ValueError) as exc:
        context = env_error_context(name, expected="float", value=value, exc=exc)
        raise ValueError(_format_env_error(context)) from exc
