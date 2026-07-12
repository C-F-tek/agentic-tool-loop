from __future__ import annotations

import json
from typing import Any

from ..job.response_values import compact_text



def compact_json(value: Any, limit: int) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False, indent=2, default=str)
    except Exception:
        text = str(value)
    return compact_text(text, limit)


def build_public_result_digest(result: Any, inline_limit: int) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {"preview": compact_json(result, inline_limit)} if result else {}

    digest: dict[str, Any] = {}
    passthrough = (
        "ok",
        "status",
        "auto_finalized_by",
        "blocked_by",
        "rejected_tool",
        "blocked_tool",
        "error",
        "error_type",
        "planner_decision",
    )
    for key in passthrough:
        if key in result and key != "planner_decision":
            digest[key] = result.get(key)

    decision = result.get("planner_decision")
    if isinstance(decision, dict):
        digest["planner_decision"] = {
            k: decision.get(k)
            for k in ("action", "tool", "reason", "selected_by_3572", "coerced_by_3572")
            if decision.get(k) not in (None, "", [], {})
        }

    history = result.get("history")
    if isinstance(history, list):
        digest["history_count"] = len(history)
        tail: list[dict[str, Any]] = []
        for item in history[-8:]:
            if not isinstance(item, dict):
                continue
            d = item.get("decision") if isinstance(item.get("decision"), dict) else {}
            r = item.get("tool_result") if isinstance(item.get("tool_result"), dict) else {}
            tail.append(
                {
                    k: v
                    for k, v in {
                        "step": item.get("step"),
                        "action": d.get("action"),
                        "tool": r.get("tool") or d.get("tool"),
                        "ok": r.get("ok"),
                        "path": r.get("path"),
                        "artifact": r.get("artifact"),
                        "returncode": r.get("returncode"),
                        "truncated": r.get("truncated"),
                    }.items()
                    if v not in (None, "", [], {})
                }
            )
        digest["history_tail"] = tail

    artifacts: list[str] = []
    for key in ("artifact", "backup_artifact"):
        value = result.get(key)
        if isinstance(value, str) and value and value not in artifacts:
            artifacts.append(value)
    for value in result.get("artifacts") or []:
        if isinstance(value, str) and value and value not in artifacts:
            artifacts.append(value)
    if artifacts:
        digest["artifacts"] = artifacts[:20]

    if not digest:
        digest["preview"] = compact_json(result, inline_limit)
    return digest
