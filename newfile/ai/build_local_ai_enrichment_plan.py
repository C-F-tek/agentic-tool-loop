#!/usr/bin/env python3
"""Build a deterministic local AI enrichment plan.

The plan is report-only and does not execute providers or apply patches. It
converts a task objective into a bounded sequence of enrichment steps and lane
scheduling decisions. For complex tasks the plan can require Ollama/GPU advisory
first and delay NPU knowledge-broker work until after the GPU output is ready,
so the NPU lane does not block the rest of the run.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PLAN_KIND = "local_ai_enrichment_plan"
APPLY_MODE = "report_only"

COMPLEXITY_TERMS = {
    "complex",
    "complesso",
    "heavy",
    "multistep",
    "multi-step",
    "provider",
    "gpu",
    "ollama",
    "npu",
    "knowledge",
    "broker",
    "context",
    "oracle",
    "patch",
    "validator",
    "wrapper",
    "architecture",
    "full-context",
}


def repo_relative(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root).as_posix()
    except ValueError:
        return path.as_posix()


def resolve_repo_path(repo_root: Path, raw: str) -> Path:
    path = Path(raw)
    return path.resolve() if path.is_absolute() else (repo_root / path).resolve()


def read_text_if_present(path: Path, limit: int = 8000) -> str:
    if not path.exists() or not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8-sig")[:limit]
    except OSError:
        return ""


def normalize_path(value: Any) -> str:
    return str(value or "").strip().replace("\\", "/")


def objective_terms(text: str) -> set[str]:
    return {term.strip(".,:;()[]{}'\"").lower() for term in text.replace("/", " ").replace("_", " ").split() if len(term.strip(".,:;()[]{}'\"")) >= 3}


def estimate_complexity(objective: str, task_text: str, profile: str) -> dict[str, Any]:
    terms = objective_terms(objective + " " + task_text)
    matched = sorted(terms & COMPLEXITY_TERMS)
    score = len(matched)
    if profile == "npu":
        score += 1
    if len(task_text) > 5000:
        score += 2
    if "full-context" in terms or "golden" in terms:
        score += 2
    if "patch" in terms or "validator" in terms:
        score += 1
    level = "low"
    if score >= 7:
        level = "high"
    elif score >= 3:
        level = "medium"
    return {
        "level": level,
        "score": score,
        "matched_terms": matched,
        "task_text_chars_sampled": len(task_text),
    }


def make_step(
    step_id: str,
    title: str,
    tool_hint: str,
    timing: str,
    lane: str,
    depends_on: list[str] | None = None,
    outputs: list[str] | None = None,
    provider_execution_required: bool = False,
    source_writes_performed: bool = False,
    patch_application_performed: bool = False,
) -> dict[str, Any]:
    return {
        "id": step_id,
        "title": title,
        "tool_hint": tool_hint,
        "timing": timing,
        "lane": lane,
        "depends_on": depends_on or [],
        "outputs": outputs or [],
        "provider_execution_required": provider_execution_required,
        "source_writes_performed": source_writes_performed,
        "patch_application_performed": patch_application_performed,
    }


def build_steps(profile: str, complexity: dict[str, Any], basename: str) -> list[dict[str, Any]]:
    high_or_medium = complexity["level"] in {"medium", "high"}
    steps: list[dict[str, Any]] = [
        make_step(
            "read_contracts",
            "Read AGENTS and local AI run bootstrap contracts",
            "manual_or_runner_context",
            "immediate",
            "control",
            outputs=["contract_understanding"],
        ),
        make_step(
            "build_semantic_chunks",
            "Build or refresh semantic chunk index",
            "Tools/npu/build_semantic_code_chunks.py",
            "after_step:read_contracts",
            "cpu_indexing",
            depends_on=["read_contracts"],
            outputs=["indexAI/code_chunks/semantic_code_chunks.json", "indexAI/code_chunks/semantic_code_chunks_manifest.json"],
        ),
        make_step(
            "select_semantic_chunks",
            "Select focused semantic chunks for the objective",
            "Tools/ai/select_semantic_code_chunks.py",
            "after_step:build_semantic_chunks",
            "cpu_selection",
            depends_on=["build_semantic_chunks"],
            outputs=[f"output/ai_context_packs/{basename}_selected_chunks.json", f"output/ai_context_packs/{basename}_selected_chunks.md"],
        ),
        make_step(
            "validate_selected_chunks",
            "Validate selected chunk budget and guardrails",
            "Tools/validation/check_selected_semantic_chunks.py",
            "after_step:select_semantic_chunks",
            "validation",
            depends_on=["select_semantic_chunks"],
            outputs=[f"output/validation/{basename}_selected_chunks_contract.json"],
        ),
        make_step(
            "build_context_pack",
            "Build bounded core context pack",
            "Tools/ai/build_ai_context_pack.py",
            "after_step:validate_selected_chunks",
            "cpu_context",
            depends_on=["validate_selected_chunks"],
            outputs=[f"output/ai_context_packs/{basename}_context_pack.json", f"output/ai_context_packs/{basename}_context_pack.md"],
        ),
        make_step(
            "build_agent_state",
            "Build SQLite-backed agent state packet without committing the DB",
            "Tools/ai/build_agent_state_packet.py",
            "after_step:build_context_pack",
            "cpu_memory_packet",
            depends_on=["build_context_pack"],
            outputs=[f"output/local_ai_runs/<run>/pipeline/agent_state/{basename}_agent_state.json"],
        ),
    ]

    if high_or_medium:
        steps.append(
            make_step(
                "ollama_gpu_advisory_first",
                "Run primary Ollama/GPU advisory before optional NPU broker follow-up",
                "Tools/workflow/run_parallel_ai_provider_multistep.ps1",
                "after_step:build_agent_state",
                "ollama_gpu_primary_advisory",
                depends_on=["build_agent_state"],
                outputs=[f"output/local_ai_runs/<run>/pipeline/{basename}_multistep_proposals.json"],
                provider_execution_required=True,
            )
        )
        steps.append(
            make_step(
                "npu_knowledge_broker_after_gpu",
                "Build NPU knowledge-broker packet after GPU advisory is available so NPU does not block the main advisory lane",
                "Tools/npu/build_npu_knowledge_broker_packet.py",
                "after_step:ollama_gpu_advisory_first",
                "npu_context_broker",
                depends_on=["ollama_gpu_advisory_first", "validate_selected_chunks"],
                outputs=[f"output/ai_pipeline/{basename}_npu_knowledge_broker_packet.json"],
            )
        )
    else:
        steps.append(
            make_step(
                "npu_knowledge_broker_parallel",
                "Build NPU knowledge-broker packet in parallel with non-provider context preparation",
                "Tools/npu/build_npu_knowledge_broker_packet.py",
                "after_step:validate_selected_chunks",
                "npu_context_broker",
                depends_on=["validate_selected_chunks"],
                outputs=[f"output/ai_pipeline/{basename}_npu_knowledge_broker_packet.json"],
            )
        )
        steps.append(
            make_step(
                "optional_ollama_gpu_advisory",
                "Optional Ollama/GPU advisory only if explicitly requested",
                "Tools/workflow/run_parallel_ai_provider_multistep.ps1",
                "explicit_only",
                "ollama_gpu_primary_advisory",
                depends_on=["build_agent_state", "npu_knowledge_broker_parallel"],
                outputs=[f"output/local_ai_runs/<run>/pipeline/{basename}_multistep_proposals.json"],
                provider_execution_required=False,
            )
        )

    steps.extend(
        [
            make_step(
                "validate_adapter_manifest",
                "Validate local AI adapter manifest consistency",
                "Tools/validation/check_local_ai_adapter_manifest.py",
                "after_step:build_agent_state",
                "validation",
                depends_on=["build_agent_state"],
                outputs=[f"output/validation/{basename}_adapter_manifest_contract.json"],
            ),
            make_step(
                "validate_npu_broker_packet",
                "Validate NPU knowledge-broker packet contract",
                "Tools/validation/check_npu_knowledge_broker_packet.py",
                "after_step:npu_knowledge_broker_after_gpu" if high_or_medium else "after_step:npu_knowledge_broker_parallel",
                "validation",
                depends_on=["npu_knowledge_broker_after_gpu" if high_or_medium else "npu_knowledge_broker_parallel"],
                outputs=[f"output/validation/{basename}_npu_knowledge_broker_packet_contract.json"],
            ),
            make_step(
                "generate_manual_review_proposals",
                "Generate manual-review-only proposals from enriched context",
                "Tools/ai/build_full_context_golden_proposals.py",
                "after_validations",
                "cpu_proposal_generation",
                depends_on=["validate_adapter_manifest", "validate_npu_broker_packet"],
                outputs=[f"output/ai_pipeline/{basename}_proposals.json"],
            ),
        ]
    )
    return steps


def build_plan(repo_root: Path, objective: str, task_file: str, profile: str, basename: str) -> dict[str, Any]:
    task_path = resolve_repo_path(repo_root, task_file) if task_file else None
    task_text = read_text_if_present(task_path) if task_path else ""
    complexity = estimate_complexity(objective, task_text, profile)
    steps = build_steps(profile, complexity, basename)
    return {
        "schema_version": 1,
        "kind": PLAN_KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repo_root": repo_root.as_posix(),
        "objective": objective,
        "task_file": repo_relative(task_path, repo_root) if task_path else "",
        "profile": profile,
        "basename": basename,
        "apply_mode": APPLY_MODE,
        "provider_execution_performed": False,
        "source_writes_performed": False,
        "patch_application_performed": False,
        "complexity": complexity,
        "lane_policy": {
            "primary_advisory_provider": "ollama_gpu",
            "npu_role": "knowledge_broker_context_oracle",
            "npu_promoted_to_advisory": False,
            "openvino_gpu_primary_lane": False,
            "complex_task_policy": "ollama_gpu_advisory_first_then_npu_broker_after_gpu_result",
            "simple_task_policy": "npu_broker_can_run_after_selected_chunks_without_blocking_optional_gpu_advisory",
        },
        "steps": steps,
        "step_count": len(steps),
        "warnings": [],
        "errors": [],
    }


def render_markdown(plan: dict[str, Any]) -> str:
    lines = [
        "# Local AI Enrichment Plan",
        "",
        f"- Objective: {plan['objective']}",
        f"- Profile: `{plan['profile']}`",
        f"- Complexity: `{plan['complexity']['level']}` / score `{plan['complexity']['score']}`",
        f"- Apply mode: `{plan['apply_mode']}`",
        f"- Provider execution performed: `{plan['provider_execution_performed']}`",
        f"- Step count: `{plan['step_count']}`",
        "",
        "## Lane policy",
        "",
    ]
    for key, value in plan["lane_policy"].items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## Steps", ""])
    for step in plan["steps"]:
        lines.append(f"### {step['id']}: {step['title']}")
        lines.append(f"- Lane: `{step['lane']}`")
        lines.append(f"- Timing: `{step['timing']}`")
        lines.append(f"- Tool: `{step['tool_hint']}`")
        lines.append(f"- Depends on: `{', '.join(step['depends_on'])}`")
        lines.append(f"- Provider required: `{step['provider_execution_required']}`")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--objective", required=True)
    parser.add_argument("--task-file", default="")
    parser.add_argument("--profile", choices=("docs", "core", "npu"), default="docs")
    parser.add_argument("--basename", default="local_ai_enrichment_plan")
    parser.add_argument("--output", default="output/ai_pipeline/local_ai_enrichment_plan.json")
    parser.add_argument("--markdown-output", default="output/ai_pipeline/local_ai_enrichment_plan.md")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    plan = build_plan(repo_root, args.objective, args.task_file, args.profile, args.basename)
    output = resolve_repo_path(repo_root, args.output)
    markdown_output = resolve_repo_path(repo_root, args.markdown_output)
    output.parent.mkdir(parents=True, exist_ok=True)
    markdown_output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    markdown_output.write_text(render_markdown(plan), encoding="utf-8")
    print(json.dumps({
        "passed": True,
        "kind": PLAN_KIND,
        "complexity": plan["complexity"],
        "step_count": plan["step_count"],
        "output": repo_relative(output, repo_root),
        "markdown_output": repo_relative(markdown_output, repo_root),
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
