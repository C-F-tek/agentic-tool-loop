#!/usr/bin/env python3
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time
from typing import Any, Iterator


ROOT = Path(r"C:\Users\carmi\AI")
STATE_DIR = ROOT / ".codex" / "state"
LOG = STATE_DIR / "mcp_tool_calls.jsonl"
PENDING = STATE_DIR / "mcp_tool_pending.json"
LOCK = STATE_DIR / "mcp_tool_calls.lock"

SCHEMA = "aicarmine_codex_mcp_tool_event.v2"
PENDING_SCHEMA = "aicarmine_codex_mcp_tool_pending.v1"
MAX_STDIN_BYTES = 4 * 1024 * 1024
MAX_STRING_CHARS = 1_000
MAX_SUMMARY_CHARS = 8_000
MAX_ERROR_CHARS = 1_000
MAX_TOOL_NAME_CHARS = 300
MAX_EVENT_KEYS = 100
MAX_DICT_KEYS = 40
MAX_LIST_ITEMS = 20
MAX_DEPTH = 4
MAX_RECORD_BYTES = 20 * 1024
MAX_ADDITIONAL_CONTEXT_CHARS = 800
MAX_PENDING_RECORDS = 512
PENDING_MAX_AGE_SECONDS = 3_600
LOG_ROTATION_BYTES = 5 * 1024 * 1024
LOCK_TIMEOUT_SECONDS = 2.0
STALE_LOCK_SECONDS = 30.0

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

RESULT_FIELDS = (
    "tool_result",
    "tool_response",
    "result",
    "output",
)
SIGNAL_FIELDS = (
    "success",
    "ok",
    "is_error",
    "error",
    "error_type",
    "message",
)

FAMILY_MAP = {
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


@dataclass(frozen=True)
class StoragePaths:
    state_dir: Path
    log: Path
    pending: Path
    lock: Path

    @classmethod
    def from_state_dir(cls, state_dir: Path) -> "StoragePaths":
        return cls(
            state_dir=state_dir,
            log=state_dir / LOG.name,
            pending=state_dir / PENDING.name,
            lock=state_dir / LOCK.name,
        )


DEFAULT_PATHS = StoragePaths(
    state_dir=STATE_DIR,
    log=LOG,
    pending=PENDING,
    lock=LOCK,
)


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


def redact_recursive(value: Any) -> Any:
    if isinstance(value, dict):
        output: dict[str, Any] = {}
        for key, item in value.items():
            safe_key = bounded_text(key, MAX_STRING_CHARS)
            output[safe_key] = (
                "[REDACTED]" if is_sensitive_key(key) else redact_recursive(item)
            )
        return output
    if isinstance(value, (list, tuple)):
        return [redact_recursive(item) for item in value]
    if isinstance(value, bytes):
        return redact_text(value.decode("utf-8", errors="replace"))
    if isinstance(value, str):
        return redact_text(value)
    return value


def summarize_value(value: Any, depth: int = 0) -> Any:
    if depth >= MAX_DEPTH and isinstance(value, (dict, list, tuple)):
        return "[truncated:max_depth]"

    if isinstance(value, dict):
        items = sorted(value.items(), key=lambda item: str(item[0]))
        truncated = len(items) > MAX_DICT_KEYS
        if truncated:
            items = items[: MAX_DICT_KEYS - 1]

        output: dict[str, Any] = {}
        for key, item in items:
            safe_key = bounded_text(key, MAX_STRING_CHARS)
            output[safe_key] = (
                "[REDACTED]"
                if is_sensitive_key(key)
                else summarize_value(item, depth + 1)
            )
        if truncated:
            output["[truncated]"] = f"{len(value) - len(items)} keys omitted"
        return output

    if isinstance(value, (list, tuple)):
        items = list(value)
        truncated = len(items) > MAX_LIST_ITEMS
        if truncated:
            items = items[: MAX_LIST_ITEMS - 1]
        output = [summarize_value(item, depth + 1) for item in items]
        if truncated:
            output.append(f"[truncated:{len(value) - len(items)} items omitted]")
        return output

    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    if isinstance(value, str):
        return bounded_redacted(value, MAX_STRING_CHARS)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return bounded_redacted(value, MAX_STRING_CHARS)


def compact_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        default=str,
    )


