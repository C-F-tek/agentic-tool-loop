#!/usr/bin/env python3
"""Build a report-only selective execution plan from context and evidence.

The selective planner reads compact Git-trackable evidence and repository
planning docs, then recommends the next validators, patch-spec drafts and local
provider evidence commands. It does not apply patches, execute providers, run
Blender, run FFmpeg or mutate generated indexes.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

PLAN_KIND = "selective_execution_plan"
SCHEMA_VERSION = 1
DEFAULT_CONTEXT_EVIDENCE = (
    "docs/LOCAL_VALIDATION_EVIDENCE/project_self_improvement_context_pack_evidence.json"
)
DEFAULT_CONTEXT_EVIDENCE_MD = (
    "docs/LOCAL_VALIDATION_EVIDENCE/project_self_improvement_context_pack_evidence.md"
)
DEFAULT_DRY_RUN_EVIDENCE = (
    "docs/LOCAL_VALIDATION_EVIDENCE/ai_pipeline_dry_run_matrix_evidence.json"
)
DEFAULT_PROVIDER_EVIDENCE = (
    "docs/LOCAL_VALIDATION_EVIDENCE/parallel_gpu_npu_multistep_real_npu_v2_evidence.json"
)
DEFAULT_VALIDATION_CONTRACT = "output/validation/validation_report_contract.json"
DEFAULT_TECH_DEBT = "docs/TECH_DEBT_TRACKER.md"
DEFAULT_EXECUTION_PLAN_DIR = "docs/EXECUTION_PLANS/active"


def repo_relative(path: Path, repo_root: Path) -> str:
    """Return a stable repo-relative POSIX path when possible."""
    resolved = path.resolve()
    try:
        return resolved.relative_to(repo_root).as_posix()
    except ValueError:
        return resolved.as_posix()


def resolve_repo_path(repo_root: Path, value: str) -> Path:
    """Resolve value under repo_root unless already absolute."""
    path = Path(value)
    if not path.is_absolute():
        path = repo_root / path
    return path.resolve()


def read_json_object(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    """Read a JSON object from path."""
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return None, f"not found: {path}"
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
    except OSError as exc:
        return None, f"read error: {exc}"
    if not isinstance(data, dict):
        return None, f"expected JSON object, got {type(data).__name__}"
    return data, None


def read_text_file(path: Path, max_chars: int = 12000) -> tuple[str | None, str | None, bool]:
    """Read a bounded text file."""
    try:
        text = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return None, f"not found: {path}", False
    except OSError as exc:
        return None, f"read error: {exc}", False
    truncated = len(text) > max_chars
    return text[:max_chars], None, truncated


def summarize_context_evidence(json_path: Path, md_path: Path, repo_root: Path) -> dict[str, Any]:
    """Summarize context-pack evidence from JSON when present, else Markdown."""
    data, error = read_json_object(json_path)
    if data is not None:
        decision = data.get("decision") if isinstance(data.get("decision"), dict) else {}
        return {
            "path": repo_relative(json_path, repo_root),
            "exists": True,
            "json_ok": True,
            "markdown_fallback": False,
            "kind": data.get("kind"),
            "passed": data.get("passed"),
            "provider_execution_performed": data.get("provider_execution_performed"),
            "included_file_count": data.get("included_file_count"),
            "forbidden_path_count": data.get("forbidden_path_count"),
            "source_writes_performed": decision.get("source_writes_performed"),
            "provider_execution_seen": decision.get("provider_execution_seen"),
            "errors": data.get("errors") if isinstance(data.get("errors"), list) else [],
            "warnings": data.get("warnings") if isinstance(data.get("warnings"), list) else [],
        }

    text, text_error, truncated = read_text_file(md_path)
    markdown_passed = text is not None and "- Passed: `True`" in text
    return {
        "path": repo_relative(json_path, repo_root),
        "exists": json_path.exists(),
        "json_ok": False,
        "json_error": error,
        "markdown_path": repo_relative(md_path, repo_root),
        "markdown_exists": md_path.exists(),
        "markdown_fallback": text is not None,
        "markdown_truncated": truncated,
        "kind": "ai_context_pack_evidence",
        "passed": markdown_passed if text is not None else None,
        "provider_execution_performed": False if text and "Provider execution performed: `False`" in text else None,
        "source_writes_performed": False if text and "source_writes_performed`: `False`" in text else None,
        "provider_execution_seen": False if text and "provider_execution_seen`: `False`" in text else None,
        "errors": [error] if error else [],
        "warnings": [f"using Markdown fallback: {repo_relative(md_path, repo_root)}"] if text is not None else [text_error or "context evidence missing"],
    }


def summarize_dry_run_evidence(path: Path, repo_root: Path) -> dict[str, Any]:
    """Summarize dry-run matrix evidence."""
    data, error = read_json_object(path)
    if data is None:
        return {
            "path": repo_relative(path, repo_root),
            "exists": path.exists(),
            "json_ok": False,
            "passed": False,
            "error": error,
            "provider_execution_performed": None,
            "case_count": None,
            "matrix_workers": None,
            "repeat_cases": None,
            "all_steps_planned_only": None,
        }

    matrix = data.get("matrix") if isinstance(data.get("matrix"), dict) else {}
    summary = data.get("case_summary") if isinstance(data.get("case_summary"), dict) else {}
    decision = data.get("decision") if isinstance(data.get("decision"), dict) else {}
    return {
        "path": repo_relative(path, repo_root),
        "exists": True,
        "json_ok": True,
        "kind": data.get("kind"),
        "passed": data.get("passed"),
        "provider_execution_performed": data.get("provider_execution_performed"),
        "case_count": summary.get("case_count"),
        "matrix_workers": matrix.get("matrix_workers"),
        "repeat_cases": matrix.get("repeat_cases"),
        "all_cases_dry_run": decision.get("all_cases_dry_run"),
        "all_steps_planned_only": decision.get("all_steps_planned_only"),
        "gpu_npu_workloads_executed": decision.get("gpu_npu_workloads_executed"),
        "errors": data.get("errors") if isinstance(data.get("errors"), list) else [],
        "warnings": data.get("warnings") if isinstance(data.get("warnings"), list) else [],
    }


def summarize_provider_evidence(path: Path, repo_root: Path) -> dict[str, Any]:
    """Summarize compact provider evidence."""
    data, error = read_json_object(path)
    if data is None:
        return {
            "path": repo_relative(path, repo_root),
            "exists": path.exists(),
            "json_ok": False,
            "passed": False,
            "error": error,
            "provider_execution_seen": False,
            "ollama_gpu_primary_advisory": False,
            "npu_decode_smoke_passed": False,
            "npu_excluded_when_unusable": False,
        }

    decision = data.get("decision") if isinstance(data.get("decision"), dict) else {}
    reports = data.get("reports") if isinstance(data.get("reports"), list) else []
    report_kinds = [
        str(item.get("kind"))
        for item in reports
        if isinstance(item, dict) and item.get("kind")
    ]
    report_pass_count = sum(1 for item in reports if isinstance(item, dict) and item.get("passed") is True)
    return {
        "path": repo_relative(path, repo_root),
        "exists": True,
        "json_ok": True,
        "kind": data.get("kind"),
        "generated_at": data.get("generated_at"),
        "report_count": len(reports),
        "report_pass_count": report_pass_count,
        "report_kinds": sorted(report_kinds),
        "ollama_gpu_primary_advisory": decision.get("ollama_gpu_primary_advisory"),
        "npu_excluded_when_unusable": decision.get("npu_excluded_when_unusable"),
        "provider_execution_seen": decision.get("provider_execution_seen"),
        "npu_decode_smoke_passed": decision.get("npu_decode_smoke_passed"),
    }


def summarize_validation_contract(path: Path, repo_root: Path) -> dict[str, Any]:
    """Summarize validation report contract output if available."""
    data, error = read_json_object(path)
    if data is None:
        return {
            "path": repo_relative(path, repo_root),
            "exists": path.exists(),
            "json_ok": False,
            "passed": None,
            "error": error,
            "warnings": ["validation report contract output is local/ignored and may be absent on GitHub"],
        }
    return {
        "path": repo_relative(path, repo_root),
        "exists": True,
        "json_ok": True,
        "kind": data.get("kind"),
        "passed": data.get("passed"),
        "errors": data.get("errors") if isinstance(data.get("errors"), list) else [],
        "warnings": data.get("warnings") if isinstance(data.get("warnings"), list) else [],
    }


def summarize_execution_plans(plan_dir: Path, repo_root: Path) -> dict[str, Any]:
    """Summarize active execution plans without validating their full contract."""
    plans: list[dict[str, Any]] = []
    if plan_dir.exists():
        for path in sorted(plan_dir.glob("*.md")):
            text, error, truncated = read_text_file(path, max_chars=8000)
            lowered = text.lower() if text else ""
            plans.append(
                {
                    "path": repo_relative(path, repo_root),
                    "exists": True,
                    "truncated": truncated,
                    "mentions_selective_planner": "selective planner" in lowered or "selective_planner" in lowered,
                    "mentions_patch_spec": "patch spec" in lowered or "patch-spec" in lowered,
                    "mentions_context_pack": "context pack" in lowered,
                    "error": error,
                }
            )
    return {
        "path": repo_relative(plan_dir, repo_root),
        "exists": plan_dir.exists(),
        "active_plan_count": len(plans),
        "related_plan_count": sum(1 for item in plans if item["mentions_selective_planner"] or item["mentions_patch_spec"]),
        "plans": plans,
    }


def summarize_tech_debt(path: Path, repo_root: Path) -> dict[str, Any]:
    """Summarize tech-debt markers relevant to this planner."""
    text, error, truncated = read_text_file(path, max_chars=16000)
    lowered = text.lower() if text else ""
    keywords = {
        "selective_planner": "selective planner" in lowered or "selective_planner" in lowered,
        "patch_spec": "patch spec" in lowered or "patch-spec" in lowered,
        "context_pack": "context pack" in lowered,
        "provider_quality_gate": "quality gate" in lowered and ("provider" in lowered or "gpu" in lowered or "npu" in lowered),
    }
    return {
        "path": repo_relative(path, repo_root),
        "exists": path.exists(),
        "read_ok": text is not None,
        "truncated": truncated,
        "keywords": keywords,
        "error": error,
    }


def validator_item(name: str, reason: str, command: str, required: bool = True) -> dict[str, Any]:
    """Build a validator recommendation item."""
    return {
        "name": name,
        "reason": reason,
        "command": command,
        "required": required,
        "execution_scope": "github_or_local",
        "provider_execution_performed": False,
    }


def patch_spec_item(identifier: str, title: str, rationale: str, target_files: list[str], blocked: bool = False) -> dict[str, Any]:
    """Build a report-only patch-spec recommendation."""
    return {
        "id": identifier,
        "title": title,
        "rationale": rationale,
        "target_files": target_files,
        "apply_mode": "manual_review_only",
        "status": "candidate_spec_only",
        "blocked": blocked,
        "provider_execution_performed": False,
        "patch_application_performed": False,
    }


def build_recommendations(
    *,
    context: dict[str, Any],
    dry_run: dict[str, Any],
    provider: dict[str, Any],
    validation: dict[str, Any],
    plans: dict[str, Any],
    tech_debt: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str], list[str], list[str], list[str]]:
    """Build validator, patch-spec and action recommendations."""
    validators: list[dict[str, Any]] = []
    patch_specs: list[dict[str, Any]] = []
    blocked: list[str] = []
    local_only: list[str] = []
    github_only: list[str] = []
    risks: list[str] = []

    validators.append(validator_item(
        "python_syntax",
        "New planner and validator are Python scripts and must compile without imports.",
        r"python .\Tools\validation\check_python_syntax.py --repo-root . --output .\output\validation\python_syntax.json",
    ))
    validators.append(validator_item(
        "ai_context_pack_contract",
        "The selective planner depends on context-pack evidence as its first input.",
        r"python .\Tools\validation\check_ai_context_pack_contract.py --repo-root . --pack .\output\ai_context_packs\project_self_improvement.json --evidence .\docs\LOCAL_VALIDATION_EVIDENCE\project_self_improvement_context_pack_evidence.json --output .\output\validation\ai_context_pack_contract.json",
    ))
    validators.append(validator_item(
        "dry_run_matrix_evidence_bundle",
        "Dry-run evidence must remain planned-only and must not imply provider execution.",
        r"python .\Tools\validation\check_dry_run_matrix_evidence_bundle.py --repo-root . --evidence .\docs\LOCAL_VALIDATION_EVIDENCE\ai_pipeline_dry_run_matrix_evidence.json --output .\output\validation\dry_run_matrix_evidence_bundle.json",
    ))
    validators.append(validator_item(
        "github_evidence_bundle",
        "Provider evidence must keep Ollama/GPU and OpenVINO/NPU roles explicit.",
        r"python .\Tools\validation\check_github_evidence_bundle.py --repo-root . --output .\output\validation\github_evidence_bundle.json",
    ))
    validators.append(validator_item(
        "selective_execution_plan",
        "Validate the report-only planner output contract before using it for next-step selection.",
        r"python .\Tools\validation\check_selective_execution_plan.py --repo-root . --plan .\output\ai_pipeline\selective_execution_plan.json --output .\output\validation\selective_execution_plan.json",
    ))
    validators.append(validator_item(
        "validation_report_contract",
        "Keep the new validator aligned with common validation report fields.",
        r"python .\Tools\validation\check_validation_report_contract.py --repo-root . --output .\output\validation\validation_report_contract.json",
    ))

    if context.get("passed") is not True:
        blocked.append("context pack evidence is missing or not passing; do not generate patch specs from incomplete context")
        risks.append("Planner may fall back to Markdown context evidence when JSON evidence is unavailable.")
    if dry_run.get("passed") is not True or dry_run.get("all_steps_planned_only") is not True:
        blocked.append("dry-run matrix evidence is not clean; do not recommend provider promotion or patch-spec generation")
    if provider.get("provider_execution_seen") is not True:
        blocked.append("real provider evidence is missing; do not promote advisory provider state")
        local_only.append("Generate new real GPU/NPU evidence with the explicit PowerShell command set.")
    if provider.get("ollama_gpu_primary_advisory") is not True:
        blocked.append("Ollama/GPU is not quality-gated as primary advisory in current evidence")
    if provider.get("npu_excluded_when_unusable") is not True:
        risks.append("NPU advisory exclusion decision is absent or false; keep NPU limited to probe/guardrail/decode diagnostic.")
    if validation.get("passed") is not True:
        risks.append("validation_report_contract output is absent or not passing in this checkout; rerun locally after planner generation.")

    patch_specs.append(patch_spec_item(
        "selective-planner-v2-validator-ranking",
        "Selective planner v2: score and rank validators",
        "Current prototype emits deterministic validator recommendations; next patch spec should add scoring without executing validators.",
        ["Tools/ai/build_selective_execution_plan.py", "docs/AI_SELECTIVE_PLANNER.md"],
        blocked=False,
    ))
    patch_specs.append(patch_spec_item(
        "provider-evidence-quality-gates",
        "Formal provider evidence quality gate spec",
        "Real GPU/NPU evidence exists but promotion criteria should be made explicit before changing provider behavior.",
        ["docs/LOCAL_AI_WORKFLOW.md", "docs/JSON_SCHEMAS.md", "Tools/validation/check_github_evidence_bundle.py"],
        blocked=provider.get("provider_execution_seen") is not True,
    ))
    patch_specs.append(patch_spec_item(
        "patch-spec-generator-integration",
        "Patch spec generator integration from selective plan",
        "After this report-only planner is validated, a future tool can convert recommended_patch_specs into draft patch specs.",
        ["Tools/ai/build_patch_specs_from_proposals.py", "Tools/validation/check_patch_spec_drafts.py"],
        blocked=context.get("passed") is not True or dry_run.get("passed") is not True,
    ))

    github_only.extend([
        "Review committed context-pack, dry-run and provider evidence summaries.",
        "Update docs and validators only; do not modify Blender runtime or generated indexes manually.",
        "Open small PRs that add report-only tooling and explicit local command sets.",
    ])
    local_only.extend([
        "Run explicit GPU/NPU provider workflow only when new evidence is needed.",
        "Commit compact evidence bundles under docs/LOCAL_VALIDATION_EVIDENCE/ after local execution.",
    ])

    if plans.get("related_plan_count", 0) == 0:
        risks.append("No active execution plan currently appears tied to selective planner work.")
    if not any(tech_debt.get("keywords", {}).values()):
        risks.append("Tech debt tracker does not yet expose strong selective-planner markers.")

    return validators, patch_specs, blocked, local_only, github_only, risks


def command_sets() -> dict[str, list[str]]:
    """Return copy-pasteable command sets."""
    return {
        "build_and_validate_selective_plan": [
            r"python .\Tools\ai\build_ai_context_pack.py --repo-root . --profile project_self_improvement",
            r"python .\Tools\ai\build_selective_execution_plan.py --repo-root . --output .\output\ai_pipeline\selective_execution_plan.json --markdown-output .\output\ai_pipeline\selective_execution_plan.md",
            r"python .\Tools\validation\check_selective_execution_plan.py --repo-root . --plan .\output\ai_pipeline\selective_execution_plan.json --output .\output\validation\selective_execution_plan.json",
        ],
        "real_gpu_npu_evidence_for_carmine": [
            r"powershell.exe -ExecutionPolicy Bypass -File .\Tools\workflow\run_parallel_ai_provider_multistep.ps1 `",
            r"  -Profile npu `",
            r"  -RunOllamaProbe `",
            r"  -RunNpuProbe `",
            r"  -RunNpuDecodeSmoke `",
            r"  -UsePrimaryAdvisoryProvider `",
            r"  -Basename parallel_gpu_npu_selective_planner_real `",
            r"  -ProposalBasename parallel_gpu_npu_selective_planner_real_proposals `",
            r"  -EvidenceBasename parallel_gpu_npu_selective_planner_real_evidence",
            r"python .\Tools\ai\build_github_evidence_bundle.py --repo-root . --basename parallel_gpu_npu_selective_planner_real_evidence",
            r"python .\Tools\validation\check_github_evidence_bundle.py --repo-root . --output .\output\validation\github_evidence_bundle.json",
            r"python .\Tools\validation\check_validation_report_contract.py --repo-root . --output .\output\validation\validation_report_contract.json",
        ],
        "minimum_pr_validation": [
            r"python .\Tools\validation\check_python_syntax.py --repo-root . --output .\output\validation\python_syntax.json",
            r"python .\Tools\validation\check_json_artifacts.py --repo-root . --output .\output\validation\json_artifacts.json",
            r"python .\Tools\validation\check_docs_links.py --repo-root . --output .\output\validation\docs_links.json",
            r"python .\Tools\validation\check_execution_plan_status.py --repo-root . --output .\output\validation\execution_plan_status.json",
            r"python .\Tools\validation\check_validation_report_contract.py --repo-root . --output .\output\validation\validation_report_contract.json",
            "git diff --check",
        ],
    }


def build_plan(args: argparse.Namespace) -> dict[str, Any]:
    """Build the selective execution plan."""
    repo_root = Path(args.repo_root).resolve()
    context_json = resolve_repo_path(repo_root, args.context_pack_evidence)
    context_md = resolve_repo_path(repo_root, args.context_pack_evidence_md)
    dry_run_path = resolve_repo_path(repo_root, args.dry_run_evidence)
    provider_path = resolve_repo_path(repo_root, args.provider_evidence)
    validation_path = resolve_repo_path(repo_root, args.validation_report_contract)
    plan_dir = resolve_repo_path(repo_root, args.execution_plan_dir)
    tech_debt_path = resolve_repo_path(repo_root, args.tech_debt)

    context = summarize_context_evidence(context_json, context_md, repo_root)
    dry_run = summarize_dry_run_evidence(dry_run_path, repo_root)
    provider = summarize_provider_evidence(provider_path, repo_root)
    validation = summarize_validation_contract(validation_path, repo_root)
    plans = summarize_execution_plans(plan_dir, repo_root)
    tech_debt = summarize_tech_debt(tech_debt_path, repo_root)

    validators, patch_specs, blocked, local_only, github_only, risks = build_recommendations(
        context=context,
        dry_run=dry_run,
        provider=provider,
        validation=validation,
        plans=plans,
        tech_debt=tech_debt,
    )

    warnings: list[str] = []
    for section in (context, dry_run, provider, validation, tech_debt):
        raw_warnings = section.get("warnings")
        if isinstance(raw_warnings, list):
            warnings.extend(str(item) for item in raw_warnings)
    errors: list[str] = []

    passed = (
        context.get("passed") is True
        and dry_run.get("passed") is True
        and dry_run.get("all_steps_planned_only") is True
        and provider.get("provider_execution_seen") is True
        and provider.get("ollama_gpu_primary_advisory") is True
        and provider.get("npu_excluded_when_unusable") is True
        and not errors
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": PLAN_KIND,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "repo_root": str(repo_root),
        "apply_mode": "report_only",
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "inputs": {
            "context_pack_evidence": context,
            "dry_run_matrix_evidence": dry_run,
            "latest_gpu_npu_evidence": provider,
            "validation_report_contract": validation,
            "execution_plan_status": plans,
            "tech_debt_tracker": tech_debt,
        },
        "provider_evidence_summary": provider,
        "dry_run_summary": dry_run,
        "validation_health": validation,
        "recommended_validators": validators,
        "recommended_patch_specs": patch_specs,
        "blocked_actions": blocked,
        "local_only_actions_for_carmine": local_only,
        "github_only_actions_for_ai": github_only,
        "risks": risks,
        "next_command_set": command_sets(),
        "passed": passed,
        "errors": errors,
        "warnings": warnings,
    }


def render_markdown(plan: dict[str, Any]) -> str:
    """Render a human-readable Markdown report."""
    provider = plan.get("provider_evidence_summary", {})
    dry_run = plan.get("dry_run_summary", {})
    lines = [
        "# Selective Execution Plan",
        "",
        f"- Generated at: `{plan.get('generated_at')}`",
        f"- Kind: `{plan.get('kind')}`",
        f"- Passed: `{plan.get('passed')}`",
        f"- Apply mode: `{plan.get('apply_mode')}`",
        f"- Provider execution performed: `{plan.get('provider_execution_performed')}`",
        f"- Patch application performed: `{plan.get('patch_application_performed')}`",
        "",
        "## Evidence Summary",
        "",
        f"- Context evidence passed: `{plan['inputs']['context_pack_evidence'].get('passed')}`",
        f"- Dry-run evidence passed: `{dry_run.get('passed')}`",
        f"- Dry-run case count: `{dry_run.get('case_count')}`",
        f"- Dry-run planned-only: `{dry_run.get('all_steps_planned_only')}`",
        f"- Provider execution seen: `{provider.get('provider_execution_seen')}`",
        f"- Ollama/GPU primary advisory: `{provider.get('ollama_gpu_primary_advisory')}`",
        f"- NPU decode smoke passed: `{provider.get('npu_decode_smoke_passed')}`",
        "",
        "## Recommended Validators",
        "",
    ]
    for item in plan.get("recommended_validators", []):
        lines.append(f"- `{item.get('name')}`: {item.get('reason')}")
        lines.append(f"  - Command: `{item.get('command')}`")
    lines.extend(["", "## Recommended Patch Specs", ""])
    for item in plan.get("recommended_patch_specs", []):
        lines.append(f"- `{item.get('id')}`: {item.get('title')} (blocked: `{item.get('blocked')}`)")
        lines.append(f"  - Rationale: {item.get('rationale')}")
        lines.append(f"  - Targets: `{', '.join(item.get('target_files', []))}`")
    lines.extend(["", "## Blocked Actions", ""])
    if plan.get("blocked_actions"):
        for item in plan["blocked_actions"]:
            lines.append(f"- {item}")
    else:
        lines.append("None.")
    lines.extend(["", "## Local-only Actions for Carmine", ""])
    for item in plan.get("local_only_actions_for_carmine", []):
        lines.append(f"- {item}")
    lines.extend(["", "## GitHub-only Actions for AI", ""])
    for item in plan.get("github_only_actions_for_ai", []):
        lines.append(f"- {item}")
    lines.extend(["", "## Next Command Sets", ""])
    for name, commands in plan.get("next_command_set", {}).items():
        lines.append(f"### {name}")
        lines.append("")
        lines.append("```powershell")
        lines.extend(commands)
        lines.append("```")
        lines.append("")
    lines.extend(["## Risks", ""])
    if plan.get("risks"):
        for item in plan["risks"]:
            lines.append(f"- {item}")
    else:
        lines.append("None.")
    lines.extend(["", "## Warnings", ""])
    if plan.get("warnings"):
        for item in plan["warnings"]:
            lines.append(f"- {item}")
    else:
        lines.append("None.")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--context-pack-evidence", default=DEFAULT_CONTEXT_EVIDENCE)
    parser.add_argument("--context-pack-evidence-md", default=DEFAULT_CONTEXT_EVIDENCE_MD)
    parser.add_argument("--dry-run-evidence", default=DEFAULT_DRY_RUN_EVIDENCE)
    parser.add_argument("--provider-evidence", default=DEFAULT_PROVIDER_EVIDENCE)
    parser.add_argument("--validation-report-contract", default=DEFAULT_VALIDATION_CONTRACT)
    parser.add_argument("--execution-plan-dir", default=DEFAULT_EXECUTION_PLAN_DIR)
    parser.add_argument("--tech-debt", default=DEFAULT_TECH_DEBT)
    parser.add_argument("--output", default="output/ai_pipeline/selective_execution_plan.json")
    parser.add_argument("--markdown-output", default="output/ai_pipeline/selective_execution_plan.md")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    plan = build_plan(args)

    output = resolve_repo_path(repo_root, args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    markdown_output = resolve_repo_path(repo_root, args.markdown_output)
    markdown_output.parent.mkdir(parents=True, exist_ok=True)
    markdown_output.write_text(render_markdown(plan), encoding="utf-8")

    print(json.dumps({
        "passed": plan["passed"],
        "kind": plan["kind"],
        "output": repo_relative(output, repo_root),
        "markdown_output": repo_relative(markdown_output, repo_root),
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "recommended_validator_count": len(plan["recommended_validators"]),
        "recommended_patch_spec_count": len(plan["recommended_patch_specs"]),
    }, indent=2, ensure_ascii=False))
    return 0 if plan["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
