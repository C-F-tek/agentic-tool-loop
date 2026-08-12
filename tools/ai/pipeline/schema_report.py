"""Schema-v6 report builders for the AI artifact pipeline."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .artifact_contracts import planned_outputs, slugify
from .defaults import DRY_RUN_REPORT_NAME, PIPELINE_SCHEMA_VERSION, RUN_REPORT_NAME
from .reports import utc_now_iso


def summarize_results(results: list[dict]) -> dict:
    """Return a compact status summary for pipeline reports."""
    failed = [item for item in results if item.get("returncode") != 0]
    planned_only = [item for item in results if item.get("planned_only")]
    durations = [float(item.get("duration_sec") or 0.0) for item in results]
    lane_counts: dict[str, int] = {}
    for item in results:
        lane = str(item.get("lane") or "UNKNOWN")
        lane_counts[lane] = lane_counts.get(lane, 0) + 1
    return {
        "ok_count": len(results) - len(failed),
        "failed_count": len(failed),
        "planned_only_count": len(planned_only),
        "total_duration_sec": round(sum(durations), 4),
        "failed_steps": [str(item.get("name") or "unknown") for item in failed],
        "lane_counts": lane_counts,
    }


def empty_failed_report(repo: Path, out: Path, dry_run: bool, pf: dict) -> dict:
    """Return a schema-compatible report when preflight fails."""
    return {
        "schema_version": PIPELINE_SCHEMA_VERSION,
        "generated_at": utc_now_iso(),
        "repo_root": str(repo),
        "output_dir": str(out),
        "dry_run": dry_run,
        "passed": False,
        "preflight": pf,
        "step_count": 0,
        "summary": summarize_results([]),
        "schedule": {},
        "steps": [],
    }


def agent_state_packet_report(repo: Path, args: argparse.Namespace, pf: dict) -> dict[str, Any]:
    """Return report metadata for the optional agent state packet touchpoint."""
    raw = getattr(args, "agent_state_packet", None)
    meta = dict(pf.get("agent_state_packet") or {})
    if not raw:
        return {"enabled": False, "path": None, "exists": False, "source": "disabled"}
    meta.setdefault("enabled", True)
    meta.setdefault("path", str(Path(raw).resolve()))
    meta.setdefault("exists", Path(raw).resolve().exists())
    meta["source"] = "cli"
    try:
        meta["repo_relative_path"] = Path(raw).resolve().relative_to(repo.resolve()).as_posix()
    except ValueError:
        meta["repo_relative_path"] = str(Path(raw).resolve())
    return meta


def build_report(
    repo: Path,
    out: Path,
    args: argparse.Namespace,
    pf: dict,
    results: list[dict],
    remediation_loop: dict,
    schedule: dict[str, Any] | None = None,
) -> dict:
    """Build the schema-v6 pipeline report."""
    track_slug = slugify(args.track_stem)
    return {
        "schema_version": PIPELINE_SCHEMA_VERSION,
        "generated_at": utc_now_iso(),
        "repo_root": str(repo),
        "output_dir": str(out),
        "dry_run": args.dry_run,
        "passed": pf["passed"] and all(item["returncode"] == 0 for item in results),
        "preflight": pf,
        "step_count": len(results),
        "summary": summarize_results(results),
        "schedule": schedule or {},
        "lanes": {
            "CPU": [item["name"] for item in results if item.get("lane") == "CPU"],
            "NPU": [item["name"] for item in results if item.get("lane") == "NPU"],
            "GPU": [item["name"] for item in results if item.get("lane") == "GPU"],
        },
        "wave_entrypoint_review": {
            "enabled": args.review_wave_entrypoints,
            "report": str(out / "wave_entrypoint_review.json") if args.review_wave_entrypoints else None,
        },
        "smart_context": {
            "enabled": args.smart_context,
            "task": args.smart_task,
            "packet": str(out / "smart_context" / f"{track_slug}_smart_context_packet.json") if args.smart_context else None,
        },
        "agent_state_packet": agent_state_packet_report(repo, args, pf),
        "guardrail_remediation_loop": remediation_loop,
        "steps": results,
        "post_run_expected_outputs": planned_outputs(repo, out, args),
    }


def write_report_if_requested(out: Path, args: argparse.Namespace, report: dict) -> None:
    """Write final or dry-run report when requested by the invocation mode."""
    if not args.dry_run:
        target = out / RUN_REPORT_NAME
    elif args.write_dry_run_report:
        target = out / DRY_RUN_REPORT_NAME
    else:
        return
    target.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
