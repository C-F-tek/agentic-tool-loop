from __future__ import annotations

from .collection import collect_report_facts, build_remaining_gaps
from .common import *  # noqa: F403
from .provider_state import (
    classify_provider_advisory_state,
    extract_full_run_patch_plan_summary,
    extract_peer_mesh_product_state,
    extract_provider_broker_loop_product_state,
    extract_provider_diagnostics_summary,
)
from .tooling import default_tool_requests, runtime_tool_capabilities

def build_final_summary(
    *,
    repo_root: Path,
    stamp: str,
    report_paths: list[str],
    artifact_paths: list[str],
    bundle_paths: list[str],
    recommended_next_task_md: str,
    missing_reports: list[dict[str, Any]],
    missing_artifacts: list[dict[str, Any]],
    recursive_defaults: dict[str, Any] | None = None,
    chunked_file_index: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    facts = collect_report_facts(repo_root, report_paths)
    patch_plan_summary = extract_full_run_patch_plan_summary(repo_root, report_paths)
    provider_diagnostics = extract_provider_diagnostics_summary(repo_root, report_paths)
    peer_mesh_product_state = extract_peer_mesh_product_state(provider_diagnostics)
    provider_broker_loop_product_state = extract_provider_broker_loop_product_state(
        provider_diagnostics
    )
    tool_capabilities = runtime_tool_capabilities()
    tool_requests = facts.get("tool_requests_executed_or_proposed") or default_tool_requests()
    remaining_gaps = build_remaining_gaps(missing_reports, missing_artifacts, facts)
    passed = not (
        facts.get("patch_application_performed")
        or facts.get("sqlite_write_performed")
        or facts.get("persistent_memory_write_performed")
        or facts.get("blender_runtime_execution_performed")
    )
    return {
        "schema_version": 1,
        "kind": "shared_toolbox_ai_to_ai_final_summary",
        "stamp": stamp,
        "passed": passed,
        "tools_available": [item["tool_name"] for item in tool_capabilities],
        "tool_capabilities": tool_capabilities,
        "tool_requests_executed_or_proposed": tool_requests,
        "reports_generated": facts.get("reports_generated", []),
        "remaining_gaps": remaining_gaps,
        "recommended_next_task_md": recommended_next_task_md,
        "compact_bundle_paths": bundle_paths,
        "provider_execution_performed": bool(facts.get("provider_execution_performed")),
        "provider_execution_claim_seen": bool(facts.get("provider_execution_claim_seen")),
        "provider_diagnostics": provider_diagnostics,
        "peer_mesh_product_state": peer_mesh_product_state,
        "provider_broker_loop_product_state": provider_broker_loop_product_state,
        "provider_broker_loop_active": provider_broker_loop_product_state.get("active"),
        "provider_broker_loop_controlled_executor": provider_broker_loop_product_state.get(
            "controlled_executor"
        ),
        "provider_broker_loop_broker_execution_count": provider_broker_loop_product_state.get(
            "broker_tool_execution_count"
        ),
        "provider_broker_loop_gpu0_broker_execution_count": provider_broker_loop_product_state.get(
            "gpu0_broker_tool_execution_count"
        ),
        "provider_broker_loop_npu_broker_execution_count": provider_broker_loop_product_state.get(
            "npu_broker_tool_execution_count"
        ),
        "provider_broker_loop_product_blockers": provider_broker_loop_product_state.get(
            "product_pass_blockers", []
        ),
        "peer_mesh_operational_lanes": peer_mesh_product_state.get("operational_lanes", []),
        "peer_mesh_support_lanes": peer_mesh_product_state.get("support_lanes", []),
        "peer_mesh_degraded_lanes": peer_mesh_product_state.get("degraded_lanes", []),
        "peer_mesh_product_blockers": peer_mesh_product_state.get("product_blockers", []),
        "gpu_primary_advisory_succeeded": bool(
            provider_diagnostics.get("gpu_primary_advisory_succeeded")
        ),
        "provider_failure_detected": bool(provider_diagnostics.get("provider_failure_detected")),
        "provider_advisory_state": provider_diagnostics.get("provider_advisory_state"),
        "provider_failure_reasons": provider_diagnostics.get("provider_failure_reasons", []),
        "degraded_provider_components": provider_diagnostics.get(
            "degraded_provider_components", []
        ),
        "deterministic_recovery_used": bool(
            provider_diagnostics.get("deterministic_recovery_used")
        ),
        "patch_plan_summary": patch_plan_summary,
        "patch_plan_summary_seen": bool(patch_plan_summary.get("seen")),
        "patch_plan_count": patch_plan_summary.get("patch_plan_count", 0),
        "manual_review_required": patch_plan_summary.get("manual_review_required"),
        "patch_application_performed": bool(facts.get("patch_application_performed")),
        "source_writes_performed": bool(facts.get("source_writes_performed")),
        "sqlite_write_performed": bool(facts.get("sqlite_write_performed")),
        "persistent_memory_write_performed": bool(facts.get("persistent_memory_write_performed")),
        "blender_runtime_execution_performed": bool(
            facts.get("blender_runtime_execution_performed")
        ),
        "artifact_paths_considered": artifact_paths,
        "recursive_defaults": recursive_defaults or {},
        "chunked_file_index": chunked_file_index or [],
        "errors": facts.get("errors", []),
        "warnings": facts.get("warnings", []),
    }

def render_final_summary_markdown(summary: dict[str, Any]) -> str:
    lines: list[str] = ["# Shared Toolbox AI-to-AI Final Summary", ""]
    for key in (
        "stamp",
        "passed",
        "provider_execution_performed",
        "provider_execution_claim_seen",
        "patch_application_performed",
        "source_writes_performed",
        "sqlite_write_performed",
        "persistent_memory_write_performed",
        "blender_runtime_execution_performed",
    ):
        lines.append(f"- {key}: {summary.get(key)}")
    lines.append("")
    lines.append("## Provider diagnostics")
    lines.append("")
    provider = summary.get("provider_diagnostics") or {}
    lines.append(f"- Provider execution seen: `{provider.get('provider_execution_seen')}`")
    lines.append(
        f"- Provider execution claim seen: `{provider.get('provider_execution_claim_seen')}`"
    )
    lines.append(
        f"- GPU primary advisory succeeded: `{provider.get('gpu_primary_advisory_succeeded')}`"
    )
    lines.append(f"- Provider failure detected: `{provider.get('provider_failure_detected')}`")
    lines.append(f"- Deterministic recovery used: `{provider.get('deterministic_recovery_used')}`")
    lines.append(f"- Provider advisory state: `{provider.get('provider_advisory_state')}`")
    reasons = provider.get("provider_failure_reasons") or []
    if reasons:
        lines.append("- Provider failure reasons:")
        for reason in reasons[:12]:
            lines.append(f"  - {reason}")
    peer_mesh_state = (
        summary.get("peer_mesh_product_state")
        if isinstance(summary.get("peer_mesh_product_state"), dict)
        else {}
    )
    if peer_mesh_state:
        lines.append("")
        lines.append("## Peer mesh product state")
        lines.append("")
        lines.append(f"- Peer mesh operational lanes: `{peer_mesh_state.get('operational_lanes')}`")
        lines.append(f"- Peer mesh support lanes: `{peer_mesh_state.get('support_lanes')}`")
        lines.append(f"- Peer mesh degraded lanes: `{peer_mesh_state.get('degraded_lanes')}`")
        lines.append(f"- Peer mesh product blockers: `{peer_mesh_state.get('product_blockers')}`")
        lines.append(
            f"- Legacy usable lanes are workload quality only: `{peer_mesh_state.get('legacy_usable_lanes_are_workload_quality_only')}`"
        )
        lines.append(
            f"- NPU degraded is product blocker: `{peer_mesh_state.get('npu_degraded_is_product_blocker')}`"
        )
        lines.append(
            f"- NPU heavy audit authority: `{peer_mesh_state.get('npu_heavy_audit_authority')}`"
        )
        lines.append("")
    for item in provider.get("diagnostics", [])[:12]:
        lines.append(
            f"- `{item.get('path')}` kind=`{item.get('kind')}` passed=`{item.get('passed')}` "
            f"source=`{item.get('source')}` source_classification=`{item.get('source_classification')}` "
            f"provider_execution_performed=`{item.get('provider_execution_performed')}` "
            f"collaboration_visibility=`{item.get('collaboration_visibility')}` "
            f"peer_mesh=`{bool(item.get('peer_mesh_visibility'))}` "
            f"npu_support=`{bool(item.get('npu_support_lane'))}` errors=`{item.get('errors')}`"
        )
    lines.append("")
    lines.append("## Patch plan summary")
    lines.append("")
    patch_summary = summary.get("patch_plan_summary") or {}
    lines.append(f"- Seen: `{patch_summary.get('seen')}`")
    lines.append(f"- Source: `{patch_summary.get('source')}`")
    lines.append(f"- Patch plan count: `{patch_summary.get('patch_plan_count')}`")
    lines.append(f"- Manual review required: `{patch_summary.get('manual_review_required')}`")
    lines.append(
        f"- Patch application performed: `{patch_summary.get('patch_application_performed')}`"
    )
    for item in patch_summary.get("top_items", [])[:20]:
        if isinstance(item, dict):
            lines.append(
                f"- `{item.get('id') or item.get('recommendation_id')}` status=`{item.get('status')}` targets=`{item.get('target_files')}`"
            )
    lines.append("")
    lines.append("## Tools available")
    lines.append("")
    for tool in summary.get("tool_capabilities", []):
        lines.append(f"### {tool.get('tool_name')}")
        lines.append("")
        lines.append(f"- Category: {tool.get('category')}")
        lines.append(f"- Safe default mode: {tool.get('safe_default_mode')}")
        lines.append(f"- Recommended next use: {tool.get('recommended_next_use')}")
        lines.append(f"- Allowed args: `{tool.get('allowed_args')}`")
        lines.append("- Can do:")
        for item in tool.get("what_it_can_do", []):
            lines.append(f"  - {item}")
        lines.append("- Must not do:")
        for item in tool.get("what_it_must_not_do", []):
            lines.append(f"  - {item}")
        lines.append("")
    lines.append("## Tool requests executed or proposed")
    lines.append("")
    for request in summary.get("tool_requests_executed_or_proposed", []):
        lines.append(f"- {request.get('id')}: {request.get('tool')} - {request.get('reason')}")
    lines.append("")
    lines.append("## Reports generated")
    lines.append("")
    for report in summary.get("reports_generated", []):
        lines.append(
            f"- {report.get('path')} exists={report.get('exists')} json_ok={report.get('json_ok')} "
            f"kind={report.get('kind')} passed={report.get('passed')}"
        )
    lines.append("")
    lines.append("## Remaining gaps")
    lines.append("")
    gaps = summary.get("remaining_gaps") or []
    if gaps:
        for gap in gaps:
            if isinstance(gap, dict):
                label = gap.get("gap") or gap.get("path") or "gap"
                detail = gap.get("detail") or gap.get("reason") or ""
                lines.append(f"- {label}: {detail}")
            else:
                lines.append(f"- {gap}")
    else:
        lines.append("- No blocking report-only guardrail gaps detected.")
    lines.append("")
    lines.append("## Recommended next task")
    lines.append("")
    lines.append(str(summary.get("recommended_next_task_md") or ""))
    lines.append("")
    lines.append("## Recursive defaults")
    lines.append("")
    recursive_defaults = summary.get("recursive_defaults") or {}
    lines.append(f"- Enabled: `{recursive_defaults.get('enabled')}`")
    lines.append(
        f"- Discovered reports: `{len(recursive_defaults.get('discovered_reports') or [])}`"
    )
    lines.append(
        f"- Discovered artifacts: `{len(recursive_defaults.get('discovered_artifacts') or [])}`"
    )
    lines.append("")
    lines.append("## Chunked large JSON/Markdown files")
    lines.append("")
    chunked = summary.get("chunked_file_index") or []
    if chunked:
        for item in chunked:
            lines.append(
                f"- {item.get('path')} lines={item.get('line_count')} "
                f"chunks={item.get('chunk_count')} chunk_size={item.get('chunk_size_lines')}"
            )
            for chunk in item.get("chunks", []):
                lines.append(
                    f"  - {chunk.get('chunk_id')} -> next: {chunk.get('next_chunk_id') or 'END'}"
                )
    else:
        lines.append("- No JSON/Markdown file above the chunk threshold was detected.")
    lines.append("")
    lines.append("## Compact bundle paths")
    lines.append("")
    for path in summary.get("compact_bundle_paths", []):
        lines.append(f"- {path}")
    lines.append("")
    return "\n".join(lines)

def write_final_summary(repo_root: Path, summary: dict[str, Any]) -> tuple[Path, Path]:
    stamp = str(summary["stamp"])
    output_dir = repo_root / "output" / "analysis"
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{DEFAULT_FINAL_SUMMARY_PREFIX}_{stamp}.json"
    md_path = output_dir / f"{DEFAULT_FINAL_SUMMARY_PREFIX}_{stamp}.md"
    write_json_report(summary, json_path)
    md_path.write_text(render_final_summary_markdown(summary), encoding="utf-8")
    return json_path, md_path
