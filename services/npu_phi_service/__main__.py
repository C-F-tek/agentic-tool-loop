from __future__ import annotations

import argparse

import uvicorn

from .app import create_app
from .settings import NpuPhiSettings


def main() -> None:
    settings = NpuPhiSettings.from_env()
    parser = argparse.ArgumentParser(description="AI-Carmine Phi-3.5 OpenVINO/NPU diagnostic sidecar")
    parser.add_argument("--host", default=settings.host)
    parser.add_argument("--port", type=int, default=settings.port)
    args = parser.parse_args()

    app = create_app(settings=settings)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
