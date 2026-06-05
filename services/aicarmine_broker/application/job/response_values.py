"""Pure value helpers for public job responses."""
from __future__ import annotations

import json
from typing import Any


def compact_text(value: Any, limit: int) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    if int(limit or 0) <= 0:
        return text
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 40)] + "\n... <full output is available in inline terminal payload when present>"


def compact_json(value: Any, limit: int) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False, indent=2, default=str)
    except Exception:
        text = str(value)
    return compact_text(text, limit)


def event_digest(event: dict[str, Any]) -> dict[str, Any]:
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    digest: dict[str, Any] = {
        "time": event.get("time") or event.get("ts"),
        "step": event.get("step"),
        "event_type": event.get("event_type"),
        "message": event.get("message"),
    }
    if payload:
        digest["payload_keys"] = sorted(str(k) for k in payload.keys())[:20]
        for key in (
            "tool",
            "ok",
            "status",
            "path",
            "artifact",
            "returncode",
            "count",
            "truncated",
        ):
            if key in payload:
                digest[key] = payload.get(key)
    return {k: v for k, v in digest.items() if v not in (None, "", [], {})}
