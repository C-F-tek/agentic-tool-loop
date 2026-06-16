#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import sys
import time
from typing import Any


ROOT = Path(r"C:\Users\carmi\AI")
STATE_DIR = ROOT / ".codex" / "state"
LOG = STATE_DIR / "mcp_tool_calls.jsonl"


def main() -> int:
    phase = sys.argv[1] if len(sys.argv) > 1 else "unknown"

    try:
        event: dict[str, Any] = json.loads(sys.stdin.read() or "{}")
    except Exception as exc:
        event = {
            "_parse_error": type(exc).__name__,
            "_parse_message": str(exc),
        }

    STATE_DIR.mkdir(parents=True, exist_ok=True)

    record = {
        "time_epoch": time.time(),
        "phase": phase,
        "hook_event_name": event.get("hook_event_name"),
        "session_id": event.get("session_id"),
        "turn_id": event.get("turn_id"),
        "model": event.get("model"),
        "tool_name": event.get("tool_name"),
        "tool_use_id": event.get("tool_use_id"),
        "tool_input": event.get("tool_input"),
        "raw_event": event,
    }

    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

    hook_event = str(event.get("hook_event_name") or ("PreToolUse" if phase == "pre" else "PostToolUse"))

    out = {
        "hookSpecificOutput": {
            "hookEventName": hook_event,
            "additionalContext": (
                f"Logged MCP tool {phase}: {event.get('tool_name')} "
                f"to {LOG}"
            ),
        }
    }

    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())