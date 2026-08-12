#!/usr/bin/env python3
"""Build task-scoped AI context packs for project self-improvement.

Context packs are local, report-only artifacts. They collect a bounded set of
repository files, validation commands and stop conditions for a specific task
profile so a human or AI assistant can start from the right context without
reading generated indexes or unrelated Blender runtime files.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from Tools.validation.report_utils import physical_line_count
except ImportError:
    repo_root_for_import = Path(__file__).resolve().parents[2]
    if str(repo_root_for_import) not in sys.path:
        sys.path.insert(0, str(repo_root_for_import))
    from Tools.validation.report_utils import physical_line_count

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
            {"path": "Tools/validation/README.md", "role": "validation_commands"},
            {"path": "Tools/ai/build_repository_change_proposals.py", "role": "proposal_builder"},
            {"path": "Tools/ai/build_patch_specs_from_proposals.py", "role": "draft_patch_spec_builder"},
            {"path": "Tools/ai/promote_patch_spec_draft.py", "role": "reviewed_patch_spec_builder"},
        ],
        "optional_files": [
            {"path": "docs/TECH_DEBT_TRACKER.md", "role": "debt_tracker"},
            {"path": "docs/LOCAL_VALIDATION_EVIDENCE/patch_spec_review_promotion_gpu_npu_multistep_evidence.md", "role": "latest_patch_spec_evidence"},
            {"path": "docs/GITHUB_ONLY_AI_CONTINUATION_GUIDE.md", "role": "github_only_mode"},
        ],
        "validation_commands": [
            "python .\\Tools\\validation\\check_python_syntax.py --repo-root . --output .\\output\\validation\\python_syntax.json",
            "python .\\Tools\\validation\\check_ai_context_pack_contract.py --repo-root . --pack .\\output\\ai_context_packs\\project_self_improvement.json --evidence .\\docs\\LOCAL_VALIDATION_EVIDENCE\\project_self_improvement_context_pack_evidence.json --output .\\output\\validation\\ai_context_pack_contract.json",
            "python .\\Tools\\validation\\check_json_artifacts.py --repo-root . --output .\\output\\validation\\json_artifacts.json",
            "python .\\Tools\\validation\\check_docs_links.py --repo-root . --output .\\output\\validation\\docs_links.json",
            "python .\\Tools\\validation\\check_validation_report_contract.py --repo-root . --output .\\output\\validation\\validation_report_contract.json",
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
            {"path": "Tools/ai/build_workload_quality_lane_routing.py", "role": "lane_routing"},
            {"path": "Tools/ai/suggest_repository_updates.py", "role": "advisory_packet"},
            {"path": "Tools/ai/build_github_evidence_bundle.py", "role": "evidence_builder"},
            {"path": "Tools/validation/README.md", "role": "validation_commands"},
        ],
        "optional_files": [
            {"path": "docs/LOCAL_VALIDATION_EVIDENCE/parallel_gpu_npu_multistep_real_npu_v2_evidence.md", "role": "baseline_evidence"},
            {"path": "docs/TECH_DEBT_TRACKER.md", "role": "debt_tracker"},
        ],
        "validation_commands": [
            "python .\\Tools\\validation\\check_python_syntax.py --repo-root . --output .\\output\\validation\\python_syntax.json",
            "python .\\Tools\\validation\\check_json_artifacts.py --repo-root . --output .\\output\\validation\\json_artifacts.json",
            "python .\\Tools\\validation\\check_validation_report_contract.py --repo-root . --output .\\output\\validation\\validation_report_contract.json",
        ],
        "stop_conditions": [
            "Use the explicit multistep runner before making provider-lane claims.",
        ],
    },
    "npu_provider_diagnostics": {
        "description": "NPU/OpenVINO probe, guardrail and decode diagnostic context.",
        "required_files": [
            {"path": "docs/LOCAL_AI_WORKFLOW.md", "role": "ai_workflow"},
            {"path": "docs/DATA_FLOW.md", "role": "data_flow"},
            {"path": "Tools/ai/run_local_provider_probe.py", "role": "provider_probe"},
            {"path": "Tools/ai/run_npu_decode_smoke_diagnostic.py", "role": "npu_decode_smoke"},
            {"path": "Tools/validation/check_npu_decode_quality_remediation.py", "role": "npu_remediation"},
            {"path": "Tools/npu/pipeline/providers.py", "role": "provider_envelopes"},
            {"path": "Tools/validation/README.md", "role": "validation_commands"},
        ],
        "optional_files": [
            {"path": "docs/LOCAL_VALIDATION_EVIDENCE/parallel_gpu_npu_multistep_real_npu_v2_evidence.md", "role": "baseline_evidence"},
        ],
        "validation_commands": [
            "python .\\Tools\\validation\\check_ai_workload_report_quality.py --repo-root . --output .\\output\\validation\\ai_workload_report_quality.json",
            "python .\\Tools\\ai\\build_workload_quality_lane_routing.py --repo-root . --output .\\output\\validation\\ai_workload_quality_lane_routing.json --markdown-output .\\output\\validation\\ai_workload_quality_lane_routing.md",
            "python .\\Tools\\validation\\check_npu_decode_quality_remediation.py --repo-root . --output .\\output\\validation\\npu_decode_quality_remediation.json",
        ],
        "stop_conditions": [
            "Do not promote NPU to advisory from decode smoke alone.",
            "Do not change model or prompt settings in a diagnostics-only context task.",
        ],
    },
    "artifact_pipeline": {
        "description": "AI artifact pipeline, dry-run matrix and refactor-status context.",
        "required_files": [
            {"path": "docs/AI_PIPELINE_ARCHITECTURE.md", "role": "pipeline_architecture"},
            {"path": "docs/AI_PIPELINE_REFACTOR_STATUS.md", "role": "pipeline_refactor_status"},
            {"path": "docs/AI_ARTIFACT_SCHEMAS.md", "role": "artifact_schema_notes"},
            {"path": "Tools/ai/pipeline/refactor_status.py", "role": "machine_readable_status"},
            {"path": "Tools/ai/run_pipeline_dry_run_matrix.py", "role": "dry_run_matrix"},
            {"path": "Tools/validation/check_refactor_status_consistency.py", "role": "status_validator"},
            {"path": "Tools/validation/README.md", "role": "validation_commands"},
        ],
        "optional_files": [
            {"path": "Tools/ai/pipeline/markdown_report.py", "role": "markdown_report"},
        ],
        "validation_commands": [
            "python .\\Tools\\validation\\check_refactor_status_consistency.py --repo-root . --output .\\output\\validation\\refactor_status_consistency.json",
            "python .\\Tools\\validation\\check_ai_pipeline_modules.py --repo-root . --output .\\output\\validation\\ai_pipeline_modules.json",
            "python .\\Tools\\ai\\run_pipeline_dry_run_matrix.py --repo-root . --continue-on-error",
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
            {"path": "Tools/validation/README.md", "role": "validation_commands"},
        ],
        "optional_files": [
            {"path": "docs/TECH_DEBT_TRACKER.md", "role": "debt_tracker"},
        ],
        "validation_commands": [
            "python .\\Tools\\validation\\check_docs_links.py --repo-root . --output .\\output\\validation\\docs_links.json",
            "python .\\Tools\\validation\\check_json_artifacts.py --repo-root . --output .\\output\\validation\\json_artifacts.json",
            "python .\\Tools\\validation\\check_execution_plan_status.py --repo-root . --output .\\output\\validation\\execution_plan_status.json",
        ],
        "stop_conditions": [
            "Do not claim local GPU/NPU validation from a docs-only task.",
        ],
    },
}


def resolve_repo_path(repo_root: Path, raw: str) -> Path:
    path = Path(raw)
    if path.is_absolute():
        return path.resolve()
    return (repo_root / path).resolve()


def repo_relative(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root).as_posix()
    except ValueError:
        return path.as_posix()


def normalize_repo_path(value: Any) -> str:
    return str(value or "").strip().replace("\\", "/")


def sanitize_filename(value: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    sanitized = sanitized.strip("._-")
    return sanitized or "ai_context_pack"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def context_unavailable_reason(entry: dict[str, Any]) -> str:
    """Return the most specific reason a context entry is unavailable."""
    return str(entry.get("policy_error") or entry.get("read_error") or "")


def path_escapes_repo(repo_root: Path, path: Path) -> bool:
    """Return true when a resolved path is outside the repository root."""
    try:
        path.relative_to(repo_root)
    except ValueError:
        return True
    return False


def path_policy_error(path: str) -> str | None:
    normalized = normalize_repo_path(path)
    if not normalized:
        return "empty path"
    if Path(normalized).is_absolute():
        return "absolute paths are not allowed in context profiles"
    if normalized in FORBIDDEN_PATH_EXACT:
        return f"forbidden exact path: {normalized}"
    if any(normalized.startswith(prefix) for prefix in FORBIDDEN_PATH_PREFIXES):
        return f"forbidden path prefix: {normalized}"
    lower = normalized.lower()
    if any(fragment in lower for fragment in FORBIDDEN_PATH_FRAGMENTS) and lower.endswith(".json"):
        return f"forbidden full-analysis JSON path: {normalized}"
    if "*" in normalized or normalized.endswith("/"):
        return "context profile entries must be concrete files"
    return None


def safe_read_text(path: Path) -> tuple[str | None, str | None]:
    try:
        return path.read_text(encoding="utf-8-sig"), None
    except UnicodeDecodeError as exc:
        return None, f"text decode failed: {exc}"
    except OSError as exc:
        return None, str(exc)


def build_file_entry(
    *,
    repo_root: Path,
    item: dict[str, Any],
    required: bool,
    remaining_chars: int,
    max_file_chars: int,
) -> tuple[dict[str, Any], int]:
    raw_path = normalize_repo_path(item.get("path"))
    role = str(item.get("role") or "context")
    policy_error = path_policy_error(raw_path)
    full_path = resolve_repo_path(repo_root, raw_path) if raw_path else repo_root
    entry: dict[str, Any] = {
        "path": raw_path,
        "role": role,
        "required": required,
        "exists": False,
        "included": False,
        "policy_ok": policy_error is None,
        "policy_error": policy_error or "",
        "size_bytes": 0,
        "line_count": 0,
        "sha256": "",
        "chars": 0,
        "included_chars": 0,
        "truncated": False,
        "read_error": "",
        "content": "",
    }
    if policy_error:
        return entry, remaining_chars
    if path_escapes_repo(repo_root, full_path):
        entry["policy_ok"] = False
        entry["policy_error"] = "path escapes repository root"
        return entry, remaining_chars
    if not full_path.exists():
        entry["read_error"] = "file is missing"
        return entry, remaining_chars
    if not full_path.is_file():
        entry["read_error"] = "path is not a file"
        return entry, remaining_chars

    text, read_error = safe_read_text(full_path)
    entry["exists"] = True
    entry["size_bytes"] = full_path.stat().st_size
    if read_error or text is None:
        entry["read_error"] = read_error or "unknown read error"
        return entry, remaining_chars

    entry["line_count"] = physical_line_count(text)
    entry["sha256"] = sha256_text(text)
    entry["chars"] = len(text)
    budget = max(0, min(remaining_chars, max_file_chars))
    if budget <= 0:
        entry["read_error"] = "context character budget exhausted"
        return entry, remaining_chars
    included = text[:budget]
    entry["included"] = True
    entry["included_chars"] = len(included)
    entry["truncated"] = len(included) < len(text)
    entry["content"] = included
    return entry, remaining_chars - len(included)


def profile_items(profile: dict[str, Any]) -> list[tuple[dict[str, Any], bool]]:
    required = [(item, True) for item in profile.get("required_files", []) if isinstance(item, dict)]
    optional = [(item, False) for item in profile.get("optional_files", []) if isinstance(item, dict)]
    return [*required, *optional]


def build_pack(
    *,
    repo_root: Path,
    profile_name: str,
    output_dir: Path,
    basename: str,
    max_total_chars: int,
    max_file_chars: int,
) -> dict[str, Any]:
    if profile_name not in PROFILES:
        raise ValueError(f"unknown profile: {profile_name}")
    profile = PROFILES[profile_name]
    errors: list[str] = []
    warnings: list[str] = []
    remaining = max_total_chars
    file_entries: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    for item, required in profile_items(profile):
        path = normalize_repo_path(item.get("path"))
        if path in seen_paths:
            warnings.append(f"duplicate profile path ignored after first occurrence: {path}")
            continue
        seen_paths.add(path)
        entry, remaining = build_file_entry(
            repo_root=repo_root,
            item=item,
            required=required,
            remaining_chars=remaining,
            max_file_chars=max_file_chars,
        )
        file_entries.append(entry)
        if required and (not entry["exists"] or not entry["included"] or not entry["policy_ok"]):
            errors.append(f"required file unavailable for context: {path} ({context_unavailable_reason(entry)})")
        elif (not required) and (not entry["exists"] or not entry["included"] or not entry["policy_ok"]):
            warnings.append(f"optional file unavailable for context: {path} ({context_unavailable_reason(entry)})")
        if entry.get("truncated"):
            warnings.append(f"context content truncated for {path}")

    validation_commands = list(profile.get("validation_commands") or [])
    stop_conditions = [*PROFILE_COMMON_STOP_CONDITIONS, *list(profile.get("stop_conditions") or [])]
    pack = {
        "schema_version": 1,
        "kind": PACK_KIND,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "repo_root": str(repo_root),
        "profile": profile_name,
        "profile_description": profile.get("description") or "",
        "apply_mode": APPLY_MODE,
        "provider_execution_performed": False,
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "max_total_chars": max_total_chars,
        "max_file_chars": max_file_chars,
        "total_included_chars": sum(int(item.get("included_chars") or 0) for item in file_entries),
        "file_count": len(file_entries),
        "included_file_count": sum(1 for item in file_entries if item.get("included") is True),
        "truncated_file_count": sum(1 for item in file_entries if item.get("truncated") is True),
        "validation_commands": validation_commands,
        "stop_conditions": stop_conditions,
        "files": file_entries,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{basename}.json"
    md_path = output_dir / f"{basename}.md"
    pack["pack_json"] = repo_relative(json_path, repo_root)
    pack["pack_markdown"] = repo_relative(md_path, repo_root)
    json_path.write_text(json.dumps(pack, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path.write_text(render_pack_markdown(pack), encoding="utf-8")
    return pack


def build_evidence(pack: dict[str, Any], repo_root: Path, evidence_dir: Path, evidence_basename: str) -> dict[str, Any]:
    evidence_dir.mkdir(parents=True, exist_ok=True)
    json_path = evidence_dir / f"{evidence_basename}.json"
    md_path = evidence_dir / f"{evidence_basename}.md"
    files = pack.get("files") if isinstance(pack.get("files"), list) else []
    evidence = {
        "schema_version": 1,
        "kind": EVIDENCE_KIND,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "repo_root": pack.get("repo_root"),
        "profile": pack.get("profile"),
        "profile_description": pack.get("profile_description"),
        "source_pack": pack.get("pack_json"),
        "source_pack_markdown": pack.get("pack_markdown"),
        "passed": pack.get("passed") is True,
        "errors": pack.get("errors") or [],
        "warnings": pack.get("warnings") or [],
        "provider_execution_performed": False,
        "apply_mode": APPLY_MODE,
        "file_count": pack.get("file_count"),
        "included_file_count": pack.get("included_file_count"),
        "truncated_file_count": pack.get("truncated_file_count"),
        "total_included_chars": pack.get("total_included_chars"),
        "validation_command_count": len(pack.get("validation_commands") or []),
        "required_missing": [
            item.get("path")
            for item in files
            if item.get("required") is True and (item.get("exists") is not True or item.get("included") is not True)
        ],
        "forbidden_path_count": sum(1 for item in files if item.get("policy_ok") is not True),
        "blender_runtime_touched": any(str(item.get("path") or "").startswith("Scripting/") for item in files),
        "included_paths": [
            {
                "path": item.get("path"),
                "role": item.get("role"),
                "required": item.get("required"),
                "included": item.get("included"),
                "truncated": item.get("truncated"),
                "sha256": item.get("sha256"),
                "included_chars": item.get("included_chars"),
            }
            for item in files
        ],
        "decision": {
            "context_pack_built": pack.get("passed") is True,
            "provider_execution_seen": False,
            "forbidden_paths_blocked": sum(1 for item in files if item.get("policy_ok") is not True) == 0,
            "source_writes_performed": False,
        },
    }
    evidence["evidence_json"] = repo_relative(json_path, repo_root)
    evidence["evidence_markdown"] = repo_relative(md_path, repo_root)
    json_path.write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path.write_text(render_evidence_markdown(evidence), encoding="utf-8")
    return evidence


def render_pack_markdown(pack: dict[str, Any]) -> str:
    lines = [f"# AI Context Pack: {pack['profile']}", ""]
    lines.append(f"- Generated at: `{pack['generated_at']}`")
    lines.append(f"- Passed: `{pack['passed']}`")
    lines.append(f"- Provider execution performed: `{pack['provider_execution_performed']}`")
    lines.append(f"- Included files: `{pack['included_file_count']}/{pack['file_count']}`")
    lines.append(f"- Included chars: `{pack['total_included_chars']}`")
    lines.append("")
    lines.append("## Validation Commands")
    lines.append("")
    for command in pack.get("validation_commands") or []:
        lines.append(f"- `{command}`")
    lines.append("")
    lines.append("## Stop Conditions")
    lines.append("")
    for condition in pack.get("stop_conditions") or []:
        lines.append(f"- {condition}")
    lines.append("")
    lines.append("## Files")
    lines.append("")
    for item in pack.get("files") or []:
        lines.append(
            f"- `{item['path']}` ({item['role']}): included `{item['included']}`, "
            f"required `{item['required']}`, truncated `{item['truncated']}`"
        )
    lines.append("")
    lines.append("## Content")
    lines.append("")
    for item in pack.get("files") or []:
        if not item.get("included"):
            continue
        lines.append(f"### `{item['path']}`")
        lines.append("")
        lines.append("```text")
        lines.append(str(item.get("content") or ""))
        lines.append("```")
        lines.append("")
    return "\n".join(lines)


def render_evidence_markdown(evidence: dict[str, Any]) -> str:
    lines = [f"# AI Context Pack Evidence: {evidence['profile']}", ""]
    lines.append(f"- Generated at: `{evidence['generated_at']}`")
    lines.append(f"- Passed: `{evidence['passed']}`")
    lines.append(f"- Provider execution performed: `{evidence['provider_execution_performed']}`")
    lines.append(f"- Source pack: `{evidence['source_pack']}`")
    lines.append(f"- Included files: `{evidence['included_file_count']}/{evidence['file_count']}`")
    lines.append(f"- Truncated files: `{evidence['truncated_file_count']}`")
    lines.append(f"- Forbidden path count: `{evidence['forbidden_path_count']}`")
    lines.append(f"- Blender runtime touched: `{evidence['blender_runtime_touched']}`")
    lines.append("")
    lines.append("## Decision")
    lines.append("")
    for key, value in evidence["decision"].items():
        lines.append(f"- `{key}`: `{value}`")
    lines.append("")
    lines.append("## Included Paths")
    lines.append("")
    for item in evidence["included_paths"]:
        lines.append(
            f"- `{item['path']}` ({item['role']}): included `{item['included']}`, "
            f"required `{item['required']}`, truncated `{item['truncated']}`"
        )
    lines.append("")
    lines.append("This evidence summarizes a local context pack. It does not prove provider execution and does not include source changes.")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--profile", default=DEFAULT_PROFILE, choices=sorted(PROFILES))
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--basename", default="")
    parser.add_argument("--max-total-chars", type=int, default=DEFAULT_MAX_TOTAL_CHARS)
    parser.add_argument("--max-file-chars", type=int, default=DEFAULT_MAX_FILE_CHARS)
    parser.add_argument("--evidence-dir", default=DEFAULT_EVIDENCE_DIR)
    parser.add_argument("--evidence-basename", default="")
    parser.add_argument("--no-evidence", action="store_true")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    basename = sanitize_filename(args.basename or args.profile)
    evidence_basename = sanitize_filename(args.evidence_basename or f"{args.profile}_context_pack_evidence")
    output_dir = resolve_repo_path(repo_root, args.output_dir)
    evidence_dir = resolve_repo_path(repo_root, args.evidence_dir)
    pack = build_pack(
        repo_root=repo_root,
        profile_name=args.profile,
        output_dir=output_dir,
        basename=basename,
        max_total_chars=args.max_total_chars,
        max_file_chars=args.max_file_chars,
    )
    evidence = None if args.no_evidence else build_evidence(pack, repo_root, evidence_dir, evidence_basename)
    print(
        json.dumps(
            {
                "passed": pack["passed"],
                "profile": pack["profile"],
                "pack_json": pack["pack_json"],
                "pack_markdown": pack["pack_markdown"],
                "evidence_json": None if evidence is None else evidence["evidence_json"],
                "included_file_count": pack["included_file_count"],
                "truncated_file_count": pack["truncated_file_count"],
                "provider_execution_performed": False,
            },
            indent=2,
        )
    )
    return 0 if pack["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
