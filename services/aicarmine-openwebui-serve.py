from __future__ import annotations

import argparse
import base64
import os
import random
import sys
from pathlib import Path

import uvicorn


KEY_FILE = Path.cwd() / ".webui_secret_key"


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _random_secret_bytes() -> bytes:
    try:
        return random.randbytes(12)
    except AttributeError:
        return os.urandom(12)


def ensure_openwebui_boot_env() -> None:
    """Mirror open-webui serve bootstrap and keep launcher-owned overrides explicit."""

    os.environ["FROM_INIT_PY"] = "true"

    if os.getenv("WEBUI_SECRET_KEY"):
        return

    if not KEY_FILE.exists():
        KEY_FILE.write_bytes(base64.b64encode(_random_secret_bytes()))

    os.environ["WEBUI_SECRET_KEY"] = KEY_FILE.read_text(encoding="utf-8").strip()


def main() -> None:
    parser = argparse.ArgumentParser(description="AI-Carmine Open WebUI uvicorn launcher with explicit WebSocket keepalive settings.")
    parser.add_argument("--host", default=os.getenv("HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=_int_env("PORT", 8080))
    parser.add_argument(
        "--ws-ping-interval",
        type=float,
        default=_float_env("AICARMINE_OPENWEBUI_WS_PING_INTERVAL", 30.0),
        help="Seconds between WebSocket ping frames. Uvicorn default is 20.",
    )
    parser.add_argument(
        "--ws-ping-timeout",
        type=float,
        default=_float_env("AICARMINE_OPENWEBUI_WS_PING_TIMEOUT", 120.0),
        help="Seconds to wait for WebSocket pong before closing. Uvicorn default is 20.",
    )
    parser.add_argument(
        "--timeout-keep-alive",
        type=int,
        default=_int_env("AICARMINE_OPENWEBUI_HTTP_KEEP_ALIVE", 75),
        help="HTTP keep-alive timeout for idle connections.",
    )
    parser.add_argument(
        "--ws-per-message-deflate",
        action=argparse.BooleanOptionalAction,
        default=not _bool_env("AICARMINE_OPENWEBUI_DISABLE_WS_DEFLATE", True),
        help="Enable/disable WebSocket per-message-deflate. Disabled by default for local Windows stability.",
    )
    args = parser.parse_args()

    ensure_openwebui_boot_env()

    # Import side effects are required by Open WebUI before serving open_webui.main:app.
    import open_webui.main  # noqa: F401

    try:
        from open_webui.env import UVICORN_WORKERS
    except Exception:
        UVICORN_WORKERS = _int_env("UVICORN_WORKERS", 1)

    # Keep parity with current Open WebUI Windows launcher logic: loop='none' allows
    # asyncio.run() to respect the Windows selector event loop policy set by Open WebUI.
    loop = "none" if sys.platform == "win32" else "auto"

    print(
        "AI-Carmine Open WebUI uvicorn launcher: "
        f"host={args.host} port={args.port} workers={UVICORN_WORKERS} "
        f"ws_ping_interval={args.ws_ping_interval} ws_ping_timeout={args.ws_ping_timeout} "
        f"timeout_keep_alive={args.timeout_keep_alive} "
        f"ws_per_message_deflate={args.ws_per_message_deflate}",
        flush=True,
    )

    uvicorn.run(
        "open_webui.main:app",
        host=args.host,
        port=args.port,
        forwarded_allow_ips="*",
        workers=int(UVICORN_WORKERS),
        loop=loop,
        ws="websockets",
        ws_ping_interval=args.ws_ping_interval,
        ws_ping_timeout=args.ws_ping_timeout,
        timeout_keep_alive=args.timeout_keep_alive,
        ws_per_message_deflate=args.ws_per_message_deflate,
    )


if __name__ == "__main__":
    main()
