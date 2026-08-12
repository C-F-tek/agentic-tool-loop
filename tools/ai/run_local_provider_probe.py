#!/usr/bin/env python3
"""Run explicit local provider probes and normalize their results.

This tool is opt-in and report-only. It can run a tiny Ollama generation probe
and a tiny OpenVINO NPU device/tensor probe, then parses the already-obtained
results through app-agnostic provider result helpers.

It does not run Blender, does not generate scene code and does not change the
legacy dual-AI runtime pipeline.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any


def ensure_repo_imports(repo_root: Path) -> None:
    for path in (repo_root, repo_root / "Tools" / "npu"):
        text = str(path)
        if text not in sys.path:
            sys.path.insert(0, text)


def run_ollama_probe(repo_root: Path, model: str | None) -> dict[str, Any]:
    ensure_repo_imports(repo_root)
    from Tools.npu.ollama_runtime import OllamaSession, choose_model, is_server_ready, list_models, list_models_from_disk  # noqa: PLC0415

    from Tools.npu.pipeline import parse_provider_result  # noqa: PLC0415

    started = time.perf_counter()
    models = list_models() if is_server_ready() else list_models_from_disk()
    selected_model = choose_model(model, models)
    if not selected_model:
        return {
            "lane": "ollama",
            "passed": False,
            "provider_execution_performed": False,
            "error": "no Ollama model available",
            "elapsed_sec": round(time.perf_counter() - started, 4),
        }
    with OllamaSession(model=selected_model, shutdown_server=False, unload_model=True) as session:
        text = session.generate(
            "Return exactly this JSON object and no prose: {\"ok\": true, \"lane\": \"ollama\"}",
            max_new_tokens=48,
            temperature=0.0,
        )
    parsed = parse_provider_result(
        {"response": text},
        provider="ollama",
        model=selected_model,
        executed=True,
        allow_json=True,
    )
    return {
        "lane": "ollama",
        "passed": parsed.ok,
        "provider_execution_performed": True,
        "elapsed_sec": round(time.perf_counter() - started, 4),
        "selected_model": selected_model,
        "parsed_result": parsed.to_dict(),
        "text_preview": text[:200],
    }


def run_npu_probe(repo_root: Path, timeout: float) -> dict[str, Any]:
    ensure_repo_imports(repo_root)
    from Tools.npu.npu_runtime import DEFAULT_NPU_PYTHON, _parse_last_json_line, _run_python  # noqa: PLC0415

    from Tools.npu.pipeline import parse_provider_result  # noqa: PLC0415

    started = time.perf_counter()
    code = r'''
import json
import numpy as np
import openvino as ov
core = ov.Core()
devices = core.available_devices
result = {"ok": "NPU" in devices, "lane": "npu", "devices": devices}
print(json.dumps(result))
'''
    ok, text, exit_code = _run_python(DEFAULT_NPU_PYTHON, code, timeout=timeout)
    parsed_payload = _parse_last_json_line(text) if ok else {"error": text, "exit_code": exit_code}
    parsed = parse_provider_result(
        {"text": json.dumps(parsed_payload)},
        provider="openvino_npu",
        model="device_probe",
        executed=True,
        allow_json=True,
    )
    return {
        "lane": "npu",
        "passed": ok and bool(parsed_payload.get("ok")) if isinstance(parsed_payload, dict) else False,
        "provider_execution_performed": True,
        "elapsed_sec": round(time.perf_counter() - started, 4),
        "parsed_result": parsed.to_dict(),
        "raw_exit_code": exit_code,
        "raw_preview": text[:300],
    }


def build_report(repo_root: Path, args: argparse.Namespace) -> dict[str, Any]:
    ensure_repo_imports(repo_root)
    from Tools.npu.pipeline import build_provider_result_report, parse_provider_result  # noqa: PLC0415

    lane_reports: list[dict[str, Any]] = []
    errors: list[str] = []
    if args.run_ollama:
        try:
            lane_reports.append(run_ollama_probe(repo_root, args.model))
        except Exception as exc:  # noqa: BLE001 - report-only tool.
            lane_reports.append({"lane": "ollama", "passed": False, "provider_execution_performed": False, "error": f"{type(exc).__name__}: {exc}"})
    if args.run_npu:
        try:
            lane_reports.append(run_npu_probe(repo_root, args.timeout))
        except Exception as exc:  # noqa: BLE001 - report-only tool.
            lane_reports.append({"lane": "npu", "passed": False, "provider_execution_performed": False, "error": f"{type(exc).__name__}: {exc}"})

    parsed_results = [
        parse_provider_result(
            {"text": json.dumps({"lane": item.get("lane"), "passed": item.get("passed")})},
            provider=str(item.get("lane") or "unknown"),
            model=str(item.get("selected_model") or "probe"),
            executed=bool(item.get("provider_execution_performed")),
            allow_json=True,
        )
        for item in lane_reports
    ]
    provider_report = build_provider_result_report(
        provider="local_probe",
        model=args.model or "auto",
        results=parsed_results,
        provider_execution_performed=any(item.get("provider_execution_performed") for item in lane_reports),
    )
    for item in lane_reports:
        if item.get("passed") is False:
            errors.append(f"{item.get('lane')}: {item.get('error') or 'probe failed'}")

    return {
        "schema_version": 1,
        "kind": "local_provider_probe",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "repo_root": str(repo_root),
        "passed": not errors,
        "errors": errors,
        "warnings": [],
        "provider_execution_performed": any(item.get("provider_execution_performed") for item in lane_reports),
        "lane_reports": lane_reports,
        "provider_result_report": provider_report,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", default="output/validation/local_provider_probe.json")
    parser.add_argument("--model", help="Preferred Ollama model.")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--run-ollama", action="store_true")
    parser.add_argument("--run-npu", action="store_true")
    args = parser.parse_args()

    if not args.run_ollama and not args.run_npu:
        parser.error("At least one explicit probe flag is required: --run-ollama or --run-npu")

    repo_root = Path(args.repo_root).resolve()
    report = build_report(repo_root, args)
    output = Path(args.output)
    if not output.is_absolute():
        output = repo_root / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "output": str(output), "provider_execution_performed": report["provider_execution_performed"]}, indent=2))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
