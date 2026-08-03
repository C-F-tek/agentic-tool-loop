"""Runtime orchestration for heap startup reload."""

from __future__ import annotations

from argparse import Namespace
from concurrent.futures import ThreadPoolExecutor
import json
import shutil
from pathlib import Path
from typing import Any

from ia_carmine._shared.file_backed_transport import write_text_artifact
from ia_carmine.context.agent_context.transient_request_context.cli import build_context as build_transient_context, render_markdown as render_transient_markdown
from ia_carmine._shared.agent_memory_inventory_cli import DEFAULT_MEMORY_DB, build_inventory as build_memory_inventory, render_markdown as render_memory_inventory_markdown
from ia_carmine.context.heap_context_memory_reload.builders import build_repo_docs_map, collect_semantic_code_chunks, write_semantic_evidence
from ia_carmine.context.heap_context_memory_reload.common import (
    effective_tool_status,
    read_json,
    repo_rel,
    run_tool,
    summarize_artifact,
    write_json,
)
from ia_carmine.context.heap_context_memory_reload.delta import build_context_delta
from ia_carmine.context.heap_context_memory_reload.dynamic_gpu1_context import (
    build_gpu1_dynamic_context_pack,
)
from ia_carmine.context.heap_context_memory_reload.manifest import build_manifest, build_print_payload
from ia_carmine.context.heap_context_memory_reload.memory_write import build_final_task_markdown, run_operational_memory_write
from ia_carmine.context.heap_context_memory_reload import rag_startup
from ia_carmine.context.heap_context_memory_reload.runner_state import ReloadRun
from ia_carmine.context.heap_context_memory_reload.scanner import context_files_from_scan
from ia_carmine.context.heap_context_memory_reload.startup_scan import (
    build_startup_repo_scan_index,
    scan_digest_for_paths,
    scan_entries_by_path,
)


STARTUP_PARALLEL_REQUIREMENT_ORDER = {
    "required_context_files": 10,
    "repo_docs_map": 20,
    "semantic_code_chunks": 30,
    "tool_catalog": 40,
    "shared_memory": 50,
    "operational_memory_status": 60,
    "operational_memory_search": 70,
}


def record_inprocess_tool(
    state: ReloadRun,
    *,
    name: str,
    requirement: str,
    required: bool,
    command: list[str],
    returncode: int,
    stdout_tail: str,
    stderr_tail: str,
    artifact_paths: list[Path],
) -> None:
    artifacts = [summarize_artifact(path, state.repo_root) for path in artifact_paths]
    existing_artifacts = [item["path"] for item in artifacts if item.get("exists")]
    status = effective_tool_status(
        requirement=requirement,
        returncode=returncode,
        artifacts=artifacts,
    )
    state.commands.append(
        {
            "name": name,
            "requirement": requirement,
            "required": required,
            "command": command,
            "returncode": returncode,
            "passed": status["passed"],
            "effective_passed": status["effective_passed"],
            "degraded": status["degraded"],
            "hard_failed": status["hard_failed"],
            "artifact_useful": status["artifact_useful"],
            "strict_artifact_contract": status["strict_artifact_contract"],
            "artifact_contract_passed": status["artifact_contract_passed"],
            "artifact_paths": [item["path"] for item in artifacts],
            "existing_artifact_paths": existing_artifacts,
            "useful_artifact_paths": status["useful_artifact_paths"],
            "artifact_summaries": artifacts,
            "stdout_tail": stdout_tail[-3000:],
            "stderr_tail": stderr_tail[-3000:],
        }
    )


