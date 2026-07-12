from __future__ import annotations

import argparse
from dataclasses import replace

import uvicorn

from .app import create_app
from .diagnostics import doctor_json
from .settings import NpuPhiSettings


def main() -> None:
    settings = NpuPhiSettings.from_env()
    parser = argparse.ArgumentParser(description="AI-Carmine Phi-3.5 OpenVINO/NPU diagnostic sidecar")
    parser.add_argument("--host", default=settings.host)
    parser.add_argument("--port", type=int, default=settings.port)
    parser.add_argument("--doctor", action="store_true", help="Print read-only runtime diagnostics and exit.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print --doctor JSON.")
    args = parser.parse_args()
    settings = replace(settings, host=args.host, port=args.port)

    if args.doctor:
        print(doctor_json(settings, pretty=args.pretty))
        return

    app = create_app(settings=settings)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
