#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
from contextlib import contextmanager
import hashlib
import json
import ntpath
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any, Iterator


ROOT = Path(r"C:\Users\carmi\AI")
CONFIG = ROOT / ".codex" / "mcp_servers_probe.json"
STATE_DIR = ROOT / ".codex" / "state"
REPORT_JSON = STATE_DIR / "mcp_probe_report.json"
REPORT_JSONL = STATE_DIR / "mcp_probe_report.jsonl"
REPORT_LOCK = STATE_DIR / "mcp_probe_report.lock"

REPORT_SCHEMA_VERSION = 2
DEFAULT_TIMEOUT_SECONDS = 25
DEFAULT_CACHE_MAX_AGE_SECONDS = 600
MAX_CACHE_MAX_AGE_SECONDS = 86_400
STDOUT_PREVIEW_LIMIT = 1_000
STDERR_PREVIEW_LIMIT = 1_000
EXCEPTION_MESSAGE_LIMIT = 500
TOOL_NAME_LIMIT = 200
TOOL_DESCRIPTION_LIMIT = 300
ADDITIONAL_CONTEXT_LIMIT = 8_000
PERSISTENCE_DIAGNOSTIC_RESERVE = 700
JSONL_MAX_BYTES = 5 * 1024 * 1024
LOCK_TIMEOUT_SECONDS = 2.0
STALE_LOCK_SECONDS = 30.0
MAX_REPORTED_ARGS = 64

SENSITIVE_KEYS = (
    "authorization",
    "bearer",
    "token",
    "access_token",
    "refresh_token",
    "api_key",
    "secret",
    "password",
    "cookie",
    "private_key",
    "credential",
)
_SENSITIVE_KEY_PATTERN = "|".join(
    re.escape(key) for key in sorted(SENSITIVE_KEYS, key=len, reverse=True)
)
_SECRET_ASSIGNMENT_RE = re.compile(
    rf"(?i)\b({_SENSITIVE_KEY_PATTERN})\b"
    r"(\s*(?:[:=]\s*|\s+))"
    r"(?:bearer\s+)?"
    r"(?:\"(?:\\.|[^\"])*\"|'(?:\\.|[^'])*'|[^\r\n,;]+)"
)
_BEARER_VALUE_RE = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")


def bounded_text(value: Any, limit: int) -> str:
    text = "" if value is None else str(value)
    if len(text) <= limit:
        return text
    marker = "...[truncated]"
    if limit <= len(marker):
        return marker[:limit]
    return text[: limit - len(marker)] + marker


def redact_text(value: Any) -> str:
    text = "" if value is None else str(value)
    text = _SECRET_ASSIGNMENT_RE.sub(
        lambda match: f"{match.group(1)}{match.group(2)}[REDACTED]",
        text,
    )
    return _BEARER_VALUE_RE.sub("Bearer [REDACTED]", text)


def bounded_redacted(value: Any, limit: int) -> str:
    return bounded_text(redact_text(value), limit)


def is_sensitive_key(key: Any) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "_", str(key).casefold()).strip("_")
    return any(sensitive in normalized for sensitive in SENSITIVE_KEYS)


