"""Built-in AI context pack profiles."""

from __future__ import annotations

from typing import Any

DEFAULT_OUTPUT_DIR = "output/ai_context_packs"
DEFAULT_EVIDENCE_DIR = "docs/LOCAL_VALIDATION_EVIDENCE"
DEFAULT_PROFILE = "project_self_improvement"
DEFAULT_MAX_TOTAL_CHARS = 64000
DEFAULT_MAX_FILE_CHARS = 4000
PACK_KIND = "ai_context_pack"
EVIDENCE_KIND = "ai_context_pack_evidence"
APPLY_MODE = "context_only"

FORBIDDEN_PATH_PREFIXES = (
    ".git/",
    ".venv/",
    "__pycache__/",
    "indexAI/",
    "output/",
    "renders/",
    "venv/",
    "Scripting/ready_to_jazz_wow_youtube_profiles_audio_sync/",
)

FORBIDDEN_PATH_EXACT = {
    "Scripting/shared/blender_compat.py",
}

FORBIDDEN_PATH_FRAGMENTS = (
    "full_analysis",
    "analysis_full",
)

PROFILE_COMMON_STOP_CONDITIONS = [
    "Do not execute providers implicitly.",
    "Do not apply patch specs or write patch_specs/inbox/ without explicit approval.",
    "Do not touch Blender runtime, Ready To Jazz, blender_compat.py, full analysis JSON or generated indexes.",
    "Do not change provider model, temperature, prompt prose or execution policy in a context-pack task.",
]

