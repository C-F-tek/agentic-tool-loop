"""Planner JSON/HTTP I/O helpers.

Contains Ollama JSON calls, streaming planner capture and strict planner JSON
parsing. The functions here do not dispatch tools or mutate source files.
"""
from __future__ import annotations

import json
import queue
import re
import socket
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from ..job_store import append_agent_event


# ---------------------------------------------------------------------------
# HTTP helpers (Ollama)
# ---------------------------------------------------------------------------


def post_json(url: str, payload: dict[str, Any], timeout: int = 120) -> dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except (socket.timeout, TimeoutError) as exc:
        return {
            "ok": False,
            "backend_timeout": True,
            "backend_unreachable": False,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "timeout_seconds": int(timeout or 0),
        }
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", None)
        reason_text = str(reason or exc)
        is_timeout = isinstance(reason, (socket.timeout, TimeoutError)) or "timed out" in reason_text.lower()
        return {
            "ok": False,
            "backend_timeout": is_timeout,
            "backend_unreachable": not is_timeout,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "network_reason_type": type(reason).__name__ if reason is not None else None,
            "timeout_seconds": int(timeout or 0),
        }
    except OSError as exc:
        is_timeout = "timed out" in str(exc).lower()
        return {
            "ok": False,
            "backend_timeout": is_timeout,
            "backend_unreachable": not is_timeout,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "timeout_seconds": int(timeout or 0),
        }
    try:
        decoded = json.loads(raw)
        return decoded if isinstance(decoded, dict) else {"ok": True, "data": decoded}
    except Exception as exc:
        return {"ok": False, "error_type": type(exc).__name__,
                "error": str(exc), "raw": raw[:4000]}


# ---------------------------------------------------------------------------
# Degenerate stream detection
# ---------------------------------------------------------------------------


def _planner_stream_block_response(
    reason: str, content: str, stream_path: Path
) -> dict[str, Any]:
    return {
        "ok": False,
        "planner_degenerate_output": True,
        "backend_timeout": False,
        "backend_unreachable": False,
        "error_type": "PlannerStreamDegenerateOutput",
        "error": reason,
        "partial_content": str(content or "")[-12000:],
        "stream_path": str(stream_path),
    }