def run_reload(state: ReloadRun) -> int:
    state.output_dir.mkdir(parents=True, exist_ok=True)
    _materialize_startup_request(state)
    _run_required_context(state)
    _build_startup_repo_scan(state)
    _run_parallel_provider_input_lanes(state)
    _sort_startup_commands(state)
    _run_transient_context(state)
    _run_ai_context_pack(state)
    rag_startup.ensure_rag_index_current(state, record_tool=record_inprocess_tool)
    rag_startup.run_rag_context_pack(state)
    rag_startup.write_unified_context_pack(state, record_tool=record_inprocess_tool)
    _run_gpu1_dynamic_context_pack(state)
    state.artifacts.update(write_semantic_evidence(state.commands, state.repo_root, state.output_dir))
    task_file = state.output_dir / "heap_startup_input_ready_context.md"
    state.artifacts["heap_task_file"] = repo_rel(state.repo_root, task_file)
    run_operational_memory_write(state)
    task_markdown = build_final_task_markdown(state)
    task_file.write_text(task_markdown, encoding="utf-8")
    manifest = build_manifest(
        stamp=state.stamp,
        repo_root=state.repo_root,
        project_python=state.project_python,
        request_text=state.request_text,
        context_files=state.context_files,
        artifacts=state.artifacts,
        commands=state.commands,
        warnings=state.warnings,
        task_file=task_file,
        context_delta=state.context_delta,
        context_pack_result=state.context_pack_result,
        strict_ai_context_pack=bool(state.args.strict_ai_context_pack),
        strict_startup_reload=bool(state.args.strict_startup_reload),
        startup_effective_config={
            "startup_provider_input_workers": int(
                getattr(state.args, "startup_provider_input_workers", 0) or 0
            ),
            "startup_required_context_profile": str(
                getattr(state.args, "startup_required_context_profile", "") or ""
            ),
            "ai_context_pack_profile": str(
                getattr(state.args, "ai_context_pack_profile", "") or ""
            ),
            "startup_operational_memory_query": str(
                getattr(state.args, "startup_operational_memory_query", "") or ""
            ),
            "startup_operational_memory_limit": int(
                getattr(state.args, "startup_operational_memory_limit", 0) or 0
            ),
            "parallel_provider_input_lanes": state.artifacts.get(
                "startup_parallel_provider_input_lanes", ""
            ),
        },
    )
    manifest_path = state.output_dir / "heap_context_memory_reload_manifest.json"
    manifest_md = state.output_dir / "heap_context_memory_reload_manifest.md"
    write_json(manifest_path, manifest)
    manifest_md.write_text(task_markdown, encoding="utf-8")
    print_payload = build_print_payload(manifest, state.repo_root, manifest_path, manifest_md)
    print(json.dumps(print_payload, indent=2, ensure_ascii=False))
    return 0 if manifest["passed"] else 2


def _materialize_startup_request(state: ReloadRun) -> None:
    if getattr(state.args, "request_file", ""):
        path = Path(str(state.args.request_file))
        if not path.is_absolute():
            path = state.repo_root / path
        state.artifacts["startup_request_file"] = repo_rel(state.repo_root, path)
        return
    if not state.request_text:
        return
    ref = write_text_artifact(
        state.repo_root,
        state.output_dir / "payload",
        name="request",
        text=state.request_text,
        kind="operator_request",
        producer="heap_context_memory_reload",
        suffix=".md",
    )
    state.artifacts["startup_request_file"] = str(ref["path"])


def _build_startup_repo_scan(state: ReloadRun) -> None:
    state.repo_scan_index = build_startup_repo_scan_index(
        state.repo_root,
        state.output_dir,
        max_hash_size=max(1, int(state.args.rag_max_file_size)),
    )
    scan_path = state.output_dir / "startup_repo_scan_index.json"
    state.artifacts["startup_repo_scan_index_json"] = repo_rel(state.repo_root, scan_path)


def _run_parallel_provider_input_lanes(state: ReloadRun) -> None:
    workers = max(1, int(getattr(state.args, "startup_provider_input_workers", 0) or 0))
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="startup-provider-input") as pool:
        futures = [
            pool.submit(_build_context_maps, state),
            pool.submit(_run_tool_catalog, state),
            pool.submit(_run_memory_inventory, state),
            pool.submit(_run_operational_memory_reads, state),
        ]
        for future in futures:
            future.result()
    state.artifacts["startup_parallel_provider_input_lanes"] = (
        "repo_docs_map,semantic_code_chunks,tool_catalog,shared_memory,"
        "operational_memory_status,operational_memory_search"
    )


def _sort_startup_commands(state: ReloadRun) -> None:
    state.commands.sort(
        key=lambda item: (
            STARTUP_PARALLEL_REQUIREMENT_ORDER.get(str(item.get("requirement") or ""), 1000),
            str(item.get("name") or ""),
        )
    )


