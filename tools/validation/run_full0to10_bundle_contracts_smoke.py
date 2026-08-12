#!/usr/bin/env python3
"""Smoke test for the Full0To10 contract validator."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def write_json(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def build_smoke_bundle(work_dir: Path) -> Path:
    evidence = work_dir / "evidence"
    names = (
        "agent_review_full_toolbox_decision_loop_workflow.json",
        "full_toolbox_orchestrator.json",
        "full_toolbox_parallel_gpu.json",
        "gpu_npu_run_sync_full_toolbox.json",
        "repository_consistency_map_full_toolbox.json",
        "repository_consistency_map_smoke_full_toolbox.json",
        "agent_review_decision_loop.json",
        "deterministic_recommendations.json",
        "agent_review_patch_plan.json",
        "runtime_tool_usage_telemetry.json",
        "runtime_tool_capability_manifest.json",
        "full_toolbox_run_telemetry_summary.json",
        "semantic_chunk_manifest.json",
        "shared_toolbox_ai_to_ai_bundle.json",
    )
    for name in names:
        write_json(evidence / name, {"kind": name.removesuffix(".json"), "passed": True})

    bundle = {
        "kind": "shared_toolbox_ai_to_ai_bundle",
        "passed": True,
        "provider_execution_performed": True,
        "patch_application_performed": False,
        "source_writes_performed": False,
        "persistent_memory_write_performed": False,
        "sqlite_write_performed": False,
        "artifact_manifest": [{"path": item.as_posix()} for item in evidence.glob("*.json")],
        "memory": {
            "scratch": "output/ai_runtime_memory/operational_context.sqlite",
            "persistent": "indexAI/agent_memory/agent_memory.sqlite",
            "tool": "runtime_sqlite_memory",
        },
        "hardware": {
            "cpu": "validation csv repository_consistency",
            "gpu": "GPU Ollama primary planner advisory recommendation_count",
            "npu": "NPU OpenVINO sampled auditor npu_audit",
        },
    }
    bundle_path = work_dir / "full0to10_smoke_bundle.json"
    write_json(bundle_path, bundle)
    return bundle_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--work-dir", default="output/validation/full0to10_contracts_smoke")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    work_dir = (repo_root / args.work_dir).resolve()
    bundle = build_smoke_bundle(work_dir)
    output = work_dir / "full0to10_contract_validation.json"
    markdown = work_dir / "full0to10_contract_validation.md"

    cmd = [
        sys.executable,
        str(repo_root / "Tools/validation/check_full0to10_bundle_contracts.py"),
        "--repo-root",
        str(repo_root),
        "--bundle",
        str(bundle),
        "--evidence-dir",
        str(work_dir / "evidence"),
        "--output",
        str(output),
        "--markdown-output",
        str(markdown),
    ]
    proc = subprocess.run(cmd, cwd=repo_root, text=True, capture_output=True, check=False)
    if proc.stdout:
        print(proc.stdout)
    if proc.stderr:
        print(proc.stderr, file=sys.stderr)

    data = json.loads(output.read_text(encoding="utf-8"))
    print(json.dumps({"passed": data["passed"], "errors": data["errors"], "warnings": data["warnings"]}, indent=2))
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
