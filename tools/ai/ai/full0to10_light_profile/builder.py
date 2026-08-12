"""Build Full0To10 light profile promotion artifacts."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .constants import NEXT_LOOP_JSON, PROMOTION_JSON, PROMOTION_MD
from .reader import read_json
from .readiness import build_readiness
from .render import build_next_loop, render_promotion


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def build_light_profile_promotion(run_report: Path, output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    run = read_json(run_report)
    report = build_readiness(run, str(run_report))
    next_loop = build_next_loop(report)

    write_json(output_dir / PROMOTION_JSON, report)
    write_json(output_dir / NEXT_LOOP_JSON, next_loop)
    (output_dir / PROMOTION_MD).write_text(render_promotion(report), encoding="utf-8")

    report["outputs"] = {
        "promotion_json": str(output_dir / PROMOTION_JSON),
        "promotion_md": str(output_dir / PROMOTION_MD),
        "next_loop_json": str(output_dir / NEXT_LOOP_JSON),
    }
    return report
