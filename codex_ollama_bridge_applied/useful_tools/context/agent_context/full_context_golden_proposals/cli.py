#!/usr/bin/env python3
"""Build deterministic full-context golden-path proposal families P1-P6.

This generator is report-only. It does not call providers, does not inspect
runtime outputs unless supplied as optional evidence metadata, and does not apply
patches. It creates concrete manual-review-only proposal objects that satisfy the
full-context golden proposal contract.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROPOSAL_KIND = "repository_change_proposals"
APPLY_MODE = "manual_review_only"


def repo_relative(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root).as_posix()
    except ValueError:
        return path.as_posix()


def resolve_repo_path(repo_root: Path, raw: str) -> Path:
    path = Path(raw)
    return path.resolve() if path.is_absolute() else (repo_root / path).resolve()


def read_json_if_present(path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def suggestion(path: str, artifact_kind: str = "python_code") -> dict[str, str]:
    return {
        "path": path,
        "artifact_kind": artifact_kind,
        "operation": "manual_patch_suggestion",
        "content_status": "proposal_only",
        "write_policy": APPLY_MODE,
    }


def base_proposal(
    pid: str,
    priority: str,
    area: str,
    title: str,
    rationale: str,
    target_files: list[str],
    change_type: str,
    patch_sketch: list[str],
    validation_commands: list[str],
    stop_conditions: list[str],
    suggestion_outputs: list[dict[str, str]],
) -> dict[str, Any]:
    return {
        "id": pid,
        "proposal_id": pid,
        "priority": priority,
        "area": area,
        "title": title,
        "rationale": rationale,
        "target_files": target_files,
        "change_type": change_type,
        "apply_mode": APPLY_MODE,
        "apply_allowed_now": False,
        "requires_manual_review": True,
        "requires_provider_execution": False,
        "risk_level": "low" if priority in {"P1", "P3", "P5"} else "medium",
        "patch_sketch": patch_sketch,
        "validation_commands": validation_commands,
        "stop_conditions": stop_conditions,
        "suggestion_outputs": suggestion_outputs,
        "do_not_touch": [
            "Scripting/shared/blender_compat.py",
            "Scripting/ready_to_jazz_wow_youtube_profiles_audio_sync/**",
            "indexAI/agent_memory/**",
            "output/**",
            "full analysis JSON files",
        ],
    }


def build_proposals() -> list[dict[str, Any]]:
    return [
        base_proposal(
            pid="P1-ADAPTER-MANIFEST-VALIDATOR",
            priority="P1",
            area="validation",
            title="Add adapter manifest validator for local AI enrichment outputs",
            rationale=(
                "The wrapper now records selected chunks, context pack, agent state, provider flags and evidence paths. "
                "A dedicated adapter manifest validator would make golden-path runs auditable and catch missing enrichment outputs early."
            ),
            target_files=[
                "Tools/validation/pipeline/check_local_ai_adapter_manifest/cli.py",
                "Tools/validation/CONTEXT_INDEX.md",
            ],
            change_type="validator",
            patch_sketch=[
                "Create a report-only validator for local_ai_task_pipeline_adapter_manifest JSON files.",
                "Validate enrichment_requested flags, enrichment_outputs paths, context_file_count, provider_execution_requested and patch_application_performed false.",
                "Reject missing selected-chunks evidence when build_selected_chunks_evidence is true.",
                "Document usage in Tools/validation/CONTEXT_INDEX.md.",
            ],
            validation_commands=[
                "python -m Tools.validation check_python_syntax --repo-root . --output output/validation/python_syntax.json",
                "python -m Tools.validation check_local_ai_adapter_manifest --repo-root . --manifest output/local_ai_runs/<run>/pipeline/full_context_golden_local_ai_context_adapter_manifest.json --output output/validation/full_context_golden_adapter_manifest.json",
                "git diff --check",
            ],
            stop_conditions=[
                "Do not inspect or commit SQLite memory DB files.",
                "Do not require provider execution to validate the manifest.",
                "Do not touch Blender runtime files.",
            ],
            suggestion_outputs=[
                suggestion("Tools/validation/pipeline/check_local_ai_adapter_manifest/cli.py"),
                suggestion("Tools/validation/CONTEXT_INDEX.md", "markdown"),
            ],
        ),
        base_proposal(
            pid="P2-REUSABLE-ENRICHMENT-PLAN-HELPER",
            priority="P2",
            area="ai_orchestration",
            title="Extract reusable enrichment-plan helper for local AI full-context runs",
            rationale=(
                "The wrapper contains repeated policy decisions for semantic chunks, selected chunks, context packs and agent state. "
                "A reusable helper can generate deterministic enrichment plans without applying them, reducing PowerShell complexity."
            ),
            target_files=[
                "ia_carmine/context/agent_context/local_ai_enrichment_plan/cli.py",
                "Tools/validation/agent_context/check_local_ai_enrichment_plan/cli.py",
            ],
            change_type="core_helper",
            patch_sketch=[
                "Create a Python helper that emits a report-only enrichment plan JSON from task/profile flags.",
                "Include selected chunks, context pack, agent state and evidence outputs as planned artifacts.",
                "Add a validator to ensure the plan is bounded, report-only and manual-review-only.",
                "Keep wrapper integration for a later PR after the helper contract is validated.",
            ],
            validation_commands=[
                "python -m ia_carmine.cli build_local_ai_enrichment_plan --repo-root . --task docs/LOCAL_AI_TASKS/full-context-ai-npu-golden-path.md --output output/ai_pipeline/full_context_enrichment_plan.json",
                "python -m Tools.validation check_local_ai_enrichment_plan --repo-root . --plan output/ai_pipeline/full_context_enrichment_plan.json --output output/validation/full_context_enrichment_plan.json",
                "git diff --check",
            ],
            stop_conditions=[
                "Do not replace the existing wrapper in the same PR.",
                "Do not execute providers from the helper.",
                "Do not emit source patches from the helper.",
            ],
            suggestion_outputs=[
                suggestion("ia_carmine/context/agent_context/local_ai_enrichment_plan/cli.py"),
                suggestion("Tools/validation/agent_context/check_local_ai_enrichment_plan/cli.py"),
            ],
        ),
        base_proposal(
            pid="P3-FULL-CONTEXT-GOLDEN-DOCS-CONTRACT",
            priority="P3",
            area="documentation",
            title="Document the full-context golden path contract in workflow docs",
            rationale=(
                "The golden path is now operational but spread across task files, validators and wrapper flags. "
                "A stable docs contract will help local runners and master-AI reviews apply it consistently."
            ),
            target_files=[
                "docs/LOCAL_AI_WORKFLOW.md",
                "docs/LOCAL_AI_RUN_BOOTSTRAP.md",
                "docs/AI_DOCS_ENTRYPOINT.md",
            ],
            change_type="docs_contract",
            patch_sketch=[
                "Add a Full-Context Golden Path section to LOCAL_AI_WORKFLOW.",
                "Define required artifacts: selected chunks evidence, context pack evidence, agent state, multistep evidence and golden proposal contract.",
                "Clarify that local outputs remain ignored and only compact evidence is committed.",
                "Link the golden task from the bootstrap and task index.",
            ],
            validation_commands=[
                "python -m Tools.validation check_docs_links --repo-root . --output output/validation/docs_links.json",
                "python -m Tools.validation check_validation_report_contract --repo-root . --output output/validation/validation_report_contract.json",
                "git diff --check",
            ],
            stop_conditions=[
                "Do not weaken AGENTS.md guardrails.",
                "Do not document NPU as primary advisory provider.",
                "Do not require committing output or SQLite files.",
            ],
            suggestion_outputs=[
                suggestion("docs/LOCAL_AI_WORKFLOW.md", "markdown"),
                suggestion("docs/LOCAL_AI_RUN_BOOTSTRAP.md", "markdown"),
                suggestion("docs/AI_DOCS_ENTRYPOINT.md", "markdown"),
            ],
        ),
        base_proposal(
            pid="P4-FULL-CONTEXT-GOLDEN-WRAPPER-PRESET",
            priority="P4",
            area="workflow",
            title="Add optional full-context golden path wrapper preset flag",
            rationale=(
                "The golden run command is long and error-prone. A preset flag can expand to the explicit safe defaults while preserving report-only behavior and explicit provider flags."
            ),
            target_files=[
                "Tools/workflow/_powershell/run_local_ai_task_via_pipeline.ps1",
                "docs/LOCAL_AI_WORKFLOW.md",
            ],
            change_type="wrapper_flag",
            patch_sketch=[
                "Add an opt-in -FullContextGoldenPath switch that sets default basenames, selected chunks, selected chunks evidence and context pack options.",
                "Keep provider execution flags explicit; do not let the preset enable providers by itself.",
                "Record preset activation in the adapter manifest.",
                "Document equivalent expanded command for auditability.",
            ],
            validation_commands=[
                "python -m Tools.workflow run_local_ai_task_via_pipeline -PromptFile docs/LOCAL_AI_TASKS/full-context-ai-npu-golden-path.md -TaskFile docs/LOCAL_AI_TASKS/full-context-ai-npu-golden-path.md -RunDir output/local_ai_runs/full_context_preset_dryrun -FullContextGoldenPath -DryRun",
                "python -m Tools.validation check_validation_report_contract --repo-root . --output output/validation/validation_report_contract.json",
                "git diff --check",
            ],
            stop_conditions=[
                "The preset must not imply UsePrimaryAdvisoryProvider.",
                "The preset must not apply patches.",
                "The preset must not touch Blender runtime files.",
            ],
            suggestion_outputs=[
                suggestion("Tools/workflow/_powershell/run_local_ai_task_via_pipeline.ps1", "powershell"),
                suggestion("docs/LOCAL_AI_WORKFLOW.md", "markdown"),
            ],
        ),
        base_proposal(
            pid="P5-SELECTED-CHUNKS-STANDARD-VALIDATION-BLOCK",
            priority="P5",
            area="validation",
            title="Add selected-chunks evidence to the standard local validation block",
            rationale=(
                "Selected chunks evidence is now available, but golden runs still require manual validation calls. "
                "Standardizing it reduces missed audit artifacts."
            ),
            target_files=[
                "ia_carmine/product/repository_product/github_evidence_bundle/cli.py",
                "docs/LOCAL_AI_WORKFLOW.md",
            ],
            change_type="validator",
            patch_sketch=[
                "Teach the compact evidence bundle builder to discover selected-chunks evidence reports when present.",
                "Add decision fields for selected_chunks_built and selected_chunks_budget_respected.",
                "Document the expected evidence file naming convention.",
            ],
            validation_commands=[
                "python -m ia_carmine.cli build_github_evidence_bundle --repo-root . --basename selected_chunks_standard_block_smoke",
                "python -m Tools.validation check_github_evidence_bundle --repo-root . --output output/validation/github_evidence_bundle.json",
                "git diff --check",
            ],
            stop_conditions=[
                "Do not require selected chunks evidence for non-selected-chunk runs.",
                "Do not include raw output/ai_context_packs files in Git evidence.",
                "Do not execute providers from evidence bundling.",
            ],
            suggestion_outputs=[
                suggestion("ia_carmine/product/repository_product/github_evidence_bundle/cli.py"),
                suggestion("docs/LOCAL_AI_WORKFLOW.md", "markdown"),
            ],
        ),
        base_proposal(
            pid="P6-NPU-KNOWLEDGE-BROKER-CONTEXT-ORACLE",
            priority="P6",
            area="npu_knowledge_broker",
            title="Prototype NPU knowledge-broker / context-oracle helper",
            rationale=(
                "The NPU should help prepare context instead of acting as the final advisory provider. "
                "A report-only helper can rank candidate chunks/docs and emit a bounded context request for validation before Ollama/GPU advisory reasoning."
            ),
            target_files=[
                "Tools/npu/provider_mesh/npu_knowledge_broker_packet/cli.py",
                "Tools/validation/provider_mesh/npu_knowledge_broker_packet/cli.py",
                "docs/LOCAL_AI_WORKFLOW.md",
            ],
            change_type="knowledge_broker",
            patch_sketch=[
                "Create a report-only NPU knowledge broker packet builder that accepts task objective, selected chunks manifest and optional probe metadata.",
                "Emit ranked candidate docs/chunks plus reasons and budget metadata.",
                "Add a validator that enforces no provider advisory promotion, no source writes and no patch application.",
                "Document NPU as retrieval/context-preparation lane, not advisory lane.",
            ],
            validation_commands=[
                'python -m Tools.npu build_npu_knowledge_broker_packet --repo-root . --objective "workflow adapter npu knowledge broker" --output output/ai_pipeline/npu_knowledge_broker_packet.json',
                "python -m Tools.validation check_npu_knowledge_broker_packet --repo-root . --packet output/ai_pipeline/npu_knowledge_broker_packet.json --output output/validation/npu_knowledge_broker_packet.json",
                "git diff --check",
            ],
            stop_conditions=[
                "Do not promote NPU to primary advisory provider.",
                "Do not require NPU provider execution for deterministic packet building.",
                "Do not use OpenVINO GPU as a primary lane.",
                "Do not apply or generate direct source patches from NPU output.",
            ],
            suggestion_outputs=[
                suggestion("Tools/npu/provider_mesh/npu_knowledge_broker_packet/cli.py"),
                suggestion("Tools/validation/provider_mesh/npu_knowledge_broker_packet/cli.py"),
                suggestion("docs/LOCAL_AI_WORKFLOW.md", "markdown"),
            ],
        ),
    ]


def build_payload(repo_root: Path, source_report: str = "") -> dict[str, Any]:
    reports_read: list[str] = []
    source_summary: dict[str, Any] = {}
    if source_report:
        source_path = resolve_repo_path(repo_root, source_report)
        source_summary = read_json_if_present(source_path)
        reports_read.append(repo_relative(source_path, repo_root))

    return {
        "schema_version": 1,
        "kind": PROPOSAL_KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repo_root": repo_root.as_posix(),
        "profile": "full_context_golden",
        "passed": True,
        "provider_execution_performed": False,
        "errors": [],
        "warnings": [],
        "apply_mode": APPLY_MODE,
        "reports_read": reports_read,
        "suggestion_contract": {
            "provider_execution_performed": False,
            "source_mutation_performed": False,
            "apply_mode": APPLY_MODE,
            "apply_allowed_now": False,
        },
        "golden_contract": {
            "required_families": ["P1", "P2", "P3", "P4", "P5", "P6"],
            "npu_role": "knowledge_broker_context_oracle_candidate_not_primary_advisory",
            "source_report_summary_kind": source_summary.get("kind"),
            "source_report_passed": source_summary.get("passed"),
        },
        "proposals": build_proposals(),
    }


def main() -> int:
    try:
        from ia_carmine._shared.full_context_golden_proposals_cli import main as cli_main
    except ModuleNotFoundError:
        from ia_carmine._shared.full_context_golden_proposals_cli import main as cli_main
    return cli_main()


if __name__ == "__main__":
    raise SystemExit(main())
