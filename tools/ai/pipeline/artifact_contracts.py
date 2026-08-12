"""Artifact contracts and path planning for the AI artifact pipeline."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any


EXPECTED_WAVE_REVIEW_ARTIFACTS = ["wave_entrypoint_review.json"]
EXPECTED_MUSIC_ARTIFACTS = [
    "track_summary.json",
    "music_segments.json",
    "audio_event_map.json",
    "ai_scene_brief.json",
    "ai_resource_budget.json",
]
EXPECTED_CHUNK_ARTIFACTS = [
    "indexAI/code_chunks/semantic_code_chunks.json",
    "indexAI/code_chunks/semantic_code_chunks_manifest.json",
]
EXPECTED_SMART_CONTEXT_ARTIFACTS = [
    "smart_context/{track_slug}_smart_context_packet.json",
    "smart_context/{track_slug}_smart_context_manifest.json",
    "smart_context/{track_slug}_smart_context_packet.md",
]


def slugify(value: str) -> str:
    """Return a stable lowercase slug suitable for artifact filenames."""
    value = re.sub(r"[^a-z0-9]+", "_", value.strip().lower())
    return re.sub(r"_+", "_", value).strip("_") or "track"


def rel(path: Path, root: Path) -> str:
    """Return a readable repository-relative path when possible."""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


def file_meta(path: Path, root: Path) -> dict[str, Any]:
    """Return small metadata for an expected input/output file."""
    from datetime import datetime, timezone

    exists = path.exists()
    meta: dict[str, Any] = {"path": rel(path, root), "exists": exists}
    if exists and path.is_file():
        stat = path.stat()
        meta.update(
            {
                "size_bytes": stat.st_size,
                "modified_time": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
            }
        )
    return meta


def planned_outputs(repo: Path, out: Path, args: Any) -> list[dict[str, Any]]:
    """Return expected output metadata for the requested pipeline configuration."""
    outputs: list[Path] = []
    track_slug = slugify(args.track_stem)
    if args.review_wave_entrypoints:
        outputs += [out / item for item in EXPECTED_WAVE_REVIEW_ARTIFACTS]
    if args.build_chunks:
        outputs += [repo / item for item in EXPECTED_CHUNK_ARTIFACTS]
    if args.build_music_summary:
        outputs += [out / item for item in EXPECTED_MUSIC_ARTIFACTS]
    if args.smart_context:
        outputs += [out / item.format(track_slug=track_slug) for item in EXPECTED_SMART_CONTEXT_ARTIFACTS]
    if args.use_npu:
        outputs.append(out / "npu_artifact_review.json")
    if args.npu_guardrail:
        outputs += [
            out / "npu_guardrail_report.json",
            out / "npu_guardrail_report.md",
            out / "npu_guardrail_preflight.json",
            out / "npu_guardrail_action_queue.json",
        ]
    if args.gpu_command:
        outputs.append(out / "gpu_planner_output.json")
    if args.validate:
        outputs.append(out / "ai_validation_report.json")
    if not args.dry_run:
        outputs.append(out / "ai_pipeline_run_report.json")
    return [file_meta(path, repo) for path in outputs]
