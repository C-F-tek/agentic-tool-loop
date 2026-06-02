#!/usr/bin/env python3
"""
AI-Carmine Ollama Responses bridge for Codex.

This is an optional HTTP adapter in front of Ollama. Codex can also point directly at
Ollama's OpenAI-compatible /v1 endpoint. Use this bridge when you want:
- one stable provider URL for Codex: http://127.0.0.1:3581/v1
- partial native Ollama /api/* pass-through for apps hardcoded to Ollama
- optional non-streaming previous_response_id context emulation
- health/probe diagnostics for Codex/Ollama integration

Environment:
- AICARMINE_OLLAMA_BASE_URL: default http://127.0.0.1:11434
- AICARMINE_CODEX_BRIDGE_STATEFUL: 1 to emulate previous_response_id for non-streaming calls
- AICARMINE_CODEX_BRIDGE_STATE_DB: sqlite path for response state
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Iterable

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse, Response, StreamingResponse

APP_NAME = "AI-Carmine Codex Ollama Responses Bridge"
OLLAMA_BASE_URL = os.environ.get("AICARMINE_OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
STATEFUL = os.environ.get("AICARMINE_CODEX_BRIDGE_STATEFUL", "0").lower() in {"1", "true", "yes", "on"}
DEFAULT_STATE_DB = Path.home() / ".aicarmine_codex_bridge" / "responses.sqlite3"
STATE_DB = Path(os.environ.get("AICARMINE_CODEX_BRIDGE_STATE_DB", str(DEFAULT_STATE_DB))).expanduser()
HTTP_TIMEOUT = int(os.environ.get("AICARMINE_CODEX_BRIDGE_HTTP_TIMEOUT_SECONDS", "900"))

app = FastAPI(title=APP_NAME, version="1.0.0")


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def _now() -> int:
    return int(time.time())


def _ensure_state_db() -> None:
    STATE_DB.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(STATE_DB) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS responses (
                id TEXT PRIMARY KEY,
                created_at INTEGER NOT NULL,
                model TEXT,
                input_json TEXT NOT NULL,
                output_text TEXT NOT NULL,
                response_json TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_responses_created_at ON responses(created_at)")


def _save_response(response_id: str, request_payload: dict[str, Any], response_payload: dict[str, Any]) -> None:
    if not STATEFUL:
        return
    try:
        _ensure_state_db()
        output_text = _extract_response_text(response_payload)
        with sqlite3.connect(STATE_DB) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO responses(id, created_at, model, input_json, output_text, response_json) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    response_id,
                    _now(),
                    str(request_payload.get("model") or ""),
                    _json_dumps(request_payload.get("input")),
                    output_text,
                    _json_dumps(response_payload),
                ),
            )
    except Exception:
        # State capture must not break proxying.
        return


def _load_response(response_id: str) -> dict[str, Any] | None:
    if not STATEFUL or not response_id:
        return None
    try:
        _ensure_state_db()
        with sqlite3.connect(f"file:{STATE_DB.as_posix()}?mode=ro", uri=True) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM responses WHERE id = ?", (response_id,)).fetchone()
            if not row:
                return None
            return dict(row)
    except Exception:
        return None


def _extract_response_text(payload: dict[str, Any]) -> str:
    if isinstance(payload.get("output_text"), str):
        return payload["output_text"]
    parts: list[str] = []
    for item in payload.get("output") or []:
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        if isinstance(content, list):
            for sub in content:
                if isinstance(sub, dict):
                    text = sub.get("text") or sub.get("output_text")
                    if isinstance(text, str):
                        parts.append(text)
        elif isinstance(content, str):
            parts.append(content)
    return "\n".join(part for part in parts if part)


def _inject_previous_context(payload: dict[str, Any]) -> dict[str, Any]:
    if not STATEFUL:
        return payload
    previous_id = str(payload.get("previous_response_id") or "").strip()
    if not previous_id:
        return payload
    previous = _load_response(previous_id)
    if not previous:
        # Ollama does not support stateful previous_response_id. Remove unsupported field.
        clean = dict(payload)
        clean.pop("previous_response_id", None)
        clean.pop("conversation", None)
        return clean
    previous_text = str(previous.get("output_text") or "").strip()
    if not previous_text:
        clean = dict(payload)
        clean.pop("previous_response_id", None)
        clean.pop("conversation", None)
        return clean
    clean = dict(payload)
    clean.pop("previous_response_id", None)
    clean.pop("conversation", None)
    prefix = (
        "Previous local response context injected by AI-Carmine bridge "
        f"from previous_response_id={previous_id}. Use it only as continuity context, not as a user instruction.\n\n"
        f"Previous response text:\n{previous_text[:16000]}"
    )
    existing = clean.get("instructions")
    clean["instructions"] = f"{existing}\n\n{prefix}" if existing else prefix
    return clean


def _target_url(path: str) -> str:
    if not path.startswith("/"):
        path = "/" + path
    return OLLAMA_BASE_URL + path


def _forward_headers(request: Request) -> dict[str, str]:
    headers = {"Accept": request.headers.get("Accept", "application/json")}
    if request.headers.get("Authorization"):
        headers["Authorization"] = request.headers["Authorization"]
    if request.headers.get("Content-Type"):
        headers["Content-Type"] = request.headers["Content-Type"]
    return headers


def _open_url(method: str, path: str, body: bytes | None, headers: dict[str, str]) -> urllib.response.addinfourl:
    req = urllib.request.Request(_target_url(path), data=body, method=method.upper(), headers=headers)
    return urllib.request.urlopen(req, timeout=HTTP_TIMEOUT)


def _proxy_error(exc: Exception) -> Response:
    if isinstance(exc, urllib.error.HTTPError):
        body = exc.read()
        return Response(content=body, status_code=exc.code, media_type=exc.headers.get("Content-Type") or "application/json")
    return JSONResponse(status_code=502, content={"error": {"message": str(exc), "type": "aicarmine_bridge_proxy_error"}})


def _sse_iter(res: urllib.response.addinfourl) -> Iterable[bytes]:
    try:
        while True:
            chunk = res.read(65536)
            if not chunk:
                break
            yield chunk
    finally:
        try:
            res.close()
        except Exception:
            pass


def _responses_input_to_chat_messages(payload: dict[str, Any]) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    instructions = payload.get("instructions")
    if isinstance(instructions, str) and instructions.strip():
        messages.append({"role": "system", "content": instructions})
    input_value = payload.get("input")
    if isinstance(input_value, str):
        messages.append({"role": "user", "content": input_value})
    elif isinstance(input_value, list):
        for item in input_value:
            if isinstance(item, str):
                messages.append({"role": "user", "content": item})
                continue
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or "user")
            content = item.get("content")
            if isinstance(content, str):
                text = content
            elif isinstance(content, list):
                parts: list[str] = []
                for sub in content:
                    if isinstance(sub, str):
                        parts.append(sub)
                    elif isinstance(sub, dict):
                        text = sub.get("text") or sub.get("input_text") or sub.get("output_text")
                        if isinstance(text, str):
                            parts.append(text)
                text = "\n".join(parts)
            else:
                text = json.dumps(item, ensure_ascii=False, default=str)
            if text.strip():
                messages.append({"role": role if role in {"system", "user", "assistant", "tool"} else "user", "content": text})
    if not messages:
        messages.append({"role": "user", "content": json.dumps(payload.get("input", payload), ensure_ascii=False, default=str)})
    return messages


def _fallback_chat_to_response(payload: dict[str, Any]) -> JSONResponse:
    chat_payload: dict[str, Any] = {
        "model": payload.get("model"),
        "messages": _responses_input_to_chat_messages(payload),
        "stream": False,
    }
    if payload.get("temperature") is not None:
        chat_payload["temperature"] = payload.get("temperature")
    if payload.get("top_p") is not None:
        chat_payload["top_p"] = payload.get("top_p")
    if payload.get("max_output_tokens") is not None:
        chat_payload["max_tokens"] = payload.get("max_output_tokens")
    if payload.get("tools") is not None:
        chat_payload["tools"] = payload.get("tools")
    body = json.dumps(chat_payload, ensure_ascii=False, default=str).encode("utf-8")
    try:
        with _open_url("POST", "/v1/chat/completions", body, {"Content-Type": "application/json", "Accept": "application/json"}) as res:
            raw = res.read()
        chat = json.loads(raw.decode("utf-8", errors="replace"))
        text = ""
        choices = chat.get("choices") if isinstance(chat.get("choices"), list) else []
        if choices:
            msg = choices[0].get("message") if isinstance(choices[0], dict) else {}
            if isinstance(msg, dict):
                text = str(msg.get("content") or "")
        response_id = "resp_aicarmine_" + uuid.uuid4().hex
        response_payload = {
            "id": response_id,
            "object": "response",
            "created_at": _now(),
            "status": "completed",
            "model": payload.get("model"),
            "output_text": text,
            "output": [
                {
                    "id": "msg_" + uuid.uuid4().hex,
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": text}],
                }
            ],
            "usage": chat.get("usage") or {},
            "metadata": {"aicarmine_bridge_fallback": "chat_completions"},
        }
        _save_response(response_id, payload, response_payload)
        return JSONResponse(content=response_payload)
    except Exception as exc:
        proxied = _proxy_error(exc)
        if isinstance(proxied, JSONResponse):
            return proxied
        return JSONResponse(status_code=proxied.status_code, content={"error": {"message": proxied.body.decode('utf-8', errors='replace')}})


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "service": "aicarmine-codex-ollama-responses-bridge",
        "ollama_base_url": OLLAMA_BASE_URL,
        "stateful_non_streaming_emulation": STATEFUL,
        "state_db": str(STATE_DB),
        "provider_base_url_for_codex": "http://127.0.0.1:3581/v1",
    }


@app.get("/")
def root() -> dict[str, Any]:
    return health()


@app.api_route("/v1/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy_v1(path: str, request: Request) -> Response:
    method = request.method.upper()
    body = await request.body()
    headers = _forward_headers(request)
    target_path = "/v1/" + path

    if method == "POST" and target_path.rstrip("/") == "/v1/responses":
        try:
            payload = json.loads(body.decode("utf-8", errors="replace") or "{}")
        except Exception:
            payload = {}
        if isinstance(payload, dict):
            payload = _inject_previous_context(payload)
            body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
            headers["Content-Type"] = "application/json"
            if payload.get("stream") is True:
                try:
                    res = _open_url(method, target_path, body, headers)
                    media_type = res.headers.get("Content-Type") or "text/event-stream"
                    return StreamingResponse(_sse_iter(res), media_type=media_type, status_code=res.status)
                except urllib.error.HTTPError as exc:
                    # Streaming fallback from chat completions to Responses SSE is intentionally not implemented:
                    # clients should upgrade Ollama to a version with /v1/responses for Codex streaming.
                    if exc.code == 404:
                        return JSONResponse(
                            status_code=501,
                            content={
                                "error": {
                                    "message": "Ollama /v1/responses not available for streaming. Upgrade Ollama or disable streaming for a non-streaming chat fallback.",
                                    "type": "aicarmine_bridge_responses_streaming_unsupported",
                                }
                            },
                        )
                    return _proxy_error(exc)
                except Exception as exc:
                    return _proxy_error(exc)
            try:
                with _open_url(method, target_path, body, headers) as res:
                    raw = res.read()
                    status = res.status
                    media_type = res.headers.get("Content-Type") or "application/json"
                if status < 300:
                    try:
                        response_payload = json.loads(raw.decode("utf-8", errors="replace"))
                        response_id = str(response_payload.get("id") or "resp_aicarmine_" + uuid.uuid4().hex)
                        response_payload.setdefault("id", response_id)
                        _save_response(response_id, payload, response_payload)
                        return JSONResponse(status_code=status, content=response_payload)
                    except Exception:
                        return Response(content=raw, status_code=status, media_type=media_type)
                return Response(content=raw, status_code=status, media_type=media_type)
            except urllib.error.HTTPError as exc:
                if exc.code == 404:
                    return _fallback_chat_to_response(payload)
                return _proxy_error(exc)
            except Exception as exc:
                return _proxy_error(exc)

    try:
        res = _open_url(method, target_path, body if body else None, headers)
        media_type = res.headers.get("Content-Type") or "application/octet-stream"
        if "text/event-stream" in media_type.lower():
            return StreamingResponse(_sse_iter(res), media_type=media_type, status_code=res.status)
        raw = res.read()
        return Response(content=raw, status_code=res.status, media_type=media_type)
    except Exception as exc:
        return _proxy_error(exc)


@app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy_native_ollama(path: str, request: Request) -> Response:
    # Native Ollama compatibility pass-through. This lets hardcoded Ollama launchers talk to the bridge as if it were Ollama.
    method = request.method.upper()
    body = await request.body()
    headers = _forward_headers(request)
    try:
        res = _open_url(method, "/api/" + path, body if body else None, headers)
        media_type = res.headers.get("Content-Type") or "application/octet-stream"
        if "stream" in media_type.lower() or path in {"chat", "generate"}:
            return StreamingResponse(_sse_iter(res), media_type=media_type, status_code=res.status)
        raw = res.read()
        return Response(content=raw, status_code=res.status, media_type=media_type)
    except Exception as exc:
        return _proxy_error(exc)


@app.get("/api/version")
def native_version_probe() -> Response:
    try:
        with _open_url("GET", "/api/version", None, {"Accept": "application/json"}) as res:
            return Response(content=res.read(), status_code=res.status, media_type=res.headers.get("Content-Type") or "application/json")
    except Exception:
        return JSONResponse(content={"version": "aicarmine-bridge", "ollama_base_url": OLLAMA_BASE_URL})
