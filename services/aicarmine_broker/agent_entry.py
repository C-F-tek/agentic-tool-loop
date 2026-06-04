"""Public agent entrypoint and background job lifecycle."""
from __future__ import annotations

import threading
import time
import uuid
from typing import Any

from .application.job_worker import AgentJobWorker
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
from .planner import run_agentic_planner_job
from .public_wrapper import deterministic_public_wrapper, fail_selector, summary_from_result
from .tool_contract import public_args, public_tool, sanitize_tool_args, text_from_payload
from .tool_dispatch import dispatch_tool
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
    )


def agent_job_worker(job_id: str) -> None:
    return build_job_worker().run(job_id)


def start_agent_job(payload: dict[str, Any], public_tool_name: str, original_args: dict[str, Any], task: str) -> dict[str, Any]:
    init_agent_job_db()
    requested_job_id = str(original_args.get('job_id') or payload.get('job_id') or '').strip()
    job_id = make_session_id(requested_job_id) if requested_job_id else make_session_id('job-' + uuid.uuid4().hex[:8])
    root = agent_job_root(job_id)
    return_mode = str(original_args.get('return_mode') or payload.get('return_mode') or 'wait').strip().lower()
    state = {'job_id': job_id, 'status': 'queued', 'goal': task, 'public_tool_name': public_tool_name, 'created_at': time.time(), 'updated_at': time.time(), 'workspace': str(root), 'request_payload': payload, 'original_args': original_args, 'max_steps': int(original_args.get('max_steps') or payload.get('max_steps') or AGENT_DEFAULT_MAX_STEPS), 'approval_mode': str(original_args.get('approval_mode') or payload.get('approval_mode') or AGENT_APPROVAL_MODE), 'return_mode': return_mode, 'agentic_planner_enabled': AGENTIC_PLANNER_ENABLED, 'planner_url': PLANNER_URL, 'planner_model': PLANNER_MODEL, 'selector_url': OLLAMA_TASK_URL, 'selector_model': OLLAMA_TASK_MODEL}
    write_agent_job_state(state)
    append_agent_event(job_id, 'job_queued', 'Agent job queued.', {'goal': task}, step=0)
    with AGENT_JOB_LOCK:
        existing = AGENT_JOB_BACKGROUND_THREADS.get(job_id)
        if not existing or not existing.is_alive():
            thread = threading.Thread(target=agent_job_worker, args=(job_id,), daemon=True, name=f'aicarmine-agent-job-{job_id}')
            AGENT_JOB_BACKGROUND_THREADS[job_id] = thread
            thread.start()
    started = {'ok': True, 'service': 'vulkan_agent', 'mode': 'agent_job_started', 'verdict': 'AGENT_JOB_STARTED', 'tool_name': public_tool_name, 'tool_result_for': public_tool_name, 'operation_id': public_tool_name, 'called_by_30b': public_tool_name, 'job_id': job_id, 'status': 'queued', 'workspace': str(root), 'job_url': job_url(job_id), 'message_for_30b': f'Agent job started internally: {job_id}. The tool call will wait for a terminal state before returning to OpenWebUI.', 'summary_for_30b': f'Agent job started internally: {job_id}. Waiting for terminal state.', 'content': f'Agent job started internally: {job_id}\nDashboard: {job_url(job_id)}'}
    wait_seconds = int(original_args.get('wait_seconds') or payload.get('wait_seconds') or AGENT_RETURN_WAIT_SECONDS)
    if return_mode in {'background', 'async', 'fire_and_forget'}:
        return started
    waited = wait_for_agent_terminal(job_id, wait_seconds)
    waited['started_job'] = started
    waited['job_id'] = job_id
    waited['job_url'] = job_url(job_id)
    waited['workspace'] = str(root)
    waited['tool_name'] = public_tool_name
    waited['tool_result_for'] = public_tool_name
    waited['operation_id'] = public_tool_name
    waited['called_by_30b'] = public_tool_name
    return waited


