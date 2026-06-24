"""AI-Carmine Codex MCP wrapper.

Stable entrypoint for Codex App.

Imports shared helpers from repo_mcp_common.py (single source of truth).
Falls back to codex_bridge.mcp_server only for raw stdio loop when needed.
"""

from __future__ import annotations

import sys

from codex_bridge import mcp_server
from repo_mcp_common import (
    call_tool,
    compact_text_generic,
    handle_request,
    json_dumps,
    ok,
    read_message,
    result_is_error,
    serve,
    self_test,
    tool_content,
    write_message,
)


def _raw_stdio_loop() -> int:
    read_msg = getattr(mcp_server, "_read_message", None) or read_message
    handle_rpc = getattr(mcp_server, "_handle_rpc", None) or handle_request
    write_msg = getattr(mcp_server, "_write_message", None) or write_message

    missing = [
        name
        for name, value in {
            "_read_message": read_msg,
            "_handle_rpc": handle_rpc,
            "_write_message": write_msg,
        }.items()
        if not callable(value)
    ]

    if missing:
        raise RuntimeError(
            "codex_bridge.mcp_server missing raw MCP functions: "
            + ", ".join(missing)
        )

    stdin = sys.stdin.buffer
    stdout = sys.stdout.buffer

    while True:
        message = read_msg(stdin)
        if message is None:
            break

        response = handle_rpc(message)
        if response is not None:
            write_msg(stdout, response)

    return 0


def main() -> int:
    exported_main = getattr(mcp_server, "main", None)
    if callable(exported_main):
        return int(exported_main() or 0)

    if "--self-test" in sys.argv or "--self-test-content-length" in sys.argv:
        self_test_fn = getattr(mcp_server, "self_test", None)
        if callable(self_test_fn):
            return int(self_test_fn() or 0)

    serve_fn = getattr(mcp_server, "serve", None)
    if callable(serve_fn):
        return int(serve_fn() or 0)

    return _raw_stdio_loop()


if __name__ == "__main__":
    raise SystemExit(main())
