from __future__ import annotations

import os
from collections.abc import Mapping


EnvMapping = Mapping[str, str]

_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}


def _env(env: EnvMapping | None = None) -> EnvMapping:
    return os.environ if env is None else env


def parse_bool(value: object, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value).strip().lower()
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
        if value is not None and value.strip():
            return value
    return default


def env_bool(name: str, default: bool, env: EnvMapping | None = None) -> bool:
    return parse_bool(_env(env).get(name), default)


def _parse_int_env(name: str, value: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an integer; got {value!r}") from exc


def env_int(name: str, default: int, env: EnvMapping | None = None) -> int:
    value = _env(env).get(name)
    if value is None or not value.strip():
        return default
    return _parse_int_env(name, value)


def env_int_any(
    names: tuple[str, ...],
    default: int,
    env: EnvMapping | None = None,
) -> int:
    source = _env(env)
    for name in names:
        value = source.get(name)
        if value is not None and value.strip():
            return _parse_int_env(name, value)
    return default


def env_float(name: str, default: float, env: EnvMapping | None = None) -> float:
    value = _env(env).get(name)
    if value is None or not value.strip():
        return default
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a float; got {value!r}") from exc
