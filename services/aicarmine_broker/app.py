"""
aicarmine_broker.app
====================
FastAPI application factory and HTTP route registration.

The main module imports only ``app`` from here; dispatcher, planner,
repository tools and job persistence stay in their dedicated modules.
"""
from __future__ import annotations

import sys
from typing import Any

from fastapi import Body, FastAPI
from fastapi.openapi.utils import get_openapi
from fastapi.responses import HTMLResponse, JSONResponse

from .config import (
    AGENT_JOB_DB,
    AGENT_JOB_ROOT,
    AGENTIC_PLANNER_NUM_CTX,
    AGENTIC_PLANNER_NUM_CTX_CAP,
    AGENTIC_PLANNER_NUM_CTX_REQUESTED,
    AGENTIC_PLANNER_PROMPT_CHAR_BUDGET,
    AGENTIC_PLANNER_PROMPT_COMPACT_RATIO,
    AGENTIC_PLANNER_PROMPT_PREVIEW_CHARS,
    AGENTIC_PLANNER_HISTORY_PROMPT_TAIL,
    AGENTIC_PLANNER_ENABLED,
    AGENTIC_PLANNER_NATIVE_MAX_PARALLEL_READONLY,
    AGENTIC_PLANNER_NATIVE_TOOLS,
    AGENTIC_PLANNER_PRESENCE_PENALTY,
    AGENTIC_PLANNER_REQUIRE_NATIVE_TOOLS,
    AGENTIC_PLANNER_TEMPERATURE,
    AGENTIC_PLANNER_TOP_K,
    AGENTIC_PLANNER_TOP_P,
    APP_DESCRIPTION,
    APP_TITLE,
    APP_VERSION,
    HEALTH_PATH,
    JOBS_INDEX_PATH,
    JOBS_JSON_PATH,
    LAB_REPO,
    OLLAMA_TASK_MODEL,
    OLLAMA_TASK_URL,
    OPENAPI_CONTRACT,
    OLLAMA_KEEP_ALIVE,
    PLANNER_MODEL,
    PLANNER_URL,
    SERVICE_NAME,
    V6_MARKER,
    VULKAN_AGENT_PATH,
    WORKSPACE,
    ollama_options,
)
from .agent_entry import agent
from .application.shared.job_html import (
    agent_job_events_view_html,
    agent_job_events_section_html,
    agent_job_final_json_view_html,
    agent_job_final_json_section_html,
    agent_job_final_markdown_view_html,
    agent_job_html,
    agent_job_ia_view_html,
    agent_job_ia_view_payload,
    agent_job_ia_view_section_html,
    agent_jobs_index_html,
    agent_job_planner_stream_view_html,
    agent_job_status_json_view_html,
    agent_job_status_json_section_html,
)
from .job_planner_lab import agent_job_planner_lab_html, planner_lab_index_html
from .job_store import agent_job_root, append_agent_event, compact_agent_terminal_response, list_agent_jobs
from .application.public_payload.lab import (
    build_planner_lab_apply_tool_call,
    build_planner_lab_compose_request,
    build_planner_payload_lab,
    parse_planner_lab_compose_response,
)
from .planner_core.json_io import post_json
from .application.tool_surface.tool_dispatch import dispatch_tool
from .tool_registry import capability_map