def redact_data(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[Any, Any] = {}
        for key, item in value.items():
            redacted[key] = "[REDACTED]" if is_sensitive_key(key) else redact_data(item)
        return redacted
    if isinstance(value, list):
        return [redact_data(item) for item in value]
    if isinstance(value, tuple):
        return [redact_data(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value


def preview(value: Any, limit: int) -> str:
    if isinstance(value, bytes):
        text = value.decode("utf-8", errors="replace")
    else:
        text = "" if value is None else str(value)
    return bounded_redacted(text, limit)


def load_stdin_event() -> dict[str, Any]:
    try:
        raw = sys.stdin.read()
        if raw.strip():
            value = json.loads(raw)
            if isinstance(value, dict):
                return value
    except Exception:
        pass
    return {}


def json_line(obj: dict[str, Any]) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n"


def parse_mcp_messages(raw: str) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []

    for line in raw.splitlines():
        text = line.strip()
        if not text or not text.startswith("{"):
            continue
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            messages.append(value)

    if messages:
        return messages

    data = raw.encode("utf-8", errors="replace")
    pos = 0
    while pos < len(data):
        header_end = data.find(b"\r\n\r\n", pos)
        if header_end < 0:
            break

        header = data[pos:header_end].decode("ascii", errors="replace")
        length = None
        for hline in header.splitlines():
            key, sep, val = hline.partition(":")
            if sep and key.strip().lower() == "content-length":
                try:
                    length = int(val.strip())
                except ValueError:
                    length = None
                break

        if not length:
            break

        body_start = header_end + 4
        body_end = body_start + length
        if body_end > len(data):
            break

        try:
            value = json.loads(data[body_start:body_end].decode("utf-8", errors="replace"))
        except json.JSONDecodeError:
            value = None

        if isinstance(value, dict):
            messages.append(value)

        pos = body_end

    return messages


def response_by_id(messages: list[dict[str, Any]], msg_id: int) -> dict[str, Any] | None:
    for msg in messages:
        if msg.get("id") == msg_id:
            return msg
    return None


def tool_surface_from_messages(
    messages: list[dict[str, Any]],
    server_name: str,
) -> list[dict[str, str]]:
    response = response_by_id(messages, 2)
    result = response.get("result") if isinstance(response, dict) else None
    raw_tools = result.get("tools") if isinstance(result, dict) else None
    if not isinstance(raw_tools, list):
        return []

    by_name: dict[str, dict[str, str]] = {}
    for raw_tool in raw_tools:
        if not isinstance(raw_tool, dict) or not isinstance(raw_tool.get("name"), str):
            continue
        name = bounded_redacted(raw_tool["name"], TOOL_NAME_LIMIT)
        if not name:
            continue
        item = {
            "name": name,
            "server": server_name,
        }
        description = raw_tool.get("description")
        if isinstance(description, str) and description.strip():
            item["description"] = bounded_redacted(
                description.strip(),
                TOOL_DESCRIPTION_LIMIT,
            )
        by_name[name] = item

    return sorted(
        by_name.values(),
        key=lambda item: (item["name"].casefold(), item["name"]),
    )


def server_classification(server_name: str) -> str:
    normalized = server_name.casefold()
    if normalized.startswith("aicarmine_"):
        normalized = normalized[len("aicarmine_") :]

    classifications = {
        "repo_state": "repository_state",
        "repo_search_det": "deterministic_search",
        "repo_validate": "validation",
        "repo_code": "code_change",
        "git_readonly": "git_readonly",
        "sqlite_readonly": "database_readonly",
        "job_artifact": "raw_job_evidence",
        "job_view": "rendered_job_view",
        "project_memory": "project_memory",
        "agentic_loop_client": "agentic_loop",
        "local_subagent": "readonly_subagent",
        "codex_ops": "operations",
        "rag": "semantic_search",
    }
    return classifications.get(normalized, "other")


def safe_arg(value: Any) -> str:
    text = str(value)
    if "\\" in text or "/" in text:
        text = ntpath.basename(text.rstrip("\\/")) or text
    return bounded_redacted(text, 300)


def safe_args(raw_args: list[Any]) -> list[str]:
    args: list[str] = []
    redact_next = False

    for value in raw_args[:MAX_REPORTED_ARGS]:
        text = str(value)
        if redact_next:
            args.append("[REDACTED]")
            redact_next = False
            continue

        option_name, separator, _ = text.partition("=")
        normalized_option = option_name.lstrip("-/")
        if is_sensitive_key(normalized_option):
            if separator:
                args.append(bounded_text(f"{option_name}=[REDACTED]", 300))
            else:
                args.append(bounded_text(text, 300))
                redact_next = True
            continue

        args.append(safe_arg(text))

    if len(raw_args) > MAX_REPORTED_ARGS:
        args.append("[args truncated]")
    return args


def server_metadata(cfg: dict[str, Any]) -> dict[str, Any]:
    command = cfg.get("command")
    raw_args = cfg.get("args") or []
    if not isinstance(raw_args, list):
        raw_args = [raw_args]

    args = safe_args(raw_args)

    env_cfg = cfg.get("env") or {}
    if not isinstance(env_cfg, dict):
        env_cfg = {}

    return {
        "command_basename": bounded_redacted(ntpath.basename(str(command or "")), 300),
        "args": args,
        "cwd": bounded_redacted(cfg.get("cwd") or str(ROOT), 500),
        "env_keys": sorted(
            bounded_text(key, 200) for key in (str(key) for key in env_cfg)
        ),
    }


def empty_probe_result(
    server_name: str,
    cfg: dict[str, Any],
    error: str,
) -> dict[str, Any]:
    return {
        "server": server_name,
        "classification": server_classification(server_name),
        "ok": False,
        "init_ok": False,
        "tools_list_ok": False,
        "tool_count": 0,
        "tool_names": [],
        "tools": [],
        "tool_surface": [],
        "error": error,
        "elapsed_ms": 0,
        **server_metadata(cfg),
    }


def probe_server(name: str, cfg: dict[str, Any], timeout_seconds: int) -> dict[str, Any]:
    started_at = time.time()

    command = cfg.get("command")
    raw_args = cfg.get("args") or []
    if not isinstance(raw_args, list):
        raw_args = [raw_args]
    args = [str(value) for value in raw_args]
    cwd = str(cfg.get("cwd") or ROOT)
    env_cfg = cfg.get("env") or {}
    if not isinstance(env_cfg, dict):
        env_cfg = {}
    metadata = server_metadata(cfg)

    if not command:
        return empty_probe_result(name, cfg, "missing_command")

    full_env = os.environ.copy()
    for key, value in env_cfg.items():
        full_env[str(key)] = str(value)

    init = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {
                "name": "aicarmine-codex-hook-mcp-probe",
                "version": "0.1.0",
            },
        },
    }
    initialized = {
        "jsonrpc": "2.0",
        "method": "notifications/initialized",
        "params": {},
    }
    tools_list = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list",
        "params": {},
    }
    stdin_payload = json_line(init) + json_line(initialized) + json_line(tools_list)

    try:
        proc = subprocess.run(
            [str(command), *args],
            input=stdin_payload,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=cwd,
            env=full_env,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "server": name,
            "classification": server_classification(name),
            "ok": False,
            "init_ok": False,
            "tools_list_ok": False,
            "tool_count": 0,
            "tool_names": [],
            "tools": [],
            "tool_surface": [],
            "error": "timeout",
            "timeout_seconds": timeout_seconds,
            "elapsed_ms": int((time.time() - started_at) * 1000),
            "stdout_prefix": preview(exc.stdout, STDOUT_PREVIEW_LIMIT),
            "stderr_prefix": preview(exc.stderr, STDERR_PREVIEW_LIMIT),
            **metadata,
        }
    except Exception as exc:
        return {
            "server": name,
            "classification": server_classification(name),
            "ok": False,
            "init_ok": False,
            "tools_list_ok": False,
            "tool_count": 0,
            "tool_names": [],
            "tools": [],
            "tool_surface": [],
            "error": type(exc).__name__,
            "message": bounded_redacted(str(exc), EXCEPTION_MESSAGE_LIMIT),
            "elapsed_ms": int((time.time() - started_at) * 1000),
            **metadata,
        }

    messages = parse_mcp_messages(proc.stdout)
    initialize_response = response_by_id(messages, 1)
    tools_response = response_by_id(messages, 2)
    tool_surface = tool_surface_from_messages(messages, name)
    tool_names = [item["name"] for item in tool_surface]

    init_ok = bool(initialize_response and "result" in initialize_response)
    tools_ok = bool(tools_response and "result" in tools_response)
    ok = bool(init_ok and tools_ok)

    result: dict[str, Any] = {
        "server": name,
        "classification": server_classification(name),
        "ok": ok,
        "init_ok": init_ok,
        "tools_list_ok": tools_ok,
        "tool_count": len(tool_names),
        "tool_names": tool_names,
        "tools": tool_names,
        "tool_surface": tool_surface,
        "returncode": proc.returncode,
        "elapsed_ms": int((time.time() - started_at) * 1000),
        "stderr_prefix": preview(proc.stderr, STDERR_PREVIEW_LIMIT),
        "stdout_message_count": len(messages),
        "stdout_prefix": "" if tools_ok else preview(proc.stdout, STDOUT_PREVIEW_LIMIT),
        **metadata,
    }
    if not init_ok:
        result["error"] = "initialize_failed"
    elif not tools_ok:
        result["error"] = "tools_list_failed"
    return result


