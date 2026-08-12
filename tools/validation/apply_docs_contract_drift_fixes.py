#!/usr/bin/env python3
"""Apply explicit docs-only fixes for docs contract drift.

This tool is intentionally narrow and idempotent. By default it runs in dry-run
mode and reports what it would change. With ``--apply`` it appends or inserts
small Markdown contract blocks that make the quality-gate docs discoverable.

It does not execute providers, apply code patches, run Blender, read ignored
runtime outputs or edit generated indexes.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from report_utils import resolve_output_path, write_json_report
except ImportError:
    from Tools.validation.report_utils import resolve_output_path, write_json_report  # type: ignore


REPORT_KIND = "docs_contract_drift_fix_plan"

README_BLOCK = """
## AI workload report quality gate

The AI workload report quality gate validates already-generated AI workload
reports before packet/proposal builders use them as advisory context.

Canonical contract:

```text
docs/AI_WORKLOAD_REPORT_QUALITY_GATE.md
```

Validator:

```powershell
python ./Tools/validation/check_ai_workload_report_quality.py --repo-root . --output ./output/validation/ai_workload_report_quality.json
```

Core report kind and policy:

```text
ai_workload_report_quality
usable_text_lanes_only_for_advisory_context
```

The validator is report-only and must keep:

```text
provider_execution_performed=false
source_writes_performed=false
```

NPU review metadata can be emitted without provider loading:

```powershell
python ./Tools/npu/run_npu_review.py --metadata-only --metadata-out ./output/validation/npu_review_metadata.json
```

The `npu_review_metadata` sidecar records advisory role and quality-gate status.
Metadata-only mode must keep provider execution disabled.
""".strip()

JSON_SCHEMA_BLOCK = """
### AI workload report quality

```text
File pattern:
output/validation/ai_workload_report_quality.json
Producer:
Tools/validation/check_ai_workload_report_quality.py
Consumer:
Tools/ai/workload_quality.py
Tools/ai/build_workload_quality_lane_routing.py
Tools/ai/suggest_repository_updates.py
Tools/ai/build_repository_change_proposals.py
Tools/ai/build_github_evidence_bundle.py
Required fields:
schema_version, kind, repo_root, passed, errors, warnings, provider_execution_performed, source_writes_performed, policy, mode, usable_lanes, unusable_lanes, decision, checks
Required kind:
ai_workload_report_quality
Required policy:
usable_text_lanes_only_for_advisory_context
Provider semantics:
This report is built from already-generated workload reports and must keep provider_execution_performed=false.
Notes:
Each checks.results entry exposes path, lane, provider, compute_lane, exists, usable, classification, advisory_use, provider_execution_performed, errors, warnings and metrics.
Ollama/GPU/CUDA can be primary advisory only when classified usable_text.
NPU/OpenVINO reports classified unusable_output are excluded from advisory context.
```

### NPU review metadata

```text
File pattern:
output/validation/npu_review_metadata.json
Producer:
Tools/npu/run_npu_review.py --metadata-out
Consumer:
validation report contract checks, workload-gate reviewers and local AI handoffs.
Required fields:
schema_version, kind, repo_root, passed, errors, warnings, engine, provider, device, metadata_only, provider_execution_performed, generated_output_written, source_writes_performed, patch_application_performed, advisory_role, quality_gate_required_before_advisory_use
Required kind:
npu_review_metadata
Provider semantics:
metadata_only=true means no provider was loaded, no generated review text was written and provider_execution_performed=false.
Notes:
A metadata sidecar does not make NPU advisory. It records that quality_gate_required_before_advisory_use is true.
```
""".strip()

CORE_ACTIVATION_BLOCK = """
## AI workload report quality gate

The local AI core/tool activation lane should use the AI workload report quality gate after provider/probe reports exist and before generated workload reports influence advisory packets.

Validator:

```powershell
python ./Tools/validation/check_ai_workload_report_quality.py --repo-root . --output ./output/validation/ai_workload_report_quality.json
```

Expected routing semantics:

```text
Ollama/GPU usable_text -> primary advisory context
NPU/OpenVINO unusable_output -> excluded from advisory context
```

The quality gate remains report-only. It must not execute providers, promote NPU to advisory, introduce OpenVINO GPU as primary lane or apply patches.
""".strip()

QUALITY_DOC_APPEND = """
## Compatibility alias

Some local reports and drift checks may refer to the promotion gate as:

```text
quality_report_required_before_advisory_use
```

This is equivalent to the sidecar field:

```text
quality_gate_required_before_advisory_use
```

