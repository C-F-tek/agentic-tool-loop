"""Operational-memory write step for heap startup reload."""

from __future__ import annotations

from ia_carmine.context.heap_context_memory_reload.common import (
    repo_rel,
    run_tool,
    write_markdown,
)
from ia_carmine.context.heap_context_memory_reload.manifest import requirement_status
from ia_carmine.context.heap_context_memory_reload.runner_state import ReloadRun
from ia_carmine.context.heap_context_memory_reload.task_docs import (
    build_operational_memory_write_content,
    build_task_markdown,
)


def run_operational_memory_write(state: ReloadRun) -> None:
    _required, _optional, blocking, degraded, optional_failed = requirement_status(state.commands)
    startup_reload_degraded = bool(degraded or optional_failed)
    content = build_operational_memory_write_content(
        stamp=state.stamp,
        request=state.request_text,
        startup_reload_degraded=startup_reload_degraded,
        degraded_requirements=degraded,
        blocking_requirements=blocking,
        artifacts=state.artifacts,
        commands=state.commands,
        context_delta=state.context_delta,
    )
    output_json = state.output_dir / "startup_operational_memory_write.json"
    output_md = state.output_dir / "startup_operational_memory_write.md"
    content_file = state.output_dir / "startup_operational_memory_write_input.md"
    write_markdown(content_file, content)
    command_result = run_tool(
        [
            state.project_python,
            "-m",
            "ia_carmine",
            "agent_runtime_sqlite_memory",
            "--repo-root",
            ".",
            "--action",
            "remember",
            "--scope",
            "operational",
            "--request-id",
            f"heap_startup_reload_{state.stamp}",
            "--summary",
            "startup context/memory reload manifest",
            "--content-file",
            str(content_file),
            "--role",
            "heap_startup_reload",
            "--tag",
            "heap_startup_context",
            "--tag",
            state.stamp,
            "--output",
            str(output_json),
            "--markdown-output",
            str(output_md),
        ],
        state.repo_root,
        name="operational_memory_write_reload",
        requirement="operational_memory_write",
        required=True,
        artifact_paths=[output_json, output_md],
    )
    if not command_result.get("passed"):
        command_result["effective_passed"] = False
        command_result["degraded"] = False
        command_result["hard_failed"] = True
    state.commands.append(command_result)
    state.artifacts["operational_memory_write_input"] = repo_rel(state.repo_root, content_file)
    state.artifacts["operational_memory_write_json"] = repo_rel(state.repo_root, output_json)
    state.artifacts["operational_memory_write_markdown"] = repo_rel(state.repo_root, output_md)


def build_final_task_markdown(state: ReloadRun) -> str:
    _required, _optional, blocking, degraded, optional_failed = requirement_status(state.commands)
    return build_task_markdown(
        repo_root=state.repo_root,
        request=state.request_text,
        stamp=state.stamp,
        context_files=state.context_files,
        artifacts=state.artifacts,
        commands=state.commands,
        warnings=state.warnings,
        context_delta=state.context_delta,
        startup_reload_degraded=bool(degraded or optional_failed),
        degraded_requirements=degraded,
        blocking_requirements=blocking,
    )
