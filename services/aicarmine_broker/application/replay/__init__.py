"""Offline replay diagnostics for agentic planner jobs."""

from __future__ import annotations

__all__ = ["replay_loop_job"]


def __getattr__(name: str):
    if name == "replay_loop_job":
        from .loop_replay import replay_loop_job

        return replay_loop_job
    raise AttributeError(name)