def inventory_record(inventory_bytes: bytes, server_count: int) -> dict[str, Any]:
    return {
        "path": str(CONFIG.resolve()),
        "sha256": hashlib.sha256(inventory_bytes).hexdigest(),
        "server_count": server_count,
    }


def normalized_path(value: Any) -> str:
    return os.path.normcase(os.path.abspath(str(value)))


def load_valid_cache(
    inventory: dict[str, Any],
    max_age_seconds: int,
) -> dict[str, Any] | None:
    try:
        cached = json.loads(REPORT_JSON.read_text(encoding="utf-8"))
    except Exception:
        return None

    if not isinstance(cached, dict):
        return None
    if cached.get("schema_version") != REPORT_SCHEMA_VERSION:
        return None
    if cached.get("complete") is not True:
        return None
    if cached.get("parse_error") or cached.get("status") == "inventory_parse_error":
        return None

    cached_inventory = cached.get("inventory")
    if not isinstance(cached_inventory, dict):
        return None
    if normalized_path(cached_inventory.get("path")) != normalized_path(inventory["path"]):
        return None
    if cached_inventory.get("sha256") != inventory["sha256"]:
        return None
    if cached_inventory.get("server_count") != inventory["server_count"]:
        return None

    probed_at = cached.get("probed_at_epoch")
    if not isinstance(probed_at, (int, float)):
        return None
    age = time.time() - float(probed_at)
    if age < 0 or age > max_age_seconds:
        return None

    results = cached.get("results")
    summary = cached.get("summary")
    if not isinstance(results, list) or not isinstance(summary, dict):
        return None
    if any(not isinstance(result, dict) for result in results):
        return None
    if summary.get("configured_servers") != inventory["server_count"]:
        return None
    if summary.get("probed_servers") != len(results):
        return None
    for result in results:
        if not isinstance(result.get("tool_names"), list):
            return None
        if "init_ok" not in result or "tools_list_ok" not in result:
            return None

    return cached


