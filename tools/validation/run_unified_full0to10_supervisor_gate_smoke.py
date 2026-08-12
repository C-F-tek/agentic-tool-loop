#!/usr/bin/env python3
"""Smoke test for the unified Full0To10 supervisor gate wrapper."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def write_json(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def repo_relative(path: Path, repo_root: Path) -> str:
    return path.resolve().relative_to(repo_root.resolve()).as_posix()


def seed(work_dir: Path) -> Path:
    evidence = work_dir / "evidence"
    names = (
        "line_count.csv",
        "runtime_tool_usage_telemetry.json",
        "runtime_tool_capability_manifest.json",
        "full_toolbox_run_telemetry_summary.json",
        "full_toolbox_parallel_gpu.json",
        "full_toolbox_orchestrator.json",
        "gpu_npu_run_sync.json",
        "repository_consistency_map.json",
        "repository_consistency_smoke.json",
        "agent_review_decision_loop.json",
        "deterministic_recommendations.json",
        "agent_review_patch_plan.json",
        "semantic_chunk_manifest.json",
        "shared_toolbox_ai_to_ai_bundle.json",
    )
    for name in names:
        path = evidence / name
        if name.endswith(".json"):
            write_json(path, {"kind": name.removesuffix(".json"), "passed": True})
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("File,Lines\nexample.py,1\n", encoding="utf-8")

    bundle = {
        "kind": "shared_toolbox_ai_to_ai_bundle",
        "persistent_memory_write_performed": False,
        "sqlite_write_performed": False,
        "artifact_manifest": [{"path": item.as_posix()} for item in evidence.iterdir()],
        "memory": {
            "scratch": "output/ai_runtime_memory/operational_context.sqlite",
            "persistent": "indexAI/agent_memory/agent_memory.sqlite",
            "tool": "runtime_sqlite_memory",
        },
        "hardware": "CPU validation CSV GPU Ollama primary planner NPU OpenVINO sampled auditor",
    }
    bundle_path = work_dir / "full0to10_smoke_bundle.json"
    write_json(bundle_path, bundle)
    return bundle_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--work-dir", default="output/validation/unified_full0to10_supervisor_gate_smoke")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    work_dir = (repo_root / args.work_dir).resolve()
    bundle = seed(work_dir)

    cmd = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(repo_root / "Tools/workflow/run_unified_full0to10_with_contract_gate.ps1"),
        "-RepoRoot",
        str(repo_root),
        "-SkipLauncher",
        "-Bundle",
        repo_relative(bundle, repo_root),
        "-EvidenceDir",
        repo_relative(work_dir / "evidence", repo_root),
        "-GateOutputDir",
        repo_relative(work_dir / "gate", repo_root),
    ]

    proc = subprocess.run(cmd, cwd=repo_root, text=True, capture_output=True, check=False)
    if proc.stdout:
        print(proc.stdout)
    if proc.stderr:
        print(proc.stderr, file=sys.stderr)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