Both names mean that workload report quality must be checked before any generated workload text is trusted as advisory context.
""".strip()


@dataclass(frozen=True)
class PatchSpec:
    path: str
    marker: str
    block: str
    anchor: str | None = None
    insert_before_anchor: bool = True


def specs() -> tuple[PatchSpec, ...]:
    return (
        PatchSpec(
            path="Tools/validation/README.md",
            marker="## AI workload report quality gate",
            block=README_BLOCK,
            anchor="## Tool map",
            insert_before_anchor=True,
        ),
        PatchSpec(
            path="docs/JSON_SCHEMAS.md",
            marker="### AI workload report quality",
            block=JSON_SCHEMA_BLOCK,
            anchor="### AI workload quality lane routing",
            insert_before_anchor=True,
        ),
        PatchSpec(
            path="docs/LOCAL_AI_CORE_TOOL_ACTIVATION.md",
            marker="## AI workload report quality gate",
            block=CORE_ACTIVATION_BLOCK,
            anchor="## Expected outputs",
            insert_before_anchor=True,
        ),
        PatchSpec(
            path="docs/AI_WORKLOAD_REPORT_QUALITY_GATE.md",
            marker="quality_report_required_before_advisory_use",
            block=QUALITY_DOC_APPEND,
            anchor="## Guardrails",
            insert_before_anchor=True,
        ),
    )


def normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def insert_block(text: str, spec: PatchSpec) -> tuple[str, bool, str]:
    if spec.marker in text:
        return text, False, "marker already present"

    block = "\n\n" + spec.block.strip() + "\n"
    if spec.anchor and spec.anchor in text:
        index = text.index(spec.anchor)
        if spec.insert_before_anchor:
            return text[:index].rstrip() + block + "\n" + text[index:].lstrip(), True, f"inserted before {spec.anchor}"
        end = index + len(spec.anchor)
        return text[:end].rstrip() + block + "\n" + text[end:].lstrip(), True, f"inserted after {spec.anchor}"

    return text.rstrip() + block, True, "appended at end"


def apply_one(repo_root: Path, spec: PatchSpec, *, apply: bool) -> dict[str, Any]:
    path = repo_root / spec.path
    if not path.exists():
        return {
            "path": spec.path,
            "exists": False,
            "changed": False,
            "applied": False,
            "reason": "missing file",
            "errors": ["file is missing"],
            "warnings": [],
        }

    original = normalize_newlines(path.read_text(encoding="utf-8-sig"))
    updated, changed, reason = insert_block(original, spec)
    if apply and changed:
        path.write_text(updated, encoding="utf-8", newline="\n")

    return {
        "path": spec.path,
        "exists": True,
        "changed": changed,
        "applied": bool(apply and changed),
        "reason": reason,
        "marker": spec.marker,
        "anchor": spec.anchor,
        "errors": [],
        "warnings": [],
    }


def build_report(repo_root: Path, *, apply: bool) -> dict[str, Any]:
    results = [apply_one(repo_root, spec, apply=apply) for spec in specs()]
    errors = [
        f"{item['path']}: {error}"
        for item in results
        for error in item.get("errors", [])
    ]
    warnings = [
        f"{item['path']}: {warning}"
        for item in results
        for warning in item.get("warnings", [])
    ]
    return {
        "schema_version": 1,
        "kind": REPORT_KIND,
        "repo_root": str(repo_root),
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "apply": apply,
        "apply_mode": "explicit_docs_only" if apply else "dry_run_report_only",
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": bool(apply and any(item["applied"] for item in results)),
        "changed_count": sum(1 for item in results if item["changed"]),
        "applied_count": sum(1 for item in results if item["applied"]),
        "results": results,
        "guardrails": {
            "docs_only": True,
            "provider_execution_performed": False,
            "blender_runtime_touched": False,
            "npu_promoted_to_advisory": False,
            "openvino_gpu_primary_lane": False,
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = ["# Docs Contract Drift Fix Plan", ""]
    lines.append(f"- Passed: `{report['passed']}`")
    lines.append(f"- Apply: `{report['apply']}`")
    lines.append(f"- Apply mode: `{report['apply_mode']}`")
    lines.append(f"- Changed count: `{report['changed_count']}`")
    lines.append(f"- Applied count: `{report['applied_count']}`")
    lines.append("")
    for item in report["results"]:
        lines.append(f"## `{item['path']}`")
        lines.append("")
        lines.append(f"- Changed: `{item['changed']}`")
        lines.append(f"- Applied: `{item['applied']}`")
        lines.append(f"- Reason: {item['reason']}")
        lines.append("")
    lines.append("## Guardrails")
    lines.append("")
    lines.append("This tool only edits Markdown contract documentation when --apply is explicitly passed.")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--apply", action="store_true", help="Actually write docs-only changes. Without this flag the tool is dry-run only.")
    parser.add_argument("--output", help="Optional JSON report path.")
    parser.add_argument("--markdown-output", help="Optional Markdown report path.")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    report = build_report(repo_root, apply=bool(args.apply))

    output = resolve_output_path(repo_root, args.output) if args.output else None
    text = write_json_report(report, output)
    print(text, end="")

    if args.markdown_output:
        markdown_output = resolve_output_path(repo_root, args.markdown_output)
        markdown_output.parent.mkdir(parents=True, exist_ok=True)
        markdown_output.write_text(render_markdown(report), encoding="utf-8")

    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
