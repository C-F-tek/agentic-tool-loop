#!/usr/bin/env python3
# Smoke-test full toolbox deterministic chunking and telemetry invariants.
from __future__ import annotations

import argparse
import json
import py_compile
from datetime import datetime
from pathlib import Path

TARGETS = [
    "Tools/workflow/run_agent_review_full_toolbox_decision_loop.ps1",
    "Tools/ai/build_repository_consistency_map.py",
    "Tools/ai/build_runtime_tool_usage_telemetry.py",
    "Tools/ai/build_runtime_tool_capability_manifest.py",
]

def read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", default="output/validation/full_toolbox_deterministic_chunks_telemetry_smoke.json")
    parser.add_argument("--markdown-output", default="output/validation/full_toolbox_deterministic_chunks_telemetry_smoke.md")
    args = parser.parse_args()
    repo_root = Path(args.repo_root).resolve()
    errors: list[str] = []
    warnings: list[str] = []
    workflow = read(repo_root / TARGETS[0])
    repo_map = read(repo_root / TARGETS[1])
    telemetry = read(repo_root / TARGETS[2])
    capability = read(repo_root / TARGETS[3])
    if "cloud_semantic_deterministic" not in workflow:
        errors.append("workflow does not use deterministic semantic chunk basename")
    if '"--no-ollama"' not in workflow:
        errors.append("workflow does not pass --no-ollama to build_semantic_evidence_chunks.py")
    if '$EvidenceChunkBase = "full_toolbox_${Stamp}_cloud_semantic"' in workflow:
        errors.append("workflow still contains non-deterministic cloud_semantic basename assignment")
    if "is_generated_evidence_chunk_path" not in repo_map:
        errors.append("repository consistency map lacks generated evidence chunk exclusion helper")
    if "generated_evidence_chunk_dirs_excluded" not in repo_map:
        errors.append("repository consistency guardrail does not expose generated chunk exclusion")
    if "_cloud_semantic" not in repo_map:
        errors.append("repository consistency exclusion does not mention cloud_semantic chunks")
    if "extract_declared_runtime_tool_counters" not in telemetry:
        errors.append("runtime telemetry lacks declared runtime tool counter extraction")
    if "declared_not_executed_count" not in telemetry:
        errors.append("runtime telemetry lacks declared_not_executed_count")
    if "declared_runtime_tool_counters" not in telemetry:
        errors.append("runtime telemetry does not expose declared_runtime_tool_counters")
    if "tool_usage_summary" not in capability:
        errors.append("capability manifest does not expose tool_usage_summary")
    if "declared_runtime_tool_counters" not in capability:
        errors.append("capability manifest does not expose declared_runtime_tool_counters")
    compile_targets = [
        repo_root / "Tools/ai/build_repository_consistency_map.py",
        repo_root / "Tools/ai/build_runtime_tool_usage_telemetry.py",
        repo_root / "Tools/ai/build_runtime_tool_capability_manifest.py",
        repo_root / "Tools/validation/run_full_toolbox_deterministic_chunks_telemetry_smoke.py",
    ]
    for target in compile_targets:
        try:
            py_compile.compile(str(target), doraise=True)
        except py_compile.PyCompileError as exc:
            errors.append(f"py_compile failed for {target.relative_to(repo_root).as_posix()}: {exc.msg}")
    report = {
        "schema_version": 1,
        "kind": "full_toolbox_deterministic_chunks_telemetry_smoke",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "repo_root": str(repo_root),
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": False,
        "sqlite_write_performed": False,
        "persistent_memory_write_performed": False,
        "blender_runtime_execution_performed": False,
        "targets": TARGETS,
        "guardrails": {
            "report_only": True,
            "provider_execution_performed": False,
            "patch_application_performed": False,
            "sqlite_write_performed": False,
            "persistent_memory_write_performed": False,
            "blender_runtime_execution_performed": False,
        },
    }
    output = (repo_root / args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md = (repo_root / args.markdown_output).resolve()
    md.parent.mkdir(parents=True, exist_ok=True)
    md_lines = ["# Full Toolbox Deterministic Chunks / Telemetry Smoke", "", f"- Passed: `{report['passed']}`", "- Provider execution performed: `False`", "- Patch application performed: `False`", "- SQLite write performed: `False`", "", "## Errors", ""]
    md_lines.extend([f"- {error}" for error in errors] or ["- none"])
    md.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "output": str(output), "markdown_output": str(md), "errors": errors}, indent=2, ensure_ascii=False))
    return 0 if report["passed"] else 2

if __name__ == "__main__":
    raise SystemExit(main())
