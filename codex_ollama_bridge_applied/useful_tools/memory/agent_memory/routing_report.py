"""Report assembly for agent memory routing policy."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from typing import Any

from .common import relative_path, resolve_repo_path
from .routing_requests import (
    build_discovery_tool_requests,
    build_memory_tool_requests,
    build_promotion_candidates,
)


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def resolve_path(repo_root: Path, value: str | Path) -> Path:
    return resolve_repo_path(repo_root, value)


def repo_rel(path: Path, repo_root: Path) -> str:
    return relative_path(path, repo_root)

def build_policy(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = Path(args.repo_root).resolve()
    memory_requests = build_memory_tool_requests(args)
    discovery_requests = build_discovery_tool_requests(args)
    tool_requests = memory_requests + discovery_requests
    promotion_candidates = build_promotion_candidates(args)

    broker_request = {
        "schema_version": 1,
        "kind": "agent_runtime_tool_request_packet",
        "generated_at": now_iso(),
        "objective": args.objective,
        "profile": args.profile,
        "tool_requests": tool_requests,
        "guardrails": {
            "free_shell_allowed": False,
            "broker_allowlist_required": True,
            "persistent_memory_write_allowed": False,
            "operational_memory_write_allowed_under_output": True,
            "automatic_promotion_allowed": False,
        },
    }

    persistent_count = sum(
        1
        for item in tool_requests
        if item.get("tool") == "runtime_sqlite_memory"
        and item.get("args", {}).get("scope") == "persistent"
    )
    operational_count = sum(
        1
        for item in tool_requests
        if item.get("tool") == "runtime_sqlite_memory"
        and item.get("args", {}).get("scope") == "operational"
    )
    operational_write_count = sum(
        1
        for item in tool_requests
        if item.get("tool") == "runtime_sqlite_memory"
        and item.get("args", {}).get("scope") == "operational"
        and item.get("args", {}).get("action") in {"remember", "clear_operational"}
    )

    return {
        "schema_version": 1,
        "kind": "agent_memory_routing_policy",
        "generated_at": now_iso(),
        "repo_root": str(repo_root),
        "objective": args.objective,
        "profile": args.profile,
        "passed": True,
        "errors": [],
        "warnings": [],
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": False,
        "sqlite_write_performed": False,
        "persistent_memory_write_performed": False,
        "operational_sqlite_write_performed": False,
        "broker_request_artifact": "",
        "broker_request_transport": "in_memory",
        "broker_request_packet": broker_request,
        "memory_plan": {
            "persistent_read_only": True,
            "persistent_query_count": persistent_count,
            "operational_query_or_write_count": operational_count,
            "operational_write_request_count": operational_write_count,
            "tool_request_count": len(tool_requests),
            "tool_requests": tool_requests,
            "promotion_candidates": promotion_candidates,
        },
        "decision": {
            "use_persistent_memory_for": [
                "validated durable project facts",
                "guardrails",
                "historical lessons",
                "stable architecture state",
            ],
            "use_operational_memory_for": [
                "current run state",
                "temporary planner notes",
                "tool results",
                "hypotheses not yet validated",
            ],
            "promotion_policy": "manual_review_after_evidence_only",
            "next_layer": "agent_runtime_tool_broker",
        },
        "guardrails": {
            "free_shell_allowed": False,
            "broker_allowlist_required": True,
            "persistent_memory_read_only": True,
            "persistent_memory_write_performed": False,
            "sqlite_write_performed": False,
            "operational_memory_write_allowed_under_output": True,
            "automatic_persistent_promotion_allowed": False,
            "manual_review_required_for_promotion": True,
            "provider_execution_performed": False,
            "patch_application_performed": False,
            "blender_runtime_touched": False,
            "git_write_performed": False,
        },
    }

def render_markdown(report: dict[str, Any]) -> str:
    lines = ["# Agent Memory Routing Policy", ""]
    for key in (
        "passed",
        "profile",
        "broker_request_transport",
        "provider_execution_performed",
        "patch_application_performed",
        "sqlite_write_performed",
        "persistent_memory_write_performed",
        "operational_sqlite_write_performed",
    ):
        lines.append(f"- {key}: `{report.get(key)}`")
    lines.append("")
    lines.append(f"- Objective: `{report.get('objective')}`")
    lines.append("")
    lines.append("## Memory plan")
    plan = report.get("memory_plan", {})
    for key in (
        "persistent_read_only",
        "persistent_query_count",
        "operational_query_or_write_count",
        "operational_write_request_count",
        "tool_request_count",
    ):
        lines.append(f"- `{key}`: `{plan.get(key)}`")
    lines.append("")
    lines.append("## Tool requests")
    lines.append("")
    for item in plan.get("tool_requests", []):
        lines.append(f"- `{item.get('id')}` -> `{item.get('tool')}`: {item.get('reason')}")
    lines.append("")
    lines.append("## Guardrails")
    lines.append("")
    for key, value in report.get("guardrails", {}).items():
        lines.append(f"- `{key}`: `{value}`")
    return "\n".join(lines) + "\n"
