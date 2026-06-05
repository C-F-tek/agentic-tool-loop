"""Read-only diagnostics for the Phi-3.5 OpenVINO/NPU sidecar."""

from __future__ import annotations

import importlib.metadata
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any

from .settings import NpuPhiSettings


SCHEMA = "npu_phi_doctor.v1"


def _package_status(package_name: str, import_name: str | None = None) -> dict[str, Any]:
    resolved_import = import_name or package_name.replace("-", "_")
    available = importlib.util.find_spec(resolved_import) is not None
    version = ""
    if available:
        try:
            version = importlib.metadata.version(package_name)
        except Exception:
            version = ""
    return {
        "package": package_name,
        "import_name": resolved_import,
        "available": available,
        "version": version,
    }


def dependency_status() -> dict[str, Any]:
    packages = {
        "openvino": _package_status("openvino", "openvino"),
        "openvino_genai": _package_status("openvino-genai", "openvino_genai"),
        "fastapi": _package_status("fastapi", "fastapi"),
        "uvicorn": _package_status("uvicorn", "uvicorn"),
        "pydantic": _package_status("pydantic", "pydantic"),
    }
    return {
        "packages": packages,
        "openvino_available": packages["openvino"]["available"],
        "openvino_genai_available": packages["openvino_genai"]["available"],
        "fastapi_available": packages["fastapi"]["available"],
        "uvicorn_available": packages["uvicorn"]["available"],
        "pydantic_available": packages["pydantic"]["available"],
    }


def _dir_status(path: Path) -> dict[str, Any]:
    parent = path if path.exists() else path.parent
    return {
        "path": str(path),
        "exists": path.exists(),
        "parent_exists": parent.exists(),
        "parent_writable_hint": os.access(parent, os.W_OK) if parent.exists() else False,
    }


def build_npu_phi_doctor(
    settings: NpuPhiSettings | None = None,
    *,
    dependencies: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resolved = settings or NpuPhiSettings.from_env()
    deps = dependencies if isinstance(dependencies, dict) else dependency_status()
    model_status = resolved.model_status()
    warnings: list[dict[str, Any]] = []
    if resolved.port == 3550:
        warnings.append({
            "rule": "port_collides_with_openvino_reranker",
            "message": "NPU Phi sidecar must not reuse the existing 3550 OpenVINO/reranker port.",
        })
    if resolved.host not in {"127.0.0.1", "localhost"}:
        warnings.append({
            "rule": "non_local_bind",
            "message": "Default sidecar bind should stay local-only.",
        })
    if str(resolved.device).upper() != "NPU":
        warnings.append({
            "rule": "device_not_npu",
            "message": "The Phi sidecar contract is diagnostic NPU serving, not CPU/GPU fallback.",
        })
    missing_deps = [
        name
        for name in ("openvino", "openvino_genai", "fastapi", "uvicorn", "pydantic")
        if not deps.get(f"{name}_available")
    ]
    if missing_deps:
        warnings.append({
            "rule": "missing_runtime_dependencies",
            "packages": missing_deps,
        })
    ready_to_start = (
        bool(model_status.get("model_ready"))
        and not missing_deps
        and resolved.port != 3550
        and str(resolved.device).upper() == "NPU"
    )
    return {
        "schema": SCHEMA,
        "ok": ready_to_start,
        "diagnostic_only": True,
        "side_effects": "none",
        "service": "npu_phi_service",
        "python": {
            "executable": sys.executable,
            "prefix": sys.prefix,
            "version": sys.version.split()[0],
        },
        "contract": {
            "host": resolved.host,
            "port": resolved.port,
            "device": resolved.device,
            "distinct_from_openvino_reranker_port": resolved.port != 3550,
            "public_to_openwebui": False,
            "broker_policy": "best_effort_diagnostic_only",
        },
        "model": model_status,
        "runtime_paths": {
            "cache_dir": _dir_status(resolved.cache_dir),
            "spool_dir": _dir_status(resolved.spool_dir),
            "blob_path": str(resolved.blob_path),
        },
        "dependencies": deps,
        "config": resolved.public_config(),
        "warnings": warnings,
        "next_checks": [
            "Start sidecar only after model_ready and openvino_genai_available are true.",
            "Use /readyz after process start; use /v1/admin/warmup only when explicit warmup is desired.",
        ],
    }


def doctor_json(settings: NpuPhiSettings | None = None, *, pretty: bool = False) -> str:
    return json.dumps(
        build_npu_phi_doctor(settings),
        ensure_ascii=False,
        indent=2 if pretty else None,
        sort_keys=pretty,
        default=str,
    )