def healthy_result(result: dict[str, Any]) -> bool:
    return bool(result.get("init_ok") is True and result.get("tools_list_ok") is True)


def build_report(
    results: list[dict[str, Any]],
    inventory: dict[str, Any],
    cache_used: bool,
    probed_at_epoch: float,
) -> dict[str, Any]:
    ordered_results = sorted(
        results,
        key=lambda result: (
            str(result.get("server") or "").casefold(),
            str(result.get("server") or ""),
        ),
    )
    healthy = [result for result in ordered_results if healthy_result(result)]
    failed = [result for result in ordered_results if not healthy_result(result)]
    tool_count = sum(int(result.get("tool_count") or 0) for result in ordered_results)

    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "complete": True,
        "generated_at_epoch": time.time(),
        "probed_at_epoch": probed_at_epoch,
        "cache_used": cache_used,
        "config": str(CONFIG),
        "inventory": inventory,
        "total": len(ordered_results),
        "ok": len(healthy),
        "bad": len(failed),
        "summary": {
            "configured_servers": inventory["server_count"],
            "probed_servers": len(ordered_results),
            "healthy_servers": len(healthy),
            "failed_servers": len(failed),
            "tool_count": tool_count,
            "cache_used": cache_used,
            "additional_context_truncated": False,
        },
        "results": ordered_results,
    }


