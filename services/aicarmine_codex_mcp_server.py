"""AI-Carmine Codex MCP wrapper.

Stable entrypoint for Codex App.

This wrapper deliberately tolerates different exports from
codex_bridge.mcp_server:
- main()
- serve()
- self_test()
- or only low-level _read_message/_handle_rpc/_write_message.
"""

from __future__ import annotations

import sys

from codex_bridge import mcp_server


def _raw_stdio_loop() -> int:
    read_message = getattr(mcp_server, "_read_message", None)
    handle_rpc = getattr(mcp_server, "_handle_rpc", None)
    write_message = getattr(mcp_server, "_write_message", None)

    missing = [
        name
        for name, value in {
            "_read_message": read_message,
            "_handle_rpc": handle_rpc,
            "_write_message": write_message,
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
        message = read_message(stdin)
        if message is None:
            break

        response = handle_rpc(message)
        if response is not None:
            write_message(stdout, response)

    return 0


def main() -> int:
    exported_main = getattr(mcp_server, "main", None)
    if callable(exported_main):
        return int(exported_main() or 0)

    if "--self-test" in sys.argv or "--self-test-content-length" in sys.argv:
        self_test = getattr(mcp_server, "self_test", None)
        if callable(self_test):
            return int(self_test() or 0)

    serve = getattr(mcp_server, "serve", None)
    if callable(serve):
        return int(serve() or 0)

    return _raw_stdio_loop()


if __name__ == "__main__":
    raise SystemExit(main())