def bounded_summary(value: Any) -> Any:
    summary = summarize_value(value)
    serialized = compact_json(summary)
    if len(serialized) <= MAX_SUMMARY_CHARS:
        return summary

    preview_budget = MAX_SUMMARY_CHARS - 100
    marker = {
        "[truncated]": "serialized_summary_limit",
        "preview": bounded_text(serialized, preview_budget),
    }
    while len(compact_json(marker)) > MAX_SUMMARY_CHARS and preview_budget > 0:
        preview_budget = max(0, preview_budget - 100)
        marker["preview"] = bounded_text(serialized, preview_budget)
    return marker


def canonical_digest(value: Any) -> str:
    serialized = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def bound_optional(value: Any, limit: int = MAX_STRING_CHARS) -> str | None:
    if value is None:
        return None
    return bounded_redacted(value, limit)


def observed_event_keys(event: dict[str, Any]) -> list[str]:
    keys = sorted(
        (bounded_text(key, 200) for key in event),
        key=lambda item: (item.casefold(), item),
    )
    if len(keys) <= MAX_EVENT_KEYS:
        return keys
    return [*keys[: MAX_EVENT_KEYS - 1], "[truncated:event_keys]"]


def parse_mcp_tool_name(tool_name: Any) -> tuple[str | None, str | None]:
    if not isinstance(tool_name, str) or not tool_name.startswith("mcp__"):
        return None, None

    remainder = tool_name[len("mcp__") :]
    server, separator, tool = remainder.partition("__")
    if not separator or not server or not tool:
        return None, None

    return (
        bounded_redacted(server, MAX_TOOL_NAME_CHARS),
        bounded_redacted(tool, MAX_TOOL_NAME_CHARS),
    )


def classify_tool_family(mcp_server: str | None) -> str:
    if not mcp_server:
        return "other"
    normalized = mcp_server.casefold()
    if normalized.startswith("aicarmine_"):
        normalized = normalized[len("aicarmine_") :]
    return FAMILY_MAP.get(normalized, "other")


def classify_effect(
    mcp_server: str | None,
    mcp_tool: str | None,
    tool_family: str,
) -> str:
    server = (mcp_server or "").casefold()
    tool = (mcp_tool or "").casefold()
    combined = f"{server} {tool}"

    if "repo_code_apply_patch" in tool or (
        tool_family == "code_change" and tool.endswith("apply_patch")
    ):
        return "SOURCE_WRITE"

    if any(
        marker in combined
        for marker in (
            "project_memory_upsert_verified",
            "project_memory_mark_stale",
            "project_memory_supersede",
            "rag_reindex",
        )
    ):
        return "STATE_WRITE"

    if any(
        marker in combined
        for marker in (
            "agentic_loop_run",
            "ensure_broker",
            "ensure_reranker",
        )
    ):
        return "SERVICE_MUTATION"

    if any(
        marker in combined
        for marker in (
            "repo_code_propose_edit",
            "repo_code_unidiff_validate",
            "repo_code_git_apply_check",
        )
    ):
        return "PROPOSAL_ONLY"

    tokens = {token for token in re.split(r"[^a-z0-9]+", tool) if token}
    if tokens.intersection({"health", "status", "capabilities"}):
        return "PURE_READ"

    if tool_family == "validation" or any(
        marker in combined
        for marker in (
            "probe_run",
            "semgrep",
            "ruff",
            "pyright",
            "pytest",
            "diffcheck",
            "shellcheck",
        )
    ):
        return "COMMAND_VALIDATION"

    if "smoke" in combined and "run" in tokens:
        return "COMMAND_VALIDATION"

    if tool_family in {
        "repository_state",
        "deterministic_search",
        "git_readonly",
        "database_readonly",
        "raw_job_evidence",
        "rendered_job_view",
    }:
        return "PURE_READ"

    if tool_family == "semantic_search" and (
        "context" in tokens or {"index", "status"}.issubset(tokens)
    ):
        return "PURE_READ"

    if tokens.intersection(
        {
            "search",
            "read",
            "list",
            "get",
            "show",
            "diff",
            "blame",
            "query",
        }
    ):
        return "PURE_READ"

    return "UNKNOWN"


