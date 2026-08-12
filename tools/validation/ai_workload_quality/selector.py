"""Report selection for AI workload quality validation."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .constants import KNOWN_WORKLOAD_REPORTS
from .paths import packet_dirs, relative_or_absolute_path


def collect_report_specs(
    repo_root: Path,
    report_dir: Path,
    include_missing_known_reports: bool = False,
) -> tuple[list[tuple[str, str]], list[dict[str, Any]]]:
    selected: list[tuple[str, str]] = []
    unselected: list[dict[str, Any]] = []
    selected_paths: set[str] = set()

    for packet_dir in packet_dirs(repo_root, report_dir):
        for lane, filename in KNOWN_WORKLOAD_REPORTS:
            candidate = packet_dir / filename
            key = str(candidate.resolve(strict=False)).lower()
            if candidate.exists() or include_missing_known_reports:
                if key not in selected_paths:
                    selected_paths.add(key)
                    selected.append((lane, str(candidate)))
            else:
                unselected.append(
                    {
                        "lane": lane,
                        "packet_dir": relative_or_absolute_path(packet_dir, repo_root),
                        "path": relative_or_absolute_path(candidate, repo_root),
                        "reason": "known_workload_report_missing_from_selected_output_folder",
                    }
                )

        known_names = {filename for _, filename in KNOWN_WORKLOAD_REPORTS}
        if packet_dir.exists() and packet_dir.is_dir():
            for candidate in sorted(packet_dir.glob("*workload_report*.md")):
                if candidate.name in known_names:
                    continue
                key = str(candidate.resolve(strict=False)).lower()
                if key in selected_paths:
                    continue
                lane = candidate.stem.replace("_real_workload_report", "").replace("_workload_report", "")
                selected_paths.add(key)
                selected.append((lane.replace("-", "_") or "unknown", str(candidate)))

    return selected, unselected