def short_tool_name(server_name: str, tool_name: str) -> str:
    prefix = server_name + "_"
    if tool_name.startswith(prefix):
        return tool_name[len(prefix) :]
    return tool_name


def append_wrapped_tool_names(
    lines: list[str],
    server_name: str,
    tool_names: list[str],
) -> None:
    if not tool_names:
        lines.append("  tools: (none returned)")
        return

    display_names = [
        short_tool_name(server_name, name)
        for name in sorted(tool_names, key=lambda item: (item.casefold(), item))
    ]
    prefix = "  tools: "
    continuation = "    "
    current = prefix

    for name in display_names:
        token = name if current == prefix else ", " + name
        if len(current) + len(token) > 500 and current != prefix:
            lines.append(current)
            current = continuation + name
        else:
            current += token
    lines.append(current)


def bounded_lines(lines: list[str], limit: int) -> tuple[str, bool]:
    output: list[str] = []
    total = 0
    truncated = False

    for line in lines:
        safe_line = bounded_redacted(line, 600)
        added = len(safe_line) + (1 if output else 0)
        if total + added > limit:
            truncated = True
            break
        output.append(safe_line)
        total += added

    if truncated:
        marker = "[tool surface truncated]"
        while output and len("\n".join([*output, marker])) > limit:
            output.pop()
        if len(marker) <= limit:
            output.append(marker)

    return "\n".join(output), truncated


def build_additional_context(report: dict[str, Any]) -> tuple[str, bool]:
    results = report["results"]
    healthy = [result for result in results if healthy_result(result)]
    failed = [result for result in results if not healthy_result(result)]
    summary = report["summary"]

    lines = [
        "AICARMINE MCP TOOL SURFACE",
        "",
        (
            "Probe evidence: "
            f"{summary['healthy_servers']}/{summary['probed_servers']} servers healthy; "
            f"{summary['tool_count']} tools; "
            f"cache_used={str(summary['cache_used']).lower()}."
        ),
        "",
        "Available dedicated servers:",
    ]

    if not healthy:
        lines.append("- none completed both initialize and tools/list")
    else:
        for result in healthy:
            server_name = str(result.get("server") or "")
            classification = str(
                result.get("classification") or server_classification(server_name)
            )
            lines.append(
                f"- {bounded_redacted(server_name, 200)} [{classification}]"
            )
            tool_names = [
                str(name)
                for name in (result.get("tool_names") or [])
                if isinstance(name, str)
            ]
            append_wrapped_tool_names(lines, server_name, tool_names)

    if failed:
        lines.extend(["", "Unavailable or incomplete dedicated servers:"])
        for result in failed:
            server_name = bounded_redacted(result.get("server"), 200)
            error = bounded_redacted(result.get("error") or "protocol_incomplete", 100)
            lines.append(
                f"- {server_name}: error={error}; "
                f"init_ok={bool(result.get('init_ok'))}; "
                f"tools_list_ok={bool(result.get('tools_list_ok'))}"
            )

    classifications = {
        str(result.get("classification") or server_classification(str(result.get("server") or "")))
        for result in healthy
    }
    lines.extend(["", "Operational policy:", "- prefer the narrowest dedicated MCP"])
    if "deterministic_search" in classifications:
        lines.append("- use repo_search_det before native rg when suitable")
    if "validation" in classifications:
        lines.append(
            "- use repo_validate reviewed probe profiles instead of inline probes"
        )
    if {"raw_job_evidence", "rendered_job_view"}.issubset(classifications):
        lines.append("- use job_artifact before job_view for primary evidence")
    if "project_memory" in classifications:
        lines.append("- use project-memory writes only when explicitly requested")
    lines.append("- use native fallback only after a concrete MCP failure")
    lines.append("- do not repeat an unchanged non-retryable MCP call")

    base_limit = ADDITIONAL_CONTEXT_LIMIT - PERSISTENCE_DIAGNOSTIC_RESERVE
    return bounded_lines(lines, base_limit)


