from __future__ import annotations

import json
import os
import re
import hashlib
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
SERVICES = ROOT / "services"
if str(SERVICES) not in sys.path:
    sys.path.insert(0, str(SERVICES))

from macro_runtine_test.lab_repo_sampling import sample_repo_files
from macro_runtine_test.payload_assertions import (
    assert_public_payload_contract,
    assert_same_openwebui_payload,
    extract_job_id,
    extract_tools_observed,
)
from macro_runtine_test.runtime_client import RuntimeUrls, get_json, get_json_or_none, get_text, post_json
from macro_runtine_test.tool_cases import build_tool_cases, missing_cases_for_tools


RUNS_DIR = Path(__file__).resolve().parent / ".runs"


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _seed() -> int:
    raw = str(os.environ.get("LOOP_PAYLOAD_SEED") or "").strip()
    if raw:
        return int(raw)
    return int(time.strftime("%Y%m%d%H%M%S"))


def _int_env(name: str, default: int) -> int:
    raw = str(os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _run_id(seed: int) -> str:
    raw = str(os.environ.get("LOOP_PAYLOAD_RUN_ID") or "").strip()
    if raw:
        return raw
    return f"{seed}-{time.time_ns()}-{uuid.uuid4().hex[:12]}"


def _safe_job_id(run_id: str, tool_name: str) -> str:
    raw = f"job-macro-{run_id}-{tool_name}"
    cleaned = re.sub(r"[^a-zA-Z0-9_.-]+", "-", raw).strip("-")
    return cleaned[:110]


def _assert_fresh_job_id(preflight: dict[str, Any], job_id: str) -> None:
    broker_health = preflight.get("broker_health") if isinstance(preflight.get("broker_health"), dict) else {}
    agent_job_root_raw = str(broker_health.get("agent_job_root") or "").strip()
    if not agent_job_root_raw:
        raise AssertionError("3572 health did not expose agent_job_root; cannot prove fresh job_id")
    agent_job_root = Path(agent_job_root_raw).resolve()
    job_root = agent_job_root / job_id
    if job_root.exists():
        raise AssertionError(f"macro job_id is not fresh; job root already exists before launch: {job_root}")


def _runtime_tools_from_health(health: dict[str, Any]) -> set[str]:
    registry = health.get("registry") if isinstance(health.get("registry"), dict) else {}
    surfaces = registry.get("surfaces") if isinstance(registry.get("surfaces"), dict) else {}
    tools = surfaces.get("planner_internal") or health.get("internal_planner_surface")
    if not isinstance(tools, list):
        raise AssertionError("3572 health does not expose planner internal tool surface")
    return {str(item) for item in tools if str(item)}


def _openapi_visible_paths(schema: dict[str, Any]) -> set[str]:
    paths = schema.get("paths")
    if not isinstance(paths, dict):
        raise AssertionError("3571 OpenAPI lacks paths object")
    return set(paths)


def _check_operator_present() -> None:
    if not _truthy(os.environ.get("AICARMINE_OPERATOR_PRESENT")):
        pytest.skip(
            "operator-only macro runtime test skipped: run "
            "macro_runtine_test/run_loop_payload_completo.ps1"
        )


def _preflight(urls: RuntimeUrls) -> dict[str, Any]:
    from aicarmine_broker.application.tool_surface.dispatcher import build_default_dispatcher
    from aicarmine_broker.config import BROKER_CONFIG
    from aicarmine_broker.tool_registry import VALID_INTERNAL_TOOLS_LIST

    # OpenWebUI may return HTML; reachability is enough for this macro test.
    get_text(urls.openwebui + "/", timeout=15)
    bridge_health = get_json(urls.bridge_3571 + "/health", timeout=15)
    broker_health = get_json(urls.broker_3572 + "/health", timeout=15)
    get_json(urls.broker_3572 + "/jobs.json", timeout=20)
    openapi = get_json(urls.bridge_3571 + "/openapi.json", timeout=20)
    visible_paths = _openapi_visible_paths(openapi)
    if visible_paths != {"/vulkan_helper"}:
        raise AssertionError(f"3571 OpenAPI must expose only /vulkan_helper, got {sorted(visible_paths)}")

    local_tools = set(VALID_INTERNAL_TOOLS_LIST)
    dispatcher_tools = set(build_default_dispatcher().tool_names())
    runtime_tools = _runtime_tools_from_health(broker_health)
    if local_tools != dispatcher_tools:
        raise AssertionError(
            "local registry and dispatcher mismatch: "
            f"registry_only={sorted(local_tools - dispatcher_tools)} "
            f"dispatcher_only={sorted(dispatcher_tools - local_tools)}"
        )
    if runtime_tools != local_tools:
        raise AssertionError(
            "runtime 3572 tool surface differs from local registry: "
            f"runtime_only={sorted(runtime_tools - local_tools)} "
            f"local_only={sorted(local_tools - runtime_tools)}"
        )
    bridge_registry_hash = bridge_health.get("registry_hash")
    broker_registry_hash = broker_health.get("registry_hash")
    if bridge_registry_hash and broker_registry_hash and bridge_registry_hash != broker_registry_hash:
        raise AssertionError(
            f"3571/3572 registry hash mismatch: {bridge_registry_hash} != {broker_registry_hash}"
        )
    if bridge_health.get("agent_url") != urls.broker_3572 + "/vulkan/agent":
        raise AssertionError(
            f"3571 agent_url is not the active 3572 broker endpoint: {bridge_health.get('agent_url')}"
        )
    if broker_health.get("agentic_planner_enabled") is not True:
        raise AssertionError("3572 agentic planner is not enabled")
    planner_url = str(broker_health.get("planner_url") or "")
    task_url = str(broker_health.get("ollama_task_url") or "")
    if ":11434" not in planner_url:
        raise AssertionError(f"planner_url must target 11434 for full agentic loop, got {planner_url}")
    if ":11435" not in task_url:
        raise AssertionError(f"ollama_task_url must target 11435 repair/task lane, got {task_url}")
    if planner_url == task_url:
        raise AssertionError("planner_url and ollama_task_url must remain distinct")
    if not BROKER_CONFIG.native_tools or not BROKER_CONFIG.require_native_tools:
        raise AssertionError(
            "native tool mode must be fully enabled for macro loop test: "
            f"native_tools={BROKER_CONFIG.native_tools} require_native_tools={BROKER_CONFIG.require_native_tools}"
        )
    if int(broker_health.get("agentic_planner_num_ctx_effective") or 0) <= 0:
        raise AssertionError("agentic planner context is not configured")
    if int(broker_health.get("agentic_planner_prompt_char_budget") or 0) <= 0:
        raise AssertionError("agentic planner prompt budget is not configured")

    lab_repo = Path(str(broker_health.get("lab_repo") or "")).resolve()
    if not lab_repo.exists() or not lab_repo.is_dir():
        raise AssertionError(f"3572 health lab_repo is not a directory: {lab_repo}")

    warnings: list[str] = []
    for env_name in ("AICARMINE_LAB_REPO", "OPEN_TERMINAL_CWD", "AICARMINE_OPEN_TERMINAL_WORKDIR"):
        value = str(os.environ.get(env_name) or "").strip()
        if not value:
            warnings.append(f"{env_name} not present in operator shell env; runtime health lab_repo used")
            continue
        try:
            env_path = Path(value).resolve()
        except Exception:
            warnings.append(f"{env_name} is not path-like: {value}")
            continue
        if env_path != lab_repo:
            raise AssertionError(f"{env_name}={env_path} does not match 3572 lab_repo={lab_repo}")

    return {
        "bridge_health": bridge_health,
        "broker_health": broker_health,
        "runtime_tools": sorted(runtime_tools),
        "lab_repo": str(lab_repo),
        "warnings": warnings,
    }


def _request_for_case(
    case: Any,
    *,
    job_id: str,
    wait_seconds: int,
    default_max_steps: int,
) -> dict[str, Any]:
    args = dict(case.args)
    max_steps = int(case.max_steps or default_max_steps)
    macro_context = {
        "schema": "macro_runtime_loop_payload_case.v1",
        "purpose": "operator_only_full_agentic_loop_audit",
        "target_internal_tool": case.tool,
        "target_arguments": args,
        "target_arguments_transport_note": (
            "These are exact target arguments for the planner native tool call. "
            "They are carried outside the free-form goal so the controller does "
            "not pre-read them before the planner turn."
        ),
        "coverage_rule": (
            "The case is covered only if the normal planner loop attempts this "
            "tool, blocks it with a typed guard, or returns a typed unavailable result."
        ),
        "not_a_direct_dispatch": True,
    }
    payload = {
        "request": (
            "MACRO_RUNTIME_LOOP_PAYLOAD_TEST. Run the full normal agentic planner loop: "
            "3571 public vulkan_helper -> 3572 queued job -> prompt pack -> 11434 planner "
            "native tool call -> 3572 validator/controller -> internal tool dispatch or typed "
            "guard -> final serializer. "
            f"The target coverage tool for this macro case is {case.tool}. "
            "Read the structured explicit_request_context and target arguments in the planner payload. Use any supporting "
            "tool if the validator/evidence contract requires it, but the case is not covered "
            f"unless {case.tool} is attempted, blocked with a typed guard, or produces a typed "
            f"unavailable result. The exact target arguments are in explicit_request_context "
            f"inside the planner payload, not in this free-form goal. {case.request}"
        ),
        "job_id": job_id,
        "context": json.dumps(macro_context, ensure_ascii=False, sort_keys=True, default=str),
        "return_mode": "wait",
        "wait_seconds": wait_seconds,
        "timeout_seconds": min(max(wait_seconds + 60, 120), 900),
        "max_steps": max_steps,
        "approval_mode": case.approval_mode,
        "user_consent": case.user_consent,
        "arguments": args,
        "parameters": args,
    }
    return payload


def _broker_result_request(job_id: str) -> dict[str, Any]:
    return {
        "tool_name": "vulkan_helper",
        "action": "result",
        "job_id": job_id,
        "audience": "openwebui",
        "arguments": {
            "action": "result",
            "job_id": job_id,
            "audience": "openwebui",
        },
    }


def _read_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise AssertionError(f"required loop artifact missing: {path}")
    try:
        parsed = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        raise AssertionError(f"loop artifact is not JSON: {path}") from exc
    if not isinstance(parsed, dict):
        raise AssertionError(f"loop artifact is not a JSON object: {path}")
    return parsed


def _read_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise AssertionError(f"required loop events file missing: {path}")
    events: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = {"event_type": "raw", "message": raw}
        if isinstance(parsed, dict):
            events.append(parsed)
    if not events:
        raise AssertionError(f"loop events file is empty: {path}")
    return events


def _artifact_preview(path: Path, *, limit: int = 800) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")[:limit]


def _payload_store_dir(run_id: str) -> Path:
    safe = re.sub(r"[^a-zA-Z0-9_.-]+", "-", str(run_id)).strip("-") or "run"
    path = RUNS_DIR / "payloads" / safe
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_payload_artifact(run_id: str, name: str, payload: Any) -> dict[str, Any]:
    raw = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    digest = hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()
    safe_name = re.sub(r"[^a-zA-Z0-9_.-]+", "-", str(name)).strip("-") or "payload"
    path = _payload_store_dir(run_id) / f"{safe_name}.json"
    path.write_text(raw, encoding="utf-8")
    return {
        "path": str(path),
        "sha256": digest,
        "size_bytes": len(raw.encode("utf-8", errors="replace")),
    }


def _assert_3572_openwebui_serializer_shape(
    *,
    serializer_request: dict[str, Any],
    serializer_result: dict[str, Any],
) -> None:
    request_args = serializer_request.get("arguments")
    if not isinstance(request_args, dict):
        request_args = {}
    requested_audience = str(
        serializer_request.get("audience")
        or request_args.get("audience")
        or ""
    ).strip().lower()
    if requested_audience != "openwebui":
        raise AssertionError(
            f"macro serializer request did not ask for openwebui audience: {requested_audience or '<missing>'}"
        )

    final_path_verification = serializer_result.get("final_path_verification")
    final_path_verification_has_final_path = (
        isinstance(final_path_verification, dict)
        and "final_path" in final_path_verification
    )
    operator_keys = [
        key
        for key in ("final_path", "final_markdown_path", "events_path")
        if key in serializer_result
    ]
    has_operator_diagnostics = "operator_diagnostics" in serializer_result
    if operator_keys or final_path_verification_has_final_path or not has_operator_diagnostics:
        raise AssertionError(
            "3572 action=result did not honor audience=openwebui; "
            "the live broker returned operator serializer fields. "
            f"operator_keys={operator_keys} "
            f"final_path_verification_has_final_path={final_path_verification_has_final_path} "
            f"has_operator_diagnostics={has_operator_diagnostics}. "
            "Restart/reload the 3572 broker process or fix the result route before trusting payload equality."
        )


def _assert_full_agentic_loop_artifacts(
    *,
    urls: RuntimeUrls,
    broker_health: dict[str, Any],
    job_id: str,
    target_tool: str,
    run_id: str,
) -> dict[str, Any]:
    if not job_id:
        raise AssertionError("test did not provide a job_id; cannot audit full 3572 loop")
    agent_job_root = Path(str(broker_health.get("agent_job_root") or "")).resolve()
    if not agent_job_root.exists():
        raise AssertionError(f"3572 health agent_job_root is missing: {agent_job_root}")
    job_root = agent_job_root / job_id
    if not job_root.exists():
        raise AssertionError(f"job root not found for full loop audit: {job_root}")

    job_state = _read_json_file(job_root / "job.json")
    final_json = _read_json_file(job_root / "final.json")
    events = _read_events(job_root / "events.ndjson")
    if str(job_state.get("public_tool_name") or "") != "vulkan_helper":
        raise AssertionError(
            f"full loop job was not created through public vulkan_helper: "
            f"public_tool_name={job_state.get('public_tool_name')!r}"
        )
    request_payload = job_state.get("request_payload") if isinstance(job_state.get("request_payload"), dict) else {}
    original_args = job_state.get("original_args") if isinstance(job_state.get("original_args"), dict) else {}
    if request_payload.get("tool_name") != "vulkan_helper":
        raise AssertionError(f"3572 job request_payload.tool_name is not vulkan_helper for job {job_id}")
    if request_payload.get("bridge_public_tool_x") != "vulkan_helper":
        raise AssertionError(f"3572 job request_payload.bridge_public_tool_x is not vulkan_helper for job {job_id}")
    for forbidden_key in ("function", "tool_name", "requested_tool_name"):
        value = original_args.get(forbidden_key)
        if isinstance(value, str) and value.strip() and value.strip() != "vulkan_helper":
            raise AssertionError(
                f"macro original_args leaked internal dispatch key {forbidden_key}={value!r} "
                f"instead of preserving planner-owned tool selection"
            )
    prompt_files = sorted((job_root / "planner-prompts").glob("step-*-planner-payload.json"))
    stream_files = sorted((job_root / "planner-stream").glob("*.txt"))
    if not prompt_files:
        raise AssertionError(f"planner prompt payload captures missing for job {job_id}")
    if not stream_files:
        raise AssertionError(f"planner stream captures missing for job {job_id}")

    first_prompt = _read_json_file(prompt_files[0])
    planner_payload = first_prompt.get("planner_payload") if isinstance(first_prompt.get("planner_payload"), dict) else first_prompt
    user_payload = first_prompt.get("user_payload") if isinstance(first_prompt.get("user_payload"), dict) else {}
    messages = planner_payload.get("messages") if isinstance(planner_payload, dict) else None
    if not isinstance(messages, list) or not messages:
        raise AssertionError(f"planner payload has no messages for job {job_id}")
    native_tools = planner_payload.get("tools") if isinstance(planner_payload, dict) else None
    if not isinstance(native_tools, list) or not native_tools:
        raise AssertionError(f"planner payload did not include native tools for job {job_id}")
    native_tool_names = [
        str((item.get("function") or {}).get("name") or "")
        for item in native_tools
        if isinstance(item, dict) and isinstance(item.get("function"), dict)
    ]
    if target_tool not in native_tool_names:
        raise AssertionError(
            f"planner native tools did not include target tool {target_tool} for job {job_id}: "
            f"{native_tool_names}"
        )
    if isinstance(planner_payload, dict) and planner_payload.get("format") == "json":
        raise AssertionError(f"planner payload used legacy JSON format instead of native tools for job {job_id}")
    explicit_request_context = (
        user_payload.get("explicit_request_context")
        if isinstance(user_payload.get("explicit_request_context"), dict)
        else {}
    )
    if explicit_request_context.get("target_internal_tool") != target_tool:
        raise AssertionError(
            f"planner payload explicit_request_context missing target tool {target_tool} for job {job_id}"
        )
    explicit_args = (
        explicit_request_context.get("target_arguments")
        if isinstance(explicit_request_context.get("target_arguments"), dict)
        else {}
    )
    if target_tool == "repo_read" and not str(explicit_args.get("path") or "").strip():
        raise AssertionError(f"planner payload explicit_request_context lacks repo_read path for job {job_id}")
    prompt_pack = user_payload.get("prompt_pack_contract") if isinstance(user_payload.get("prompt_pack_contract"), dict) else {}
    if prompt_pack.get("native_tools_schema_accounted_in_budget") is not True:
        raise AssertionError(f"prompt pack did not account for native tool schema for job {job_id}")
    if int(prompt_pack.get("native_tools_schema_chars") or 0) <= 0:
        raise AssertionError(f"prompt pack native_tools_schema_chars missing/zero for job {job_id}")
    user_payload_text = json.dumps(user_payload, ensure_ascii=False, default=str)
    for required in ("evidence_contract", "available_tools", "required_working_set"):
        if required not in user_payload_text:
            raise AssertionError(f"planner prompt missing normal loop context section {required} for job {job_id}")

    event_types = {str(item.get("event_type") or "") for item in events}
    if "job_queued" not in event_types:
        raise AssertionError(f"job_queued event missing for job {job_id}")
    if "agentic_loop_started" not in event_types:
        raise AssertionError(f"agentic_loop_started event missing for job {job_id}")
    if "planner_request_started" not in event_types:
        raise AssertionError(f"planner_request_started event missing for job {job_id}")
    if "planner_decision" not in event_types:
        raise AssertionError(f"planner_decision event missing for job {job_id}")
    if target_tool == "repo_read" and "controller_preseed_file_surface" in event_types:
        raise AssertionError(
            f"target repo_read was covered by deterministic controller preseed before planner for job {job_id}"
        )
    if not any(("tool" in value or "controller" in value or "validator" in value or "job_completed" in value or "job_failed" in value) for value in event_types):
        raise AssertionError(f"events do not show tool/controller/validator/terminal loop activity for job {job_id}: {sorted(event_types)}")

    observed_tools = extract_tools_observed(final_json)
    final_text = json.dumps(final_json, ensure_ascii=False, default=str)
    typed_result_for_target = (
        target_tool in observed_tools
        or f'"tool": "{target_tool}"' in final_text
        or target_tool in final_text and any(marker in final_text for marker in ("unavailable", "blocked", "missing", "requires"))
    )
    if not typed_result_for_target:
        raise AssertionError(
            f"full loop final artifact does not show target tool attempt/typed block: {target_tool}"
        )

    planner_lab = get_json_or_none(urls.broker_3572 + f"/jobs/{job_id}/planner-lab.json", timeout=20)
    return {
        "job_root": str(job_root),
        "job_state_artifact": _write_payload_artifact(run_id, f"{target_tool}-3572-job-state", job_state),
        "final_json_artifact": _write_payload_artifact(run_id, f"{target_tool}-3572-final-json", final_json),
        "events_artifact": _write_payload_artifact(run_id, f"{target_tool}-3572-events", events),
        "first_planner_payload_artifact": _write_payload_artifact(run_id, f"{target_tool}-3572-first-planner-payload", first_prompt),
        **(
            {"planner_lab_artifact": _write_payload_artifact(run_id, f"{target_tool}-3572-planner-lab", planner_lab)}
            if isinstance(planner_lab, dict)
            else {}
        ),
        "job_status": job_state.get("status"),
        "public_tool_name": job_state.get("public_tool_name"),
        "request_payload_tool_name": request_payload.get("tool_name"),
        "request_payload_bridge_public_tool_x": request_payload.get("bridge_public_tool_x"),
        "event_count": len(events),
        "event_types_preview": sorted(event_types)[:20],
        "planner_prompt_count": len(prompt_files),
        "planner_stream_count": len(stream_files),
        "native_tool_schema_count": len(native_tools),
        "native_tool_names": native_tool_names,
        "explicit_request_context": explicit_request_context,
        "prompt_pack_contract": prompt_pack,
        "first_prompt_preview": _artifact_preview(prompt_files[0]),
        "first_stream_preview": _artifact_preview(stream_files[0]),
        "final_status": final_json.get("status"),
        "target_tool_in_final": typed_result_for_target,
        "planner_lab_available": isinstance(planner_lab, dict),
        "planner_lab_schema": planner_lab.get("schema") if isinstance(planner_lab, dict) else None,
    }


def _write_report(report: dict[str, Any]) -> Path:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    seed = report.get("seed", "unknown")
    path = RUNS_DIR / f"loop_payload_completo_{seed}_{int(time.time())}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return path


@pytest.mark.operator_runtime
def test_loop_payload_completo_dynamic_tool_matrix() -> None:
    _check_operator_present()
    urls = RuntimeUrls()
    seed = _seed()
    run_id = _run_id(seed)
    wait_seconds = _int_env("LOOP_PAYLOAD_WAIT_SECONDS", 240)
    default_max_steps = _int_env("LOOP_PAYLOAD_MAX_STEPS", 8)
    max_tools = _int_env("LOOP_PAYLOAD_MAX_TOOLS", 0)
    only_tool = str(os.environ.get("LOOP_PAYLOAD_ONLY_TOOL") or "").strip()

    report: dict[str, Any] = {
        "schema": "macro_loop_payload_completo_report.v1",
        "seed": seed,
        "run_id": run_id,
        "started_at": time.time(),
        "runtime": {},
        "samples": {},
        "cases": [],
        "failures": [],
    }
    try:
        preflight = _preflight(urls)
        report["runtime"] = preflight
        samples = sample_repo_files(Path(preflight["lab_repo"]), seed=seed)
        report["samples"] = {"seed": samples.seed, "files": list(samples.files)}

        tool_names = set(preflight["runtime_tools"])
        cases = build_tool_cases(sample_file=samples.first(), sample_files=samples.files, seed=seed, run_id=run_id)
        missing = missing_cases_for_tools(tool_names, cases)
        if missing:
            raise AssertionError(f"missing_macro_case_for_tool: {missing}")

        selected_tools = sorted(tool_names)
        if only_tool:
            if only_tool not in tool_names:
                raise AssertionError(f"LOOP_PAYLOAD_ONLY_TOOL not in dynamic runtime surface: {only_tool}")
            selected_tools = [only_tool]
        if max_tools > 0:
            selected_tools = selected_tools[:max_tools]

        for tool_name in selected_tools:
            case = cases[tool_name]
            expected_job_id = _safe_job_id(run_id, tool_name)
            _assert_fresh_job_id(preflight, expected_job_id)
            row: dict[str, Any] = {
                "tool": tool_name,
                "expected_job_id": expected_job_id,
                "requested_at": time.time(),
                "status": "pending",
            }
            report["cases"].append(row)
            try:
                payload = _request_for_case(
                    case,
                    job_id=expected_job_id,
                    wait_seconds=wait_seconds,
                    default_max_steps=default_max_steps,
                )
                result = post_json(urls.bridge_3571 + "/vulkan_helper", payload, timeout=wait_seconds + 120)
                row["request_payload_artifact"] = _write_payload_artifact(run_id, f"{tool_name}-3571-request", payload)
                row["public_3571_payload_artifact"] = _write_payload_artifact(run_id, f"{tool_name}-3571-public-payload", result)
                serializer_request = _broker_result_request(expected_job_id)
                row["serializer_3572_request_artifact"] = _write_payload_artifact(
                    run_id,
                    f"{tool_name}-3572-final-serializer-request",
                    serializer_request,
                )
                serializer_result = post_json(
                    urls.broker_3572 + "/vulkan/agent",
                    serializer_request,
                    timeout=60,
                )
                row["serializer_3572_payload_artifact"] = _write_payload_artifact(
                    run_id,
                    f"{tool_name}-3572-final-serializer-payload",
                    serializer_result,
                )
                public_job_id = extract_job_id(result)
                row["public_payload_job_id"] = public_job_id
                if public_job_id != expected_job_id:
                    raise AssertionError(
                        f"3571 public payload did not expose the expected fresh job_id: "
                        f"expected={expected_job_id} got={public_job_id or '<missing>'}"
                    )
                row["job_id"] = public_job_id or expected_job_id
                row["status"] = str(result.get("status") or result.get("job_status") or "")
                row["payload_assertions"] = assert_public_payload_contract(result)
                serializer_job_id = extract_job_id(serializer_result)
                row["serializer_payload_job_id"] = serializer_job_id
                if serializer_job_id != expected_job_id:
                    raise AssertionError(
                        f"3572 final serializer did not return the same job_id: "
                        f"expected={expected_job_id} got={serializer_job_id or '<missing>'}"
                    )
                _assert_3572_openwebui_serializer_shape(
                    serializer_request=serializer_request,
                    serializer_result=serializer_result,
                )
                row["serializer_payload_assertions"] = assert_public_payload_contract(serializer_result)
                row["same_openwebui_payload_assertions"] = assert_same_openwebui_payload(result, serializer_result)
                row["agentic_loop_audit"] = _assert_full_agentic_loop_artifacts(
                    urls=urls,
                    broker_health=preflight["broker_health"],
                    job_id=expected_job_id,
                    target_tool=tool_name,
                    run_id=run_id,
                )
                observed_tools = extract_tools_observed(result) | extract_tools_observed(serializer_result)
                row["observed_tools"] = sorted(observed_tools)
                final_target_ok = bool((row["agentic_loop_audit"] or {}).get("target_tool_in_final"))
                if case.expect_tool_call and tool_name not in observed_tools and not final_target_ok and result.get("status") == "completed":
                    raise AssertionError(
                        f"requested tool {tool_name} was not observed in completed payload; "
                        f"observed={sorted(observed_tools)}"
                    )
                row["ok"] = True
            except Exception as exc:
                row["ok"] = False
                row["error_type"] = type(exc).__name__
                row["error"] = str(exc)
                report["failures"].append(
                    {
                        "tool": tool_name,
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    }
                )

        if report["failures"]:
            raise AssertionError(
                "loop_payload_completo failures: "
                + json.dumps(report["failures"], ensure_ascii=False, indent=2)
            )
    finally:
        report["finished_at"] = time.time()
        report_path = _write_report(report)
        print(f"\nmacro_loop_payload_completo_report={report_path}")
