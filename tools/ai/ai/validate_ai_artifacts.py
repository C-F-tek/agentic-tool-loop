#!/usr/bin/env python3
"""Validate AI pipeline artifacts without touching runtime packages."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REQUIRED = {
    "track_summary.json": ["schema_version", "source_analysis"],
    "music_segments.json": ["schema_version", "segments"],
    "audio_event_map.json": ["schema_version"],
    "ai_scene_brief.json": ["schema_version", "creative_intent", "technical_intent"],
    "ai_resource_budget.json": ["schema_version", "recommendations"],
    "ai_mapping_candidates.json": ["schema_version", "candidates"],
    "ai_selected_mapping.json": ["schema_version", "selected"],
}

LOCAL_PATH_ALLOWED_ARTIFACTS = {
    "track_summary.json",
    "music_segments.json",
    "audio_event_map.json",
    "ai_mapping_candidates.json",
    "ai_pipeline_dry_run_report.json",
    "ai_pipeline_run_report.json",
    "npu_artifact_review.json",
    "ai_validation_report.json",
}

CODELIKE_SUFFIXES = {".py", ".ps1", ".bat", ".cmd", ".sh"}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8", errors="replace"))


def load_patterns(capsules: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    blocked, warnings = [], []
    if capsules.exists():
        for path in sorted(capsules.glob("*.json")):
            try:
                data = load_json(path)
            except Exception:
                continue
            blocked += data.get("blocked_patterns", []) if isinstance(data, dict) else []
            warnings += data.get("warning_patterns", []) if isinstance(data, dict) else []
    return blocked, warnings


def is_guardrail_reference(path: Path, text: str, pattern: str) -> bool:
    """Return True when a blocked pattern appears as an instruction, not generated code."""
    if path.suffix in CODELIKE_SUFFIXES:
        return False
    lower = text.lower()
    pattern_lower = pattern.lower()
    guardrail_terms = ("avoid", "blocked", "guardrail", "do not use", "non usare", "vietato", "replacement", "preferred")
    return pattern_lower in lower and any(term in lower for term in guardrail_terms)


def should_ignore_local_path_warning(path: Path) -> bool:
    return path.name in LOCAL_PATH_ALLOWED_ARTIFACTS


def scan(path: Path, blocked, warn_patterns, errors, warnings, positives) -> None:
    text = path.read_text(encoding="utf-8", errors="replace")
    for item in blocked:
        pattern = item.get("pattern")
        if not pattern or pattern not in text:
            continue
        if is_guardrail_reference(path, text, pattern):
            positives.append(f"{path.name}: guardrail reference for `{pattern}` present.")
            continue
        errors.append(f"{path}: blocked pattern `{pattern}`: {item.get('reason', 'blocked')}")
    for item in warn_patterns:
        pattern = item.get("pattern")
        if not pattern or pattern not in text:
            continue
        if pattern.startswith("C:") and should_ignore_local_path_warning(path):
            positives.append(f"{path.name}: local path metadata accepted as pipeline context.")
            continue
        warnings.append(f"{path}: warning pattern `{pattern}`: {item.get('reason', 'warning')}")


def validate_semantics(path: Path, data: Any, errors: list[str], warnings: list[str], positives: list[str]) -> None:
    if not isinstance(data, dict):
        return
    if path.name == "track_summary.json":
        readiness = data.get("ai_readiness") or {}
        score = readiness.get("score")
        if isinstance(score, (int, float)):
            positives.append(f"track_summary ai_readiness score={score}")
            if score < 0.5:
                warnings.append("track_summary ai_readiness score is low; generated scene planning may need manual context.")
        else:
            warnings.append("track_summary missing ai_readiness score.")
        if not data.get("primary_series"):
            warnings.append("track_summary has no primary_series; peak mapping may be weak.")
    elif path.name == "music_segments.json":
        segments = data.get("segments") or []
        if not segments:
            warnings.append("music_segments has no segments.")
        for i, segment in enumerate(segments):
            if not isinstance(segment, dict):
                continue
            if "visual_directive" not in segment:
                warnings.append(f"music_segments segment {i} missing visual_directive.")
    elif path.name == "ai_mapping_candidates.json":
        candidates = data.get("candidates") or []
        if len(candidates) < 2:
            warnings.append("ai_mapping_candidates contains fewer than 2 candidates; creative selection is weak.")
        else:
            positives.append(f"ai_mapping_candidates candidate_count={len(candidates)}")
    elif path.name == "ai_scene_brief.json":
        if not data.get("recommended_visual_progression"):
            warnings.append("ai_scene_brief missing recommended_visual_progression.")
        constraints = data.get("constraints") or []
        if any("ShaderNodeTexMusgrave" in str(item) for item in constraints):
            positives.append("ai_scene_brief includes Blender 5.x ShaderNodeTexMusgrave guardrail.")
        else:
            warnings.append("ai_scene_brief does not mention Blender 5.x ShaderNodeTexMusgrave guardrail.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", default=".")
    ap.add_argument("--artifact-dir", default="output/ai_pipeline")
    ap.add_argument("--capsules-dir", default="indexAI/task_capsules")
    ap.add_argument("--package-dir")
    ap.add_argument("--output", default="output/ai_pipeline/ai_validation_report.json")
    ap.add_argument("--allow-errors", action="store_true")
    args = ap.parse_args()
    repo = Path(args.repo_root).resolve()
    artifact_dir = (repo / args.artifact_dir).resolve()
    errors: list[str] = []
    warnings: list[str] = []
    positives: list[str] = []
    checked: list[str] = []

    if artifact_dir.exists():
        for path in sorted(artifact_dir.glob("*.json")):
            checked.append(str(path))
            try:
                data = load_json(path)
            except Exception as exc:
                errors.append(f"Invalid JSON {path}: {exc}")
                continue
            for key in REQUIRED.get(path.name, []):
                if not isinstance(data, dict) or key not in data:
                    errors.append(f"{path.name} missing `{key}`")
            validate_semantics(path, data, errors, warnings, positives)
    else:
        warnings.append(f"Artifact directory not found: {artifact_dir}")

    assumptions = artifact_dir / "ai_assumptions.md"
    if artifact_dir.exists() and not assumptions.exists():
        warnings.append("ai_assumptions.md not found; downstream AI should receive explicit assumptions.")
    elif assumptions.exists():
        positives.append("ai_assumptions.md present.")

    blocked, warn_patterns = load_patterns((repo / args.capsules_dir).resolve())
    files = list(artifact_dir.rglob("*")) if artifact_dir.exists() else []
    if args.package_dir:
        pkg = (repo / args.package_dir).resolve()
        if not pkg.exists():
            errors.append(f"Package directory not found: {pkg}")
        else:
            if not (pkg / "README.md").exists():
                errors.append("Generated package missing README.md")
            files += list(pkg.rglob("*"))
    for path in files:
        if path.is_file() and path.suffix in {".py", ".md", ".json", ".ps1", ".bat", ".cmd", ".sh"}:
            scan(path, blocked, warn_patterns, errors, warnings, positives)

    score = max(0.0, round(1.0 - min(0.7, len(errors) * 0.2) - min(0.3, len(warnings) * 0.04), 4))
    report = {
        "schema_version": 3,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "passed": not errors,
        "score": score,
        "checked_files": checked,
        "blocking_errors": errors,
        "warnings": warnings,
        "positives": positives,
        "quality_summary": {
            "error_count": len(errors),
            "warning_count": len(warnings),
            "positive_count": len(positives),
        },
    }
    out = Path(args.output).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["passed"] or args.allow_errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