def add_persistence_diagnostic(
    context: str,
    diagnostic: str,
) -> tuple[str, bool]:
    if not diagnostic:
        return context, False
    lines = context.splitlines()
    lines.extend(
        [
            "",
            "Persistence diagnostic (fail-open):",
            f"- {bounded_redacted(diagnostic, EXCEPTION_MESSAGE_LIMIT)}",
        ]
    )
    return bounded_lines(lines, ADDITIONAL_CONTEXT_LIMIT)


def atomic_write_report(path: Path, report: dict[str, Any]) -> None:
    payload = json.dumps(
        redact_data(report),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"
    temporary = path.with_name(
        f".{path.name}.{os.getpid()}.{time.time_ns()}.tmp"
    )
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            if temporary.exists():
                temporary.unlink()
        except OSError:
            pass


@contextmanager
def report_lock(timeout_seconds: float = LOCK_TIMEOUT_SECONDS) -> Iterator[bool]:
    timeout = max(0.0, min(float(timeout_seconds), LOCK_TIMEOUT_SECONDS))
    deadline = time.monotonic() + timeout
    token = f"{os.getpid()}-{time.time_ns()}"
    acquired = False

    while True:
        try:
            descriptor = os.open(
                REPORT_LOCK,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            )
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(token)
                handle.flush()
            acquired = True
            break
        except FileExistsError:
            try:
                age = time.time() - REPORT_LOCK.stat().st_mtime
                if age > STALE_LOCK_SECONDS:
                    REPORT_LOCK.unlink()
                    continue
            except OSError:
                pass
        except OSError:
            break

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(0.05, remaining))

    try:
        yield acquired
    finally:
        if acquired:
            try:
                if REPORT_LOCK.read_text(encoding="utf-8") == token:
                    REPORT_LOCK.unlink()
            except OSError:
                pass


def rotate_jsonl_if_needed() -> None:
    if not REPORT_JSONL.exists():
        return
    if REPORT_JSONL.stat().st_size <= JSONL_MAX_BYTES:
        return

    backup = REPORT_JSONL.with_name(REPORT_JSONL.name + ".1")
    if backup.exists():
        backup.unlink()
    os.replace(REPORT_JSONL, backup)


