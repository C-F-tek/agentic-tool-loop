from __future__ import annotations

import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path

CONFIG = Path(os.environ["USERPROFILE"]) / ".codex" / "config.toml"
PYTHON = Path(r"C:\Users\carmi\AI\venvs\labtools\Scripts\python.exe")
MCP = Path(r"C:\Users\carmi\AI\services\aicarmine_codex_mcp_server.py")


def fail(msg: str) -> int:
    print(f"FAIL: {msg}")
    return 1


def load_config() -> dict:
    return tomllib.loads(CONFIG.read_text(encoding="utf-8-sig"))


def run_mcp(messages: list[dict]) -> list[dict]:
    payload = "".join(json.dumps(m, separators=(",", ":")) + "\n" for m in messages)

    proc = subprocess.run(
        [str(PYTHON), str(MCP)],
        input=payload,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=Path.cwd(),
        timeout=30,
    )

    if proc.returncode != 0:
        raise RuntimeError(
            f"MCP exited {proc.returncode}\nSTDERR:\n{proc.stderr}\nSTDOUT:\n{proc.stdout}"
        )

    out = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        out.append(json.loads(line))
    return out


def result_by_id(responses: list[dict], msg_id: int) -> dict:
    for item in responses:
        if item.get("id") == msg_id:
            return item
    raise KeyError(msg_id)


def main() -> int:
    cfg = load_config()

    server = cfg.get("mcp_servers", {}).get("aicarmine_tools")
    if not isinstance(server, dict):
        return fail("mcp_servers.aicarmine_tools missing")

    enabled = set(server.get("enabled_tools") or [])
    disabled = set(server.get("disabled_tools") or [])
    effective_enabled = enabled - disabled

    print(f"CONFIG={CONFIG}")
    print(f"CWD={Path.cwd()}")
    print(f"enabled={len(enabled)} disabled={len(disabled)} effective={len(effective_enabled)}")

    responses = run_mcp([
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "allowlist-audit", "version": "1"},
            },
        },
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        {"jsonrpc": "2.0", "id": 3, "method": "resources/list", "params": {}},
        {"jsonrpc": "2.0", "id": 4, "method": "roots/list", "params": {}},
        {"jsonrpc": "2.0", "id": 5, "method": "prompts/list", "params": {}},
        {"jsonrpc": "2.0", "id": 6, "method": "completion/complete", "params": {}},
    ])

    tools_result = result_by_id(responses, 2)
    if "error" in tools_result:
        return fail(f"tools/list error: {tools_result['error']}")

    server_tools = {
        t.get("name")
        for t in tools_result.get("result", {}).get("tools", [])
        if isinstance(t, dict)
    }

    missing = sorted(effective_enabled - server_tools)
    extra_blocked = sorted(disabled & server_tools)

    print(f"server_tools={len(server_tools)}")

    if missing:
        print("MISSING_FROM_SERVER:")
        for name in missing:
            print(f"  {name}")

    if extra_blocked:
        print("DISABLED_BUT_EXPOSED_BY_SERVER:")
        for name in extra_blocked:
            print(f"  {name}")

    for msg_id, label in [
        (3, "resources/list"),
        (4, "roots/list"),
        (5, "prompts/list"),
        (6, "completion/complete"),
    ]:
        item = result_by_id(responses, msg_id)
        if "error" in item:
            return fail(f"{label} error: {item['error']}")
        print(f"OK: {label}")

    roots = result_by_id(responses, 4).get("result", {}).get("roots", [])
    print("ROOTS:")
    for root in roots:
        print(f"  {root.get('name')} -> {root.get('uri')}")

    if missing or extra_blocked:
        return 2

    print("OK: allowlist matches MCP tools/list")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
