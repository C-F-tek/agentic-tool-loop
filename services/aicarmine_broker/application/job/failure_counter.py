"""Failure counter for agent jobs.

Tracks per-job failure counts across different error categories:
- planner_failure_count: Planner decision/validation failures
- tool_failure_count: Tool execution failures
- guard_failure_count: Controller guard rejections
- vulkan_repair_failure_count: Vulkan repair attempts that failed

Counts are persisted in job state JSON files and read back on job load.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)


class FailureCounter:
    """Thread-safe failure counter for a single job."""

    def __init__(self, job_id: str, root: Path) -> None:
        self.job_id = job_id
        self.root = root
        self._counts: Dict[str, int] = {}
        self._load()

    def _load(self) -> None:
        """Load persisted counts from job state file."""
        try:
            state_path = self.root / "state.json"
            if state_path.exists():
                data = json.loads(state_path.read_text(encoding="utf-8"))
                saved = data.get("failure_counts", {})
                if isinstance(saved, dict):
                    for key, val in saved.items():
                        if isinstance(val, int) and val >= 0:
                            self._counts[key] = val
        except Exception as exc:
            logger.warning(
                "Failed to load failure_counts for job=%s: %s",
                self.job_id,
                type(exc).__name__,
            )

    def _save(self) -> None:
        """Persist counts to job state file."""
        try:
            state_path = self.root / "state.json"
            if not state_path.exists():
                return
            data = json.loads(state_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return
            data["failure_counts"] = dict(self._counts)
            state_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.warning(
                "Failed to save failure_counts for job=%s: %s",
                self.job_id,
                type(exc).__name__,
            )

    def increment(self, category: str, amount: int = 1) -> int:
        """Increment a counter and return new value."""
        if category not in self._counts:
            self._counts[category] = 0
        self._counts[category] += amount
        self._save()
        return self._counts[category]

    def get(self, category: str) -> int:
        """Get current count for a category (0 if unset)."""
        return self._counts.get(category, 0)

    def reset(self, category: str) -> None:
        """Reset a specific counter to 0."""
        if category in self._counts:
            self._counts[category] = 0
            self._save()

    def snapshot(self) -> Dict[str, int]:
        """Return copy of all counts."""
        return dict(self._counts)


# Module-level convenience functions
_counter_cache: Dict[str, FailureCounter] = {}


def get_counter(job_id: str, root: Path) -> FailureCounter:
    """Get or create a FailureCounter for a job (cached)."""
    key = f"{job_id}:{str(root)}"
    if key not in _counter_cache:
        _counter_cache[key] = FailureCounter(job_id, root)
    return _counter_cache[key]


def reset_counter(job_id: str) -> None:
    """Remove cached counter to force reload."""
    keys_to_remove = [k for k in _counter_cache if job_id in k]
    for k in keys_to_remove:
        _counter_cache.pop(k, None)