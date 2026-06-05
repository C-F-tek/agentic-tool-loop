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
    PLANNER_MODEL,
    PLANNER_URL,
    SERVICE_NAME,
    V6_MARKER,
    VULKAN_AGENT_PATH,
    WORKSPACE,
)
from .agent_entry import agent
from .job_html import (
    agent_job_events_view_html,
    agent_job_final_json_view_html,
    agent_job_final_markdown_view_html,
    agent_job_html,
    agent_job_ia_view_html,
    agent_job_ia_view_payload,
    agent_job_ia_view_section_html,
    agent_jobs_index_html,
    agent_job_planner_stream_view_html,
    agent_job_status_json_view_html,
)
from .job_planner_lab import agent_job_planner_lab_html, planner_lab_index_html
from .job_store import agent_job_root, append_agent_event, compact_agent_terminal_response, list_agent_jobs
from .application.public_payload.planner_lab import build_planner_lab_apply_tool_call, build_planner_payload_lab
from .tool_dispatch import dispatch_tool
from .tool_registry import capability_map


def jobs_endpoint_paths() -> list[str]:
    return [
        JOBS_INDEX_PATH,
        JOBS_JSON_PATH,
        f"{JOBS_INDEX_PATH}/{{job_id}}",
        f"{JOBS_INDEX_PATH}/{{job_id}}/json",
        f"{JOBS_INDEX_PATH}/{{job_id}}/events",
        f"{JOBS_INDEX_PATH}/{{job_id}}/final.json",
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
        try:
            wait_seconds = max(1, min(int(payload.get("wait_seconds") or 1), 30))
        except Exception:
            return {
                "ok": False,
                "error": "invalid_wait_seconds",
                "expected": "integer between 1 and 30",
            }
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

    @app.get(f"{JOBS_INDEX_PATH}/{{job_id}}/ia-view", include_in_schema=False)
    def job_dashboard_ia_view(job_id: str) -> HTMLResponse:
        return HTMLResponse(agent_job_ia_view_html(job_id))

    @app.get(f"{JOBS_INDEX_PATH}/{{job_id}}/ia-view.json", include_in_schema=False)
    def job_dashboard_ia_view_json(job_id: str) -> JSONResponse:
        return JSONResponse(agent_job_ia_view_payload(job_id))

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

    @app.get(f"{JOBS_INDEX_PATH}/{{job_id}}/events", include_in_schema=False)
    def job_dashboard_events(job_id: str) -> HTMLResponse:
        return HTMLResponse(agent_job_events_view_html(job_id))

    @app.get(f"{JOBS_INDEX_PATH}/{{job_id}}/final.json", include_in_schema=False)
    def job_dashboard_final_json(job_id: str) -> HTMLResponse:
        return HTMLResponse(agent_job_final_json_view_html(job_id))

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
            "agentic_planner_num_ctx": AGENTIC_PLANNER_NUM_CTX,
            "agentic_planner_num_ctx_requested": AGENTIC_PLANNER_NUM_CTX_REQUESTED,
            "agentic_planner_num_ctx_cap": AGENTIC_PLANNER_NUM_CTX_CAP,
            "agentic_planner_num_ctx_effective": AGENTIC_PLANNER_NUM_CTX,
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