def agent(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        payload = {'payload': payload}
    public_tool_name = public_tool(payload)
    original_args = public_args(payload)
    session_id = make_session_id(str(payload.get('session_id') or original_args.get('session_id') or ''))
    root = session_root(session_id)
    task = text_from_payload(payload, original_args, public_tool_name)
    allow_command = parse_bool(payload.get('allow_command', original_args.get('allow_command', True)), True)
    user_consent = str(payload.get('user_consent') or original_args.get('user_consent') or '')
    try:
        timeout_seconds = int(payload.get('timeout_seconds') or original_args.get('timeout_seconds') or 120)
    except Exception:
        timeout_seconds = 120
    timeout_seconds = max(15, min(timeout_seconds, 240))
    raw_job_action = str(original_args.get('job_action') or payload.get('job_action') or original_args.get('action') or payload.get('action') or '').strip().lower()
    job_id = str(original_args.get('job_id') or payload.get('job_id') or '').strip()
    start_actions = {'', 'start', 'job_start', 'async', 'background', 'run', 'execute'}
    status_actions = {'status', 'job_status'}
    result_actions = {'result', 'job_result', 'final'}
    cancel_actions = {'cancel', 'job_cancel'}
    if public_tool_name == 'vulkan_helper' and (not job_id):
        job_action = 'start'
    elif raw_job_action in start_actions:
        job_action = 'start'
    elif raw_job_action in status_actions:
        job_action = 'status'
    elif raw_job_action in result_actions:
        job_action = 'result'
    elif raw_job_action in cancel_actions:
        job_action = 'cancel'
    elif public_tool_name == 'vulkan_helper':
        job_action = 'start'
    else:
        job_action = raw_job_action
    if job_action == 'start':
        return start_agent_job(payload, public_tool_name, original_args, task)
    if job_action == 'status':
        return compact_agent_status(job_id, include_events=True)
    if job_action == 'result':
        return compact_agent_terminal_response(job_id)
    if job_action == 'cancel':
        state = load_agent_job_state(job_id)
        if not state:
            return compact_agent_status(job_id, include_events=True)
        state['status'] = 'cancel_requested'
        write_agent_job_state(state)
        append_agent_event(job_id, 'cancel_requested', 'Cancel requested by user.', {}, step=None)
        return compact_agent_status(job_id, include_events=True)
    internal_tool, raw_internal_args, selector_response = select_internal_tool(public_tool_name=public_tool_name, task=task, original_args=original_args, timeout_seconds=timeout_seconds)
    if not internal_tool:
        fallback_tool, fallback_args = selector_fallback_tool(public_tool_name, task, original_args, selector_response if isinstance(selector_response, dict) else {})
        if fallback_tool:
            internal_tool = fallback_tool
            raw_internal_args = fallback_args
            selector_response = dict(selector_response or {}) if isinstance(selector_response, dict) else {}
            selector_response['aicarmine_selector_fallback'] = {'forced_internal_tool': fallback_tool, 'reason': '11435/Vulkan was called but did not emit a usable native tool_call.'}
        else:
            envelope = fail_selector(public_tool_name, task, original_args, root, selector_response if isinstance(selector_response, dict) else {})
            write_json(root / 'broker-session.json', envelope)
            return envelope
    internal_args = sanitize_tool_args(internal_tool, raw_internal_args, original_args, public_tool_name)
    if needs_composite_review(public_tool_name, task, original_args, internal_tool, internal_args):
        selector_response = dict(selector_response or {})
        selector_response['aicarmine_selector_guard'] = {'reason': 'generic_repo_analysis_requires_composite_evidence', 'selected_tool_from_vulkan': internal_tool, 'selected_args_from_vulkan': internal_args, 'forced_internal_tool': 'vulkan_helper'}
        internal_tool = 'vulkan_helper'
        internal_args = {'public_tool_name': public_tool_name, 'public_tool_x': public_tool_name, 'task': task, 'reason': 'generic repo analysis must gather composite repo evidence, not a single broad search', 'arguments': original_args, 'original_30b_arguments': original_args, 'force_composite_review': True}
    dispatcher_result = dispatch_tool(internal_tool, internal_args, root, allow_command, user_consent)
    dispatcher_result = dict(dispatcher_result or {})
    dispatcher_result.setdefault('called_by_vulkan', internal_tool)
    dispatcher_artifact = root / 'tool-results' / f'{now()}-{internal_tool}-dispatcher-v6.json'
    write_json(dispatcher_artifact, dispatcher_result)
    dispatcher_result.setdefault('artifact', str(dispatcher_artifact))
    envelope = deterministic_public_wrapper(public_tool_name=public_tool_name, original_args=original_args, internal_tool=internal_tool, internal_args=internal_args, dispatcher_result=dispatcher_result, selector_response=selector_response if isinstance(selector_response, dict) else {}, root=root)
    write_json(root / 'broker-session.json', envelope)
    return envelope
