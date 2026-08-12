#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def resolve(repo_root: Path, value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = repo_root / path
    return path.resolve()


def rel(repo_root: Path, path: Path) -> str:
    try:
        return path.resolve(strict=False).relative_to(repo_root.resolve(strict=False)).as_posix()
    except ValueError:
        return str(path)


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def summarize_source(repo_root: Path, path: Path) -> dict[str, Any]:
    data = load_json(path)
    return {
        "path": rel(repo_root, path),
        "exists": path.exists(),
        "kind": data.get("kind") if data else None,
        "passed": data.get("passed") if data else None,
        "classifications": data.get("classifications", []) if data else [],
        "errors": data.get("errors", []) if data else [],
        "warnings": data.get("warnings", []) if data else [],
    }


def tasks_from_sources(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tasks = [
        {
            "id": "gpu0_companion_provider_warning_triage",
            "role": "companion_worker",
            "objective": "Classify provider/Ollama warnings before the primary planner treats the run as green.",
            "requires_semantic_model": False,
        },
        {
            "id": "gpu0_companion_npu_audit_precompute",
            "role": "companion_worker",
            "objective": "Precompute compact evidence signals that can be attached to NPU audit checkpoints.",
            "requires_semantic_model": False,
        },
        {
            "id": "gpu0_companion_patch_plan_evidence_check",
            "role": "companion_worker",
            "objective": "Score whether recommendations and patch plans reference available evidence.",
            "requires_semantic_model": False,
        },
    ]
    if any(src.get("passed") is False for src in sources):
        tasks.append(
            {
                "id": "gpu0_companion_failed_report_root_cause_scan",
                "role": "companion_worker",
                "objective": "Scan failed reports and produce root-cause hints for GPU1/Ollama.",
                "requires_semantic_model": False,
            }
        )
    return tasks


def tool_requests(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": f"gpu0_companion_tool_request_{idx:03d}",
            "tool": "build_runtime_tool_usage_telemetry",
            "reason": f"GPU0 companion task {task['id']} requests runtime telemetry context.",
            "args": {},
            "source": "gpu0_companion_worker",
            "task_id": task["id"],
        }
        for idx, task in enumerate(tasks, start=1)
    ]


def run_gpu0_workload(repo_root: Path, stamp: str, out_dir: Path, iterations: int, min_seconds: float) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    workload_json = out_dir / f"gpu0_companion_worker_workload_{stamp}.json"
    workload_md = out_dir / f"gpu0_companion_worker_workload_{stamp}.md"
    cmd = [
        sys.executable,
        "Tools/ai/build_openvino_gpu0_workload_report.py",
        "--repo-root",
        ".",
        "--output",
        str(workload_json),
        "--markdown-output",
        str(workload_md),
        "--iterations",
        str(iterations),
        "--min-seconds",
        str(min_seconds),
        "--role",
        "companion_worker",
        "--production-support",
    ]
    p = subprocess.run(cmd, cwd=repo_root, text=True, capture_output=True, check=False, env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    return load_json(workload_json), {
        "command": cmd,
        "returncode": p.returncode,
        "stdout_tail": p.stdout[-4000:],
        "stderr_tail": p.stderr[-4000:],
        "workload_json": rel(repo_root, workload_json),
        "workload_markdown": rel(repo_root, workload_md),
        "workload_exists": workload_json.exists(),
    }


def render_md(report: dict[str, Any]) -> str:
    lines = [
        "# GPU0 Companion Worker Lane",
        "",
        f"- Passed: `{report['passed']}`",
        f"- Production role: `{report['production_role']}`",
        f"- Companion task count: `{report['companion_task_count']}`",
        f"- Tool request count: `{report['tool_request_count']}`",
        f"- GPU0 workload passed: `{report['gpu0_workload_passed']}`",
        f"- Semantic execution mode: `{report['semantic_execution_mode']}`",
        "",
        "## Tasks",
    ]
    lines += [f"- `{task['id']}`: {task['objective']}" for task in report["companion_tasks"]]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--stamp", required=True)
    parser.add_argument("--source-report", action="append", default=[])
    parser.add_argument("--output", required=True)
    parser.add_argument("--markdown-output", required=True)
    parser.add_argument("--tool-requests-output", required=True)
    parser.add_argument("--iterations", type=int, default=64)
    parser.add_argument("--min-seconds", type=float, default=2.0)
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    output = resolve(repo_root, args.output)
    markdown = resolve(repo_root, args.markdown_output)
    tool_req_out = resolve(repo_root, args.tool_requests_output)
    output.parent.mkdir(parents=True, exist_ok=True)

    sources = [summarize_source(repo_root, resolve(repo_root, item)) for item in args.source_report]
    companion_tasks = tasks_from_sources(sources)
    requests = tool_requests(companion_tasks)
    workload, workload_meta = run_gpu0_workload(repo_root, args.stamp, output.parent, args.iterations, args.min_seconds)

    model_dir = os.environ.get("IA_CARMINE_GPU0_COMPANION_MODEL_DIR", "").strip()
    warnings: list[str] = []
    errors: list[str] = []
    classifications: list[str] = []
    if workload is None:
        classifications.append("gpu0_companion_workload_missing")
        errors.append("GPU0 companion workload report missing or invalid")
    elif workload.get("passed") is not True:
        classifications.append("gpu0_companion_workload_failed")
        errors.append("GPU0 companion workload failed")
    if not model_dir:
        warnings.append("IA_CARMINE_GPU0_COMPANION_MODEL_DIR not set; semantic LLM subtasks unavailable, numeric/tool companion active.")

    report = {
        "schema_version": 1,
        "kind": "gpu0_companion_worker_lane",
        "generated_at": now_iso(),
        "stamp": args.stamp,
        "repo_root": str(repo_root),
        "passed": not errors,
        "production_role": "companion_worker",
        "production_support": True,
        "provider_execution_performed": bool(workload and workload.get("provider_execution_performed") is True),
        "semantic_execution_mode": "model_configured_report_only" if model_dir else "model_unconfigured_numeric_tool_companion",
        "gpu0_model_dir_configured": bool(model_dir),
        "gpu0_model_dir": model_dir,
        "companion_task_count": len(companion_tasks),
        "tool_request_count": len(requests),
        "companion_tasks": companion_tasks,
        "tool_requests_output": rel(repo_root, tool_req_out),
        "source_reports": sources,
        "gpu0_workload": workload,
        "gpu0_workload_meta": workload_meta,
        "gpu0_workload_passed": bool(workload and workload.get("passed") is True),
        "classifications": classifications,
        "errors": errors,
        "warnings": warnings,
        "guardrails": {
            "report_only": True,
            "tool_execution_delegated_to_runtime_broker": True,
            "provider_model_execution_requires_explicit_model_dir": True,
            "patch_application_performed": False,
            "source_writes_performed": False,
        },
    }
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    markdown.write_text(render_md(report), encoding="utf-8")
    tool_req_out.write_text(json.dumps({"schema_version": 1, "kind": "gpu0_companion_tool_requests", "stamp": args.stamp, "tool_requests": requests}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "output": str(output), "markdown": str(markdown), "tool_requests": str(tool_req_out), "companion_task_count": len(companion_tasks)}, indent=2, ensure_ascii=False))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
