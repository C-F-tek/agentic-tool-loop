"""CLI parser for the AI artifact pipeline."""
from __future__ import annotations

import argparse

from .defaults import (
    DEFAULT_GUARDRAIL_MAX_PASSES,
    DEFAULT_NPU_WORKERS,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_REPO_ROOT,
    DEFAULT_SMART_MAX_CAPSULE_CHARS,
    DEFAULT_SMART_MAX_PACKET_CHARS,
    DEFAULT_SMART_TASK,
    DEFAULT_TRACK_STEM,
)


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser for the AI artifact pipeline."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", default=DEFAULT_REPO_ROOT)
    ap.add_argument("--analysis-json")
    ap.add_argument("--track-stem", default=DEFAULT_TRACK_STEM)
    ap.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    ap.add_argument("--review-wave-entrypoints", dest="review_wave_entrypoints", action="store_true", default=True)
    ap.add_argument("--no-review-wave-entrypoints", dest="review_wave_entrypoints", action="store_false")
    ap.add_argument("--build-chunks", action="store_true")
    ap.add_argument("--build-music-summary", action="store_true")
    ap.add_argument("--smart-context", dest="smart_context", action="store_true", default=True)
    ap.add_argument("--no-smart-context", dest="smart_context", action="store_false")
    ap.add_argument("--smart-task", default=DEFAULT_SMART_TASK)
    ap.add_argument("--smart-max-packet-chars", type=int, default=DEFAULT_SMART_MAX_PACKET_CHARS)
    ap.add_argument("--smart-max-capsule-chars", type=int, default=DEFAULT_SMART_MAX_CAPSULE_CHARS)
    ap.add_argument(
        "--agent-state-packet",
        help="Optional prebuilt agent state packet JSON to expose in reports without changing pipeline behavior.",
    )
    ap.add_argument("--use-npu", action="store_true")
    ap.add_argument("--npu-guardrail", dest="npu_guardrail", action="store_true", default=True)
    ap.add_argument("--no-npu-guardrail", dest="npu_guardrail", action="store_false")
    ap.add_argument("--npu-workers", type=int, default=DEFAULT_NPU_WORKERS)
    ap.add_argument("--guardrail-auto-remediate", dest="guardrail_auto_remediate", action="store_true", default=True)
    ap.add_argument("--no-guardrail-auto-remediate", dest="guardrail_auto_remediate", action="store_false")
    ap.add_argument("--guardrail-max-passes", type=int, default=DEFAULT_GUARDRAIL_MAX_PASSES)
    ap.add_argument("--gpu-command", help="External command with placeholders {brief} and {output}.")
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--write-dry-run-report", action="store_true", help="Write ai_pipeline_dry_run_report.json even in dry-run mode.")
    ap.add_argument("--continue-on-error", action="store_true")
    return ap