PROFILES: dict[str, dict[str, Any]] = {
    "project_self_improvement": {
        "description": "Prototype context pack for the repo helping plan its own next validated work.",
        "required_files": [
            {"path": "README.md", "role": "project_identity"},
            {"path": "WORKFLOW.md", "role": "operational_workflow"},
            {"path": "docs/README.md", "role": "documentation_index"},
            {"path": "docs/PROJECT_STATUS_POINT.md", "role": "status_checkpoint"},
            {"path": "docs/DATA_FLOW.md", "role": "data_flow"},
            {"path": "docs/LOCAL_AI_WORKFLOW.md", "role": "ai_workflow"},
            {"path": "docs/PATCH_SPEC_WORKFLOW.md", "role": "patch_spec_workflow"},
            {"path": "docs/JSON_SCHEMAS.md", "role": "schema_notes"},
            {"path": "Tools/validation/CONTEXT_INDEX.md", "role": "validation_commands"},
            {"path": "Tools/validation/TOOL_CONTEXT.md", "role": "validation_tool_context"},
            {
                "path": "ia_carmine/product/repository_product/repository_change_proposals/cli.py",
                "role": "proposal_builder",
            },
            {
                "path": "ia_carmine/product/generated_patch_specs/proposal_cli.py",
                "role": "draft_patch_spec_builder",
            },
            {
                "path": "ia_carmine/product/generated_patch_specs/review_cli.py",
                "role": "reviewed_patch_spec_builder",
            },
            {
                "path": "ia_carmine/product/generated_patch_specs/apply_cli.py",
                "role": "generated_patch_spec_apply_boundary",
            },
        ],
        "optional_files": [
            {"path": "docs/TECH_DEBT_TRACKER.md", "role": "debt_tracker"},
            {
                "path": "docs/LOCAL_VALIDATION_EVIDENCE/patch_spec_review_promotion_gpu_npu_multistep_evidence.md",
                "role": "latest_patch_spec_evidence",
            },
            {
                "path": "docs/GITHUB_ONLY_AI_CONTINUATION_GUIDE.md",
                "role": "github_only_mode",
            },
        ],
        "validation_commands": [
            "python -m Tools.validation check_python_syntax --repo-root . --output .\\output\\validation\\python_syntax.json",
            "python -m Tools.validation check_ai_context_pack_contract --repo-root . --pack .\\output\\ai_context_packs\\project_self_improvement.json --evidence .\\docs\\LOCAL_VALIDATION_EVIDENCE\\project_self_improvement_context_pack_evidence.json --output .\\output\\validation\\ai_context_pack_contract.json",
            "python -m Tools.validation check_json_artifacts --repo-root . --output .\\output\\validation\\json_artifacts.json",
            "python -m Tools.validation check_docs_links --repo-root . --output .\\output\\validation\\docs_links.json",
            "python -m Tools.validation check_validation_report_contract --repo-root . --output .\\output\\validation\\validation_report_contract.json",
        ],
        "stop_conditions": [
            "If the next task needs provider execution, switch to the explicit GPU/NPU multistep workflow.",
            "If the next task needs source edits, generate proposals or reviewed patch specs before queue/apply work.",
        ],
    },
    "core_ai_backend": {
        "description": "Core backend orchestration, validation and evidence context.",
        "required_files": [
            {"path": "README.md", "role": "project_identity"},
            {"path": "WORKFLOW.md", "role": "operational_workflow"},
            {"path": "docs/DATA_FLOW.md", "role": "data_flow"},
            {"path": "docs/LOCAL_AI_WORKFLOW.md", "role": "ai_workflow"},
            {"path": "docs/JSON_SCHEMAS.md", "role": "schema_notes"},
            {
                "path": "ia_carmine/product/ai_workload/quality_lane_routing/cli.py",
                "role": "lane_routing",
            },
            {
                "path": "ia_carmine/product/repository_product/repository_update_suggestions/cli.py",
                "role": "advisory_packet",
            },
            {
                "path": "ia_carmine/product/repository_product/github_evidence_bundle/cli.py",
                "role": "evidence_builder",
            },
            {"path": "Tools/validation/CONTEXT_INDEX.md", "role": "validation_commands"},
            {"path": "Tools/validation/TOOL_CONTEXT.md", "role": "validation_tool_context"},
        ],
        "optional_files": [
            {
                "path": "docs/LOCAL_VALIDATION_EVIDENCE/parallel_gpu_npu_multistep_real_npu_v2_evidence.md",
                "role": "baseline_evidence",
            },
            {"path": "docs/TECH_DEBT_TRACKER.md", "role": "debt_tracker"},
        ],
        "validation_commands": [
            "python -m Tools.validation check_python_syntax --repo-root . --output .\\output\\validation\\python_syntax.json",
            "python -m Tools.validation check_json_artifacts --repo-root . --output .\\output\\validation\\json_artifacts.json",
            "python -m Tools.validation check_validation_report_contract --repo-root . --output .\\output\\validation\\validation_report_contract.json",
        ],
        "stop_conditions": [
            "Use the explicit multistep runner before making provider-lane claims.",
        ],
    },
    "artifact_pipeline": {
        "description": "AI artifact pipeline, dry-run matrix and refactor-status context.",
        "required_files": [
            {
                "path": "docs/IA_UNIVERSE_MODEL_TO_CODE_MAP.md",
                "role": "pipeline_architecture",
            },
            {
                "path": "docs/PATCH_CODE_PRODUCT_BOUNDARY_MODEL.md",
                "role": "pipeline_refactor_status",
            },
            {"path": "docs/JSON_SCHEMAS.md", "role": "artifact_schema_notes"},
            {
                "path": "ia_carmine/product/pipeline/dry_run_matrix/cli.py",
                "role": "dry_run_matrix",
            },
            {"path": "Tools/validation/CONTEXT_INDEX.md", "role": "validation_commands"},
            {"path": "Tools/validation/TOOL_CONTEXT.md", "role": "validation_tool_context"},
        ],
        "optional_files": [
            {"path": "tools/ai/pipeline/markdown_report.py", "role": "markdown_report"},
        ],
        "validation_commands": [
            "python -m Tools.validation check_refactor_status_consistency --repo-root . --output .\\output\\validation\\refactor_status_consistency.json",
            "python -m Tools.validation check_ai_pipeline_modules --repo-root . --output .\\output\\validation\\ai_pipeline_modules.json",
            "python -m ia_carmine.cli pipeline_dry_run_matrix --repo-root . --continue-on-error",
        ],
        "stop_conditions": [
            "Do not interpret pending matrix evidence as provider execution.",
        ],
    },
    "docs_only": {
        "description": "Documentation-only task context with lightweight validators.",
        "required_files": [
            {"path": "README.md", "role": "project_identity"},
            {"path": "WORKFLOW.md", "role": "operational_workflow"},
            {"path": "docs/README.md", "role": "documentation_index"},
            {"path": "docs/PROJECT_STATUS_POINT.md", "role": "status_checkpoint"},
            {"path": "docs/DATA_FLOW.md", "role": "data_flow"},
            {"path": "docs/JSON_SCHEMAS.md", "role": "schema_notes"},
            {"path": "Tools/validation/CONTEXT_INDEX.md", "role": "validation_commands"},
            {"path": "Tools/validation/TOOL_CONTEXT.md", "role": "validation_tool_context"},
        ],
        "optional_files": [
            {"path": "docs/TECH_DEBT_TRACKER.md", "role": "debt_tracker"},
        ],
        "validation_commands": [
            "python -m Tools.validation check_docs_links --repo-root . --output .\\output\\validation\\docs_links.json",
            "python -m Tools.validation check_json_artifacts --repo-root . --output .\\output\\validation\\json_artifacts.json",
            "python -m Tools.validation check_execution_plan_status --repo-root . --output .\\output\\validation\\execution_plan_status.json",
        ],
        "stop_conditions": [
            "Do not claim local GPU/NPU validation from a docs-only task.",
        ],
    },
}