def append_jsonl(report: dict[str, Any]) -> None:
    payload = json.dumps(
        redact_data(report),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    with REPORT_JSONL.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(payload + "\n")
        handle.flush()


def persist_report(report: dict[str, Any]) -> str:
    diagnostics: list[str] = []

    with report_lock() as acquired:
        if not acquired:
            return "report lock unavailable after at most 2 seconds"

        try:
            rotate_jsonl_if_needed()
        except Exception as exc:
            diagnostics.append(
                f"JSONL rotation {type(exc).__name__}: "
                f"{bounded_redacted(str(exc), EXCEPTION_MESSAGE_LIMIT)}"
            )

        try:
            append_jsonl(report)
        except Exception as exc:
            diagnostics.append(
                f"JSONL append {type(exc).__name__}: "
                f"{bounded_redacted(str(exc), EXCEPTION_MESSAGE_LIMIT)}"
            )

        try:
            atomic_write_report(REPORT_JSON, report)
        except Exception as exc:
            diagnostics.append(
                f"report replace {type(exc).__name__}: "
                f"{bounded_redacted(str(exc), EXCEPTION_MESSAGE_LIMIT)}"
            )

    return bounded_redacted("; ".join(diagnostics), EXCEPTION_MESSAGE_LIMIT)


def emit_hook_output(hook_event: str, additional_context: str) -> None:
    out = {
        "hookSpecificOutput": {
            "hookEventName": hook_event,
            "additionalContext": bounded_redacted(
                additional_context,
                ADDITIONAL_CONTEXT_LIMIT,
            ),
        }
    }
    print(json.dumps(out, ensure_ascii=False))


def cache_age_seconds(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if parsed < 0 or parsed > MAX_CACHE_MAX_AGE_SECONDS:
        raise argparse.ArgumentTypeError(
            f"must be between 0 and {MAX_CACHE_MAX_AGE_SECONDS}"
        )
    return parsed


def run_hook(
    quick: bool,
    cache_max_age_seconds: int,
    hook_event: str,
) -> int:
    if not CONFIG.exists():
        emit_hook_output(
            hook_event,
            f"AI-Carmine MCP probe config missing: {CONFIG.name}",
        )
        return 0

    try:
        inventory_bytes = CONFIG.read_bytes()
    except Exception as exc:
        emit_hook_output(
            hook_event,
            (
                "AI-Carmine MCP probe config read failed: "
                f"{type(exc).__name__}: "
                f"{bounded_redacted(str(exc), EXCEPTION_MESSAGE_LIMIT)}"
            ),
        )
        return 0

    try:
        inventory_payload = json.loads(inventory_bytes.decode("utf-8"))
        if not isinstance(inventory_payload, dict):
            raise ValueError("inventory root must be an object")
    except Exception as exc:
        emit_hook_output(
            hook_event,
            (
                "AI-Carmine MCP probe config invalid: "
                f"{type(exc).__name__}: "
                f"{bounded_redacted(str(exc), EXCEPTION_MESSAGE_LIMIT)}"
            ),
        )
        return 0

    servers = inventory_payload.get("servers") or {}
    if not isinstance(servers, dict):
        servers = {}

    inventory = inventory_record(inventory_bytes, len(servers))
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    cached = load_valid_cache(inventory, cache_max_age_seconds) if quick else None
    if cached is not None:
        results = copy.deepcopy(cached["results"])
        probed_at_epoch = float(cached["probed_at_epoch"])
        report = build_report(
            results,
            inventory,
            cache_used=True,
            probed_at_epoch=probed_at_epoch,
        )
    else:
        results = []
        for name in sorted(servers, key=lambda item: (item.casefold(), item)):
            cfg = servers[name]
            if not isinstance(cfg, dict):
                results.append(empty_probe_result(name, {}, "invalid_server_config"))
                continue
            results.append(probe_server(name, cfg, DEFAULT_TIMEOUT_SECONDS))
        report = build_report(
            results,
            inventory,
            cache_used=False,
            probed_at_epoch=time.time(),
        )

    additional_context, context_truncated = build_additional_context(report)
    report["summary"]["additional_context_truncated"] = context_truncated

    persistence_diagnostic = persist_report(report)
    additional_context, diagnostic_truncated = add_persistence_diagnostic(
        additional_context,
        persistence_diagnostic,
    )
    if diagnostic_truncated:
        report["summary"]["additional_context_truncated"] = True

    emit_hook_output(hook_event, additional_context)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Probe the dedicated AI-Carmine MCP inventory for Codex."
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="reuse a compatible fresh report before probing servers",
    )
    parser.add_argument(
        "--cache-max-age-seconds",
        type=cache_age_seconds,
        default=DEFAULT_CACHE_MAX_AGE_SECONDS,
        help=(
            "maximum quick-cache age in seconds "
            f"(default: {DEFAULT_CACHE_MAX_AGE_SECONDS})"
        ),
    )
    args = parser.parse_args()

    event = load_stdin_event()
    hook_event = str(event.get("hook_event_name") or "SessionStart")

    try:
        return run_hook(
            quick=args.quick,
            cache_max_age_seconds=args.cache_max_age_seconds,
            hook_event=hook_event,
        )
    except Exception as exc:
        emit_hook_output(
            hook_event,
            (
                "AI-Carmine MCP probe failed open: "
                f"{type(exc).__name__}: "
                f"{bounded_redacted(str(exc), EXCEPTION_MESSAGE_LIMIT)}"
            ),
        )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
