#!/usr/bin/env python3
"""Summarize Full0To10 light evidence-only run for launcher promotion."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


SAFETY_FALSE_FIELDS = (
    "provider_execution_performed",
    "patch_application_performed",
    "blender_runtime_execution_performed",
    "ffmpeg_execution_performed",
)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def bool_field(data: dict[str, Any], name: str) -> bool:
    return bool(data.get(name))


def step_table(run: dict[str, Any]) -> list[dict[str, Any]]:
    steps = run.get("steps", [])
    return steps if isinstance(steps, list) else []


def build_summary(run: dict[str, Any], source: Path) -> dict[str, Any]:
    steps = step_table(run)
    failed = [step for step in steps if step.get("status") in {"failed", "missing_required"}]
    skipped = [step for step in steps if str(step.get("status", "")).startswith("skipped")]
    safety_ok = all(bool_field(run, field) is False for field in SAFETY_FALSE_FIELDS)
    passed = bool(run.get("passed")) and not failed and safety_ok

    report = {
        "kind": "full0to10_light_evidence_promotion",
        "source_report": str(source),
        "passed": passed,
        "promotable_to_unified_launcher": passed,
        "step_count": len(steps),
        "failed_count": len(failed),
        "skipped_count": len(skipped),
        "failed_steps": failed,
        "skipped_steps": skipped,
        "safety_ok": safety_ok,
        "provider_execution_performed": bool_field(run, "provider_execution_performed"),
        "patch_application_performed": bool_field(run, "patch_application_performed"),
        "blender_runtime_execution_performed": bool_field(run, "blender_runtime_execution_performed"),
        "ffmpeg_execution_performed": bool_field(run, "ffmpeg_execution_performed"),
        "recommended_launcher_flag": "-LightFull0To10",
        "recommended_default_flags": ["-NoExternalProbes", "-SkipProviderGeneration"],
        "next_action": "Promote wrapper profile into unified launcher only after this report is passed.",
    }
    return report


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Full0To10 light evidence promotion",
        "",
        f"- Passed: `{report['passed']}`",
        f"- Promotable: `{report['promotable_to_unified_launcher']}`",
        f"- Steps: `{report['step_count']}`",
        f"- Failed: `{report['failed_count']}`",
        f"- Skipped: `{report['skipped_count']}`",
        f"- Safety OK: `{report['safety_ok']}`",
        "",
        "## Failed steps",
        "",
    ]
    for step in report["failed_steps"] or ["None"]:
        lines.append(f"- `{step}`" if isinstance(step, str) else f"- `{step.get('name')}` status=`{step.get('status')}`")
    lines.extend(["", "## Next action", "", report["next_action"], ""])
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-report", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--markdown-output", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source = Path(args.run_report)
    report = build_summary(read_json(source), source)
    output = Path(args.output)
    md = Path(args.markdown_output)
    output.parent.mkdir(parents=True, exist_ok=True)
    md.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md.write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
