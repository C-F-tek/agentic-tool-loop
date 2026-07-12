from __future__ import annotations

from .common import *  # noqa: F403
from ia_carmine._shared.provider_work_verification import provider_work_status


def _provider_lane(data: dict[str, Any]) -> str:
    lane = str(data.get("lane") or data.get("provider_id") or "").strip()
    if lane:
        return lane
    kind = str(data.get("kind") or "").strip()
    if kind == "gpu0_peer_response":
        return "gpu0_peer"
    if kind in {"npu_gpu_deep_review_audit", "npu_micro_task_auditor"}:
        return "npu_micro_task_auditor"
    if kind in {"local_provider_probe", "gpu1_primary_advisory"}:
        return "gpu1_planner"
    return ""


def _provider_execution_claim_seen(data: dict[str, Any]) -> bool:
    return bool(
        data.get("provider_execution_performed")
        or data.get("provider_execution_attempted")
        or data.get("provider_io_observed")
    )


def _provider_work_verified(data: dict[str, Any]) -> bool:
    if data.get("provider_work_verified") is True:
        return True
    lane = _provider_lane(data)
    if not lane:
        return False
    return bool(provider_work_status(lane=lane, report=data).get("provider_work_verified"))

def extract_full_run_patch_plan_summary(repo_root: Path, report_paths: list[str]) -> dict[str, Any]:
    # Promote full-run patch-plan summary into the production bundle final summary.
    for rel in report_paths:
        path = resolve_repo_path(repo_root, rel)
        data, parse_error = read_json_object(path)
        if parse_error or not data:
            continue
        if data.get("kind") != "agent_review_patch_plan":
            continue
        raw_summary = data.get("patch_plan_summary")
        summary_items = raw_summary if isinstance(raw_summary, list) else []
        return {
            "seen": True,
            "source": repo_relative(path, repo_root),
            "passed": data.get("passed"),
            "patch_plan_count": data.get("patch_plan_count") or len(summary_items),
            "evidence_only_plan_synthesis_blocked": data.get(
                "evidence_only_plan_synthesis_blocked"
            ),
            "manual_review_required": data.get("manual_review_required"),
            "provider_execution_claim_seen": _provider_execution_claim_seen(data),
            "provider_work_verified": _provider_work_verified(data),
            "provider_execution_performed": _provider_work_verified(data),
            "patch_application_performed": data.get("patch_application_performed"),
            "source_writes_performed": data.get("source_writes_performed"),
            "summary_count": len(summary_items),
            "top_items": summary_items[:20],
            "warnings": (data.get("warnings") if isinstance(data.get("warnings"), list) else []),
            "errors": (data.get("errors") if isinstance(data.get("errors"), list) else []),
        }
    return {
        "seen": False,
        "source": "",
        "patch_plan_count": 0,
        "summary_count": 0,
        "top_items": [],
        "warnings": [],
        "errors": ["full-run patch plan report not found in production bundle inputs"],
    }

