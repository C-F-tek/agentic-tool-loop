"""Agent state packet selection and rendering."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .common import DEFAULT_MAX_MEMORY_CHARS, SCHEMA_VERSION, keywords, slugify, utc_now_iso
from .models import AgentMicroTask, MemoryRecord

def score_record(record: MemoryRecord, objective: str) -> float:
    """Score a memory record against the current objective."""
    objective_terms = set(keywords(objective, 80))
    record_terms = set(record.tags) | set(keywords(record.summary + " " + record.source, 80))
    overlap = len(objective_terms & record_terms)
    tag_bonus = (
        0.7 if {"guardrail", "memory", "pipeline", "blender", "audio"} & set(record.tags) else 0.0
    )
    return round(overlap * 4.0 + record.confidence * 2.0 + tag_bonus, 4)

def select_memory(
    records: Iterable[MemoryRecord], objective: str, max_chars: int
) -> list[dict[str, Any]]:
    """Rank and select memory records under a character budget."""
    ranked = sorted(records, key=lambda item: score_record(item, objective), reverse=True)
    selected: list[dict[str, Any]] = []
    used = 0
    for record in ranked:
        cost = len(record.content) + 320
        if selected and used + cost > max_chars:
            continue
        payload = record.to_dict()
        payload["rank_score"] = score_record(record, objective)
        selected.append(payload)
        used += cost
        if used >= max_chars:
            break
    return selected

def default_microtasks(
    objective: str, selected_memory: list[dict[str, Any]]
) -> list[AgentMicroTask]:
    """Create a generic first-pass microtask graph."""
    source_paths = tuple(str(item.get("source")) for item in selected_memory if item.get("source"))
    objective_slug = slugify(objective, "objective")[:48]
    return [
        AgentMicroTask(
            task_id=f"{objective_slug}_context_read",
            title="Read selected context and constraints",
            lane="CPU",
            purpose="Build the immediate working context without loading unrelated files.",
            priority=9,
            blocking=True,
            inputs=source_paths,
            expected_outputs=("agent_state_packet.json",),
        ),
        AgentMicroTask(
            task_id=f"{objective_slug}_npu_guardrail",
            title="Run non-blocking NPU-light guardrail",
            lane="NPU",
            purpose="Score packet risks, missing assumptions, stale context and blocked patterns.",
            priority=8,
            blocking=False,
            inputs=("agent_state_packet.json",),
            expected_outputs=(
                "agent_guardrail_report.json",
                "agent_guardrail_action_queue.json",
            ),
            depends_on=(f"{objective_slug}_context_read",),
            metadata={"soft_fail": True, "recommended_workers_max": 4},
        ),
        AgentMicroTask(
            task_id=f"{objective_slug}_gpu_optional_planner",
            title="Optional GPU heavy planning lane",
            lane="GPU",
            purpose="Use only when explicitly requested or app policy allows heavy generation.",
            priority=4,
            blocking=False,
            status="opt_in_required",
            inputs=("agent_state_packet.json",),
            expected_outputs=("gpu_planner_output.json",),
            depends_on=(f"{objective_slug}_context_read",),
            metadata={"heavy": True, "do_not_run_with_heavy_blender_render": True},
        ),
        AgentMicroTask(
            task_id=f"{objective_slug}_validate",
            title="Validate artifacts and update memory",
            lane="VALIDATION",
            purpose="Run focused validators, summarize results and append durable lessons.",
            priority=9,
            blocking=True,
            inputs=("agent_state_packet.json", "agent_guardrail_report.json"),
            expected_outputs=("validation_report.json", "persistent_memory.jsonl"),
            depends_on=(f"{objective_slug}_context_read",),
        ),
    ]

def build_agent_state_packet(
    *,
    repo_root: Path,
    objective: str,
    records: Iterable[MemoryRecord],
    max_memory_chars: int = DEFAULT_MAX_MEMORY_CHARS,
    packet_name: str = "agent_state_packet",
) -> dict[str, Any]:
    """Build a task-specific agent state packet."""
    record_list = list(records)
    selected = select_memory(record_list, objective, max_memory_chars)
    microtasks = default_microtasks(objective, selected)
    manifest = [
        {
            "record_id": item.record_id,
            "kind": item.kind,
            "scope": item.scope,
            "source": item.source,
            "tags": list(item.tags),
            "confidence": item.confidence,
            "rank_score": score_record(item, objective),
        }
        for item in record_list
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "agent_state_packet",
        "packet_name": packet_name,
        "generated_at": utc_now_iso(),
        "repo_root": str(repo_root),
        "objective": objective,
        "policy": {
            "token_strategy": "Select ranked memory records under budget; expand by source path or record_id only when needed.",
            "recent_memory": "Use included files and conversation-derived records for the immediate task.",
            "persistent_memory": "Use JSONL records for durable constraints, known fixes and prior validation results.",
            "hardware_lanes": "CPU is deterministic orchestration, NPU is non-blocking light review, GPU is explicit opt-in heavy generation.",
            "runtime_safety": "This packet does not execute Blender, GPU, NPU, FFmpeg or source-code modifications.",
        },
        "budgets": {
            "max_memory_chars": max_memory_chars,
            "selected_memory_chars": sum(len(str(item.get("content") or "")) for item in selected),
        },
        "selected_memory": selected,
        "memory_manifest": sorted(manifest, key=lambda item: item["rank_score"], reverse=True),
        "microtasks": [item.to_dict() for item in microtasks],
        "assumptions": [
            "Operational self-awareness means structured state, constraints, memory and validation status.",
            "Hardware lanes are declared as planned work only; execution is controlled by the app or pipeline policy.",
            "Future file types should be represented as memory records with kind, scope, source, tags and metadata.",
        ],
    }

def write_agent_state_markdown(packet: dict[str, Any], path: Path) -> None:
    """Write a compact Markdown companion for human review."""
    lines = [
        "# Agent State Packet",
        "",
        f"Generated: `{packet.get('generated_at')}`",
        f"Objective: `{packet.get('objective')}`",
        "",
        "## Selected Memory",
    ]
    for item in packet.get("selected_memory", []):
        lines.extend(
            [
                "",
                f"### {item.get('record_id')} - {item.get('source')}",
                f"- Kind: `{item.get('kind')}`",
                f"- Tags: `{', '.join(item.get('tags') or [])}`",
                f"- Score: `{item.get('rank_score')}`",
                "",
                str(item.get("summary") or ""),
            ]
        )
    lines.extend(["", "## Microtasks"])
    for item in packet.get("microtasks", []):
        lines.append(
            f"- `{item.get('task_id')}` [{item.get('lane')}] blocking={item.get('blocking')} status={item.get('status')}: {item.get('purpose')}"
        )
    lines.extend(["", "## Policy"])
    for key, value in (packet.get("policy") or {}).items():
        lines.append(f"- `{key}`: {value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