def _parse_planner_lab_wait_seconds(payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    raw = payload.get("wait_seconds") if isinstance(payload, dict) else None
    if raw in (None, ""):
        return 1, {}
    if isinstance(raw, bool):
        return 1, {
            "ok": False,
            "error": "invalid_wait_seconds",
            "received_type": type(raw).__name__,
            "received_preview": str(raw)[:120],
            "expected": "integer between 1 and 30",
            "min": 1,
            "max": 30,
        }
    if isinstance(raw, int):
        value = raw
    elif isinstance(raw, str) and raw.strip().lstrip("+-").isdigit():
        value = int(raw.strip())
    else:
        return 1, {
            "ok": False,
            "error": "invalid_wait_seconds",
            "received_type": type(raw).__name__,
            "received_preview": str(raw)[:120],
            "expected": "integer between 1 and 30",
            "min": 1,
            "max": 30,
        }
    return max(1, min(value, 30)), {}


def jobs_endpoint_paths() -> list[str]:
    return [
        JOBS_INDEX_PATH,
        JOBS_JSON_PATH,
        f"{JOBS_INDEX_PATH}/{{job_id}}",
        f"{JOBS_INDEX_PATH}/{{job_id}}/json",
        f"{JOBS_INDEX_PATH}/{{job_id}}/json/section/{{section}}",
        f"{JOBS_INDEX_PATH}/{{job_id}}/events",
        f"{JOBS_INDEX_PATH}/{{job_id}}/events/section/{{section}}",
        f"{JOBS_INDEX_PATH}/{{job_id}}/final.json",
        f"{JOBS_INDEX_PATH}/{{job_id}}/final.json/section/{{section}}",
        f"{JOBS_INDEX_PATH}/{{job_id}}/final.md",
        f"{JOBS_INDEX_PATH}/{{job_id}}/planner-stream",
        f"{JOBS_INDEX_PATH}/{{job_id}}/ia-view",
        f"{JOBS_INDEX_PATH}/{{job_id}}/ia-view.json",
        f"{JOBS_INDEX_PATH}/{{job_id}}/ia-view/section/{{section}}",
        "/planner-lab",
        "/planner-lab/start",
        f"{JOBS_INDEX_PATH}/{{job_id}}/planner-lab",
        f"{JOBS_INDEX_PATH}/{{job_id}}/planner-lab.json",
        f"{JOBS_INDEX_PATH}/{{job_id}}/planner-lab/apply",
        f"{JOBS_INDEX_PATH}/{{job_id}}/planner-lab/compose",
    ]


def create_app() -> FastAPI:
    app = FastAPI(
        title=APP_TITLE,
        version=APP_VERSION,
        description=APP_DESCRIPTION,
    )

    @app.get(JOBS_INDEX_PATH, include_in_schema=False)
    def jobs_index(limit: int = 50) -> HTMLResponse:
        return HTMLResponse(
            agent_jobs_index_html(
                limit=limit,
                title=APP_TITLE,
                refresh_seconds=0,
            )
        )

    @app.get(JOBS_JSON_PATH, include_in_schema=False)
    def jobs_json(limit: int = 50) -> dict[str, Any]:
        return {
            "ok": True,
            "jobs": list_agent_jobs(limit=max(1, min(int(limit or 50), 200))),
        }

    @app.get("/planner-lab", include_in_schema=False)
    def planner_lab_index(limit: int = 20) -> HTMLResponse:
        return HTMLResponse(planner_lab_index_html(limit=limit))

    @app.post("/planner-lab/start", include_in_schema=False)
    def planner_lab_start(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
        task = str(
            payload.get("task")
            or payload.get("request")
            or payload.get("prompt")
            or ""
        ).strip()
        if not task:
            return {"ok": False, "error": "missing_task"}
        wait_seconds, wait_error = _parse_planner_lab_wait_seconds(payload)
        if wait_error:
            return wait_error
        arguments = {
            "task": task,
            "request": task,
            "return_mode": str(payload.get("return_mode") or "background"),
            "wait_seconds": wait_seconds,
        }
        for key in ("max_steps", "approval_mode", "user_consent"):
            if payload.get(key) not in (None, "", [], {}):
                arguments[key] = payload.get(key)
        return agent(
            {
                "tool_name": "vulkan_helper",
                "task": task,
                "arguments": arguments,
            }
        )

    @app.get(f"{JOBS_INDEX_PATH}/{{job_id}}", include_in_schema=False)
    def job_dashboard(job_id: str) -> HTMLResponse:
        return HTMLResponse(agent_job_html(job_id))

    @app.get(f"{JOBS_INDEX_PATH}/{{job_id}}/json", include_in_schema=False)
    def job_dashboard_json(job_id: str) -> HTMLResponse:
        return HTMLResponse(agent_job_status_json_view_html(job_id))

    @app.get(f"{JOBS_INDEX_PATH}/{{job_id}}/json/section/{{section}}", include_in_schema=False)
    def job_dashboard_json_section(job_id: str, section: str, key: str = "", index: int = 0) -> HTMLResponse:
        return HTMLResponse(agent_job_status_json_section_html(job_id, section, key=key, index=index))

    @app.get(f"{JOBS_INDEX_PATH}/{{job_id}}/ia-view", include_in_schema=False)
    def job_dashboard_ia_view(job_id: str) -> HTMLResponse:
        return HTMLResponse(agent_job_ia_view_html(job_id))

    @app.get(f"{JOBS_INDEX_PATH}/{{job_id}}/ia-view.json", include_in_schema=False)
    def job_dashboard_ia_view_json(job_id: str, heavy: bool = False) -> JSONResponse:
        return JSONResponse(agent_job_ia_view_payload(job_id, include_heavy=heavy))

    @app.get(f"{JOBS_INDEX_PATH}/{{job_id}}/ia-view/section/{{section}}", include_in_schema=False)
    def job_dashboard_ia_view_section(job_id: str, section: str, step: int = 0) -> HTMLResponse:
        return HTMLResponse(agent_job_ia_view_section_html(job_id, section, step=step))

    @app.get(f"{JOBS_INDEX_PATH}/{{job_id}}/planner-lab", include_in_schema=False)
    def job_planner_lab(job_id: str) -> HTMLResponse:
        return HTMLResponse(agent_job_planner_lab_html(job_id))

    @app.get(f"{JOBS_INDEX_PATH}/{{job_id}}/planner-lab.json", include_in_schema=False)
    def job_planner_lab_json(
        job_id: str,
        summary_chars: int = 4000,
        step_limit: int = 80,
        code_product_limit: int = 40,
    ) -> JSONResponse:
        ia_payload = agent_job_ia_view_payload(job_id, include_heavy=True)
        if not ia_payload.get("ok"):
            return JSONResponse(ia_payload)
        terminal = compact_agent_terminal_response(job_id, audience="openwebui")
        return JSONResponse(
            build_planner_payload_lab(
                job_id=job_id,
                ia_view_payload=ia_payload,
                terminal_response=terminal,
                summary_text_chars=summary_chars,
                step_summary_limit=step_limit,
                code_product_limit=code_product_limit,
            )
        )

    @app.post(f"{JOBS_INDEX_PATH}/{{job_id}}/planner-lab/apply", include_in_schema=False)
    def job_planner_lab_apply(job_id: str, payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
        ia_payload = agent_job_ia_view_payload(job_id, include_heavy=True)
        if not ia_payload.get("ok"):
            return ia_payload
        terminal = compact_agent_terminal_response(job_id, audience="openwebui")
        lab_payload = build_planner_payload_lab(
            job_id=job_id,
            ia_view_payload=ia_payload,
            terminal_response=terminal,
        )
        apply_request = build_planner_lab_apply_tool_call(
            lab_payload,
            candidate_id=str(payload.get("candidate_id") or ""),
            confirm_apply=payload.get("confirm_apply") is True,
        )
        if not apply_request.get("ok"):
            return apply_request
        result = dispatch_tool(
            "repo_apply_patch",
            apply_request["arguments"],
            agent_job_root(job_id),
            allow_command=True,
            user_consent=str(payload.get("user_consent") or ""),
        )
        append_agent_event(
            job_id,
            "planner_lab_apply_patch",
            "Planner lab applied an exact old_text/new_text patch candidate.",
            {
                "candidate_id": apply_request.get("candidate_id"),
                "target_file": (apply_request.get("candidate") or {}).get("target_file"),
                "result_ok": result.get("ok") if isinstance(result, dict) else None,
            },
            step=None,
        )
        return {
            "ok": bool(isinstance(result, dict) and result.get("ok")),
            "tool": "planner_lab_apply",
            "candidate_id": apply_request.get("candidate_id"),
            "apply_tool": "repo_apply_patch",
            "result": result,
        }

    @app.post(f"{JOBS_INDEX_PATH}/{{job_id}}/planner-lab/compose", include_in_schema=False)
    def job_planner_lab_compose(job_id: str, payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
        ia_payload = agent_job_ia_view_payload(job_id, include_heavy=True)
        if not ia_payload.get("ok"):
            return ia_payload
        terminal = compact_agent_terminal_response(job_id, audience="openwebui")
        lab_payload = build_planner_payload_lab(
            job_id=job_id,
            ia_view_payload=ia_payload,
            terminal_response=terminal,
            summary_text_chars=int(payload.get("summary_chars") or 4000),
            step_summary_limit=int(payload.get("step_limit") or 80),
            code_product_limit=int(payload.get("code_product_limit") or 40),
        )
        conversation = payload.get("conversation")
        compose_payload = build_planner_lab_compose_request(
            lab_payload,
            model=str(payload.get("model") or PLANNER_MODEL),
            user_instruction=str(payload.get("instruction") or ""),
            conversation=conversation if isinstance(conversation, list) else [],
            think=payload.get("think") is True,
            max_payload_chars=int(payload.get("max_payload_chars") or 30000),
        )
        compose_payload["keep_alive"] = OLLAMA_KEEP_ALIVE
        compose_payload["options"] = ollama_options(num_predict=2000)
        response = post_json(
            PLANNER_URL,
            compose_payload,
            timeout=max(15, min(int(payload.get("timeout_seconds") or 60), 180)),
        )
        parsed = parse_planner_lab_compose_response(response if isinstance(response, dict) else {})
        return {
            "ok": bool(parsed.get("ok")),
            "tool": "planner_lab_compose",
            "diagnostic_only": True,
            "planner_url": PLANNER_URL,
            "model": compose_payload.get("model"),
            "think": compose_payload.get("think"),
            "compose_request_shape": {
                "format": "json_schema",
                "messages": len(compose_payload.get("messages") or []),
                "tools": 0,
            },
            "result": parsed,
        }

    @app.get(f"{JOBS_INDEX_PATH}/{{job_id}}/events", include_in_schema=False)
    def job_dashboard_events(job_id: str) -> HTMLResponse:
        return HTMLResponse(agent_job_events_view_html(job_id))

    @app.get(f"{JOBS_INDEX_PATH}/{{job_id}}/events/section/{{section}}", include_in_schema=False)
    def job_dashboard_events_section(job_id: str, section: str, step: str = "", index: int = 0) -> HTMLResponse:
        return HTMLResponse(agent_job_events_section_html(job_id, section, step=step, index=index))

    @app.get(f"{JOBS_INDEX_PATH}/{{job_id}}/final.json", include_in_schema=False)
    def job_dashboard_final_json(job_id: str) -> HTMLResponse:
        return HTMLResponse(agent_job_final_json_view_html(job_id))

    @app.get(f"{JOBS_INDEX_PATH}/{{job_id}}/final.json/section/{{section}}", include_in_schema=False)
    def job_dashboard_final_json_section(job_id: str, section: str, key: str = "", index: int = 0) -> HTMLResponse:
        return HTMLResponse(agent_job_final_json_section_html(job_id, section, key=key, index=index))

    @app.get(f"{JOBS_INDEX_PATH}/{{job_id}}/final.md", include_in_schema=False)
    def job_dashboard_final_markdown(job_id: str) -> HTMLResponse:
        return HTMLResponse(agent_job_final_markdown_view_html(job_id))

    @app.get(HEALTH_PATH, include_in_schema=False)
    def health() -> dict[str, Any]:
        registry = capability_map()
        return {
            "ok": True,
            "service": SERVICE_NAME,
            "mode": V6_MARKER,
            "registry": registry,
            "registry_hash": registry["registry_hash"],
            "registry_version": registry["registry_version"],
            "runtime_contract": registry["runtime_contract"],
            "public_surface": registry["surfaces"]["openwebui_public"],
            "internal_planner_surface": registry["surfaces"]["planner_internal"],
            "module_loaded": __name__,
            "python_executable": sys.executable,
            "python_prefix": sys.prefix,
            "python_base_prefix": sys.base_prefix,
            "ollama_task_url": OLLAMA_TASK_URL,
            "ollama_task_model": OLLAMA_TASK_MODEL,
            "planner_url": PLANNER_URL,
            "planner_model": PLANNER_MODEL,
            "agentic_planner_enabled": AGENTIC_PLANNER_ENABLED,
            "agentic_planner_native_tools": {
                "enabled": AGENTIC_PLANNER_NATIVE_TOOLS,
                "required": AGENTIC_PLANNER_REQUIRE_NATIVE_TOOLS,
                "max_parallel_readonly": AGENTIC_PLANNER_NATIVE_MAX_PARALLEL_READONLY,
            },
            "agentic_planner_num_ctx": AGENTIC_PLANNER_NUM_CTX,
            "agentic_planner_num_ctx_requested": AGENTIC_PLANNER_NUM_CTX_REQUESTED,
            "agentic_planner_num_ctx_cap": AGENTIC_PLANNER_NUM_CTX_CAP,
            "agentic_planner_num_ctx_effective": AGENTIC_PLANNER_NUM_CTX,
            "agentic_planner_sampling": {
                "temperature": AGENTIC_PLANNER_TEMPERATURE,
                "top_k": AGENTIC_PLANNER_TOP_K,
                "top_p": AGENTIC_PLANNER_TOP_P,
                "presence_penalty": AGENTIC_PLANNER_PRESENCE_PENALTY,
            },
            "agentic_planner_prompt_char_budget": AGENTIC_PLANNER_PROMPT_CHAR_BUDGET,
            "agentic_planner_prompt_compact_ratio": AGENTIC_PLANNER_PROMPT_COMPACT_RATIO,
            "agentic_planner_prompt_compact_threshold_chars": (
                max(
                    1000,
                    int(
                        AGENTIC_PLANNER_PROMPT_CHAR_BUDGET
                        * max(0.1, min(float(AGENTIC_PLANNER_PROMPT_COMPACT_RATIO or 0.5), 0.95))
                    ),
                )
                if AGENTIC_PLANNER_PROMPT_CHAR_BUDGET > 0
                else 0
            ),
            "agentic_planner_history_prompt_tail": AGENTIC_PLANNER_HISTORY_PROMPT_TAIL,
            "agentic_planner_prompt_preview_chars": AGENTIC_PLANNER_PROMPT_PREVIEW_CHARS,
            "agent_job_root": str(AGENT_JOB_ROOT),
            "agent_job_db": str(AGENT_JOB_DB),
            "job_endpoints": jobs_endpoint_paths(),
            "lab_repo": str(LAB_REPO),
            "workspace": str(WORKSPACE),
        }

    @app.get(f"{JOBS_INDEX_PATH}/{{job_id}}/planner-stream", include_in_schema=False)
    def job_planner_stream_index(job_id: str) -> HTMLResponse:
        return HTMLResponse(agent_job_planner_stream_view_html(job_id))

    @app.post(
        VULKAN_AGENT_PATH,
        operation_id="ask_vulkan_agent",
        summary="Internal Vulkan public-X provider",
        description=APP_DESCRIPTION,
    )
    def ask_vulkan_agent(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
        return agent(payload)

    def custom_openapi() -> dict[str, Any]:
        registry = capability_map()
        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )
        schema["paths"] = {
            path: methods
            for path, methods in schema.get("paths", {}).items()
            if path == VULKAN_AGENT_PATH
        }
        schema["x-aicarmine-internal"] = True
        schema["x-aicarmine-mode"] = V6_MARKER
        schema["x-aicarmine-contract"] = OPENAPI_CONTRACT
        schema["x-aicarmine-runtime-contract"] = registry["runtime_contract"]
        schema["x-aicarmine-registry-hash"] = registry["registry_hash"]
        schema["x-aicarmine-registry-version"] = registry["registry_version"]
        schema["x-aicarmine-public-surface"] = registry["surfaces"]["openwebui_public"]
        schema["x-aicarmine-internal-planner-surface"] = registry["surfaces"]["planner_internal"]
        return schema

    app.openapi_schema = None
    app.openapi = custom_openapi  # type: ignore[method-assign]
    return app


app = create_app()