def extract_provider_diagnostics_summary(
    repo_root: Path, report_paths: list[str]
) -> dict[str, Any]:
    # Summarize provider/GPU/NPU diagnostics without hiding recovered failures.
    diagnostics: list[dict[str, Any]] = []
    provider_execution_seen = False
    provider_execution_claim_seen = False
    gpu_primary_advisory_succeeded = False
    deterministic_recovery_used = False

    for rel in report_paths:
        path = resolve_repo_path(repo_root, rel)
        data, parse_error = read_json_object(path)
        if parse_error or not data:
            continue

        kind = str(data.get("kind") or "")
        passed = data.get("passed")
        provider_execution_seen = provider_execution_seen or _provider_work_verified(data)
        provider_execution_claim_seen = (
            provider_execution_claim_seen or _provider_execution_claim_seen(data)
        )

        if kind in {
            "agent_gpu_npu_parallel_orchestrator",
            "agent_gpu_parallel_report",
            "local_provider_probe",
            "ai_workload_report_quality",
            "gpu1_primary_advisory",
            "gpu0_peer_response",
            "npu_gpu_deep_review_audit",
            "agent_runtime_tool_broker",
            "ai_peer_exchange",
            "ai_peer_exchange_contract",
            "provider_runtime_live_signals",
            "provider_runtime_heap_from_peer_reports",
        }:
            errors = data.get("errors") if isinstance(data.get("errors"), list) else []
            warnings = data.get("warnings") if isinstance(data.get("warnings"), list) else []
            diagnostics.append(
                {
                    "path": repo_relative(path, repo_root),
                    "kind": kind,
                    "passed": passed,
                    "provider_execution_requested": data.get("provider_execution_requested"),
                    "provider_execution_claim_seen": _provider_execution_claim_seen(data),
                    "provider_work_verified": _provider_work_verified(data),
                    "provider_execution_performed": _provider_work_verified(data),
                    "classification": data.get("classification"),
                    "classifications": (
                        data.get("classifications")
                        if isinstance(data.get("classifications"), list)
                        else []
                    ),
                    "role": data.get("role"),
                    "source": data.get("source"),
                    "source_classification": data.get("source_classification"),
                    "request_kind": data.get("request_kind"),
                    "non_blocking": data.get("non_blocking"),
                    "peer_mesh_visibility": data.get("peer_mesh_visibility"),
                    "npu_support_lane": data.get("npu_support_lane"),
                    "provider_broker_loop": data.get("provider_broker_loop"),
                    "collaboration_visibility": (
                        (data.get("collaboration_round") or {}).get("synchronized_visibility")
                        if isinstance(data.get("collaboration_round"), dict)
                        else None
                    ),
                    "tool_request_count": data.get("tool_request_count"),
                    "tool_execution_count": data.get("tool_execution_count"),
                    "event_count": data.get("event_count"),
                    "broker_result_count": data.get("broker_result_count"),
                    "pending_broker_request_count": data.get("pending_broker_request_count"),
                    "direct_execution_violation_count": data.get(
                        "direct_execution_violation_count"
                    ),
                    "provider_error": data.get("provider_error"),
                    "recommendation_count": data.get("recommendation_count"),
                    "errors": errors[:20],
                    "warnings": warnings[:20],
                }
            )
            if (
                kind == "agent_gpu_parallel_report"
                and passed is True
                and int(data.get("recommendation_count") or 0) > 0
            ):
                gpu_primary_advisory_succeeded = True
            if kind == "gpu1_primary_advisory" and passed is True:
                gpu_primary_advisory_succeeded = True

        if (
            kind
            in {
                "deterministic_recommendation_synthesizer",
                "agent_review_decision_loop",
                "agent_review_patch_plan",
            }
            and passed is True
        ):
            if (
                int(data.get("recommendation_count") or 0) > 0
                or int(data.get("patch_plan_count") or 0) > 0
            ):
                deterministic_recovery_used = True

    provider_failure_detected = any(item.get("passed") is False for item in diagnostics)
    return {
        "provider_execution_seen": provider_execution_seen,
        "provider_execution_claim_seen": provider_execution_claim_seen,
        "gpu_primary_advisory_succeeded": gpu_primary_advisory_succeeded,
        "provider_failure_detected": provider_failure_detected,
        "deterministic_recovery_used": deterministic_recovery_used,
        "diagnostics": diagnostics,
        **classify_provider_advisory_state(
            {
                "provider_execution_seen": provider_execution_seen,
                "provider_execution_claim_seen": provider_execution_claim_seen,
                "gpu_primary_advisory_succeeded": gpu_primary_advisory_succeeded,
                "provider_failure_detected": provider_failure_detected,
                "deterministic_recovery_used": deterministic_recovery_used,
                "diagnostics": diagnostics,
            }
        ),
    }

