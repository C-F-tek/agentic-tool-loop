#!/usr/bin/env python3
"""Smart AI gatekeeper.

Reads AI artifacts and reports, then decides whether the current output should be
promoted, repaired, or blocked. When repair is needed it writes a targeted repair
packet for the central AI instead of asking it to regenerate the whole context.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BLOCKING_PATTERNS = {
    "ShaderNodeTexMusgrave": "Blender 5.x target does not expose this node in project failures.",
    "TODO": "Generated artifact still contains TODO placeholders.",
    "placeholder": "Generated artifact still references placeholder content.",
}
SCRIPT_REQUIRED_PATTERNS = ["import bpy", "keyframe_insert"]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception as exc:
        return {"read_error": str(exc), "path": str(path)}


def read_text(path: Path, limit: int = 240000) -> str:
    if not path.exists() or not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")[:limit]


def file_meta(path: Path) -> dict[str, Any]:
    item: dict[str, Any] = {"path": str(path), "exists": path.exists()}
    if path.exists() and path.is_file():
        st = path.stat()
        item.update({"size_bytes": st.st_size, "modified_at": datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat()})
    return item


def scan_artifact(path: Path) -> dict[str, Any]:
    text = read_text(path)
    lowered = text.lower()
    warnings: list[str] = []
    blockers: list[str] = []
    positives: list[str] = []
    for pattern, reason in BLOCKING_PATTERNS.items():
        if pattern.lower() in lowered:
            blockers.append(f"blocked_pattern:{pattern}: {reason}")
    if path.suffix.lower() == ".py" or "scene_script" in path.name:
        for pattern in SCRIPT_REQUIRED_PATTERNS:
            if pattern in text:
                positives.append(f"script_required_pattern_present:{pattern}")
            else:
                warnings.append(f"script_required_pattern_missing:{pattern}")
        if len(text) < 8000:
            warnings.append("script_size_low: generated scene script may be fallback-like")
    if "analysis_blender_keyframes" in lowered or "keyframe" in lowered:
        positives.append("keyframe_context_present")
    else:
        warnings.append("keyframe_context_missing")
    return {"file": file_meta(path), "warnings": warnings, "blockers": blockers, "positives": positives}


def collect_report_issues(report: Any, label: str) -> tuple[list[str], list[str], list[str]]:
    warnings: list[str] = []
    blockers: list[str] = []
    positives: list[str] = []
    if not isinstance(report, dict):
        warnings.append(f"{label}: report missing or unreadable")
        return warnings, blockers, positives
    if report.get("passed") is False:
        warnings.append(f"{label}: passed=false")
    for key in ("blocking_errors", "errors"):
        values = report.get(key)
        if isinstance(values, list):
            blockers.extend(f"{label}:{item}" for item in values)
    values = report.get("warnings")
    if isinstance(values, list):
        warnings.extend(f"{label}:{item}" for item in values)
    values = report.get("positives")
    if isinstance(values, list):
        positives.extend(f"{label}:{item}" for item in values)
    reviews = report.get("reviews")
    if isinstance(reviews, list):
        for review in reviews:
            if not isinstance(review, dict):
                continue
            if review.get("passed") is False:
                warnings.append(f"{label}:review_failed:{review.get('path')}")
            for item in review.get("warnings") or []:
                warnings.append(f"{label}:{review.get('path')}:{item}")
            for item in review.get("positives") or []:
                positives.append(f"{label}:{review.get('path')}:{item}")
    return warnings, blockers, positives


def find_candidate_artifacts(artifact_dir: Path) -> list[Path]:
    names = [
        "ai_scene_brief.json",
        "ai_validation_report.json",
        "npu_guardrail_report.json",
        "npu_artifact_review.json",
        "ai_mapping_candidates.json",
        "track_summary.json",
        "smart_repair_packet.json",
    ]
    results = [artifact_dir / name for name in names if (artifact_dir / name).exists()]
    smart = artifact_dir / "smart_context"
    if smart.exists():
        results.extend(sorted(smart.glob("*.json")))
    return results


def gatekeep(artifact_dir: Path, target_files: list[Path], max_repair_attempts: int, current_attempt: int) -> dict[str, Any]:
    validation = read_json(artifact_dir / "ai_validation_report.json")
    guardrail = read_json(artifact_dir / "npu_guardrail_report.json")
    npu_review = read_json(artifact_dir / "npu_artifact_review.json")
    warnings: list[str] = []
    blockers: list[str] = []
    positives: list[str] = []
    for label, report in [("validation", validation), ("npu_guardrail", guardrail), ("npu_review", npu_review)]:
        w, b, p = collect_report_issues(report, label)
        warnings.extend(w)
        blockers.extend(b)
        positives.extend(p)
    scans = [scan_artifact(path) for path in target_files if path.exists()]
    for scan in scans:
        warnings.extend(scan["warnings"])
        blockers.extend(scan["blockers"])
        positives.extend(scan["positives"])
    if blockers:
        decision = "repair" if current_attempt < max_repair_attempts else "block"
    elif len(warnings) >= 8:
        decision = "repair" if current_attempt < max_repair_attempts else "promote_with_warnings"
    else:
        decision = "promote"
    return {
        "schema_version": 1,
        "kind": "smart_ai_gatekeeper_decision",
        "generated_at": now_iso(),
        "artifact_dir": str(artifact_dir),
        "decision": decision,
        "current_attempt": current_attempt,
        "max_repair_attempts": max_repair_attempts,
        "summary": {"warning_count": len(warnings), "blocker_count": len(blockers), "positive_count": len(positives), "scanned_files": len(scans)},
        "warnings": warnings[:140],
        "blockers": blockers[:100],
        "positives": positives[:140],
        "scans": scans,
    }


def build_repair_packet(decision: dict[str, Any], artifact_dir: Path, context_packet: Path | None) -> dict[str, Any]:
    context = read_json(context_packet) if context_packet else None
    selected_capsules = []
    if isinstance(context, dict):
        for capsule in context.get("selected_capsules") or []:
            if isinstance(capsule, dict):
                selected_capsules.append({"capsule_id": capsule.get("capsule_id"), "path": capsule.get("path"), "title": capsule.get("title"), "summary": capsule.get("summary"), "keywords": capsule.get("keywords")})
    return {
        "schema_version": 1,
        "kind": "smart_ai_repair_packet",
        "generated_at": now_iso(),
        "artifact_dir": str(artifact_dir),
        "decision": decision.get("decision"),
        "repair_goal": "Repair only failing artifact fields and keep valid context untouched.",
        "blockers": decision.get("blockers", []),
        "warnings": decision.get("warnings", []),
        "selected_context_capsules": selected_capsules[:30],
        "instructions_for_central_ai": [
            "Do not regenerate the whole project context.",
            "Use selected capsule ids and source paths to repair only failing fields.",
            "Preserve full Blender keyframe usage and Blender 5.x compatibility.",
            "Avoid blocked patterns reported by validation and guardrail reports.",
            "Return structured JSON with changed fields, rationale and validation expectations.",
        ],
    }


def write_markdown(decision: dict[str, Any], path: Path) -> None:
    lines = ["# Smart AI Gatekeeper Decision", "", f"Generated: `{decision.get('generated_at')}`", f"Decision: `{decision.get('decision')}`", f"Warnings: `{decision.get('summary', {}).get('warning_count')}`", f"Blockers: `{decision.get('summary', {}).get('blocker_count')}`", "", "## Blockers"]
    for item in decision.get("blockers", [])[:100]:
        lines.append(f"- {item}")
    lines.append("\n## Warnings")
    for item in decision.get("warnings", [])[:140]:
        lines.append(f"- {item}")
    lines.append("\n## Positives")
    for item in decision.get("positives", [])[:100]:
        lines.append(f"- {item}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--artifact-dir", default="output/ai_pipeline")
    ap.add_argument("--target-file", action="append", default=[])
    ap.add_argument("--context-packet")
    ap.add_argument("--output", default="output/ai_pipeline/smart_gatekeeper_decision.json")
    ap.add_argument("--repair-output", default="output/ai_pipeline/smart_repair_packet.json")
    ap.add_argument("--max-repair-attempts", type=int, default=2)
    ap.add_argument("--current-attempt", type=int, default=0)
    args = ap.parse_args()
    artifact_dir = Path(args.artifact_dir).resolve()
    targets = [Path(item).resolve() for item in args.target_file]
    if not targets:
        targets = find_candidate_artifacts(artifact_dir)
    decision = gatekeep(artifact_dir, targets, args.max_repair_attempts, args.current_attempt)
    out = Path(args.output).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(decision, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_markdown(decision, out.with_suffix(".md"))
    if decision["decision"] in {"repair", "block"}:
        repair_packet = build_repair_packet(decision, artifact_dir, Path(args.context_packet).resolve() if args.context_packet else None)
        repair_out = Path(args.repair_output).resolve()
        repair_out.write_text(json.dumps(repair_packet, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(decision, indent=2, ensure_ascii=False))
    return 0 if decision["decision"] in {"promote", "promote_with_warnings"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