def _run_required_context(state: ReloadRun) -> None:
    context_json = state.output_dir / "startup_required_ai_context_files.json"
    context_md = state.output_dir / "startup_required_ai_context_files.md"
    state.commands.append(
        run_tool(
            [
                state.project_python,
                "-m",
                "ia_carmine",
                "ensure_ai_context_required_files",
                "--repo-root",
                ".",
                "--profile",
                str(state.args.startup_required_context_profile),
                "--output",
                str(context_json),
                "--markdown-output",
                str(context_md),
                "--apply",
            ],
            state.repo_root,
            name="required_context_files_reload",
            requirement="required_context_files",
            required=True,
            artifact_paths=[context_json, context_md],
        )
    )
    state.artifacts["required_context_files_json"] = repo_rel(state.repo_root, context_json)
    state.artifacts["required_context_files_markdown"] = repo_rel(state.repo_root, context_md)


def _build_context_maps(state: ReloadRun) -> None:
    state.context_files = context_files_from_scan(
        state.repo_scan_index,
        repo_root=state.repo_root,
        max_files=state.args.startup_scan_context_files,
    )
    build_context_delta(state)
    changed_paths = set(state.context_delta.get("changed_context_files") or [])
    delta_active = state.context_delta.get("reload_mode") == "delta_index"
    state.artifacts.update(
        build_repo_docs_map(
            state.repo_root,
            state.context_files,
            state.output_dir,
            changed_paths=changed_paths,
            delta_active=delta_active,
            scan_index=state.repo_scan_index,
        )
    )
    state.artifacts.update(
        collect_semantic_code_chunks(
            state.repo_root,
            state.output_dir,
            state.request_text,
            limit=max(1, state.args.max_context_files),
            preview_chars=max(1, state.args.max_chars_per_file),
            changed_paths=changed_paths,
            delta_active=delta_active,
            scan_index=state.repo_scan_index,
        )
    )


def _run_tool_catalog(state: ReloadRun) -> None:
    tool_catalog_json = state.output_dir / "startup_tool_catalog.json"
    tool_catalog_md = state.output_dir / "startup_tool_catalog.md"
    cache_hit = _try_restore_tool_catalog_cache(state, tool_catalog_json, tool_catalog_md)
    if cache_hit:
        state.commands.append(cache_hit)
        state.artifacts["tool_catalog_json"] = repo_rel(state.repo_root, tool_catalog_json)
        state.artifacts["tool_catalog_markdown"] = repo_rel(state.repo_root, tool_catalog_md)
        return
    state.commands.append(
        run_tool(
            [
                state.project_python,
                "-m",
                "ia_carmine",
                "build_agent_agnostic_tool_inventory",
                "--repo-root",
                ".",
                "--output",
                str(tool_catalog_json),
                "--markdown-output",
                str(tool_catalog_md),
            ],
            state.repo_root,
            name="tool_catalog_reload",
            requirement="tool_catalog",
            required=True,
            artifact_paths=[tool_catalog_json, tool_catalog_md],
        )
    )
    _store_tool_catalog_cache(state, tool_catalog_json, tool_catalog_md, state.commands[-1])
    state.artifacts["tool_catalog_json"] = repo_rel(state.repo_root, tool_catalog_json)
    state.artifacts["tool_catalog_markdown"] = repo_rel(state.repo_root, tool_catalog_md)


def _tool_catalog_cache_paths(state: ReloadRun) -> tuple[Path, Path, Path]:
    cache_dir = state.repo_root / "output" / "ai_runtime_memory" / "startup_tool_catalog_cache"
    return cache_dir / "startup_tool_catalog.json", cache_dir / "startup_tool_catalog.md", cache_dir / "meta.json"


def _tool_catalog_dependency_digest(state: ReloadRun) -> tuple[str, int]:
    entries = scan_entries_by_path(state.repo_scan_index)
    relevant = [
        item
        for rel_path, item in entries.items()
        if rel_path.startswith("Tools/")
        or (
            rel_path.startswith("ia_carmine/")
            and (
                rel_path.endswith("/cli.py")
                or rel_path.endswith("/dispatch.py")
                or rel_path.endswith("/TOOL_CONTEXT.md")
                or rel_path.endswith("/CONTEXT_INDEX.md")
            )
        )
    ]
    return scan_digest_for_paths(relevant), len(relevant)