def classify_provider_advisory_state(
    provider_diagnostics: dict[str, Any],
) -> dict[str, Any]:
    # Classify provider state without hiding recovered/degraded runs.
    diagnostics = (
        provider_diagnostics.get("diagnostics") if isinstance(provider_diagnostics, dict) else []
    )
    diagnostics = diagnostics if isinstance(diagnostics, list) else []
    failure_reasons: list[str] = []
    degraded_components: list[str] = []

    for item in diagnostics:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "")
        kind = str(item.get("kind") or "")
        passed = item.get("passed")
        errors = item.get("errors") if isinstance(item.get("errors"), list) else []
        provider_error = item.get("provider_error")

        if passed is False:
            degraded_components.append(path or kind or "provider_report")
        if provider_error:
            failure_reasons.append(f"{path or kind}: {provider_error}")
        for error in errors[:5]:
            if error:
                failure_reasons.append(f"{path or kind}: {error}")

    gpu_ok = bool(provider_diagnostics.get("gpu_primary_advisory_succeeded"))
    provider_seen = bool(provider_diagnostics.get("provider_execution_seen"))
    failure_seen = bool(provider_diagnostics.get("provider_failure_detected"))
    recovered = bool(provider_diagnostics.get("deterministic_recovery_used"))

    if gpu_ok:
        state = "primary_gpu_advisory_succeeded"
    elif provider_seen and failure_seen and recovered:
        state = "recovered_degraded_provider"
    elif provider_seen and failure_seen:
        state = "provider_failed_without_recovery"
    elif provider_seen:
        state = "provider_seen_without_primary_gpu_advisory"
    else:
        state = "provider_not_seen"

    return {
        "provider_advisory_state": state,
        "provider_failure_reasons": failure_reasons[:20],
        "degraded_provider_components": degraded_components[:20],
    }

def extract_peer_mesh_product_state(
    provider_diagnostics: dict[str, Any],
) -> dict[str, Any]:
    """Derive product-facing peer-mesh state from existing provider diagnostics."""

    operational_lanes: list[str] = []
    support_lanes: list[str] = []
    degraded_lanes: list[str] = []
    product_blockers: list[str] = []

    def add_unique(items: list[str], value: str) -> None:
        if value and value not in items:
            items.append(value)

    for item in provider_diagnostics.get("diagnostics", []):
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "")
        classifications = (
            item.get("classifications") if isinstance(item.get("classifications"), list) else []
        )
        mesh = (
            item.get("peer_mesh_visibility")
            if isinstance(item.get("peer_mesh_visibility"), dict)
            else {}
        )
        support = (
            item.get("npu_support_lane") if isinstance(item.get("npu_support_lane"), dict) else {}
        )
        if kind == "gpu1_primary_advisory" and item.get("passed") is True:
            add_unique(operational_lanes, "gpu1_ollama_primary_advisory")
        if kind == "gpu0_peer_response":
            if item.get("provider_work_verified") is True:
                add_unique(operational_lanes, "gpu0_openvino_peer_companion")
                add_unique(support_lanes, "gpu0_openvino_numeric_tool_peer")
            if "gpu0_peer_semantic_model_unconfigured" in classifications:
                add_unique(degraded_lanes, "gpu0_semantic_companion_model_unconfigured")
        if kind == "agent_runtime_tool_broker" and int(item.get("tool_execution_count") or 0) > 0:
            add_unique(operational_lanes, "runtime_tool_broker")
            source_classification = str(
                item.get("source_classification") or item.get("source") or ""
            )
            if "gpu0" in source_classification:
                add_unique(support_lanes, "gpu0_brokered_tool_supply")
            if "npu" in source_classification:
                add_unique(support_lanes, "npu_brokered_tool_supply")
        if kind == "ai_peer_exchange":
            for lane in (
                item.get("peer_mesh_operational_lanes", [])
                if isinstance(item.get("peer_mesh_operational_lanes"), list)
                else []
            ):
                add_unique(operational_lanes, str(lane))
            if mesh.get("gpu0_tool_requests_broker_consumed") is True:
                add_unique(support_lanes, "gpu0_brokered_tool_supply")
            if mesh.get("npu_tool_requests_broker_consumed") is True:
                add_unique(support_lanes, "npu_brokered_tool_supply")
            if support.get("provider_slow_or_degraded") is True:
                add_unique(degraded_lanes, "npu_semantic_provider_slow_or_degraded")
            if support.get("product_pass_blocker") is True:
                add_unique(product_blockers, "npu_support_lane_marked_product_blocker")
    if operational_lanes and "deterministic_scripts" not in operational_lanes:
        add_unique(operational_lanes, "deterministic_scripts")
    return {
        "operational_lanes": operational_lanes,
        "support_lanes": support_lanes,
        "degraded_lanes": degraded_lanes,
        "product_blockers": product_blockers,
        "legacy_usable_lanes_are_workload_quality_only": True,
        "npu_degraded_is_product_blocker": False,
        "npu_heavy_audit_authority": False,
    }

