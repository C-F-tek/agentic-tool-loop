"""Public agent entrypoint and background job lifecycle."""
from __future__ import annotations

from typing import Any

from .application.job.action_router import AgentJobActionRouter
from .application.job.lifecycle import AgentJobLifecycle
from .application.job.worker import AgentJobWorker
from .application.job.selector_runner import SelectorRunner
from .config import (
    AGENT_APPROVAL_MODE,
    AGENT_DEFAULT_MAX_STEPS,
    AGENT_JOB_BACKGROUND_THREADS,
    AGENT_JOB_LOCK,
    AGENT_RETURN_WAIT_SECONDS,
    AGENTIC_FALLBACK_ONESHOT,
    AGENTIC_PLANNER_ENABLED,
    OLLAMA_TASK_MODEL,
    OLLAMA_TASK_URL,
    PLANNER_MODEL,
    PLANNER_URL,
    parse_bool,
)
from .job_store import (
    agent_job_root,
    append_agent_event,
    compact_agent_status,
    compact_agent_terminal_response,
    init_agent_job_db,
    job_url,
    load_agent_job_state,
    make_session_id,
    now,
    session_root,
    wait_for_agent_terminal,
    write_agent_job_state,
    write_json,
)
from .planner import finalize_agentic_job, run_agentic_planner_job
from .application.public_payload.public_wrapper import deterministic_public_wrapper, fail_selector, summary_from_result
from .tool_contract import public_args, public_tool, sanitize_tool_args, text_from_payload
from .application.tool_surface.tool_dispatch import dispatch_tool
from .tool_selection import needs_composite_review, select_internal_tool, selector_fallback_tool


def build_job_worker() -> AgentJobWorker:
    return AgentJobWorker(
        load_state=load_agent_job_state,
        write_state=write_agent_job_state,
        append_event=append_agent_event,
        agent_job_root=agent_job_root,
        write_json=write_json,
        planner_runner=run_agentic_planner_job,
        agent_runner=agent,
        summary_from_result=summary_from_result,
        agentic_planner_enabled=AGENTIC_PLANNER_ENABLED,
        agentic_fallback_oneshot=AGENTIC_FALLBACK_ONESHOT,
        terminal_finalizer=finalize_agentic_job,
    )


def agent_job_worker(job_id: str) -> None:
    return build_job_worker().run(job_id)


def build_job_lifecycle() -> AgentJobLifecycle:
    return AgentJobLifecycle(
        init_agent_job_db=init_agent_job_db,
        make_session_id=make_session_id,
        agent_job_root=agent_job_root,
        write_state=write_agent_job_state,
        append_event=append_agent_event,
        job_url=job_url,
        wait_for_terminal=wait_for_agent_terminal,
        worker=agent_job_worker,
        background_threads=AGENT_JOB_BACKGROUND_THREADS,
        lock=AGENT_JOB_LOCK,
        agent_default_max_steps=AGENT_DEFAULT_MAX_STEPS,
        approval_mode=AGENT_APPROVAL_MODE,
        return_wait_seconds=AGENT_RETURN_WAIT_SECONDS,
        agentic_planner_enabled=AGENTIC_PLANNER_ENABLED,
        planner_url=PLANNER_URL,
        planner_model=PLANNER_MODEL,
        selector_url=OLLAMA_TASK_URL,
        selector_model=OLLAMA_TASK_MODEL,
    )


def start_agent_job(
    payload: dict[str, Any],
    public_tool_name: str,
    original_args: dict[str, Any],
    task: str,
) -> dict[str, Any]:
    return build_job_lifecycle().start(payload, public_tool_name, original_args, task)


def build_selector_runner() -> SelectorRunner:
    return SelectorRunner(
        select_internal_tool=select_internal_tool,
        selector_fallback_tool=selector_fallback_tool,
        fail_selector=fail_selector,
        sanitize_tool_args=sanitize_tool_args,
        needs_composite_review=needs_composite_review,
        dispatch_tool=dispatch_tool,
        public_wrapper=deterministic_public_wrapper,
        write_json=write_json,
        now=now,
    )


def build_job_action_router() -> AgentJobActionRouter:
    return AgentJobActionRouter(
        public_tool=public_tool,
        public_args=public_args,
        make_session_id=make_session_id,
        session_root=session_root,
        text_from_payload=text_from_payload,
        parse_bool=parse_bool,
        start_agent_job=start_agent_job,
        compact_agent_status=compact_agent_status,
        compact_agent_terminal_response=compact_agent_terminal_response,
        load_state=load_agent_job_state,
        write_state=write_agent_job_state,
        append_event=append_agent_event,
        selector_runner=build_selector_runner(),
    )


def agent(payload: dict[str, Any]) -> dict[str, Any]:
    return build_job_action_router().handle(payload)