def _try_restore_tool_catalog_cache(
    state: ReloadRun, tool_catalog_json: Path, tool_catalog_md: Path
) -> dict[str, Any] | None:
    cache_json, cache_md, cache_meta = _tool_catalog_cache_paths(state)
    digest, dependency_count = _tool_catalog_dependency_digest(state)
    meta = read_json(cache_meta)
    miss_reason = ""
    if not meta:
        miss_reason = "cache_meta_missing"
    elif meta.get("dependency_digest") != digest:
        miss_reason = "dependency_digest_changed"
    elif not cache_json.exists() or not cache_md.exists():
        miss_reason = "cached_artifact_missing"
    if miss_reason:
        state.artifacts["tool_catalog_cache_hit"] = "False"
        state.artifacts["tool_catalog_cache_miss_reason"] = miss_reason
        return None
    tool_catalog_json.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(cache_json, tool_catalog_json)
    shutil.copyfile(cache_md, tool_catalog_md)
    artifacts = [summarize_artifact(path, state.repo_root) for path in [tool_catalog_json, tool_catalog_md]]
    result = {
        "name": "tool_catalog_reload",
        "requirement": "tool_catalog",
        "required": True,
        "command": ["cache_hit", "startup_tool_catalog_cache"],
        "returncode": 0,
        "passed": True,
        "effective_passed": True,
        "degraded": False,
        "hard_failed": False,
        "artifact_useful": True,
        "artifact_paths": [item["path"] for item in artifacts],
        "existing_artifact_paths": [item["path"] for item in artifacts if item.get("exists")],
        "useful_artifact_paths": [item["path"] for item in artifacts if item.get("useful")],
        "artifact_summaries": artifacts,
        "stdout_tail": json.dumps(
            {
                "cache_hit": True,
                "source_run": meta.get("source_run"),
                "dependency_count": dependency_count,
            },
            ensure_ascii=False,
        ),
        "stderr_tail": "",
        "cache_hit": True,
        "cache_miss_reason": "",
        "source_run": str(meta.get("source_run") or ""),
    }
    state.artifacts["tool_catalog_cache_hit"] = "True"
    state.artifacts["tool_catalog_cache_source_run"] = result["source_run"]
    return result


def _store_tool_catalog_cache(
    state: ReloadRun, tool_catalog_json: Path, tool_catalog_md: Path, result: dict[str, Any]
) -> None:
    cache_json, cache_md, cache_meta = _tool_catalog_cache_paths(state)
    digest, dependency_count = _tool_catalog_dependency_digest(state)
    if not result.get("effective_passed") or not tool_catalog_json.exists() or not tool_catalog_md.exists():
        return
    cache_json.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(tool_catalog_json, cache_json)
    shutil.copyfile(tool_catalog_md, cache_md)
    write_json(
        cache_meta,
        {
            "schema_version": 1,
            "kind": "startup_tool_catalog_cache_meta",
            "source_run": state.stamp,
            "dependency_digest": digest,
            "dependency_count": dependency_count,
            "json_path": repo_rel(state.repo_root, cache_json),
            "markdown_path": repo_rel(state.repo_root, cache_md),
        },
    )
    result["cache_hit"] = False
    result["cache_miss_reason"] = state.artifacts.get("tool_catalog_cache_miss_reason", "cache_populated")
    result["source_run"] = state.stamp
    state.artifacts["tool_catalog_cache_hit"] = "False"


def _run_memory_inventory(state: ReloadRun) -> None:
    memory_json = state.output_dir / "startup_memory_inventory.json"
    memory_md = state.output_dir / "startup_memory_inventory.md"
    command = ["in_process", "ia_carmine._shared.agent_memory_inventory_cli.build_inventory"]
    try:
        inventory_args = Namespace(
            repo_root=str(state.repo_root),
            objective=state.request_text or "heap startup memory reload",
            memory_db=DEFAULT_MEMORY_DB,
            memory_jsonl=[],
            memory_db_limit=1000,
            max_memory_chars=state.args.max_memory_chars,
            max_preview_records=20,
            max_policy_items=30,
            max_sqlite_tables=40,
            output=str(memory_json),
            markdown_output=str(memory_md),
        )
        report = build_memory_inventory(inventory_args)
        write_json(memory_json, report)
        memory_md.write_text(render_memory_inventory_markdown(report), encoding="utf-8")
        stdout = json.dumps(
            {
                "passed": report.get("passed"),
                "record_count": report.get("records", {}).get("record_count"),
                "memory_db_exists": report.get("inputs", {}).get("memory_db_exists"),
                "request_transport": "in_memory",
            },
            ensure_ascii=False,
        )
        returncode = 0 if report.get("passed") is True else 2
        stderr = ""
    except Exception as exc:  # noqa: BLE001
        stdout = ""
        stderr = f"{type(exc).__name__}: {exc}"
        returncode = 1
    record_inprocess_tool(
        state,
        name="shared_memory_reload",
        requirement="shared_memory",
        required=True,
        command=command,
        returncode=returncode,
        stdout_tail=stdout,
        stderr_tail=stderr,
        artifact_paths=[memory_json, memory_md],
    )
    state.artifacts["shared_memory_json"] = repo_rel(state.repo_root, memory_json)
    state.artifacts["shared_memory_markdown"] = repo_rel(state.repo_root, memory_md)


