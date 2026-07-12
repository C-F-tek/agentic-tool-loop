#!/usr/bin/env python3
"""
Build compact AI-friendly music artifacts from an existing analysis JSON.

The source analysis JSON is read-only. New artifacts are written to the output
directory.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from Tools.validation._shared.report_utils import write_json_report, write_text_report
except ImportError:
    repo_root_for_import = Path(__file__).resolve().parents[4]
    if str(repo_root_for_import) not in sys.path:
        sys.path.insert(0, str(repo_root_for_import))
    from Tools.validation._shared.report_utils import write_json_report, write_text_report


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8", errors="replace"))


def first_number(data: Any, keys: tuple[str, ...]) -> float | None:
    if isinstance(data, dict):
        for key in keys:
            value = data.get(key)
            if isinstance(value, (int, float)):
                return float(value)
        for value in data.values():
            found = first_number(value, keys)
            if found is not None:
                return found
    if isinstance(data, list):
        for value in data[:40]:
            found = first_number(value, keys)
            if found is not None:
                return found
    return None


def find_series(data: Any) -> dict[str, list[float]]:
    wanted = ("energy", "intensity", "onset", "rms", "low", "mid", "high", "amplitude")
    out: dict[str, list[float]] = {}

    def walk(value: Any, path: str) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                walk(child, f"{path}.{key}" if path else key)
        elif isinstance(value, list):
            if value and all(isinstance(x, (int, float)) for x in value[: min(200, len(value))]):
                if any(token in path.lower() for token in wanted):
                    out[path] = [float(x) for x in value if isinstance(x, (int, float))]
            elif value and isinstance(value[0], dict):
                for key in (
                    "energy",
                    "intensity",
                    "value",
                    "amplitude",
                    "onset_strength",
                ):
                    vals = [
                        float(x[key])
                        for x in value
                        if isinstance(x, dict) and isinstance(x.get(key), (int, float))
                    ]
                    if vals:
                        out[f"{path}.{key}"] = vals
                        break

    walk(data, "")
    return out


def normalize(values: list[float]) -> list[float]:
    if not values:
        return []
    lo, hi = min(values), max(values)
    if math.isclose(lo, hi):
        return [0.0 for _ in values]
    return [(v - lo) / (hi - lo) for v in values]


def stats(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"count": 0}
    return {
        "count": len(values),
        "min": round(min(values), 6),
        "max": round(max(values), 6),
        "mean": round(statistics.mean(values), 6),
        "median": round(statistics.median(values), 6),
    }


def trend(values: list[float]) -> str:
    if len(values) < 8:
        return "unknown"
    thirds = len(values) / 3
    a = statistics.mean(values[:thirds])
    b = statistics.mean(values[thirds : 2 * thirds])
    c = statistics.mean(values[2 * thirds :])
    if c > b > a:
        return "rising"
    if c < b < a:
        return "falling"
    if b > a and b > c:
        return "middle_peak"
    if c > a and c >= b:
        return "late_peak"
    return "mixed"


def top_events(values: list[float], duration: float, limit: int = 16) -> list[dict[str, Any]]:
    if not values or duration <= 0:
        return []
    norm = normalize(values)
    indexed = sorted(enumerate(norm), key=lambda item: item[1], reverse=True)[:limit]
    denom = max(len(values) - 1, 1)
    return sorted(
        [
            {
                "time_sec": round(index / denom * duration, 3),
                "score": round(score, 4),
                "index": index,
            }
            for index, score in indexed
        ],
        key=lambda item: item["time_sec"],
    )


def synthetic_beats(duration: float, bpm: float | None) -> list[float]:
    if not bpm or duration <= 0:
        return []
    step = 60.0 / bpm
    beats, t = [], 0.0
    while t <= duration and len(beats) < 2000:
        beats.append(round(t, 3))
        t += step
    return beats


def visual_directive(name: str, intensity: float | None, event_count: int) -> dict[str, Any]:
    level = "medium"
    if intensity is not None:
        level = "high" if intensity >= 0.66 else "low" if intensity <= 0.33 else "medium"
    return {
        "intensity_level": level,
        "camera": (
            "slow reveal"
            if name == "intro"
            else ("impact moves on peaks" if level == "high" else "stable rhythmic motion")
        ),
        "lighting": (
            "soft establishing light"
            if name == "intro"
            else "burst accents"
            if event_count
            else "controlled ambient variation"
        ),
        "materials": (
            "subtle shader modulation"
            if level == "low"
            else "strong emissive/audio-reactive modulation"
        ),
        "fog": "low density" if level == "low" else "pulsed volumetric depth",
    }


def segments(duration: float, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if duration <= 0:
        return []
    names = (
        ["intro", "build", "development", "climax", "release", "outro"]
        if duration >= 180
        else ["intro", "build", "climax", "release", "outro"]
    )
    step = duration / len(names)
    result = []
    for i, name in enumerate(names):
        start = i * step
        end = duration if i == len(names) - 1 else (i + 1) * step
        local = [e for e in events if start <= e["time_sec"] < end]
        intensity = round(statistics.mean([e["score"] for e in local]), 4) if local else None
        result.append(
            {
                "name": name,
                "start_sec": round(start, 3),
                "end_sec": round(end, 3),
                "duration_sec": round(end - start, 3),
                "estimated_intensity": intensity,
                "event_count": len(local),
                "peak_events": local[:6],
                "visual_directive": visual_directive(name, intensity, len(local)),
                "ai_use": "Use this section to vary camera, lighting, materials, fog, density, and motion intensity.",
            }
        )
    return result


def mapping_candidates(
    segs: list[dict[str, Any]], bpm: float | None, peaks: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    return [
        {
            "candidate_id": "cinematic_orbital_energy",
            "score": 0.82,
            "summary": "Use BPM for orbital rhythm, peaks for light/fog bursts, and segments for scene density progression.",
            "audio_to_visual": {
                "bpm": ["orbital motion cadence", "camera pulse timing"],
                "peak_events": ["emission bursts", "fog shocks", "camera micro-impact"],
                "segments": ["object density", "palette shifts", "camera path phases"],
            },
            "recommended_for": "cosmic audio-reactive scenes with wow factor",
        },
        {
            "candidate_id": "jazz_light_materials",
            "score": 0.74,
            "summary": "Favor material shimmer, light call-and-response, and controlled camera movement over excessive object count.",
            "audio_to_visual": {
                "bpm": ["subtle material oscillation"],
                "peak_events": ["localized light accents"],
                "segments": ["color warmth and shader complexity"],
            },
            "recommended_for": "music-driven scene with lower render risk",
        },
        {
            "candidate_id": "minimal_safe_reference",
            "score": 0.66,
            "summary": "Keep geometry stable and make most reactivity happen in lighting, fog, materials, and camera.",
            "audio_to_visual": {
                "bpm": ["safe rhythmic keyframes"],
                "peak_events": ["non-destructive accent markers"],
                "segments": ["scene tuning presets"],
            },
            "recommended_for": "first validation render or low-risk package generation",
        },
    ]


def assumptions(
    duration: float, bpm: float | None, primary_name: str | None, series_count: int
) -> list[str]:
    out = []
    if not duration:
        out.append("Duration was not found in the analysis JSON; segment timing may be empty.")
    if not bpm:
        out.append("BPM was not found; beat map may be empty or synthetic beat mapping disabled.")
    if not primary_name:
        out.append("No usable energy/intensity series was found; peak events may be empty.")
    if series_count:
        out.append(
            "Primary intensity series was selected heuristically from available numeric series."
        )
    out.append(
        "Full frame-level analysis JSON remains read-only and is not rewritten by this tool."
    )
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--analysis-json", required=True)
    parser.add_argument("--output-dir", default="output/ai_pipeline")
    args = parser.parse_args()

    source = Path(args.analysis_json).resolve()
    out = Path(args.output_dir).resolve()
    data = load_json(source)
    duration = (
        first_number(data, ("duration_sec", "duration_seconds", "duration", "track_duration_sec"))
        or 0.0
    )
    bpm = first_number(data, ("bpm", "estimated_bpm", "tempo"))
    sample_rate = first_number(data, ("sample_rate", "sr", "samplerate"))
    series = find_series(data)
    primary_name = next(iter(series), None)
    primary = series.get(primary_name, []) if primary_name else []
    peaks = top_events(primary, duration)
    segs = segments(duration, peaks)
    beats = synthetic_beats(duration, bpm)
    now = datetime.now(timezone.utc).isoformat()
    ass = assumptions(duration, bpm, primary_name, len(series))

    artifacts = {
        "track_summary.json": {
            "schema_version": 2,
            "generated_at": now,
            "source_analysis": str(source),
            "duration_sec": round(duration, 3) if duration else None,
            "estimated_bpm": round(bpm, 3) if bpm else None,
            "sample_rate": int(sample_rate) if sample_rate else None,
            "series_detected": sorted(series.keys()),
            "primary_series": primary_name,
            "primary_series_stats": stats(primary),
            "primary_series_trend": trend(primary),
            "segment_count": len(segs),
            "beat_count": len(beats),
            "peak_event_count": len(peaks),
            "ai_readiness": {
                "has_duration": bool(duration),
                "has_bpm": bool(bpm),
                "has_primary_series": bool(primary_name),
                "score": round(
                    sum([bool(duration), bool(bpm), bool(primary_name), bool(segs)]) / 4,
                    3,
                ),
            },
            "assumptions": ass,
        },
        "music_segments.json": {
            "schema_version": 2,
            "generated_at": now,
            "source_analysis": str(source),
            "segments": segs,
        },
        "audio_event_map.json": {
            "schema_version": 2,
            "generated_at": now,
            "source_analysis": str(source),
            "beats_sec": beats[:512],
            "peak_events": peaks,
            "series_used_for_peaks": primary_name,
            "event_density": round(len(peaks) / duration, 6) if duration else None,
        },
        "ai_scene_brief.json": {
            "schema_version": 2,
            "generated_at": now,
            "creative_intent": "audio-reactive cinematic Blender scene",
            "technical_intent": "Generate or patch a Blender package using compact audio summaries and validated scene mapping.",
            "track_facts": {
                "duration_sec": round(duration, 3) if duration else None,
                "estimated_bpm": round(bpm, 3) if bpm else None,
                "segment_count": len(segs),
                "primary_series_trend": trend(primary),
            },
            "recommended_visual_progression": [
                {
                    "segment": s["name"],
                    "start_sec": s["start_sec"],
                    "end_sec": s["end_sec"],
                    "visual_directive": s["visual_directive"],
                }
                for s in segs
            ],
            "constraints": [
                "Do not overwrite full analysis JSON files.",
                "Keep generated scripts configurable.",
                "Validate before accepting generated code.",
                "Avoid ShaderNodeTexMusgrave in Blender 5.x.",
            ],
            "assumptions": ass,
        },
        "ai_resource_budget.json": {
            "schema_version": 2,
            "generated_at": now,
            "target_profile": "local_workstation_32gb_ram_16gb_vram",
            "recommendations": {
                "max_parallel_npu_jobs": 4,
                "gpu_role": "main generation and merge",
                "npu_role": "short review and scoring",
                "cpu_role": "validation and orchestration",
                "avoid_concurrent_heavy_render_and_large_llm": True,
            },
        },
        "ai_mapping_candidates.json": {
            "schema_version": 2,
            "generated_at": now,
            "source_analysis": str(source),
            "candidates": mapping_candidates(segs, bpm, peaks),
        },
        "ai_assumptions.md": "# AI Assumptions\n\n" + "\n".join(f"- {item}" for item in ass) + "\n",
    }

    written = {}
    for name, payload in artifacts.items():
        path = out / name
        if isinstance(payload, str):
            write_text_report(payload, path)
        else:
            write_json_report(payload, path)
        written[name] = str(path)
    print(json.dumps(written, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
