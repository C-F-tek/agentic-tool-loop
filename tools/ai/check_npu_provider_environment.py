#!/usr/bin/env python3
"""Check the dedicated OpenVINO/NPU Python environment.

This is a read-only agnostic provider preflight. It verifies that the configured
NPU Python can import OpenVINO and OpenVINO GenAI and can see the NPU device.
It does not run a model, apply patches, write SQLite, or act as advisory lane.

Naming is intentional:
- Python import module: openvino_genai
- PyPI package name: openvino-genai
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from Tools.npu.npu_runtime import DEFAULT_NPU_PYTHON
except ImportError:
    DEFAULT_NPU_PYTHON = Path(os.environ.get("SPAZIOTEMPO_NPU_PYTHON", Path.home() / "blender" / "venvs" / "blender-npu-ai" / "Scripts" / "python.exe"))

DEFAULT_OUTPUT = "output/validation/npu_provider_environment.json"
DEFAULT_MARKDOWN = "output/validation/npu_provider_environment.md"


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def resolve_path(repo_root: Path, value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = repo_root / path
    return path.resolve()


def run_command(command: list[str], timeout_seconds: int) -> tuple[int, str, str, str]:
    try:
        completed = subprocess.run(command, text=True, capture_output=True, timeout=timeout_seconds, check=False)
        return completed.returncode, completed.stdout[-12000:], completed.stderr[-12000:], ""
    except Exception as exc:  # noqa: BLE001 - diagnostic report only.
        return 1, "", "", f"{type(exc).__name__}: {exc}"


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = Path(args.repo_root).resolve()
    npu_python = Path(args.npu_python or os.environ.get("SPAZIOTEMPO_NPU_PYTHON", str(DEFAULT_NPU_PYTHON))).expanduser()
    code = """
import json
import sys
result = {"python": sys.executable}
try:
    import openvino as ov
    result["openvino_import"] = True
    result["available_devices"] = ov.Core().available_devices
    result["npu_available"] = "NPU" in result["available_devices"]
except Exception as exc:
    result["openvino_import"] = False
    result["openvino_error"] = f"{type(exc).__name__}: {exc}"
try:
    import openvino_genai
    result["openvino_genai_import"] = True
except Exception as exc:
    result["openvino_genai_import"] = False
    result["openvino_genai_error"] = f"{type(exc).__name__}: {exc}"
print(json.dumps(result))
"""
    warnings: list[str] = []
    errors: list[str] = []
    stdout = ""
    stderr = ""
    error = ""
    parsed: dict[str, Any] = {}
    if not npu_python.exists():
        errors.append(f"NPU Python not found: {npu_python}")
        returncode = 1
    else:
        returncode, stdout, stderr, error = run_command([str(npu_python), "-c", code], args.timeout_seconds)
        if error:
            errors.append(error)
        try:
            parsed = json.loads(stdout.strip().splitlines()[-1]) if stdout.strip() else {}
        except Exception as exc:  # noqa: BLE001
            errors.append(f"unable to parse NPU Python probe JSON: {type(exc).__name__}: {exc}")
    openvino_ok = bool(parsed.get("openvino_import"))
    genai_ok = bool(parsed.get("openvino_genai_import"))
    npu_available = bool(parsed.get("npu_available"))
    if npu_python.exists() and not openvino_ok:
        errors.append(str(parsed.get("openvino_error") or "openvino import failed"))
    if npu_python.exists() and not genai_ok:
        errors.append(str(parsed.get("openvino_genai_error") or "openvino_genai import failed; install PyPI package openvino-genai"))
    if npu_python.exists() and openvino_ok and not npu_available:
        warnings.append("OpenVINO imported but NPU was not listed in available devices")
    return {
        "schema_version": 1,
        "kind": "npu_provider_environment",
        "generated_at": now_iso(),
        "repo_root": str(repo_root),
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": False,
        "apply_mode": "report_only_read_only_provider_preflight",
        "npu_python": str(npu_python),
        "npu_python_exists": npu_python.exists(),
        "returncode": returncode,
        "stdout_tail": stdout,
        "stderr_tail": stderr,
        "probe": parsed,
        "checks": {
            "openvino_import": openvino_ok,
            "openvino_genai_import": genai_ok,
            "openvino_genai_pip_package": "openvino-genai",
            "npu_available": npu_available,
        },
        "decision": {
            "npu_ready_for_auditor": openvino_ok and genai_ok and npu_available,
            "gpu_review_should_be_blocked": False,
            "npu_primary_advisory": False,
        },
        "guardrails": {
            "read_only": True,
            "no_model_execution": True,
            "provider_execution_performed": False,
            "patch_application_performed": False,
            "real_github_pr_created": False,
            "sqlite_write_performed": False,
            "persistent_memory_write_performed": False,
        },
    }


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def render_markdown(report: dict[str, Any]) -> str:
    lines = ["# NPU Provider Environment", ""]
    for key in ["passed", "npu_python", "npu_python_exists"]:
        lines.append(f"- `{key}`: `{report.get(key)}`")
    for key, value in report.get("checks", {}).items():
        lines.append(f"- `{key}`: `{value}`")
    if report.get("errors"):
        lines.append("\n## Errors")
        for item in report["errors"]:
            lines.append(f"- {item}")
    if report.get("warnings"):
        lines.append("\n## Warnings")
        for item in report["warnings"]:
            lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--npu-python", default=None)
    parser.add_argument("--timeout-seconds", type=int, default=60)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--markdown-output", default=DEFAULT_MARKDOWN)
    args = parser.parse_args()
    repo_root = Path(args.repo_root).resolve()
    report = build_report(args)
    output = resolve_path(repo_root, args.output)
    markdown = resolve_path(repo_root, args.markdown_output)
    write_json(output, report)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    markdown.write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps({
        "passed": report["passed"],
        "output": str(output),
        "markdown": str(markdown),
        "npu_ready_for_auditor": report["decision"]["npu_ready_for_auditor"],
        "provider_execution_performed": False,
        "patch_application_performed": False,
    }, indent=2, ensure_ascii=False))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