def _planner_stream_repetition_reason(
    text: str,
    *,
    allow_plain_text_without_json: bool = False,
) -> str:
    raw = str(text or "")
    poisoned_tokens = (
        "<|endoftext|>", "<|im_start|>", "<|im_end|>",
    )
    for marker in poisoned_tokens:
        if marker in raw:
            return f"role_boundary_marker:{marker}"
    role_boundary = re.search(
        r"(?m)^\s*(Human|Assistant|System):(?=\s|$)",
        raw,
    )
    if role_boundary:
        return f"role_boundary_marker:{role_boundary.group(1)}:"

    if re.search(r"</?JupyterNotebookCell\b", raw, re.I):
        return "unsupported_native_notebook_cell_output"

    stripped = raw.strip().strip("` \r\n\t").lower()
    if stripped in {"halted", "temps", "stopped", "stop", "done"}:
        return f"dead_stop_token:{stripped}"

    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    if len(lines) >= 3 and lines[-1] == lines[-2] == lines[-3]:
        return f"repeated_line:{lines[-1][:120]}"

    max_block = min(8, len(lines) // 3)
    for bs in range(2, max_block + 1):
        if lines[-bs:] == lines[-2 * bs : -bs] == lines[-3 * bs : -2 * bs]:
            return f"repeated_block_{bs}_lines:{' | '.join(lines[-bs:])[:240]}"

    low = raw.lower()
    repeated_path_reason = _planner_stream_repeated_path_segment_reason(raw)
    if repeated_path_reason:
        return repeated_path_reason

    fenced_json_count = len(re.findall(r"```(?:json|JSON)?\s*\r?\n\s*[\[{]", raw))
    example_marker_count = sum(
        low.count(marker)
        for marker in (
            "出力の例",
            "output example",
            "example ",
            "esempio",
            "ejemplo",
            "例",
        )
    )
    if fenced_json_count >= 4 and example_marker_count >= 2:
        return (
            "repeated_fenced_json_examples_no_pure_decision:"
            f"fenced_json_count={fenced_json_count};example_marker_count={example_marker_count}"
        )
    if fenced_json_count >= 6:
        return f"long_mixed_json_examples_no_pure_decision:fenced_json_count={fenced_json_count}"
    if len(raw) >= 4096 and fenced_json_count >= 3:
        repeated_tool_mentions = sum(
            low.count(f'"tool": "{tool.lower()}"') + low.count(f'"tool":"{tool.lower()}"')
            for tool in ("repo_read", "repo_search", "repo_tree", "repo_list_files")
        )
        if repeated_tool_mentions >= 3:
            return (
                "repeated_embedded_json_tool_examples_no_pure_decision:"
                f"fenced_json_count={fenced_json_count};tool_mentions={repeated_tool_mentions}"
            )

    # v3: catch single-line runaway prose loops. The observed qwen3-coder
    # failure streamed the same German sentence thousands of times without ever
    # producing a JSON object, so the old line-based detector never fired and
    # every OpenWebUI call waited for the full planner timeout.
    repeated_markers = (
        "der patch ist nicht anwendbar",
        "the patch is not applicable",
        "la patch non è applicabile",
        "la patch non e' applicabile",
        "il patch non è applicabile",
        "the file already has the desired form",
        "die datei bereits die gewünschte form hat",
    )
    for marker in repeated_markers:
        if low.count(marker) >= 3:
            return f"repeated_phrase:{marker[:80]}"

    # Generic repeated-fragment guard for long one-line loops.  This is only
    # evaluated after the stream is already long and has no JSON opening brace,
    # so it does not interfere with normal early JSON detection.
    if "{" not in raw and len(raw) >= 4096:
        compact_tail = re.sub(r"\s+", " ", low[-6000:]).strip()
        for width in (48, 72, 96, 128):
            seen: dict[str, int] = {}
            step = max(12, width // 4)
            for pos in range(0, max(0, len(compact_tail) - width), step):
                frag = compact_tail[pos : pos + width].strip()
                if len(frag) < width // 2:
                    continue
                seen[frag] = seen.get(frag, 0) + 1
                if seen[frag] >= 4:
                    return f"repeated_fragment_no_json:{frag[:120]}"

    if not allow_plain_text_without_json and "{" not in raw and len(raw) > 600:
        if any(m in low for m in ("from ", "import ", "def ", "class ", "#!/usr/bin")):
            return "non_json_code_like_stream_without_object"

    # v3: planner decisions are required to be JSON. If a stream grows beyond
    # a reasonable limit without even an opening brace, abort it early and let
    # the controller feed a validator/repair guard back to the planner instead
    # of burning the whole 120s timeout.
    if not allow_plain_text_without_json and "{" not in raw and len(raw) >= 8192:
        return "long_non_json_stream_without_object"

    return ""


def _planner_stream_repeated_path_segment_reason(text: str) -> str:
    """Detect runaway path construction inside otherwise JSON-shaped streams.

    The planner can fail by repeatedly appending the same path component inside
    a JSON argument, for example ``Tools/Tools/Tools/...``. That stream contains
    ``{``, so the no-JSON repetition guard intentionally does not apply. This
    guard is scoped to path-like strings and only fires after a high consecutive
    repeat count.
    """
    raw = str(text or "")
    if len(raw) < 1024 or ("/" not in raw and "\\" not in raw):
        return ""
    tail = raw[-12000:].replace("\\", "/")
    path_values: list[str] = []
    for match in re.finditer(
        r"""["'](?:path|paths|directory|cwd)["']\s*:\s*["'](?P<value>[^"']{120,})""",
        tail,
        re.I,
    ):
        path_values.append(match.group("value"))
    for match in re.finditer(r"(?:[A-Za-z0-9_.-]+/){16,}[A-Za-z0-9_.-]*", tail):
        path_values.append(match.group(0))

    for value in path_values:
        parts = [part for part in value.split("/") if part and part not in {".", ".."}]
        last = ""
        count = 0
        for part in parts:
            if part == last:
                count += 1
            else:
                last = part
                count = 1
            if count >= 16 and len(part) >= 2:
                return f"repeated_repo_path_segment_in_json:segment={part[:40]};count={count}"
    return ""


# ---------------------------------------------------------------------------
# Streaming Ollama call with degeneration guard
# ---------------------------------------------------------------------------


def post_json_stream_to_file(
    url: str,
    payload: dict[str, Any],
    timeout: int,
    *,
    job_id: str,
    step: int,
    stream_path: Path,
    allow_plain_text_without_json: bool = False,
) -> dict[str, Any]:
    started = time.time()
    stream_timeout_seconds = max(1, int(timeout or 1))
    chunks: list[str] = []
    guard_chunks: list[str] = []
    native_tool_calls: list[dict[str, Any]] = []
    stream_payload = {**payload, "stream": True}
    json_detected_event_sent = False
    terminal_item: dict[str, Any] = {}

    data = json.dumps(stream_payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    stream_path.parent.mkdir(parents=True, exist_ok=True)
    stream_path.write_text("", encoding="utf-8")

    raw_path = stream_path.with_suffix(".raw.ndjson")
    thinking_path = stream_path.with_suffix(".thinking.txt")
    content_path = stream_path.with_suffix(".content.txt")
    all_path = stream_path.with_suffix(".all.txt")

    last_progress_at = last_waiting_at = 0.0
    deadline = started + stream_timeout_seconds

    append_agent_event(job_id, "planner_stream_started",
                       f"Planner stream started step={step}.",
                       {
                           "planner_url": url,
                           "timeout_seconds": stream_timeout_seconds,
                           "planner_step_timeout_requested_seconds": int(timeout or 0),
                           "allow_plain_text_without_json": allow_plain_text_without_json,
                       }, step=step)

    response_queue: queue.Queue[tuple[str, Any]] = queue.Queue(maxsize=1)
    response_abandoned = threading.Event()

    def open_response() -> None:
        try:
            response = urllib.request.urlopen(req, timeout=timeout)
            if response_abandoned.is_set():
                try:
                    response.close()
                except Exception:
                    pass
                return
            response_queue.put(("response", response), block=False)
        except Exception as exc:  # pragma: no cover - transported to caller thread
            if response_abandoned.is_set():
                return
            response_queue.put(("exception", exc), block=False)

    opener = threading.Thread(
        target=open_response,
        name=f"aicarmine-planner-stream-open-{job_id}-step-{step}",
        daemon=True,
    )
    opener.start()
    response_kind = ""
    response_value: Any = None
    while True:
        remaining = deadline - time.time()
        if remaining <= 0:
            response_abandoned.set()
            append_agent_event(
                job_id,
                "planner_stream_header_timeout",
                f"Planner stream did not return HTTP headers within {stream_timeout_seconds}s.",
                {
                    "elapsed_seconds": round(time.time() - started, 3),
                    "timeout_seconds": stream_timeout_seconds,
                    "planner_step_timeout_requested_seconds": int(timeout or 0),
                    "stream_path": str(stream_path),
                    "phase": "awaiting_response_headers",
                },
                step=step,
            )
            return {
                "ok": False,
                "backend_timeout": True,
                "backend_unreachable": False,
                "error_type": "PlannerStreamHeaderTimeout",
                "error": f"planner stream did not return HTTP headers within {stream_timeout_seconds}s",
                "partial_content": "",
                "stream_path": str(stream_path),
                "elapsed_seconds": round(time.time() - started, 3),
                "timeout_phase": "awaiting_response_headers",
                "timeout_seconds": stream_timeout_seconds,
            }
        try:
            response_kind, response_value = response_queue.get(timeout=min(5.0, max(0.1, remaining)))
            break
        except queue.Empty:
            now_ts = time.time()
            if now_ts - last_waiting_at >= 5:
                last_waiting_at = now_ts
                append_agent_event(
                    job_id,
                    "planner_stream_waiting",
                    "Waiting for planner HTTP headers.",
                    {
                        "elapsed_seconds": round(now_ts - started, 3),
                        "timeout_seconds": stream_timeout_seconds,
                        "planner_step_timeout_requested_seconds": int(timeout or 0),
                        "stream_path": str(stream_path),
                        "phase": "awaiting_response_headers",
                    },
                    step=step,
                )
    if response_kind == "exception":
        exc = response_value
        return {
            "ok": False,
            "backend_timeout": "timed out" in str(exc).lower() or isinstance(exc, (socket.timeout, TimeoutError)),
            "backend_unreachable": "timed out" not in str(exc).lower(),
            "error_type": type(exc).__name__,
            "error": str(exc),
            "timeout_seconds": stream_timeout_seconds,
            "partial_content": "",
            "stream_path": str(stream_path),
            "elapsed_seconds": round(time.time() - started, 3),
            "timeout_phase": "awaiting_response_headers",
        }

    response = response_value
    try:
        with response:
            while True:
                if time.time() >= deadline:
                    return {
                        "ok": False,
                        "backend_timeout": True,
                        "backend_unreachable": False,
                        "error_type": "PlannerStreamTimeout",
                        "error": f"planner stream exceeded {timeout}s",
                        "partial_content": "".join(chunks)[-12000:],
                        "stream_path": str(stream_path),
                    }
                try:
                    raw_line = response.readline()
                except (socket.timeout, TimeoutError):
                    now_ts = time.time()
                    if now_ts - last_waiting_at >= 5:
                        last_waiting_at = now_ts
                        append_agent_event(
                            job_id, "planner_stream_waiting",
                            f"Waiting for tokens. chars={sum(len(x) for x in chunks)}",
                            {"elapsed_seconds": round(now_ts - started, 3)}, step=step,
                        )
                    continue
                if not raw_line:
                    break

                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except Exception:
                    item = {"raw": line}

                message = item.get("message") if isinstance(item.get("message"), dict) else {}
                calls = message.get("tool_calls") if isinstance(message.get("tool_calls"), list) else []
                if calls:
                    native_tool_calls.extend(call for call in calls if isinstance(call, dict))
                with raw_path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(item, ensure_ascii=False, default=str) + "\n")

                thinking_parts = [
                    message.get("thinking"), item.get("thinking"),
                    message.get("reasoning"), item.get("reasoning"),
                ]
                content_parts = [
                    message.get("content"), item.get("response"), item.get("content"),
                ]
                thinking_text = "".join(str(p) for p in thinking_parts if p)
                content_text = "".join(str(p) for p in content_parts if p)

                # extract <think>...</think> blocks embedded in content
                think_blocks = re.findall(
                    r"<think>(.*?)</think>", content_text, flags=re.DOTALL | re.IGNORECASE
                )
                if think_blocks:
                    extra = "\n\n".join(b.strip() for b in think_blocks if b.strip())
                    thinking_text += ("\n" if thinking_text else "") + extra

                if thinking_text:
                    guard_chunks.append(thinking_text)
                    thinking_path.open("a", encoding="utf-8").write(thinking_text)
                    all_path.open("a", encoding="utf-8").write(thinking_text)

                if content_text:
                    chunks.append(content_text)
                    guard_chunks.append(content_text)
                    content_path.open("a", encoding="utf-8").write(content_text)
                    all_path.open("a", encoding="utf-8").write(content_text)

                guard_text = "".join(guard_chunks)

                # Valid JSON is a candidate decision, but keep consuming until
                # Ollama sends done:true so diagnostics such as load_duration
                # remain visible and native tool_calls are not hidden by an
                # early local return. Degenerate/failing streams are still
                # closed by the guards below instead of waiting for timeout.
                decoded_now = _parse_strict_json_object(guard_text)
                if decoded_now and not json_detected_event_sent:
                    json_detected_event_sent = True
                    append_agent_event(
                        job_id, "planner_stream_json_detected",
                        "Valid JSON detected in stream; waiting for Ollama done frame.",
                        {"action": decoded_now.get("action"), "tool": decoded_now.get("tool"),
                         "elapsed_seconds": round(time.time() - started, 3)}, step=step,
                    )

                degenerate_reason = _planner_stream_repetition_reason(
                    guard_text,
                    allow_plain_text_without_json=allow_plain_text_without_json,
                )
                if degenerate_reason:
                    append_agent_event(
                        job_id, "planner_stream_degenerate_output",
                        f"Degenerate stream: {degenerate_reason}",
                        {"reason": degenerate_reason, "chars": len(guard_text)}, step=step,
                    )
                    return _planner_stream_block_response(degenerate_reason, guard_text, stream_path)

                now_ts = time.time()
                if now_ts - last_progress_at >= 5:
                    last_progress_at = now_ts
                    append_agent_event(
                        job_id, "planner_stream_progress",
                        f"Stream active. chars={sum(len(x) for x in chunks)}",
                        {"elapsed_seconds": round(now_ts - started, 3)}, step=step,
                    )

                if item.get("done") is True:
                    terminal_item = item
                    break
    except Exception as exc:
        return {
            "ok": False,
            "backend_timeout": "timed out" in str(exc).lower(),
            "backend_unreachable": "timed out" not in str(exc).lower(),
            "error_type": type(exc).__name__,
            "error": str(exc),
            "partial_content": "".join(chunks)[-12000:],
            "stream_path": str(stream_path),
        }

    content = "".join(chunks)
    terminal_meta = {
        "ollama_done_seen": bool(terminal_item.get("done") is True),
        "ollama_done_reason": terminal_item.get("done_reason"),
        "ollama_load_duration": terminal_item.get("load_duration"),
        "ollama_total_duration": terminal_item.get("total_duration"),
        "ollama_eval_count": terminal_item.get("eval_count"),
        "ollama_prompt_eval_count": terminal_item.get("prompt_eval_count"),
    }
    if native_tool_calls:
        append_agent_event(
            job_id, "planner_stream_native_tool_calls_detected",
            f"Native tool_calls detected. count={len(native_tool_calls)}",
            {"tool_call_count": len(native_tool_calls), **terminal_meta}, step=step,
        )
        return {
            "ok": True,
            "planner_native_tool_calls_detected": True,
            "message": {"role": "assistant", "content": content, "tool_calls": native_tool_calls},
            "response": content,
            "native_tool_calls": native_tool_calls,
            "stream_path": str(stream_path),
            "elapsed_seconds": round(time.time() - started, 3),
            **terminal_meta,
        }
    final_json = _parse_strict_json_object(content)
    if terminal_item.get("done") is not True:
        append_agent_event(job_id, "planner_stream_missing_done",
                           f"Stream ended without Ollama done:true. chars={len(content)}",
                           {
                               "elapsed_seconds": round(time.time() - started, 3),
                               "planner_json_detected": bool(final_json),
                               **terminal_meta,
                           }, step=step)
        return {
            "ok": False,
            "backend_timeout": True,
            "backend_unreachable": False,
            "error_type": "PlannerStreamMissingDone",
            "error": "ollama stream ended before done:true",
            "partial_content": content[-12000:],
            "stream_path": str(stream_path),
            "elapsed_seconds": round(time.time() - started, 3),
            **terminal_meta,
        }
    append_agent_event(job_id, "planner_stream_finished",
                       f"Stream finished. chars={len(content)}",
                       {
                           "elapsed_seconds": round(time.time() - started, 3),
                           "planner_json_detected": bool(final_json),
                           **terminal_meta,
                       }, step=step)
    return {
        "ok": True,
        "planner_json_detected": bool(final_json),
        "message": {"role": "assistant", "content": content},
        "response": content,
        "stream_path": str(stream_path),
        "elapsed_seconds": round(time.time() - started, 3),
        **terminal_meta,
    }


# ---------------------------------------------------------------------------
# JSON extraction / normalisation
# ---------------------------------------------------------------------------


def parse_strict_json_object_diagnostics(text: str) -> dict[str, Any]:
    """Return diagnostics for the strict planner JSON parser."""
    raw_input = str(text or "")
    raw = raw_input.strip()
    diagnostics: dict[str, Any] = {
        "schema": "strict_json_object_parse_diagnostics.v1",
        "ok": False,
        "raw_response_chars": len(raw_input),
        "stripped_chars": len(raw),
    }
    if not raw:
        diagnostics["error_type"] = "empty"
        return diagnostics
    if not raw.startswith("{"):
        diagnostics.update({
            "error_type": "not_json_object",
            "start_preview": raw[:80],
        })
        return diagnostics
    try:
        decoder = json.JSONDecoder()
        decoded, end = decoder.raw_decode(raw)
    except json.JSONDecodeError as exc:
        diagnostics.update({
            "error_type": "json_decode_error",
            "error": str(exc)[:500],
            "line": exc.lineno,
            "column": exc.colno,
            "position": exc.pos,
        })
        return diagnostics
    except Exception as exc:
        diagnostics.update({
            "error_type": type(exc).__name__,
            "error": str(exc)[:500],
        })
        return diagnostics
    trailing = raw[end:].strip()
    if trailing:
        diagnostics.update({
            "error_type": "trailing_content",
            "trailing_preview": trailing[:200],
            "json_end": end,
        })
        return diagnostics
    if not isinstance(decoded, dict):
        diagnostics.update({
            "error_type": "not_json_object",
            "decoded_type": type(decoded).__name__,
        })
        return diagnostics
    diagnostics["ok"] = True
    diagnostics["decoded"] = decoded
    return diagnostics


def _parse_strict_json_object(text: str) -> dict[str, Any]:
    """Parse only one complete JSON object.

    A valid planner response is either:
    - {"action":"tool", ...}
    - {"action":"final", "final_answer":"...", ...}
    - {"action":"block", "final_answer":"...", ...}

    Markdown fences, prose before/after the object, embedded snippets, multiple
    objects, and partial JSON recovered from a degenerate stream remain invalid.
    """
    diagnostics = parse_strict_json_object_diagnostics(text)
    decoded = diagnostics.get("decoded") if diagnostics.get("ok") is True else {}
    return decoded if isinstance(decoded, dict) else {}