def signal_containers(event: dict[str, Any]) -> list[dict[str, Any]]:
    containers = [event]
    for field in RESULT_FIELDS:
        value = event.get(field)
        if isinstance(value, dict):
            containers.append(value)
    return containers


def nonempty_error(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return value not in (None, "", 0, [], {})


def looks_like_failure_text(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    lowered = value.casefold()
    return any(
        marker in lowered
        for marker in (
            "edit_kind_invalid",
            "invalid_argument",
            "invalid argument",
            "missing required property",
            "permission denied",
            "approval denied",
            "timed out",
            "timeout",
            "server unavailable",
            "connection refused",
            "connection closed",
            "non_retryable",
            "failed:",
            "error:",
        )
    )


def result_source(event: dict[str, Any]) -> tuple[bool, Any]:
    for field in RESULT_FIELDS:
        if field in event:
            return True, event[field]

    signals = {
        field: event[field]
        for field in SIGNAL_FIELDS
        if field in event
    }
    return (False, signals if signals else None)


def error_details(
    containers: list[dict[str, Any]],
    source: Any,
) -> str | None:
    details: list[str] = []
    for container in containers:
        for field in ("error_type", "error", "message"):
            if field in container and nonempty_error(container[field]):
                details.append(f"{field}={container[field]}")
    if not details and looks_like_failure_text(source):
        details.append(str(source))
    if not details:
        return None
    return bounded_redacted("; ".join(details), MAX_ERROR_CHARS)


def classify_error(error_summary: str | None) -> tuple[str, bool | None]:
    lowered = (error_summary or "").casefold()

    if any(
        marker in lowered
        for marker in (
            "edit_kind_invalid",
            "invalid_argument",
            "invalid argument",
            "missing required property",
            "missing required",
        )
    ):
        return "argument_contract_error", False
    if "approval denied" in lowered or "approval_denied" in lowered:
        return "approval_denied", False
    if "permission denied" in lowered or "permission_denied" in lowered:
        return "permission_denied", False
    if "timeout" in lowered or "timed out" in lowered:
        return "timeout", None
    if any(
        marker in lowered
        for marker in (
            "server unavailable",
            "connection refused",
            "connection closed",
            "server_unavailable",
        )
    ):
        return "server_unavailable", None
    if any(
        marker in lowered
        for marker in (
            "non_retryable",
            "non-retryable",
            "do not retry",
        )
    ):
        return "non_retryable_failure", False
    if any(
        marker in lowered
        for marker in (
            "temporarily unavailable",
            "rate limit",
            "rate_limit",
            "try again",
            "busy",
            "429",
            "503",
        )
    ):
        return "transient_failure", None
    return "unknown_failure", None


def classify_post_result(
    event: dict[str, Any],
) -> tuple[str, str | None, bool | None, str | None, Any]:
    containers = signal_containers(event)
    has_result, source = result_source(event)

    explicit_failure = False
    explicit_success = False
    for container in containers:
        if container.get("is_error") is True:
            explicit_failure = True
        if container.get("success") is False or container.get("ok") is False:
            explicit_failure = True
        if nonempty_error(container.get("error")):
            explicit_failure = True
        if nonempty_error(container.get("error_type")):
            explicit_failure = True

        if container.get("success") is True or container.get("ok") is True:
            explicit_success = True
        if container.get("is_error") is False:
            explicit_success = True

    if looks_like_failure_text(source):
        explicit_failure = True

    if explicit_failure:
        summary = error_details(containers, source) or "explicit failure signal"
        error_class, retry_unchanged = classify_error(summary)
        return "failed", error_class, retry_unchanged, summary, source

    if explicit_success or (has_result and source is not None):
        return "succeeded", None, None, None, source

    return "unknown_result", None, None, None, source


def build_record(
    phase: str,
    event: dict[str, Any],
    parse_diagnostic: str | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    timestamp = time.time() if now is None else float(now)
    tool_name = bound_optional(event.get("tool_name"), MAX_TOOL_NAME_CHARS)
    mcp_server, mcp_tool = parse_mcp_tool_name(tool_name)
    tool_family = classify_tool_family(mcp_server)
    effect_class = classify_effect(mcp_server, mcp_tool, tool_family)

    has_input = "tool_input" in event
    input_value = event.get("tool_input") if has_input else None
    input_digest = canonical_digest(input_value) if has_input else None
    input_summary = bounded_summary(input_value) if has_input else None

    status = "attempted" if phase == "pre" else "unknown_result"
    error_class: str | None = None
    retry_unchanged: bool | None = None
    error_summary = (
        bounded_redacted(parse_diagnostic, MAX_ERROR_CHARS)
        if parse_diagnostic
        else None
    )
    result_summary: Any = None

    if phase == "post":
        (
            status,
            error_class,
            retry_unchanged,
            classified_error,
            result_value,
        ) = classify_post_result(event)
        if classified_error:
            error_summary = classified_error
        if result_value is not None:
            result_summary = bounded_summary(result_value)

    return {
        "schema": SCHEMA,
        "time_epoch": timestamp,
        "phase": phase,
        "hook_event_name": bound_optional(event.get("hook_event_name"), 200),
        "session_id": bound_optional(event.get("session_id"), 300),
        "turn_id": bound_optional(event.get("turn_id"), 300),
        "model": bound_optional(event.get("model"), 300),
        "tool_name": tool_name,
        "tool_use_id": bound_optional(event.get("tool_use_id"), 300),
        "mcp_server": mcp_server,
        "mcp_tool": mcp_tool,
        "tool_family": tool_family,
        "effect_class": effect_class,
        "input_digest": input_digest,
        "input_summary": input_summary,
        "result_summary": result_summary,
        "status": status,
        "error_class": error_class,
        "error_summary": error_summary,
        "retry_unchanged": retry_unchanged,
        "elapsed_ms": None,
        "event_keys": observed_event_keys(event),
    }


def record_line(record: dict[str, Any]) -> str:
    safe_record = redact_recursive(record)

    def serialize() -> str:
        return json.dumps(
            safe_record,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
            default=str,
        )

    line = serialize()
    if len((line + "\n").encode("utf-8")) <= MAX_RECORD_BYTES:
        return line

    event_keys = safe_record.get("event_keys")
    if isinstance(event_keys, list) and len(event_keys) > 20:
        safe_record["event_keys"] = [
            *event_keys[:19],
            "[truncated:record_limit]",
        ]
        line = serialize()

    for field in ("result_summary", "input_summary"):
        if len((line + "\n").encode("utf-8")) <= MAX_RECORD_BYTES:
            break
        if safe_record.get(field) is not None:
            safe_record[field] = {"[truncated]": "record_limit"}
            line = serialize()

    if len((line + "\n").encode("utf-8")) > MAX_RECORD_BYTES:
        safe_record["error_summary"] = bounded_redacted(
            safe_record.get("error_summary"),
            200,
        )
        line = serialize()

    if len((line + "\n").encode("utf-8")) > MAX_RECORD_BYTES:
        for field in (
            "hook_event_name",
            "session_id",
            "turn_id",
            "model",
            "tool_name",
            "tool_use_id",
            "mcp_server",
            "mcp_tool",
        ):
            safe_record[field] = bound_optional(safe_record.get(field), 100)
        safe_record["event_keys"] = ["[truncated:record_limit]"]
        line = serialize()

    if len((line + "\n").encode("utf-8")) > MAX_RECORD_BYTES:
        raise ValueError("bounded record exceeds 20 KiB")
    return line


def pending_key(record: dict[str, Any]) -> str | None:
    session_id = record.get("session_id")
    tool_use_id = record.get("tool_use_id")
    if session_id and tool_use_id:
        return "session_tool:" + canonical_digest([session_id, tool_use_id])

    turn_id = record.get("turn_id")
    tool_name = record.get("tool_name")
    input_digest = record.get("input_digest")
    if turn_id and tool_name and input_digest:
        return "turn_tool_input:" + canonical_digest(
            [turn_id, tool_name, input_digest]
        )
    return None


def prune_pending(
    records: dict[str, dict[str, Any]],
    now: float,
) -> dict[str, dict[str, Any]]:
    cutoff = now - PENDING_MAX_AGE_SECONDS
    valid: list[tuple[str, dict[str, Any]]] = []
    for key, value in records.items():
        if not isinstance(value, dict):
            continue
        timestamp = value.get("time_epoch")
        if not isinstance(timestamp, (int, float)) or timestamp < cutoff:
            continue
        valid.append((str(key), value))

    valid.sort(
        key=lambda item: (
            float(item[1].get("time_epoch") or 0),
            item[0],
        ),
        reverse=True,
    )
    return dict(valid[:MAX_PENDING_RECORDS])


def load_pending(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema") != PENDING_SCHEMA:
        raise ValueError("incompatible pending schema")
    records = payload.get("records")
    if not isinstance(records, dict):
        raise ValueError("invalid pending records")
    return {
        str(key): value
        for key, value in records.items()
        if isinstance(value, dict)
    }


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    safe_payload = redact_recursive(payload)
    serialized = json.dumps(
        safe_payload,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
        default=str,
    ) + "\n"
    temporary = path.with_name(
        f".{path.name}.{os.getpid()}.{time.time_ns()}.tmp"
    )
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(serialized)
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
def best_effort_lock(
    lock_path: Path,
    timeout_seconds: float = LOCK_TIMEOUT_SECONDS,
) -> Iterator[bool]:
    timeout = max(0.0, min(float(timeout_seconds), LOCK_TIMEOUT_SECONDS))
    deadline = time.monotonic() + timeout
    token = f"{os.getpid()}-{time.time_ns()}"
    acquired = False

    while True:
        try:
            descriptor = os.open(
                lock_path,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            )
            with os.fdopen(
                descriptor,
                "w",
                encoding="utf-8",
                newline="\n",
            ) as handle:
                handle.write(token)
                handle.flush()
            acquired = True
            break
        except FileExistsError:
            try:
                age = time.time() - lock_path.stat().st_mtime
                if age > STALE_LOCK_SECONDS:
                    lock_path.unlink()
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
                if lock_path.read_text(encoding="utf-8") == token:
                    lock_path.unlink()
            except OSError:
                pass


def rotate_jsonl(path: Path, threshold_bytes: int = LOG_ROTATION_BYTES) -> None:
    if not path.exists() or path.stat().st_size <= threshold_bytes:
        return
    backup = path.with_name(path.name + ".1")
    if backup.exists():
        backup.unlink()
    os.replace(path, backup)


def append_record(path: Path, record: dict[str, Any]) -> None:
    line = record_line(record)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(line + "\n")
        handle.flush()


def persist_record(
    record: dict[str, Any],
    paths: StoragePaths = DEFAULT_PATHS,
    now: float | None = None,
    rotation_bytes: int = LOG_ROTATION_BYTES,
) -> tuple[dict[str, Any], str | None]:
    timestamp = time.time() if now is None else float(now)
    diagnostics: list[str] = []

    try:
        paths.state_dir.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        return record, bounded_redacted(
            f"state directory {type(exc).__name__}: {exc}",
            MAX_ERROR_CHARS,
        )

    with best_effort_lock(paths.lock) as acquired:
        if not acquired:
            return record, "logger lock unavailable after at most 2 seconds"

        try:
            pending_records = load_pending(paths.pending)
        except Exception as exc:
            pending_records = {}
            diagnostics.append(
                f"pending read {type(exc).__name__}: "
                f"{bounded_redacted(str(exc), MAX_ERROR_CHARS)}"
            )

        pending_records = prune_pending(pending_records, timestamp)
        key = pending_key(record)

        if record.get("phase") == "pre" and key:
            pending_records[key] = {
                "time_epoch": timestamp,
                "tool_name": bound_optional(
                    record.get("tool_name"),
                    MAX_TOOL_NAME_CHARS,
                ),
                "input_digest": record.get("input_digest"),
            }
            pending_records = prune_pending(pending_records, timestamp)
        elif record.get("phase") == "post" and key:
            pending = pending_records.pop(key, None)
            if isinstance(pending, dict) and isinstance(
                pending.get("time_epoch"),
                (int, float),
            ):
                elapsed = max(
                    0.0,
                    (timestamp - float(pending["time_epoch"])) * 1_000,
                )
                record["elapsed_ms"] = int(round(elapsed))

        try:
            atomic_write_json(
                paths.pending,
                {
                    "schema": PENDING_SCHEMA,
                    "records": pending_records,
                },
            )
        except Exception as exc:
            diagnostics.append(
                f"pending write {type(exc).__name__}: "
                f"{bounded_redacted(str(exc), MAX_ERROR_CHARS)}"
            )

        try:
            rotate_jsonl(paths.log, rotation_bytes)
        except Exception as exc:
            diagnostics.append(
                f"log rotation {type(exc).__name__}: "
                f"{bounded_redacted(str(exc), MAX_ERROR_CHARS)}"
            )

        try:
            append_record(paths.log, record)
        except Exception as exc:
            diagnostics.append(
                f"log append {type(exc).__name__}: "
                f"{bounded_redacted(str(exc), MAX_ERROR_CHARS)}"
            )

    diagnostic = (
        bounded_redacted("; ".join(diagnostics), MAX_ERROR_CHARS)
        if diagnostics
        else None
    )
    return record, diagnostic


def read_stdin_event() -> tuple[dict[str, Any], str | None]:
    try:
        stream = getattr(sys.stdin, "buffer", sys.stdin)
        raw = stream.read(MAX_STDIN_BYTES + 1)
        if isinstance(raw, str):
            raw_bytes = raw.encode("utf-8", errors="replace")
        else:
            raw_bytes = raw

        if len(raw_bytes) > MAX_STDIN_BYTES:
            return {}, "stdin_event_too_large"

        text = raw_bytes.decode("utf-8", errors="strict")
        value = json.loads(text or "{}")
        if not isinstance(value, dict):
            return {}, "stdin_event_root_not_object"
        return value, None
    except Exception as exc:
        return {}, bounded_redacted(
            f"{type(exc).__name__}: {exc}",
            MAX_ERROR_CHARS,
        )


def failure_context(record: dict[str, Any]) -> str:
    retry = record.get("retry_unchanged")
    retry_text = "null" if retry is None else str(bool(retry)).lower()
    lines = [
        "MCP tool failed:",
        f"tool={bounded_redacted(record.get('tool_name') or 'unknown', MAX_TOOL_NAME_CHARS)}",
        f"class={bounded_redacted(record.get('error_class') or 'unknown_failure', 100)}",
        f"retry_unchanged={retry_text}",
    ]
    if retry is False:
        lines.extend(
            [
                "",
                "Do not repeat the same tool call with unchanged arguments.",
            ]
        )
    return "\n".join(lines)


def additional_context(
    record: dict[str, Any],
    persistence_diagnostic: str | None,
) -> str:
    phase = record.get("phase")
    status = record.get("status")

    if phase == "pre":
        context = (
            "MCP attempt recorded: "
            f"{bounded_redacted(record.get('tool_name') or 'unknown', MAX_TOOL_NAME_CHARS)}"
        )
    elif phase == "post" and status == "failed":
        context = failure_context(record)
    else:
        context = ""

    if persistence_diagnostic:
        diagnostic = (
            "MCP logger persistence diagnostic: "
            f"{bounded_redacted(persistence_diagnostic, MAX_ERROR_CHARS)}"
        )
        context = f"{context}\n{diagnostic}".strip()

    return bounded_redacted(context, MAX_ADDITIONAL_CONTEXT_CHARS)


def emit_hook_output(
    hook_event_name: str,
    context: str,
) -> None:
    output = {
        "hookSpecificOutput": {
            "hookEventName": bounded_redacted(hook_event_name, 200),
            "additionalContext": bounded_redacted(
                context,
                MAX_ADDITIONAL_CONTEXT_CHARS,
            ),
        }
    }
    print(json.dumps(output, ensure_ascii=False))


def self_test_check(condition: bool, message: str, state: dict[str, int]) -> None:
    state["tests"] += 1
    if not condition:
        raise AssertionError(message)


def run_self_test() -> int:
    state = {"tests": 0}
    result = {
        "ok": False,
        "tests": 0,
        "network_calls": False,
        "mcp_calls": False,
        "real_state_writes": False,
    }

    try:
        server, tool = parse_mcp_tool_name(
            "mcp__aicarmine_repo_state__aicarmine_repo_state_status"
        )
        self_test_check(
            server == "aicarmine_repo_state"
            and tool == "aicarmine_repo_state_status",
            "tool name parsing",
            state,
        )

        family = classify_tool_family(server)
        effect = classify_effect(server, tool, family)
        self_test_check(
            family == "repository_state" and effect == "PURE_READ",
            "family/effect classification",
            state,
        )

        secret_source = {
            "Authorization": "Bearer top-secret",
            "nested": {"Api_Key": "abc", "value": "token=xyz"},
        }
        secret_copy = json.loads(json.dumps(secret_source))
        redacted = summarize_value(secret_source)
        self_test_check(
            redacted["Authorization"] == "[REDACTED]"
            and redacted["nested"]["Api_Key"] == "[REDACTED]"
            and "xyz" not in compact_json(redacted)
            and secret_source == secret_copy,
            "recursive redaction",
            state,
        )

        pre_event = {
            "hook_event_name": "PreToolUse",
            "session_id": "session-1",
            "turn_id": "turn-1",
            "model": "synthetic",
            "tool_name": (
                "mcp__aicarmine_repo_code__"
                "aicarmine_repo_code_propose_edit"
            ),
            "tool_use_id": "tool-use-1",
            "tool_input": {
                "path": "owner.py",
                "token": "not-persisted",
            },
        }
        pre_record = build_record("pre", pre_event, now=1_000.0)
        line = record_line(pre_record)
        self_test_check(
            "tool_input" not in pre_record and "not-persisted" not in line,
            "tool input not persisted",
            state,
        )
        self_test_check(
            "raw_event" not in pre_record and "raw_event" not in line,
            "raw event not persisted",
            state,
        )
        self_test_check(
            canonical_digest(pre_event["tool_input"])
            == canonical_digest(
                {
                    "token": "not-persisted",
                    "path": "owner.py",
                }
            ),
            "stable digest",
            state,
        )

        large_value = {
            **{f"k{index:02d}": index for index in range(50)},
            "items": list(range(25)),
            "text": "x" * 2_000,
        }
        bounded = summarize_value(large_value)
        bounded_list = summarize_value(list(range(25)))
        bounded_string = summarize_value("x" * 2_000)
        self_test_check(
            len(bounded) <= MAX_DICT_KEYS
            and len(bounded_list) <= MAX_LIST_ITEMS
            and len(bounded_string) <= MAX_STRING_CHARS
            and len(compact_json(bounded_summary(large_value)))
            <= MAX_SUMMARY_CHARS,
            "summary bounds",
            state,
        )

        with tempfile.TemporaryDirectory() as directory:
            paths = StoragePaths.from_state_dir(Path(directory))
            persisted_pre, pre_diagnostic = persist_record(
                pre_record,
                paths=paths,
                now=1_000.0,
            )
            post_event = {
                "hook_event_name": "PostToolUse",
                "session_id": "session-1",
                "turn_id": "turn-1",
                "model": "synthetic",
                "tool_name": pre_event["tool_name"],
                "tool_use_id": "tool-use-1",
                "tool_input": pre_event["tool_input"],
                "tool_result": {"ok": True, "result": {"applied": False}},
            }
            post_record = build_record("post", post_event, now=1_000.125)
            persisted_post, post_diagnostic = persist_record(
                post_record,
                paths=paths,
                now=1_000.125,
            )
            pending_after = load_pending(paths.pending)

            self_test_check(
                pre_diagnostic is None
                and post_diagnostic is None
                and pending_key(persisted_pre) not in pending_after,
                "pre/post correlation",
                state,
            )
            self_test_check(
                persisted_post.get("elapsed_ms") == 125,
                "elapsed milliseconds",
                state,
            )

            failed_status = classify_post_result(
                {"tool_result": {"error": "edit_kind_invalid"}}
            )
            self_test_check(
                failed_status[1] == "argument_contract_error",
                "argument contract error classification",
                state,
            )
            self_test_check(
                failed_status[2] is False,
                "non-retryable unchanged classification",
                state,
            )

            succeeded_status = classify_post_result(
                {"tool_result": {"ok": True, "result": {"value": 1}}}
            )
            self_test_check(
                succeeded_status[0] == "succeeded",
                "explicit success classification",
                state,
            )

            ambiguous_status = classify_post_result(
                {"message": "result not supplied"}
            )
            self_test_check(
                ambiguous_status[0] == "unknown_result",
                "ambiguous result classification",
                state,
            )

            paths.log.write_text("x" * 256, encoding="utf-8")
            rotate_jsonl(paths.log, threshold_bytes=128)
            self_test_check(
                not paths.log.exists()
                and paths.log.with_name(paths.log.name + ".1").exists(),
                "JSONL rotation",
                state,
            )

            pruned = prune_pending(
                {
                    "old": {"time_epoch": 1.0},
                    "fresh": {"time_epoch": 10_000.0},
                },
                now=10_000.0,
            )
            self_test_check(
                "old" not in pruned and "fresh" in pruned,
                "pending cleanup",
                state,
            )

        result["ok"] = True
        result["tests"] = state["tests"]
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as exc:
        result["tests"] = state["tests"]
        result["error"] = bounded_redacted(
            f"{type(exc).__name__}: {exc}",
            MAX_ERROR_CHARS,
        )
        print(json.dumps(result, ensure_ascii=False))
        return 1


def main() -> int:
    if "--self-test" in sys.argv[1:]:
        return run_self_test()

    phase = sys.argv[1] if len(sys.argv) > 1 else "unknown"
    if phase not in {"pre", "post"}:
        emit_hook_output(
            "PreToolUse",
            "MCP logger invocation ignored: expected phase pre or post.",
        )
        return 0

    try:
        event, parse_diagnostic = read_stdin_event()
        record = build_record(
            phase,
            event,
            parse_diagnostic=parse_diagnostic,
        )
        record, persistence_diagnostic = persist_record(record)

        if parse_diagnostic:
            print(
                bounded_redacted(
                    f"MCP logger parse diagnostic: {parse_diagnostic}",
                    MAX_ERROR_CHARS,
                ),
                file=sys.stderr,
            )
        if persistence_diagnostic:
            print(
                bounded_redacted(
                    f"MCP logger persistence diagnostic: {persistence_diagnostic}",
                    MAX_ERROR_CHARS,
                ),
                file=sys.stderr,
            )

        hook_event = str(
            event.get("hook_event_name")
            or ("PreToolUse" if phase == "pre" else "PostToolUse")
        )
        emit_hook_output(
            hook_event,
            additional_context(record, persistence_diagnostic),
        )
        return 0
    except Exception as exc:
        diagnostic = bounded_redacted(
            f"{type(exc).__name__}: {exc}",
            MAX_ERROR_CHARS,
        )
        print(
            f"MCP logger fail-open diagnostic: {diagnostic}",
            file=sys.stderr,
        )
        emit_hook_output(
            "PreToolUse" if phase == "pre" else "PostToolUse",
            f"MCP logger fail-open diagnostic: {diagnostic}",
        )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