def _run_operational_memory_reads(state: ReloadRun) -> None:
    status_json = state.output_dir / "startup_operational_memory_status.json"
    status_md = state.output_dir / "startup_operational_memory_status.md"
    search_json = state.output_dir / "startup_operational_memory_search.json"
    search_md = state.output_dir / "startup_operational_memory_search.md"
    _run_memory_action(state, "status", [], status_json, status_md, "operational_memory_status")
    _run_memory_action(
        state,
        "search",
        [
            "--query",
            str(state.args.startup_operational_memory_query),
            "--limit",
            str(state.args.startup_operational_memory_limit),
        ],
        search_json,
        search_md,
        "operational_memory_search",
    )


def _run_memory_action(
    state: ReloadRun,
    action: str,
    extra: list[str],
    output_json: Path,
    output_md: Path,
    requirement: str,
) -> None:
    state.commands.append(
        run_tool(
            [
                state.project_python,
                "-m",
                "ia_carmine",
                "agent_runtime_sqlite_memory",
                "--repo-root",
                ".",
                "--action",
                action,
                "--scope",
                "operational",
                *extra,
                "--output",
                str(output_json),
                "--markdown-output",
                str(output_md),
            ],
            state.repo_root,
            name=f"{requirement}_reload",
            requirement=requirement,
            required=True,
            artifact_paths=[output_json, output_md],
        )
    )
    state.artifacts[f"{requirement}_json"] = repo_rel(state.repo_root, output_json)
    state.artifacts[f"{requirement}_markdown"] = repo_rel(state.repo_root, output_md)


def _run_transient_context(state: ReloadRun) -> None:
    raw_limit = max(1, min(state.args.startup_scan_context_files, state.args.max_context_files))
    raw_files = state.context_files[:raw_limit]
    transient_json = state.output_dir / "startup_transient_request_context.json"
    transient_md = state.output_dir / "startup_transient_request_context.md"
    command = ["in_process", "ia_carmine.context.agent_context.transient_request_context.cli.build_context"]
    try:
        context_args = Namespace(
            repo_root=str(state.repo_root),
            objective="heap startup context/memory reload before provider lanes",
            memory_note=[state.request_text or "heap startup request"],
            memory_note_file=[],
            raw_file=raw_files,
            raw_file_list=[],
            report_file=[
                str(state.output_dir / "startup_tool_catalog.json"),
                str(state.output_dir / "startup_memory_inventory.json"),
                str(state.output_dir / "startup_operational_memory_status.json"),
                str(state.output_dir / "startup_operational_memory_search.json"),
            ],
            max_raw_files=raw_limit,
            max_chars_per_file=state.args.max_chars_per_file,
            output=str(transient_json),
            markdown_output=str(transient_md),
        )
        report = build_transient_context(context_args)
        write_json(transient_json, report)
        transient_md.write_text(render_transient_markdown(report), encoding="utf-8")
        stdout = json.dumps(
            {
                "passed": report.get("passed"),
                "memory_note_count": len(report.get("memory_notes", [])),
                "raw_file_count": report.get("raw_context", {}).get("file_count"),
                "request_transport": "in_memory",
            },
            ensure_ascii=False,
        )
        returncode = 0 if report.get("passed") is True else 2
        stderr = ""
    except Exception as exc:  # noqa: BLE001
        stdout = ""
        stderr = f"{type(exc).__name__}: {exc}"
        returncode = 1
    record_inprocess_tool(
        state,
        name="shared_context_reload",
        requirement="shared_context_chunks",
        required=True,
        command=command,
        returncode=returncode,
        stdout_tail=stdout,
        stderr_tail=stderr,
        artifact_paths=[transient_json, transient_md],
    )
    state.artifacts["shared_context_json"] = repo_rel(state.repo_root, transient_json)
    state.artifacts["shared_context_markdown"] = repo_rel(state.repo_root, transient_md)
    state.artifacts["startup_context_raw_file_count"] = str(len(raw_files))


