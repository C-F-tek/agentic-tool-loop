#!/usr/bin/env python3
"""Smoke-check Scripting/shared/blender_compat.py.

Outside Blender this validator verifies import safety and reports the Blender
runtime portion as skipped. Inside Blender it creates a disposable material,
frame range and silent audio strip without rendering or touching package code.
"""
from __future__ import annotations

import argparse
import json
import sys
import wave
from pathlib import Path
from typing import Any


REQUIRED_FUNCTIONS = (
    "require_bpy",
    "get_scene",
    "ensure_sequence_editor",
    "clear_sequence_editor",
    "create_sound_strip",
    "safe_set_scene_sync_audio",
    "safe_create_noise_texture_node",
    "set_frame_range_from_seconds",
    "set_render_fps",
)


def import_blender_compat(repo_root: Path) -> Any:
    root = str(repo_root)
    if root not in sys.path:
        sys.path.insert(0, root)
    from Scripting.shared import blender_compat

    return blender_compat


def write_silent_wav(path: Path, sample_rate: int = 8000, duration_seconds: float = 0.1) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame_count = max(1, int(sample_rate * duration_seconds))
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(b"\x00\x00" * frame_count)


def run_smoke(repo_root: Path, require_blender: bool, output_dir: Path) -> dict[str, Any]:
    errors: list[str] = []
    checks: dict[str, Any] = {}
    compat = import_blender_compat(repo_root)
    missing = [name for name in REQUIRED_FUNCTIONS if not hasattr(compat, name)]
    if missing:
        errors.append(f"missing required functions: {', '.join(missing)}")
    checks["required_function_count"] = len(REQUIRED_FUNCTIONS)
    checks["missing_functions"] = missing

    try:
        bpy = compat.require_bpy()
    except RuntimeError as exc:
        checks["blender_runtime"] = "skipped_outside_blender"
        checks["runtime_skip_reason"] = str(exc)
        if require_blender:
            errors.append("Blender bpy runtime is required but unavailable")
        return {
            "schema_version": 1,
            "kind": "blender_shared_compat_smoke",
            "repo_root": str(repo_root),
            "passed": not errors,
            "skipped_blender_runtime": True,
            "errors": errors,
            "warnings": [],
            "checks": checks,
        }

    scene = bpy.context.scene
    checks["blender_runtime"] = "available"
    checks["blender_version"] = ".".join(str(part) for part in getattr(bpy.app, "version", ()))
    compat.set_render_fps(scene, 24)
    start, end = compat.set_frame_range_from_seconds(0.5, scene=scene, fps=24, frame_start=1)
    checks["frame_range"] = [start, end]
    if (start, end) != (1, 12):
        errors.append(f"unexpected frame range {(start, end)}")

    material = bpy.data.materials.new("agent_compat_smoke_material")
    material.use_nodes = True
    node = compat.safe_create_noise_texture_node(material.node_tree)
    checks["noise_node_type"] = getattr(node, "bl_idname", type(node).__name__)

    removed_before = compat.clear_sequence_editor(scene)
    audio_path = output_dir / "blender_shared_compat_smoke.wav"
    write_silent_wav(audio_path)
    strip = compat.create_sound_strip(audio_path, scene=scene, name="Agent Compat Smoke", channel=1, frame_start=1)
    checks["strip_created"] = strip is not None
    checks["strip_name"] = getattr(strip, "name", None)
    removed_after = compat.clear_sequence_editor(scene)
    checks["removed_strips_before"] = removed_before
    checks["removed_strips_after"] = removed_after
    checks["audio_sync_property_set"] = compat.safe_set_scene_sync_audio(scene, True)

    try:
        bpy.data.materials.remove(material)
    except Exception:
        pass

    if not checks["strip_created"]:
        errors.append("sound strip was not created")

    return {
        "schema_version": 1,
        "kind": "blender_shared_compat_smoke",
        "repo_root": str(repo_root),
        "passed": not errors,
        "skipped_blender_runtime": False,
        "errors": errors,
        "warnings": [],
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", help="Optional JSON report path.")
    parser.add_argument("--output-dir", default="output/validation")
    parser.add_argument("--require-blender", action="store_true")
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else None
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = repo_root / output_dir
    report = run_smoke(repo_root, args.require_blender, output_dir)
    text = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        output = Path(args.output).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
