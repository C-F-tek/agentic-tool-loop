from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RuntimeUrls:
    openwebui: str = "http://127.0.0.1:8080"
    bridge_3571: str = "http://127.0.0.1:3571"
    broker_3572: str = "http://127.0.0.1:3572"


class RuntimeHttpError(RuntimeError):
    pass


def _request(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    timeout: int = 30,
) -> tuple[int, str]:
    data = None
    headers: dict[str, str] = {}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            return int(getattr(response, "status", 200)), raw
    except (urllib.error.URLError, urllib.error.HTTPError, socket.timeout) as exc:
        raise RuntimeHttpError(f"{method} {url} failed: {exc}") from exc


def get_text(url: str, *, timeout: int = 15) -> str:
    status, raw = _request(url, timeout=timeout)
    if status < 200 or status >= 300:
        raise RuntimeHttpError(f"GET {url} returned HTTP {status}")
    return raw


def get_json(url: str, *, timeout: int = 15) -> dict[str, Any]:
    raw = get_text(url, timeout=timeout)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeHttpError(f"GET {url} did not return JSON: {raw[:300]}") from exc
    if not isinstance(parsed, dict):
        raise RuntimeHttpError(f"GET {url} returned non-object JSON")
    return parsed


def get_json_or_none(url: str, *, timeout: int = 15) -> dict[str, Any] | None:
    try:
        return get_json(url, timeout=timeout)
    except Exception:
        return None


def post_json(url: str, payload: dict[str, Any], *, timeout: int = 300) -> dict[str, Any]:
    status, raw = _request(url, method="POST", payload=payload, timeout=timeout)
    if status < 200 or status >= 300:
        raise RuntimeHttpError(f"POST {url} returned HTTP {status}: {raw[:500]}")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeHttpError(f"POST {url} did not return JSON: {raw[:500]}") from exc
    if not isinstance(parsed, dict):
        raise RuntimeHttpError(f"POST {url} returned non-object JSON")
    return parsed


def wait_for_url(url: str, *, timeout_seconds: int = 20) -> bool:
    deadline = time.time() + timeout_seconds
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            get_text(url, timeout=5)
            return True
        except Exception as exc:  # pragma: no cover - only used against live runtime
            last_error = exc
            time.sleep(0.5)
    if last_error:
        raise RuntimeHttpError(f"{url} not reachable within {timeout_seconds}s: {last_error}") from last_error
    return False