def _run_ai_context_pack(state: ReloadRun) -> None:
    pack_dir = state.output_dir / "startup_ai_context_pack"
    evidence_dir = state.output_dir / "startup_ai_context_pack_evidence"
    basename = f"heap_startup_context_pack_{state.stamp}"
    pack_json = pack_dir / f"{basename}.json"
    pack_md = pack_dir / f"{basename}.md"
    evidence_json = evidence_dir / f"{basename}_evidence.json"
    evidence_md = evidence_dir / f"{basename}_evidence.md"
    state.context_pack_result = run_tool(
        [
            state.project_python,
            "-m",
            "ia_carmine",
            "ai_context_pack",
            "--repo-root",
            ".",
            "--profile",
            str(
                getattr(state.args, "ai_context_pack_profile", "")
                or getattr(state.args, "startup_required_context_profile", "")
                or "project_self_improvement"
            ),
            "--output-dir",
            str(pack_dir),
            "--basename",
            basename,
            "--evidence-dir",
            str(evidence_dir),
            "--evidence-basename",
            f"{basename}_evidence",
        ],
        state.repo_root,
        name="ai_context_pack_reload",
        requirement="ai_context_pack",
        required=True,
        artifact_paths=[pack_json, pack_md, evidence_json, evidence_md],
    )
    state.commands.append(state.context_pack_result)
    state.artifacts["ai_context_pack_json"] = repo_rel(state.repo_root, pack_json)
    state.artifacts["ai_context_pack_markdown"] = repo_rel(state.repo_root, pack_md)
    state.artifacts["ai_context_pack_evidence_json"] = repo_rel(state.repo_root, evidence_json)
    state.artifacts["ai_context_pack_evidence_markdown"] = repo_rel(state.repo_root, evidence_md)
    if state.context_pack_result["degraded"]:
        pack_payload = read_json(pack_json)
        warning = (
            "ai_context_pack_reload returned non-zero "
            + f"rc={state.context_pack_result['returncode']} but useful artifacts exist"
        )
        errors = pack_payload.get("errors") if isinstance(pack_payload.get("errors"), list) else []
        if errors:
            warning += "; errors=" + "; ".join(str(item) for item in errors[:5])
        state.warnings.append(warning)
        warnings = pack_payload.get("warnings") if isinstance(pack_payload.get("warnings"), list) else []
        state.warnings.extend(f"ai_context_pack warning: {item}" for item in warnings[:5])


def _run_gpu1_dynamic_context_pack(state: ReloadRun) -> None:
    command = ["in_process", "gpu1_dynamic_context_pack"]
    try:
        payload, output_json, output_md = build_gpu1_dynamic_context_pack(
            repo_root=state.repo_root,
            output_dir=state.output_dir,
            stamp=state.stamp,
            artifacts=state.artifacts,
            commands=state.commands,
            request_text=state.request_text,
        )
        returncode = 0 if payload.get("passed") is True else 2
        stdout = json.dumps(
            {
                "passed": payload.get("passed"),
                "active_context_pack": payload.get("active_context_pack"),
                "tool_definition_count": payload.get("broker_tool_schema_count"),
                "artifact_ref_count": len(payload.get("artifact_refs") or {}),
            },
            ensure_ascii=False,
        )
        stderr = ""
    except Exception as exc:  # noqa: BLE001
        output_json = state.output_dir / "startup_gpu1_dynamic_context_pack.json"
        output_md = state.output_dir / "startup_gpu1_dynamic_context_pack.md"
        returncode = 1
        stdout = ""
        stderr = f"{type(exc).__name__}: {exc}"
    record_inprocess_tool(
        state,
        name="gpu1_dynamic_context_pack",
        requirement="gpu1_dynamic_context_pack",
        required=True,
        command=command,
        returncode=returncode,
        stdout_tail=stdout,
        stderr_tail=stderr,
        artifact_paths=[output_json, output_md],
    )
    state.artifacts["gpu1_dynamic_context_pack_json"] = repo_rel(state.repo_root, output_json)
    state.artifacts["gpu1_dynamic_context_pack_markdown"] = repo_rel(state.repo_root, output_md)
