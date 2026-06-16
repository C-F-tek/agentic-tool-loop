#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any


ROOT = Path(r"C:\Users\carmi\AI")
CONFIG = ROOT / ".codex" / "mcp_servers_probe.json"
STATE_DIR = ROOT / ".codex" / "state"
REPORT_JSON = STATE_DIR / "mcp_probe_report.json"
REPORT_JSONL = STATE_DIR / "mcp_probe_report.jsonl"

DEFAULT_TIMEOUT_SECONDS = 25


def load_stdin_event() -> dict[str, Any]:
    try:
        raw = sys.stdin.read()
        if raw.strip():
            return json.loads(raw)
    except Exception:
        pass
    return {}


def json_line(obj: dict[str, Any]) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n"


def parse_mcp_messages(raw: str) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []

    # JSONL parser
    for line in raw.splitlines():
        text = line.strip()
        if not text or not text.startswith("{"):
            continue
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            messages.append(value)

    if messages:
        return messages

    # Content-Length parser fallback
    data = raw.encode("utf-8", errors="replace")
    pos = 0
    while pos < len(data):
        header_end = data.find(b"\r\n\r\n", pos)
        if header_end < 0:
            break

        header = data[pos:header_end].decode("ascii", errors="replace")
        length = None
        for hline in header.splitlines():
            key, sep, val = hline.partition(":")
            if sep and key.strip().lower() == "content-length":
                try:
                    length = int(val.strip())
                except ValueError:
                    length = None
                break

        if not length:
            break

        body_start = header_end + 4
        body_end = body_start + length
        if body_end > len(data):
            break

        try:
            value = json.loads(data[body_start:body_end].decode("utf-8", errors="replace"))
        except json.JSONDecodeError:
            value = None

        if isinstance(value, dict):
            messages.append(value)

        pos = body_end

    return messages


def tool_names_from_messages(messages: list[dict[str, Any]]) -> list[str]:
    for msg in messages:
        if msg.get("id") != 2:
            continue
        result = msg.get("result") or {}
        tools = result.get("tools") or []
        names = []
        for tool in tools:
            if isinstance(tool, dict) and isinstance(tool.get("name"), str):
                names.append(tool["name"])
        return names
    return []


def response_by_id(messages: list[dict[str, Any]], msg_id: int) -> dict[str, Any] | None:
    for msg in messages:
        if msg.get("id") == msg_id:
            return msg
    return None