def extract_provider_broker_loop_product_state(
    provider_diagnostics: dict[str, Any],
) -> dict[str, Any]:
    """Derive provider-broker loop product state from existing provider diagnostics."""

    for item in provider_diagnostics.get("diagnostics", []):
        if not isinstance(item, dict):
            continue
        loop = item.get("provider_broker_loop")
        if isinstance(loop, dict) and loop:
            return {
                "seen": True,
                "active": loop.get("active"),
                "controlled_executor": loop.get("controlled_executor"),
                "direct_tool_execution_allowed": loop.get("direct_tool_execution_allowed"),
                "broker_tool_execution_count": loop.get("broker_tool_execution_count"),
                "gpu0_broker_tool_execution_count": loop.get("gpu0_broker_tool_execution_count"),
                "npu_broker_tool_execution_count": loop.get("npu_broker_tool_execution_count"),
                "npu_non_blocking": loop.get("npu_non_blocking"),
                "npu_product_pass_blocker": loop.get("npu_product_pass_blocker"),
                "deterministic_scripts_heavy_audit_authority": loop.get(
                    "deterministic_scripts_heavy_audit_authority"
                ),
                "product_pass_blockers": loop.get("product_pass_blockers", []),
                "topology": loop.get("topology", []),
            }

    heap_items = [
        item
        for item in provider_diagnostics.get("diagnostics", [])
        if isinstance(item, dict) and item.get("kind") == "provider_runtime_heap_from_peer_reports"
    ]
    if heap_items:
        return {
            "seen": True,
            "active": True,
            "controlled_executor": "provider_runtime_heap + agent_runtime_tool_broker",
            "direct_tool_execution_allowed": False,
            "broker_tool_execution_count": 0,
            "gpu0_broker_tool_execution_count": 0,
            "npu_broker_tool_execution_count": 0,
            "npu_non_blocking": True,
            "npu_product_pass_blocker": False,
            "deterministic_scripts_heavy_audit_authority": True,
            "product_pass_blockers": [],
            "topology": [
                "gpu1 -> gpu0 evidence_request",
                "broker -> gpu0 broker_result",
                "npu -> gpu1 evidence_response",
            ],
        }

    return {
        "seen": False,
        "active": False,
        "controlled_executor": "",
        "direct_tool_execution_allowed": None,
        "broker_tool_execution_count": 0,
        "gpu0_broker_tool_execution_count": 0,
        "npu_broker_tool_execution_count": 0,
        "npu_non_blocking": None,
        "npu_product_pass_blocker": None,
        "deterministic_scripts_heavy_audit_authority": None,
        "product_pass_blockers": ["provider_broker_loop_not_found_in_bundle_inputs"],
        "topology": [],
    }
