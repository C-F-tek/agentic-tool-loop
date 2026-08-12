"""Central defaults for the AI artifact pipeline."""
from __future__ import annotations


PIPELINE_SCHEMA_VERSION = 6
DEFAULT_REPO_ROOT = "."
DEFAULT_TRACK_STEM = "track"
DEFAULT_OUTPUT_DIR = "output/ai_pipeline"
DEFAULT_SMART_TASK = "Scene Director Blender Python generation audio-reactive full keyframe preservation asset-aware composition"
DEFAULT_SMART_MAX_PACKET_CHARS = 22000
DEFAULT_SMART_MAX_CAPSULE_CHARS = 3200
DEFAULT_NPU_WORKERS = 4
DEFAULT_GUARDRAIL_MAX_PASSES = 2
DRY_RUN_REPORT_NAME = "ai_pipeline_dry_run_report.json"
RUN_REPORT_NAME = "ai_pipeline_run_report.json"