def probe_server(name: str, cfg: dict[str, Any], timeout_seconds: int) -> dict[str, Any]:
    started_at = time.time()

    command = cfg.get("command")
    args = cfg.get("args") or []
    cwd = cfg.get("cwd") or str(ROOT)
    env_cfg = cfg.get("env") or {}

    if not command:
        return {
            "server": name,
            "ok": False,
            "error": "missing_command",
            "elapsed_ms": 0,
        }

    full_env = os.environ.copy()
    for k, v in env_cfg.items():
        full_env[str(k)] = str(v)

    init = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {
                "name": "aicarmine-codex-hook-mcp-probe",
                "version": "0.1.0",
            },
        },
    }

    initialized = {
        "jsonrpc": "2.0",
        "method": "notifications/initialized",
        "params": {},
    }

    tools_list = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list",
        "params": {},
    }

    stdin_payload = json_line(init) + json_line(initialized) + json_line(tools_list)

    try:
        proc = subprocess.run(
            [str(command), *[str(a) for a in args]],
            input=stdin_payload,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(cwd),
            env=full_env,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "server": name,
            "ok": False,
            "error": "timeout",
            "timeout_seconds": timeout_seconds,
            "command": command,
            "args": args,
            "cwd": cwd,
            "elapsed_ms": int((time.time() - started_at) * 1000),
            "stdout_prefix": (exc.stdout or "")[:2000] if isinstance(exc.stdout, str) else "",
            "stderr_prefix": (exc.stderr or "")[:2000] if isinstance(exc.stderr, str) else "",
        }
    except Exception as exc:
        return {
            "server": name,
            "ok": False,
            "error": type(exc).__name__,
            "message": str(exc),
            "command": command,
            "args": args,
            "cwd": cwd,
            "elapsed_ms": int((time.time() - started_at) * 1000),
        }

    messages = parse_mcp_messages(proc.stdout)
    initialize_response = response_by_id(messages, 1)
    tools_response = response_by_id(messages, 2)
    tools = tool_names_from_messages(messages)

    init_ok = bool(initialize_response and "result" in initialize_response)
    tools_ok = bool(tools_response and "result" in tools_response)

    return {
        "server": name,
        "ok": bool(init_ok and tools_ok),
        "init_ok": init_ok,
        "tools_list_ok": tools_ok,
        "tool_count": len(tools),
        "tools": tools,
        "returncode": proc.returncode,
        "command": command,
        "args": args,
        "cwd": cwd,
        "env_keys": sorted(env_cfg.keys()),
        "elapsed_ms": int((time.time() - started_at) * 1000),
        "stderr_prefix": proc.stderr[:4000],
        "stdout_message_count": len(messages),
        "stdout_prefix": proc.stdout[:1000] if not tools_ok else "",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quick", action="store_true")
    args = parser.parse_args()

    event = load_stdin_event()
    hook_event = str(event.get("hook_event_name") or "SessionStart")

    STATE_DIR.mkdir(parents=True, exist_ok=True)

    if not CONFIG.exists():
        out = {
            "hookSpecificOutput": {
                "hookEventName": hook_event,
                "additionalContext": f"AI-Carmine MCP probe config missing: {CONFIG}",
            }
        }
        print(json.dumps(out, ensure_ascii=False))
        return 0

    try:
        inventory = json.loads(CONFIG.read_text(encoding="utf-8"))
    except Exception as exc:
        out = {
            "hookSpecificOutput": {
                "hookEventName": hook_event,
                "additionalContext": f"AI-Carmine MCP probe config invalid: {type(exc).__name__}: {exc}",
            }
        }
        print(json.dumps(out, ensure_ascii=False))
        return 0

    servers = inventory.get("servers") or {}
    if not isinstance(servers, dict):
        servers = {}

    results = []
    for name, cfg in servers.items():
        if not isinstance(cfg, dict):
            continue
        results.append(probe_server(name, cfg, DEFAULT_TIMEOUT_SECONDS))

    ok = [r for r in results if r.get("ok")]
    bad = [r for r in results if not r.get("ok")]

    report = {
        "generated_at_epoch": time.time(),
        "config": str(CONFIG),
        "total": len(results),
        "ok": len(ok),
        "bad": len(bad),
        "results": results,
    }

    REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    with REPORT_JSONL.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(report, ensure_ascii=False, default=str) + "\n")

    lines = [
        "AI-Carmine MCP stdio probe completed.",
        f"Report: {REPORT_JSON}",
        f"Servers OK: {len(ok)}/{len(results)}",
    ]

    if ok:
        lines.append("")
        lines.append("OK servers and exposed tools:")
        for r in ok:
            tool_list = ", ".join(r.get("tools") or [])
            lines.append(f"- {r['server']}: {r.get('tool_count', 0)} tools")
            if tool_list:
                lines.append(f"  tools: {tool_list}")

    if bad:
        lines.append("")
        lines.append("FAILED servers:")
        for r in bad:
            lines.append(
                f"- {r.get('server')}: error={r.get('error')} "
                f"init_ok={r.get('init_ok')} tools_list_ok={r.get('tools_list_ok')} "
                f"returncode={r.get('returncode')} elapsed_ms={r.get('elapsed_ms')}"
            )
            stderr = (r.get("stderr_prefix") or "").strip()
            if stderr:
                lines.append(f"  stderr_prefix: {stderr[:500]}")

    lines.append("")
    lines.append(
        "Important: this hook probes the MCP server processes directly. "
        "It does not prove that the active local model will invoke MCP tools. "
        "Actual Codex MCP tool calls are logged by the PreToolUse/PostToolUse hooks."
    )

    out = {
        "hookSpecificOutput": {
            "hookEventName": hook_event,
            "additionalContext": "\n".join(lines),
        }
    }

    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())