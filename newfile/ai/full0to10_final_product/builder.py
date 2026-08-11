"""Build Full0To10 final tool product package."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from full0to10_accelerator_control.builder import build_accelerator_control
from full0to10_effective_use.builder import build_effective_use_optimization
from full0to10_provider_execution_bridge.builder import build_provider_execution_bridge
from full0to10_provider_governor.builder import build_provider_governor
from full0to10_provider_invocation_plan.builder import build_provider_invocation_plan
from full0to10_quality_gate.builder import build_quality_gate
from full0to10_track_inputs.builder import build_track_input_contract

from .artifacts import product_artifacts
from .constants import EVIDENCE_INDEX, PRODUCT_MANIFEST, PRODUCT_MARKDOWN, README_NAME, READINESS_JSON, SAFETY_FLAGS
from .evidence import build_evidence_index, output_record
from .paths import ensure_dir, repo_relative
from .readiness import build_readiness
from .render import render_product_markdown, render_readme


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def build_final_tool_product(
    repo_root: Path,
    output_dir: Path,
    request: str,
    no_external_probes: bool,
    timeout_seconds: int,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    output_dir = ensure_dir(output_dir)
    effective_dir = ensure_dir(output_dir / "effective_use")
    quality_dir = ensure_dir(output_dir / "quality_gate")
    accelerator_dir = ensure_dir(output_dir / "accelerator_control")
    governor_dir = ensure_dir(output_dir / "provider_governor")
    invocation_dir = ensure_dir(output_dir / "provider_invocation_plan")
    bridge_dir = ensure_dir(output_dir / "provider_execution_bridge")
    track_dir = ensure_dir(output_dir / "track_inputs")

    track_contract = build_track_input_contract(repo_root, track_dir, "current", False, 8)
    accelerator_control = build_accelerator_control(repo_root, accelerator_dir, request, no_external_probes, timeout_seconds)
    provider_governor = build_provider_governor(repo_root, governor_dir, request, False, False, no_external_probes, timeout_seconds)
    invocation_plan = build_provider_invocation_plan(repo_root, invocation_dir, request, False, False, no_external_probes, timeout_seconds)
    execution_bridge = build_provider_execution_bridge(repo_root, bridge_dir, request, False, False, no_external_probes, timeout_seconds)
    effective_summary = build_effective_use_optimization(repo_root, effective_dir, request, None, no_external_probes, timeout_seconds)

    quality_gate = build_quality_gate(repo_root, None)
    write_json(quality_dir / "full0to10_quality_gate.json", quality_gate)

    records = product_artifacts(effective_dir, quality_dir, accelerator_dir, governor_dir, invocation_dir, bridge_dir, track_dir, repo_root)
    evidence = build_evidence_index(repo_root, records)
    readiness = build_readiness(records, evidence)

    product_path = output_dir / PRODUCT_MARKDOWN
    evidence_path = output_dir / EVIDENCE_INDEX
    readiness_path = output_dir / READINESS_JSON
    manifest_path = output_dir / PRODUCT_MANIFEST
    readme_path = output_dir / README_NAME

    product_path.write_text(render_product_markdown(request, evidence, readiness), encoding="utf-8")
    write_json(evidence_path, evidence)
    write_json(readiness_path, readiness)

    outputs = {
        "product_markdown": repo_relative(product_path, repo_root),
        "evidence_index": repo_relative(evidence_path, repo_root),
        "readiness": repo_relative(readiness_path, repo_root),
        "manifest": repo_relative(manifest_path, repo_root),
        "readme": repo_relative(readme_path, repo_root),
        "track_input_contract": track_contract["outputs"].get("contract"),
        "provider_execution_bridge": execution_bridge["outputs"].get("bridge"),
    }

    manifest: dict[str, Any] = {
        "kind": "full0to10_final_tool_product_manifest",
        "passed": evidence["passed"] and readiness["passed"] and effective_summary["passed"] and execution_bridge["passed"],
        "request": request,
        "outputs": outputs,
        "evidence": evidence,
        "readiness": readiness,
        "track_input_contract": track_contract,
        "accelerator_control": accelerator_control,
        "provider_governor": provider_governor,
        "provider_invocation_plan": invocation_plan,
        "provider_execution_bridge": execution_bridge,
        "effective_use_summary": effective_summary,
        "quality_gate": quality_gate,
        "output_records": [
            output_record(product_path, repo_root, "product_markdown"),
            output_record(evidence_path, repo_root, "evidence_index"),
            output_record(readiness_path, repo_root, "readiness"),
        ],
        "errors": evidence["errors"] + readiness["blockers"],
        "warnings": readiness["warnings"] + track_contract["warnings"],
    }
    manifest.update(SAFETY_FLAGS)
    write_json(manifest_path, manifest)
    readme_path.write_text(render_readme(manifest), encoding="utf-8")
    return manifest
