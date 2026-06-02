#!/usr/bin/env python3
"""Build shared-toolbox AI-to-AI final summaries and compact evidence bundles.

Report-only builder for issue #141. It assembles a final summary from existing
reports, delegates compact bundle construction to the common GitHub evidence
bundle builder, and optionally validates the resulting bundle.

The tool itself does not execute providers, apply patches, run Blender, or write
SQLite/persistent memory.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from ia_carmine.runtime.runtime_tool.broker.registry import TOOL_SPECS
    from ia_carmine.product.repository_product.github_evidence_bundle import build_bundle
    from ia_carmine._shared.github_evidence_bundle_artifacts import (
        DEFAULT_CHUNK_LINES,
        DEFAULT_RECURSIVE_MAX_FILES,
    )
    from ia_carmine._shared.github_evidence_bundle_io import (
        read_json,
        read_text,
        repo_relative,
        resolve_repo_path,
        split_path_values,
    )
    from Tools.validation.repository_product.github_evidence_bundle import (
        validate_github_evidence_bundles,
    )
    from Tools.validation._shared.report_utils import resolve_output_path, write_json_report
except ImportError:
    repo_root_for_import = Path(__file__).resolve().parents[3]
    if str(repo_root_for_import) not in sys.path:
        sys.path.insert(0, str(repo_root_for_import))
    from ia_carmine.runtime.runtime_tool.broker.registry import TOOL_SPECS
    from ia_carmine.product.repository_product.github_evidence_bundle import build_bundle
    from ia_carmine._shared.github_evidence_bundle_artifacts import (
        DEFAULT_CHUNK_LINES,
        DEFAULT_RECURSIVE_MAX_FILES,
    )
    from ia_carmine._shared.github_evidence_bundle_io import (
        read_json,
        read_text,
        repo_relative,
        resolve_repo_path,
        split_path_values,
    )
    from Tools.validation.repository_product.github_evidence_bundle import (
        validate_github_evidence_bundles,
    )
    from Tools.validation._shared.report_utils import resolve_output_path, write_json_report


DEFAULT_STAMP_FORMAT = "%Y%m%d-%H%M%S"
DEFAULT_BASENAME_PREFIX = "shared_toolbox_ai_to_ai_bundle"
DEFAULT_FINAL_SUMMARY_PREFIX = "shared_toolbox_ai_to_ai_final_summary"
DEFAULT_RECURSIVE_REPORT_ROOTS: tuple[str, ...] = (
    "output/validation",
    "output/analysis",
    "output/ai_pipeline",
)
DEFAULT_RECURSIVE_ARTIFACT_ROOTS: tuple[str, ...] = (
    "output/analysis",
    "output/ai_pipeline",
    "docs/LOCAL_AI_TASKS",
)

DEFAULT_REPORT_TEMPLATES: tuple[str, ...] = (
    "output/validation/shared_toolbox_python_syntax_{stamp}.json",
    "output/analysis/shared_toolbox_code_interpreter_{stamp}.json",
    "output/validation/shared_toolbox_gpu_contract_smoke_{stamp}.json",
    "output/validation/shared_toolbox_gpu_routing_{stamp}.json",
    "output/validation/shared_toolbox_npu_execution_{stamp}.json",
    "output/validation/shared_toolbox_npu_contract_{stamp}.json",
    "output/validation/npu_provider_environment_shared_toolbox_{stamp}.json",
    "output/ai_pipeline/shared_toolbox_ai_to_ai_{stamp}_orchestrator.json",
    "output/ai_pipeline/shared_toolbox_ai_to_ai_{stamp}_gpu.json",
    "output/analysis/shared_toolbox_gpu_npu_sync_{stamp}.json",
    "output/analysis/shared_toolbox_gpu_contract_replay_{stamp}.json",
)

FULL_TOOLBOX_REPORT_TEMPLATES: tuple[str, ...] = (
    "output/validation/agent_review_full_toolbox_decision_loop_{stamp}_integrated.json",
    "output/validation/agent_review_full_toolbox_decision_loop_{stamp}_workflow.json",
    "output/validation/agent_review_warning_policy_{stamp}.json",
    "output/ai_pipeline/full_toolbox_{stamp}_agent_review_decision_loop.json",
    "output/patch_specs/full_toolbox_{stamp}_agent_review_patch_plan.json",
    "output/ai_pipeline/full_toolbox_{stamp}_deterministic_recommendations.json",
    "output/ai_pipeline/full_toolbox_{stamp}_bridge_orchestrator.json",
    "output/ai_pipeline/full_toolbox_{stamp}_orchestrator.json",
    "output/ai_pipeline/full_toolbox_{stamp}_parallel_gpu.json",
    "output/validation/local_provider_probe.json",
    "output/validation/ai_workload_report_quality.json",
    "output/analysis/repository_consistency_map_full_toolbox_{stamp}.json",
    "output/validation/repository_consistency_map_smoke_full_toolbox_{stamp}.json",
    "output/analysis/code_interpreter_full_toolbox_{stamp}.json",
    "output/validation/python_line_count_full_toolbox_{stamp}.json",
    "output/validation/python_syntax_full_toolbox_{stamp}.json",
    "output/validation/gpu_planner_json_contract_smoke_full_toolbox_{stamp}.json",
    "output/validation/deterministic_recommendation_synthesizer_smoke_full_toolbox_{stamp}.json",
    "output/validation/agent_review_decision_loop_smoke_full_toolbox_{stamp}.json",
    "output/validation/npu_provider_environment_full_toolbox_{stamp}.json",
    "output/validation/gpu1_primary_advisory_{stamp}.json",
    "output/validation/gpu0_peer_task_packet_{stamp}.json",
    "output/validation/gpu0_peer_response_{stamp}.json",
    "output/validation/gpu0_tool_requests_{stamp}.json",
    "output/validation/gpu0_peer_runtime_tool_broker_{stamp}.json",
    "output/validation/npu_micro_peer_assistant_{stamp}.json",
    "output/validation/npu_micro_runtime_tool_broker_{stamp}.json",
    "output/validation/ai_peer_exchange_{stamp}.json",
    "output/validation/ai_peer_exchange_contract_{stamp}.json",
    "output/validation/provider_runtime_live_signals_init_{stamp}.json",
    "output/validation/provider_runtime_live_signals_gpu1_request_{stamp}.json",
    "output/validation/provider_runtime_live_signals_broker_results_{stamp}.json",
    "output/validation/provider_runtime_live_signals_npu_support_{stamp}.json",
    "output/validation/provider_runtime_heap_from_peer_reports_{stamp}.json",
    "output/ai_runtime_heap/{stamp}/snapshot.json",
    "docs/LOCAL_VALIDATION_EVIDENCE/runtime_tool_capability_manifest_{stamp}.json",
    "docs/LOCAL_VALIDATION_EVIDENCE/full_toolbox_{stamp}_cloud_semantic_deterministic_chunk_manifest.json",
)

FULL_TOOLBOX_ARTIFACT_TEMPLATES: tuple[str, ...] = (
    "output/patch_specs/full_toolbox_{stamp}_agent_review_patch_plan.md",
    "output/ai_pipeline/full_toolbox_{stamp}_agent_review_decision_loop.md",
    "output/ai_pipeline/full_toolbox_{stamp}_deterministic_recommendations.md",
    "output/ai_pipeline/full_toolbox_{stamp}_orchestrator.md",
    "output/ai_pipeline/full_toolbox_{stamp}_parallel_gpu.md",
    "output/analysis/repository_consistency_map_full_toolbox_{stamp}.md",
    "output/validation/repository_consistency_map_smoke_full_toolbox_{stamp}.md",
    "output/analysis/code_interpreter_full_toolbox_{stamp}.md",
    "output/validation/python_line_count_full_toolbox_{stamp}.md",
    "output/validation/python_line_count_all_python_files_{stamp}.md",
    "output/validation/gpu_planner_json_contract_smoke_full_toolbox_{stamp}.md",
    "output/validation/deterministic_recommendation_synthesizer_smoke_full_toolbox_{stamp}.md",
    "output/validation/agent_review_decision_loop_smoke_full_toolbox_{stamp}.md",
    "output/validation/npu_provider_environment_full_toolbox_{stamp}.md",
    "output/validation/gpu1_primary_advisory_{stamp}.md",
    "output/validation/gpu0_peer_response_{stamp}.md",
    "output/validation/gpu0_peer_runtime_tool_broker_{stamp}.md",
    "output/validation/npu_micro_peer_assistant_{stamp}.md",
    "output/validation/npu_micro_runtime_tool_broker_{stamp}.md",
    "output/validation/ai_peer_exchange_{stamp}.md",
    "output/validation/ai_peer_exchange_contract_{stamp}.md",
    "output/validation/provider_runtime_live_signals_init_{stamp}.md",
    "output/validation/provider_runtime_live_signals_gpu1_request_{stamp}.md",
    "output/validation/provider_runtime_live_signals_broker_results_{stamp}.md",
    "output/validation/provider_runtime_live_signals_npu_support_{stamp}.md",
    "output/validation/provider_runtime_heap_from_peer_reports_{stamp}.md",
    "output/ai_runtime_heap/{stamp}/snapshot.md",
    "output/validation/agent_review_full_toolbox_decision_loop_{stamp}_integrated.md",
    "output/validation/agent_review_full_toolbox_decision_loop_{stamp}_workflow.md",
    "docs/LOCAL_VALIDATION_EVIDENCE/runtime_tool_capability_manifest_{stamp}.md",
    "docs/LOCAL_VALIDATION_EVIDENCE/full_toolbox_{stamp}_cloud_semantic_deterministic_chunk_manifest.md",
)

DEFAULT_ARTIFACT_TEMPLATES: tuple[str, ...] = (
    "docs/LOCAL_AI_TASKS/shared-runtime-toolbox-ai-to-ai-next-task-2026-05-03.md",
    "docs/LOCAL_AI_TASKS/shared-runtime-toolbox-orchestration-architecture.md",
    "output/analysis/shared_toolbox_code_interpreter_{stamp}.md",
    "output/ai_pipeline/shared_toolbox_ai_to_ai_{stamp}_orchestrator.md",
    "output/ai_pipeline/shared_toolbox_ai_to_ai_{stamp}_gpu.md",
    "output/analysis/shared_toolbox_gpu_npu_sync_{stamp}.md",
    "output/analysis/shared_toolbox_gpu_contract_replay_{stamp}.md",
    "output/analysis/shared_toolbox_ai_to_ai_final_summary_{stamp}.md",
)
