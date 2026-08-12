#!/usr/bin/env python3
"""Check local AI resource lanes without running project generation.

The check is app-agnostic and observability-only. It can inspect NPU/OpenVINO,
GPU/OpenVINO visibility and Ollama availability, optionally in parallel. It does
not execute Blender, does not generate scene code, does not call long model
prompts by default, and does not mutate source files.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable


def ensure_repo_imports(repo_root: Path) -> None:
    for path in (repo_root, repo_root / "Tools" / "npu"):
        text = str(path)
        if text not in sys.path:
            sys.path.insert(0, text)


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def unavailable_lane(name: str, kind: str, message: str, *, elapsed_sec: float = 0.0) -> dict[str, Any]:
    return {
        "lane": name,
        "kind": kind,
        "passed": False,
        "ready": False,
        "available": False,
        "provider_execution_performed": False,
        "elapsed_sec": round(elapsed_sec, 4),
        "report": {"errors": [], "warnings": [message]},
    }


def check_npu_lane(repo_root: Path, timeout: float) -> dict[str, Any]:
    ensure_repo_imports(repo_root)
    started = time.perf_counter()
    try:
        from Tools.npu.npu_runtime import DEFAULT_MODEL_DIR, DEFAULT_NPU_PYTHON, npu_preflight  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001 - report-only check.
        return unavailable_lane(
            "npu",
            "openvino_npu_preflight",
            f"NPU runtime helper import failed: {type(exc).__name__}: {exc}",
            elapsed_sec=time.perf_counter() - started,
        )

    try:
        report = npu_preflight(DEFAULT_NPU_PYTHON, DEFAULT_MODEL_DIR, timeout=timeout)
    except Exception as exc:  # noqa: BLE001 - report-only check.
        return {
            "lane": "npu",
            "kind": "openvino_npu_preflight",
            "passed": False,
            "ready": False,
            "available": False,
            "provider_execution_performed": False,
            "elapsed_sec": round(time.perf_counter() - started, 4),
            "report": {"errors": [f"{type(exc).__name__}: {exc}"], "warnings": []},
        }

    available = bool(report.get("npu_device_available"))
    ready = bool(report.get("ready"))
    return {
        "lane": "npu",
        "kind": "openvino_npu_preflight",
        "passed": ready or available,
        "ready": ready,
        "available": available,
        "provider_execution_performed": False,
        "elapsed_sec": round(time.perf_counter() - started, 4),
        "report": report,
    }


def check_gpu_lane(repo_root: Path, timeout: float) -> dict[str, Any]:
    ensure_repo_imports(repo_root)
    started = time.perf_counter()
    try:
        from Tools.npu.npu_runtime import DEFAULT_NPU_PYTHON, _parse_last_json_line, _run_python  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001 - report-only check.
        return unavailable_lane(
            "gpu",
            "openvino_gpu_preflight",
            f"NPU runtime helper import failed: {type(exc).__name__}: {exc}",
            elapsed_sec=time.perf_counter() - started,
        )

    code = "import json, openvino as ov; print(json.dumps(ov.Core().available_devices))"
    try:
        ok, text, exit_code = _run_python(DEFAULT_NPU_PYTHON, code, timeout=timeout)
    except Exception as exc:  # noqa: BLE001 - report-only check.
        ok, text, exit_code = False, f"{type(exc).__name__}: {exc}", 1
    devices = _parse_last_json_line(text) if ok else []
    if not isinstance(devices, list):
        devices = []
    gpu_devices = [item for item in devices if str(item).upper().startswith("GPU")]
    return {
        "lane": "gpu",
        "kind": "openvino_gpu_preflight",
        "passed": ok and bool(gpu_devices),
        "ready": ok and bool(gpu_devices),
        "available": bool(gpu_devices),
        "provider_execution_performed": False,
        "elapsed_sec": round(time.perf_counter() - started, 4),
        "report": {
            "python_exe": str(DEFAULT_NPU_PYTHON),
            "python_starts": ok,
            "exit_code": exit_code,
            "openvino_available_devices": devices,
            "gpu_devices": gpu_devices,
            "errors": [] if ok else [text],
            "warnings": [] if gpu_devices else ["No OpenVINO GPU device visible from the configured NPU Python environment."],
        },
    }


def check_ollama_lane(repo_root: Path, model: str | None, *, probe_generate: bool) -> dict[str, Any]:
    ensure_repo_imports(repo_root)
    started = time.perf_counter()
    try:
        from Tools.npu.ollama_runtime import (  # noqa: PLC0415
            DEFAULT_BASE_URL,
            OllamaSession,
            choose_model,
            is_server_ready,
            list_models,
            list_models_from_disk,
        )
    except Exception as exc:  # noqa: BLE001 - report-only check.
        return unavailable_lane(
            "ollama",
            "ollama_preflight",
            f"Ollama runtime helper import failed: {type(exc).__name__}: {exc}",
            elapsed_sec=time.perf_counter() - started,
        )

    errors: list[str] = []
    warnings: list[str] = []
    server_ready = is_server_ready(DEFAULT_BASE_URL)
    models: list[str] = []
    selected_model: str | None = None
    generated_probe = ""

    try:
        models = list_models(DEFAULT_BASE_URL) if server_ready else list_models_from_disk()
        selected_model = choose_model(model, models)
    except Exception as exc:  # noqa: BLE001 - report-only check.
        errors.append(f"{type(exc).__name__}: {exc}")

    if probe_generate and selected_model:
        try:
            with OllamaSession(model=selected_model, shutdown_server=False, unload_model=True) as session:
                generated_probe = session.generate(
                    "Return exactly this JSON object and no prose: {\"ok\": true}",
                    max_new_tokens=32,
                    temperature=0.0,
                )
        except Exception as exc:  # noqa: BLE001 - optional probe.
            errors.append(f"probe_generate {type(exc).__name__}: {exc}")

    if not server_ready:
        warnings.append("Ollama server is not currently reachable; disk manifests may still list models.")
    if not models:
        warnings.append("No Ollama models discovered.")

    return {
        "lane": "ollama",
        "kind": "ollama_preflight",
        "passed": bool(selected_model) and (not probe_generate or not errors),
        "ready": bool(selected_model),
        "available": bool(models),
        "provider_execution_performed": bool(probe_generate and generated_probe),
        "elapsed_sec": round(time.perf_counter() - started, 4),
        "report": {
            "base_url": DEFAULT_BASE_URL,
            "server_ready": server_ready,
            "model_count": len(models),
            "selected_model": selected_model,
            "probe_generate_enabled": probe_generate,
            "probe_response_preview": generated_probe[:160],
            "errors": errors,
            "warnings": warnings,
        },
    }


def run_checks(repo_root: Path, args: argparse.Namespace) -> dict[str, Any]:
    tasks: list[tuple[str, Callable[[], dict[str, Any]]]] = []
    if not args.skip_npu:
        tasks.append(("npu", lambda: check_npu_lane(repo_root, args.timeout)))
    if not args.skip_gpu:
        tasks.append(("gpu", lambda: check_gpu_lane(repo_root, args.timeout)))
    if not args.skip_ollama:
        tasks.append(("ollama", lambda: check_ollama_lane(repo_root, args.model, probe_generate=args.probe_ollama_generate)))

    started = time.perf_counter()
    lane_reports: list[dict[str, Any]] = []
    if args.parallel and len(tasks) > 1:
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(tasks)) as executor:
            future_map = {executor.submit(func): name for name, func in tasks}
            for future in concurrent.futures.as_completed(future_map):
                name = future_map[future]
                try:
                    lane_reports.append(future.result())
                except Exception as exc:  # noqa: BLE001 - report all lanes.
                    lane_reports.append(
                        {
                            "lane": name,
                            "kind": f"{name}_preflight",
                            "passed": False,
                            "ready": False,
                            "available": False,
                            "provider_execution_performed": False,
                            "elapsed_sec": 0,
                            "report": {"errors": [f"{type(exc).__name__}: {exc}"], "warnings": []},
                        }
                    )
    else:
        for name, func in tasks:
            try:
                lane_reports.append(func())
            except Exception as exc:  # noqa: BLE001 - report all lanes.
                lane_reports.append(
                    {
                        "lane": name,
                        "kind": f"{name}_preflight",
                        "passed": False,
                        "ready": False,
                        "available": False,
                        "provider_execution_performed": False,
                        "elapsed_sec": 0,
                        "report": {"errors": [f"{type(exc).__name__}: {exc}"], "warnings": []},
                    }
                )

    lane_reports = sorted(lane_reports, key=lambda item: item["lane"])
    required = set(args.require_lane or [])
    errors: list[str] = []
    warnings: list[str] = []
    for lane in lane_reports:
        report = lane.get("report") or {}
        warnings.extend(f"{lane['lane']}: {item}" for item in report.get("warnings", [])[:5])
        if lane["lane"] in required and not lane.get("ready"):
            errors.append(f"required lane is not ready: {lane['lane']}")

    return {
        "schema_version": 1,
        "kind": "local_ai_resource_lanes",
        "generated_at": now_iso(),
        "repo_root": str(repo_root),
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "parallel": bool(args.parallel),
        "provider_execution_performed": any(item.get("provider_execution_performed") for item in lane_reports),
        "lane_count": len(lane_reports),
        "ready_lanes": [item["lane"] for item in lane_reports if item.get("ready")],
        "available_lanes": [item["lane"] for item in lane_reports if item.get("available")],
        "elapsed_sec": round(time.perf_counter() - started, 4),
        "lanes": lane_reports,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = ["# Local AI Resource Lanes", ""]
    lines.append(f"- Passed: `{report['passed']}`")
    lines.append(f"- Parallel: `{report['parallel']}`")
    lines.append(f"- Provider execution performed: `{report['provider_execution_performed']}`")
    lines.append(f"- Ready lanes: `{', '.join(report['ready_lanes'])}`")
    lines.append(f"- Available lanes: `{', '.join(report['available_lanes'])}`")
    lines.append("")
    lines.append("| Lane | Ready | Available | Elapsed sec | Provider execution |")
    lines.append("|---|---:|---:|---:|---:|")
    for lane in report["lanes"]:
        lines.append(
            f"| {lane['lane']} | {lane['ready']} | {lane['available']} | {lane['elapsed_sec']} | {lane['provider_execution_performed']} |"
        )
    if report["warnings"]:
        lines.append("\n## Warnings")
        for warning in report["warnings"]:
            lines.append(f"- {warning}")
    if report["errors"]:
        lines.append("\n## Errors")
        for error in report["errors"]:
            lines.append(f"- {error}")
    lines.append("")
    lines.append("This report is observability-only and app-agnostic.")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", default="output/validation/local_ai_resource_lanes.json")
    parser.add_argument("--markdown-output", default="output/validation/local_ai_resource_lanes.md")
    parser.add_argument("--model", help="Preferred Ollama model for selection/probe.")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--parallel", action="store_true", help="Run lane checks concurrently.")
    parser.add_argument("--probe-ollama-generate", action="store_true", help="Run a tiny Ollama generation probe.")
    parser.add_argument("--require-lane", action="append", choices=("npu", "gpu", "ollama"), default=[])
    parser.add_argument("--skip-npu", action="store_true")
    parser.add_argument("--skip-gpu", action="store_true")
    parser.add_argument("--skip-ollama", action="store_true")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    report = run_checks(repo_root, args)

    output = Path(args.output)
    if not output.is_absolute():
        output = repo_root / output
    md_output = Path(args.markdown_output)
    if not md_output.is_absolute():
        md_output = repo_root / md_output
    output.parent.mkdir(parents=True, exist_ok=True)
    md_output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md_output.write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "output": str(output), "markdown": str(md_output), "ready_lanes": report["ready_lanes"]}, indent=2))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
