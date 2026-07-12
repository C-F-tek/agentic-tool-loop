"""RAG startup preload helpers for heap context memory reload."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from ia_carmine.context.agent_context.rag_context.chunking import ChunkPolicy
from ia_carmine.context.agent_context.rag_context.index_status import inspect_index
from ia_carmine.context.agent_context.rag_context.unified_pack import (
    build_unified_context_pack,
    render_markdown as render_unified_context_pack_markdown,
)
from ia_carmine.context.heap_context_memory_reload.common import (
    read_json,
    repo_rel,
    run_tool,
    write_json,
)
from ia_carmine.context.heap_context_memory_reload.runner_state import ReloadRun

RecordTool = Callable[..., None]


def write_startup_progress(
    state: ReloadRun,
    *,
    step: str,
    extra: dict[str, Any] | None = None,
) -> None:
    path = state.output_dir / "startup_rag_progress.json"
    previous = read_json(path)
    payload: dict[str, Any] = {
        "schema_version": 1,
        "kind": "startup_rag_progress",
        "step": step,
        "resource_lane": "ollama_embedding_gpu1",
        "embedding_endpoint": str(state.args.rag_embedding_endpoint),
        "embedding_model": str(state.args.rag_embedding_model),
        "ollama_embedding_performed": step.startswith("rag_"),
        "provider_execution_performed": False,
        "provider_lanes_started": False,
    }
    for key in (
        "rag_index_ready",
        "rag_index_action",
        "embedding_written_count",
        "missing_embedding_count_before",
        "missing_embedding_count_after",
        "providers_not_started_reason",
    ):
        if key in previous:
            payload[key] = previous[key]
    if extra:
        payload.update(extra)
    if payload.get("rag_index_ready") is False:
        payload.setdefault("providers_not_started_reason", "startup_rag_index_not_ready")
    write_json(path, payload)


def run_rag_context_pack(state: ReloadRun) -> None:
    write_startup_progress(state, step="rag_context_pack")
    pack_dir = state.output_dir / "startup_rag_context_pack"
    pack_json = pack_dir / f"rag_context_pack_{state.stamp}.json"
    pack_md = pack_dir / f"rag_context_pack_{state.stamp}.md"
    command = [
        state.project_python,
        "-m",
        "ia_carmine",
        "rag_build_context_pack",
        "--repo-root",
        ".",
        "--db",
        str(state.args.rag_db),
        "--top-k",
        str(state.args.rag_top_k),
        "--char-budget",
        str(state.args.rag_char_budget),
        "--embedding-endpoint",
        str(state.args.rag_embedding_endpoint),
        "--embedding-model",
        str(state.args.rag_embedding_model),
        "--output",
        str(pack_json),
        "--markdown-output",
        str(pack_md),
    ]
    request_file = str(state.args.request_file or state.artifacts.get("startup_request_file") or "")
    if request_file:
        command.extend(["--task-file", request_file])
    else:
        command.extend(["--query", state.request_text])
    if state.args.rag_skip_query_embedding:
        command.append("--skip-query-embedding")
    result = run_tool(
        command,
        state.repo_root,
        name="rag_context_pack_reload",
        requirement="rag_context_pack",
        required=True,
        artifact_paths=[pack_json, pack_md],
    )
    if result.get("returncode") != 0:
        result["effective_passed"] = False
        result["degraded"] = False
        result["hard_failed"] = True
    state.commands.append(result)
    state.artifacts["rag_context_pack_json"] = repo_rel(state.repo_root, pack_json)
    state.artifacts["rag_context_pack_markdown"] = repo_rel(state.repo_root, pack_md)
    pack_payload = read_json(pack_json)
    event_id = str(pack_payload.get("retrieval_event_id") or "")
    if event_id:
        state.artifacts["rag_retrieval_event_id"] = event_id
    if result.get("degraded"):
        state.warnings.append(
            "rag_context_pack_reload returned non-zero but useful artifacts exist"
        )
    warnings = pack_payload.get("warnings") if isinstance(pack_payload.get("warnings"), list) else []
    state.warnings.extend(f"rag_context_pack warning: {item}" for item in warnings[:5])
    write_startup_progress(
        state,
        step="rag_context_pack_complete" if result.get("returncode") == 0 else "rag_context_pack_failed",
        extra={
            "rag_context_pack_passed": result.get("returncode") == 0,
            "retrieval_event_id": event_id,
        },
    )


def harden_failed_required_result(result: dict[str, Any]) -> dict[str, Any]:
    if result.get("returncode") == 0:
        return result
    result["effective_passed"] = False
    result["degraded"] = False
    result["hard_failed"] = True
    return result


def _rag_db_path(state: ReloadRun) -> Path:
    path = Path(str(state.args.rag_db))
    if not path.is_absolute():
        path = state.repo_root / path
    return path.resolve(strict=False)


def _rag_chunk_policy(state: ReloadRun) -> ChunkPolicy:
    return ChunkPolicy(
        min_chars=int(state.args.rag_chunk_min_chars),
        max_chars=int(state.args.rag_chunk_max_chars),
        overlap_chars=int(state.args.rag_chunk_overlap_chars),
    ).normalized()


def _write_rag_index_status_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# RAG Index Status",
        "",
        f"- Passed: `{report.get('passed')}`",
        f"- Action: `{report.get('action')}`",
        f"- Ready: `{report.get('rag_index_ready')}`",
        f"- Reasons: `{report.get('reasons') or []}`",
        f"- Missing embeddings: `{report.get('missing_embedding_count')}`",
        "",
    ]
    if report.get("errors"):
        lines.extend(["## Errors", ""])
        lines.extend(f"- {item}" for item in report["errors"])
    if report.get("warnings"):
        lines.extend(["## Warnings", ""])
        lines.extend(f"- {item}" for item in report["warnings"][:40])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _record_rag_noop_or_block(
    state: ReloadRun,
    *,
    record_tool: RecordTool,
    report: dict[str, Any],
    output_json: Path,
    output_md: Path,
    passed: bool,
) -> None:
    payload = dict(report)
    payload.update(
        {
            "passed": passed,
            "provider_execution_performed": False,
            "patch_application_performed": False,
            "source_writes_performed": False,
        }
    )
    write_json(output_json, payload)
    _write_rag_index_status_markdown(output_md, payload)
    record_tool(
        state,
        name="rag_repo_ingest",
        requirement="rag_repo_ingest",
        required=True,
        command=["in_process", "ia_carmine.context.agent_context.rag_context.index_status"],
        returncode=0 if passed else 2,
        stdout_tail=json.dumps(
            {
                "action": payload.get("action"),
                "rag_index_ready": payload.get("rag_index_ready"),
                "reasons": payload.get("reasons") or [],
            },
            ensure_ascii=False,
        ),
        stderr_tail="",
        artifact_paths=[output_json, output_md],
    )
    if not passed:
        harden_failed_required_result(state.commands[-1])


def ensure_rag_index_current(state: ReloadRun, *, record_tool: RecordTool) -> None:
    smoke_json = state.output_dir / "startup_rag_ollama_embed_smoke.json"
    smoke_md = state.output_dir / "startup_rag_ollama_embed_smoke.md"
    ingest_json = state.output_dir / "startup_rag_ingest_repo.json"
    ingest_md = state.output_dir / "startup_rag_ingest_repo.md"
    state.artifacts["rag_ollama_embed_smoke_json"] = repo_rel(state.repo_root, smoke_json)
    state.artifacts["rag_ollama_embed_smoke_markdown"] = repo_rel(state.repo_root, smoke_md)
    state.artifacts["rag_repo_ingest_json"] = repo_rel(state.repo_root, ingest_json)
    state.artifacts["rag_repo_ingest_markdown"] = repo_rel(state.repo_root, ingest_md)
    policy = str(state.args.rag_index_policy or "auto").strip().lower()
    write_startup_progress(state, step="rag_embed_smoke")
    smoke_result = run_tool(
        [
            state.project_python,
            "-m",
            "Tools.validation",
            "run_rag_ollama_embed_smoke",
            "--repo-root",
            ".",
            "--endpoint",
            str(state.args.rag_embedding_endpoint),
            "--model",
            str(state.args.rag_embedding_model),
            "--batch-size",
            str(state.args.rag_embed_smoke_batch_size),
            "--output",
            str(smoke_json),
            "--markdown-output",
            str(smoke_md),
        ],
        state.repo_root,
        name="rag_ollama_embed_preflight",
        requirement="rag_ollama_embed_preflight",
        required=True,
        artifact_paths=[smoke_json, smoke_md],
    )
    state.commands.append(harden_failed_required_result(smoke_result))
    if smoke_result.get("returncode") != 0:
        write_startup_progress(
            state,
            step="rag_embed_smoke_failed",
            extra={
                "rag_index_ready": False,
                "rag_ollama_embed_preflight_passed": False,
                "providers_not_started_reason": "startup_rag_embed_smoke_failed",
            },
        )
        _record_rag_noop_or_block(
            state,
            record_tool=record_tool,
            report={
                "schema_version": 1,
                "kind": "rag_index_status",
                "action": "block",
                "rag_index_ready": False,
                "reasons": ["rag_embedding_preflight_failed"],
                "errors": ["rag embedding preflight failed"],
                "warnings": [],
            },
            output_json=ingest_json,
            output_md=ingest_md,
            passed=False,
        )
        return
    write_startup_progress(
        state,
        step="rag_index_status",
        extra={"rag_ollama_embed_preflight_passed": True},
    )
    status_report = inspect_index(
        repo_root=state.repo_root,
        db_path=_rag_db_path(state),
        embedding_model=str(state.args.rag_embedding_model),
        embedding_endpoint=str(state.args.rag_embedding_endpoint),
        max_file_size=int(state.args.rag_max_file_size),
        chunk_policy=_rag_chunk_policy(state),
        scan_index=state.repo_scan_index,
    )
    if status_report.get("action") == "block":
        write_startup_progress(
            state,
            step="rag_index_status_blocked",
            extra={
                "rag_index_ready": False,
                "providers_not_started_reason": "startup_rag_index_status_blocked",
                "missing_embedding_count_after": status_report.get("missing_embedding_count"),
            },
        )
        _record_rag_noop_or_block(
            state,
            record_tool=record_tool,
            report=status_report,
            output_json=ingest_json,
            output_md=ingest_md,
            passed=False,
        )
        return
    if policy == "never":
        passed = bool(status_report.get("rag_index_ready") or state.args.rag_allow_missing_embeddings)
        if not passed:
            status_report.setdefault("errors", []).append(
                "rag index policy is never but index is not ready"
            )
            status_report.setdefault("reasons", []).append("rag_index_policy_never_not_ready")
        _record_rag_noop_or_block(
            state,
            record_tool=record_tool,
            report=status_report,
            output_json=ingest_json,
            output_md=ingest_md,
            passed=passed,
        )
        write_startup_progress(
            state,
            step="rag_index_policy_never",
            extra={
                "rag_index_ready": passed,
                "missing_embedding_count_after": status_report.get("missing_embedding_count"),
            },
        )
        return
    if policy == "auto" and status_report.get("rag_index_ready") is True:
        _record_rag_noop_or_block(
            state,
            record_tool=record_tool,
            report=status_report,
            output_json=ingest_json,
            output_md=ingest_md,
            passed=True,
        )
        write_startup_progress(
            state,
            step="rag_index_noop_current",
            extra={
                "rag_index_ready": True,
                "rag_index_action": "noop_current",
                "missing_embedding_count_after": status_report.get("missing_embedding_count"),
            },
        )
        return
    write_startup_progress(
        state,
        step="rag_ingest_embeddings",
        extra={
            "rag_index_action": "ingest_required",
            "missing_embedding_count_before": status_report.get("missing_embedding_count"),
        },
    )
    command = [
        state.project_python,
        "-m",
        "ia_carmine",
        "rag_ingest_repo",
        "--repo-root",
        ".",
        "--db",
        str(state.args.rag_db),
        "--embedding-endpoint",
        str(state.args.rag_embedding_endpoint),
        "--embedding-model",
        str(state.args.rag_embedding_model),
        "--batch-size",
        str(state.args.rag_ingest_batch_size),
        "--chunk-min-chars",
        str(state.args.rag_chunk_min_chars),
        "--chunk-max-chars",
        str(state.args.rag_chunk_max_chars),
        "--chunk-overlap-chars",
        str(state.args.rag_chunk_overlap_chars),
        "--max-file-size",
        str(state.args.rag_max_file_size),
        "--startup-scan-index",
        str(state.output_dir / "startup_repo_scan_index.json"),
        "--output",
        str(ingest_json),
        "--markdown-output",
        str(ingest_md),
        "--require-embeddings",
    ]
    result = run_tool(
        command,
        state.repo_root,
        name="rag_repo_ingest",
        requirement="rag_repo_ingest",
        required=True,
        artifact_paths=[ingest_json, ingest_md],
    )
    state.commands.append(harden_failed_required_result(result))
    ingest_payload = read_json(ingest_json)
    write_startup_progress(
        state,
        step="rag_ingest_embeddings_complete"
        if ingest_payload.get("rag_index_ready") is True
        else "rag_ingest_embeddings_blocked",
        extra={
            "rag_index_ready": ingest_payload.get("rag_index_ready") is True,
            "rag_index_action": ingest_payload.get("action"),
            "embedding_written_count": ingest_payload.get("embedding_written_count"),
            "missing_embedding_count_before": ingest_payload.get("missing_embedding_count_before"),
            "missing_embedding_count_after": ingest_payload.get("missing_embedding_count_after"),
            "providers_not_started_reason": ""
            if ingest_payload.get("rag_index_ready") is True
            else "startup_rag_index_not_ready",
        },
    )


def write_unified_context_pack(state: ReloadRun, *, record_tool: RecordTool) -> None:
    write_startup_progress(state, step="startup_unified_context_pack")
    output_json = state.output_dir / "startup_unified_context_pack.json"
    output_md = state.output_dir / "startup_unified_context_pack.md"
    ai_json = state.repo_root / state.artifacts.get("ai_context_pack_json", "")
    rag_json = state.repo_root / state.artifacts.get("rag_context_pack_json", "")
    try:
        pack = build_unified_context_pack(
            repo_root=state.repo_root,
            ai_context_pack_json=ai_json,
            rag_context_pack_json=rag_json,
            stamp=state.stamp,
        )
        write_json(output_json, pack)
        output_md.write_text(render_unified_context_pack_markdown(pack), encoding="utf-8")
        returncode = 0 if pack.get("passed") is True else 2
        stdout = json.dumps(
            {
                "passed": pack.get("passed"),
                "context_pack_id": pack.get("context_pack_id"),
                "active_context_pack": pack.get("active_context_pack"),
            },
            ensure_ascii=False,
        )
        stderr = ""
    except Exception as exc:  # noqa: BLE001
        returncode = 1
        stdout = ""
        stderr = f"{type(exc).__name__}: {exc}"
    record_tool(
        state,
        name="startup_unified_context_pack",
        requirement="startup_unified_context_pack",
        required=True,
        command=["in_process", "ia_carmine.context.agent_context.rag_context.unified_pack"],
        returncode=returncode,
        stdout_tail=stdout,
        stderr_tail=stderr,
        artifact_paths=[output_json, output_md],
    )
    state.artifacts["startup_context_pack_json"] = repo_rel(state.repo_root, output_json)
    state.artifacts["startup_context_pack_markdown"] = repo_rel(state.repo_root, output_md)
    write_startup_progress(
        state,
        step="startup_unified_context_pack_complete"
        if returncode == 0
        else "startup_unified_context_pack_failed",
        extra={"startup_unified_context_pack_passed": returncode == 0},
    )
    if returncode != 0:
        harden_failed_required_result(state.commands[-1])
        state.warnings.append("startup unified context pack reported warnings/errors")
