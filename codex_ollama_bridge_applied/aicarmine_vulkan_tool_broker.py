from __future__ import annotations

import hashlib
import html
import json
from logging import root
import os
import re
import sqlite3
import subprocess
import threading
import time
import traceback
import uuid
import socket
import urllib.request
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI
from fastapi.responses import HTMLResponse, PlainTextResponse


OLLAMA_TASK_URL = (
    os.environ.get("AICARMINE_OLLAMA_TASK_URL")
    or os.environ.get("AICARMINE_VULKAN_BROKER_OLLAMA_URL")
    or "http://127.0.0.1:11435/api/chat"
)
OLLAMA_TASK_MODEL = (
    os.environ.get("AICARMINE_OLLAMA_TASK_MODEL")
    or os.environ.get("AICARMINE_VULKAN_BROKER_MODEL")
    or "codex-qwen25-7b-vulkan"
)
OLLAMA_KEEP_ALIVE = (
    os.environ.get("AICARMINE_OLLAMA_KEEP_ALIVE")
    or os.environ.get("AICARMINE_VULKAN_KEEP_ALIVE")
    or "24h"
)

PLANNER_URL = (
    os.environ.get("AICARMINE_AGENT_PLANNER_URL")
    or os.environ.get("AICARMINE_PLANNER_URL")
    or "http://127.0.0.1:11434/api/chat"
)
PLANNER_MODEL = (
    os.environ.get("AICARMINE_AGENT_PLANNER_MODEL")
    or os.environ.get("AICARMINE_PLANNER_MODEL")
    or os.environ.get("AICARMINE_OLLAMA_PLANNER_MODEL")
    or "Qwen-AgentWorld-35B-A3B-UD-IQ2_XXS-gguf:latest"
)
AGENTIC_PLANNER_ENABLED = os.environ.get("AICARMINE_AGENTIC_PLANNER_ENABLED", "1").strip().lower() not in {"0", "false", "no", "off"}
AGENTIC_FALLBACK_ONESHOT = os.environ.get("AICARMINE_AGENTIC_FALLBACK_ONESHOT", "1").strip().lower() in {"1", "true", "yes", "on"}
AGENTIC_RESULT_COMPACT_CHARS = int(os.environ.get("AICARMINE_AGENTIC_RESULT_COMPACT_CHARS", "6000"))
AGENTIC_PLANNER_NUM_CTX = int(os.environ.get("AICARMINE_AGENTIC_PLANNER_NUM_CTX", "4096"))
AGENTIC_PLANNER_NUM_PREDICT = int(os.environ.get("AICARMINE_AGENTIC_PLANNER_NUM_PREDICT", "-1"))
AGENTIC_PLANNER_STEP_TIMEOUT = int(os.environ.get("AICARMINE_AGENTIC_PLANNER_STEP_TIMEOUT", "60"))
AGENTIC_PLANNER_FORCED_DECISION_TIMEOUT = int(os.environ.get("AICARMINE_AGENTIC_PLANNER_FORCED_DECISION_TIMEOUT", "75"))
AGENT_DEFAULT_MAX_STEPS = int(os.environ.get("AICARMINE_AGENT_DEFAULT_MAX_STEPS", "20"))
AGENT_MAX_STEPS = int(os.environ.get("AICARMINE_AGENT_MAX_STEPS", "60"))
AGENT_RETURN_WAIT_SECONDS = int(os.environ.get("AICARMINE_AGENT_RETURN_WAIT_SECONDS", "900"))
AGENT_WAIT_POLL_SECONDS = float(os.environ.get("AICARMINE_AGENT_WAIT_POLL_SECONDS", "1.0"))
AGENT_TERMINAL_STATUSES = {
    "completed",
    "blocked_needs_attention",
    "blocked_needs_consent",
    "failed",
    "failed_tool_error",
    "failed_planner_error",
    "max_steps_reached",
    "cancelled",
}

LAB_REPO = Path(os.environ.get("AICARMINE_LAB_REPO", r"C:\Users\someo\agentic-tool-loop")).resolve(strict=False)
REAL_REPO = Path(os.environ.get("AICARMINE_REAL_REPO", r"C:\Users\someo\agentic-tool-loop")).resolve(strict=False)
WORKSPACE = Path(os.environ.get("AICARMINE_VULKAN_WORKSPACE", r"C:\Users\someo\agentic-tool-loop\services\codex_bridge\workspace")).resolve(strict=False)

AGENT_JOB_ROOT = Path(
    os.environ.get("AICARMINE_AGENT_JOB_ROOT", str(WORKSPACE / "agent-jobs"))
).resolve(strict=False)
AGENT_JOB_DB = Path(
    os.environ.get("AICARMINE_AGENT_JOB_DB", str(AGENT_JOB_ROOT / "agent_jobs.sqlite3"))
).resolve(strict=False)
AGENT_PUBLIC_BASE_URL = os.environ.get("AICARMINE_AGENT_PUBLIC_BASE_URL", "http://127.0.0.1:3572")
AGENT_JOB_MAX_INLINE_EVENTS = int(os.environ.get("AICARMINE_AGENT_JOB_MAX_INLINE_EVENTS", "12"))
AGENT_JOB_BACKGROUND_THREADS: dict[str, threading.Thread] = {}
AGENT_JOB_LOCK = threading.RLock()

COMMAND_TIMEOUT_SECONDS = int(os.environ.get("AICARMINE_CODEX_COMMAND_TIMEOUT", "600"))
MAX_TOOL_RESULT_CHARS = int(
    os.environ.get("AICARMINE_CODEX_MAX_TOOL_RESULT_CHARS")
    or os.environ.get("AICARMINE_VULKAN_MAX_TOOL_RESULT_CHARS")
    or "30000"
)
V6_MARKER = "public_x_v6_vulkan_select_dispatcher_execute_deterministic_wrap"
VALID_INTERNAL_TOOLS = {
    "repo_capabilities",
    "repo_status",
    "repo_tree",
    "repo_search",
    "repo_read",
    "repo_list_files",
    "repo_apply_patch",
    "repo_write_file",
    "repo_validate",
    "repo_command",
    "vulkan_helper",
}
HELPER_PUBLIC_ALIASES = {"helper_for_all", "help_for_all", "helper", "help"}


app = FastAPI(
    title="AI-Carmine Vulkan Tool Broker",
    version="2.0.0",
    description=(
        "Internal 3572 broker. Receives public tool X from 3571, asks 11435/Vulkan to select "
        "one internal tool L, executes L, then deterministically wraps the dispatcher result as public X."
    ),
)


def now() -> int:
    return int(time.time())


def make_session_id(value: str = "") -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_.-]+", "-", str(value or "").strip()).strip("-")
    if cleaned:
        return cleaned[:120]
    return time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]


def session_root(session_id: str) -> Path:
    root = WORKSPACE / "sessions" / make_session_id(session_id)
    for name in ("commands", "reads", "tool-results", "artifacts"):
        (root / name).mkdir(parents=True, exist_ok=True)
    return root


def write_json(path: Path, payload: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return str(path)



def read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def init_agent_job_db() -> None:
    AGENT_JOB_ROOT.mkdir(parents=True, exist_ok=True)
    AGENT_JOB_DB.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(AGENT_JOB_DB)) as db:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                goal TEXT NOT NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                workspace TEXT NOT NULL,
                final_path TEXT,
                error TEXT
            )
            """
        )
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL,
                ts REAL NOT NULL,
                step INTEGER,
                event_type TEXT NOT NULL,
                message TEXT NOT NULL,
                payload_json TEXT NOT NULL
            )
            """
        )
        db.commit()


def agent_job_root(job_id: str) -> Path:
    return AGENT_JOB_ROOT / make_session_id(job_id)


def agent_job_state_path(job_id: str) -> Path:
    return agent_job_root(job_id) / "job.json"


def agent_job_events_path(job_id: str) -> Path:
    return agent_job_root(job_id) / "events.ndjson"

def agent_job_planner_stream_dir(job_id: str) -> Path:
    path = agent_job_root(job_id) / "planner-stream"
    path.mkdir(parents=True, exist_ok=True)
    return path


def agent_job_planner_stream_path(job_id: str, step: int, suffix: str = "") -> Path:
    extra = f"-{suffix}" if suffix else ""
    return agent_job_planner_stream_dir(job_id) / f"step-{int(step):03d}{extra}.txt"

def job_url(job_id: str) -> str:
    return f"{AGENT_PUBLIC_BASE_URL.rstrip('/')}/jobs/{job_id}"


def write_agent_job_state(state: dict[str, Any]) -> None:
    job_id = str(state["job_id"])
    root = agent_job_root(job_id)
    root.mkdir(parents=True, exist_ok=True)
    state["workspace"] = str(root)
    state["updated_at"] = time.time()
    write_json(agent_job_state_path(job_id), state)
    try:
        init_agent_job_db()
        with sqlite3.connect(str(AGENT_JOB_DB)) as db:
            db.execute(
                """
                INSERT INTO jobs(job_id, status, goal, created_at, updated_at, workspace, final_path, error)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                    status=excluded.status,
                    goal=excluded.goal,
                    updated_at=excluded.updated_at,
                    workspace=excluded.workspace,
                    final_path=excluded.final_path,
                    error=excluded.error
                """,
                (
                    job_id,
                    str(state.get("status") or "unknown"),
                    str(state.get("goal") or ""),
                    float(state.get("created_at") or time.time()),
                    float(state.get("updated_at") or time.time()),
                    str(state.get("workspace") or root),
                    str(state.get("final_path") or ""),
                    str(state.get("error") or ""),
                ),
            )
            db.commit()
    except Exception:
        pass


def load_agent_job_state(job_id: str) -> dict[str, Any]:
    state = read_json(agent_job_state_path(job_id), {})
    return state if isinstance(state, dict) else {}


def append_agent_event(job_id: str, event_type: str, message: str, payload: dict[str, Any] | None = None, step: int | None = None) -> None:
    event = {
        "ts": time.time(),
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "job_id": job_id,
        "step": step,
        "event_type": event_type,
        "message": message,
        "payload": payload or {},
    }
    root = agent_job_root(job_id)
    root.mkdir(parents=True, exist_ok=True)
    with agent_job_events_path(job_id).open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
    try:
        init_agent_job_db()
        with sqlite3.connect(str(AGENT_JOB_DB)) as db:
            db.execute(
                "INSERT INTO events(job_id, ts, step, event_type, message, payload_json) VALUES(?, ?, ?, ?, ?, ?)",
                (
                    job_id,
                    float(event["ts"]),
                    step,
                    event_type,
                    message,
                    json.dumps(payload or {}, ensure_ascii=False, default=str),
                ),
            )
            db.commit()
    except Exception:
        pass


def read_agent_events(job_id: str, limit: int = 200) -> list[dict[str, Any]]:
    path = agent_job_events_path(job_id)
    if not path.exists():
        return []
    rows = path.read_text(encoding="utf-8", errors="replace").splitlines()
    events: list[dict[str, Any]] = []
    for raw in rows[-max(1, limit):]:
        try:
            decoded = json.loads(raw)
            if isinstance(decoded, dict):
                events.append(decoded)
        except Exception:
            events.append({"event_type": "raw", "message": raw})
    return events


def compact_agent_status(job_id: str, include_events: bool = True) -> dict[str, Any]:
    state = load_agent_job_state(job_id)
    if not state:
        return {
            "ok": False,
            "service": "vulkan_agent",
            "tool_name": "vulkan_helper",
            "error": "job_not_found",
            "job_id": job_id,
        }

    events = read_agent_events(job_id, AGENT_JOB_MAX_INLINE_EVENTS) if include_events else []
    return {
        "ok": True,
        "service": "vulkan_agent",
        "mode": "agent_job_status",
        "tool_name": str(state.get("public_tool_name") or "vulkan_helper"),
        "tool_result_for": str(state.get("public_tool_name") or "vulkan_helper"),
        "called_by_30b": str(state.get("public_tool_name") or "vulkan_helper"),
        "job_id": job_id,
        "status": state.get("status"),
        "goal": state.get("goal"),
        "created_at": state.get("created_at"),
        "updated_at": state.get("updated_at"),
        "workspace": state.get("workspace"),
        "job_url": job_url(job_id),
        "events_tail": events,
        "final_path": state.get("final_path"),
        "final_summary": state.get("final_summary", ""),
        "current_step": state.get("current_step"),
        "status_message": state.get("status_message", ""),
        "result": state.get("result", {}),
        "message_for_30b": (
            f"Agent job {job_id} status={state.get('status')}. "
            f"Open {job_url(job_id)} or call action=status/result with job_id."
        ),
    }

def wait_for_agent_terminal(job_id: str, timeout_seconds: int) -> dict[str, Any]:
    deadline = time.time() + max(1, int(timeout_seconds or AGENT_RETURN_WAIT_SECONDS))
    last_status: dict[str, Any] = {}

    while time.time() < deadline:
        last_status = compact_agent_status(job_id, include_events=True)
        status = str(last_status.get("status") or "")
        if status in AGENT_TERMINAL_STATUSES:
            last_status["mode"] = "agent_job_final_waited"
            last_status["wait_completed"] = True
            last_status["message_for_30b"] = (
                f"Agent job {job_id} reached terminal status={status}. "
                "Use final_summary/result only; do not call more tools unless the user asks."
            )
            return last_status
        time.sleep(AGENT_WAIT_POLL_SECONDS)

    last_status = compact_agent_status(job_id, include_events=True)
    last_status["mode"] = "agent_job_wait_timeout"
    last_status["wait_completed"] = False
    last_status["wait_timeout_seconds"] = timeout_seconds
    last_status["message_for_30b"] = (
        f"Agent job {job_id} is still running after {timeout_seconds}s. "
        "Report that the backend is still working and give the dashboard URL. "
        "Do not call more tools automatically."
    )
    return last_status
def agent_job_html(job_id: str) -> str:
    status = compact_agent_status(job_id, include_events=True)
    if not status.get("ok"):
        return f"<html><body><h1>Job not found</h1><pre>{html.escape(json.dumps(status, ensure_ascii=False, indent=2))}</pre></body></html>"
    events = read_agent_events(job_id, 500)
    rows = []
    for ev in events:
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(ev.get('time') or ev.get('ts') or ''))}</td>"
            f"<td>{html.escape(str(ev.get('step') or ''))}</td>"
            f"<td>{html.escape(str(ev.get('event_type') or ''))}</td>"
            f"<td><pre>{html.escape(str(ev.get('message') or ''))}</pre></td>"
            "</tr>"
        )
    final_summary = html.escape(str(status.get("final_summary") or ""))
    planner_thinking_text = ""
    planner_content_text = ""
    planner_all_text = ""

    planner_stream_dir = agent_job_planner_stream_dir(job_id)
    thinking_files = sorted(planner_stream_dir.glob("step-*.thinking.txt"))
    content_files = sorted(planner_stream_dir.glob("step-*.content.txt"))
    all_files = sorted(planner_stream_dir.glob("step-*.all.txt"))

    if thinking_files:
        planner_thinking_text = thinking_files[-1].read_text(encoding="utf-8", errors="replace")[-20000:]

    if content_files:
        planner_content_text = content_files[-1].read_text(encoding="utf-8", errors="replace")[-12000:]

    if all_files:
        planner_all_text = all_files[-1].read_text(encoding="utf-8", errors="replace")[-20000:]

    planner_thinking_html = html.escape(planner_thinking_text)
    planner_content_html = html.escape(planner_content_text)
    planner_all_html = html.escape(planner_all_text)
    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>AI-Carmine Agent Job {html.escape(job_id)}</title>
<meta http-equiv="refresh" content="2">
<style>
body {{ font-family: Segoe UI, Arial, sans-serif; margin: 20px; background: #111; color: #ddd; }}
a {{ color: #8fd3ff; }}
.card {{ border: 1px solid #444; border-radius: 10px; padding: 14px; margin-bottom: 14px; background: #1b1b1b; }}
table {{ border-collapse: collapse; width: 100%; }}
td, th {{ border-bottom: 1px solid #333; padding: 8px; vertical-align: top; }}
pre {{ white-space: pre-wrap; margin: 0; }}
.status {{ font-size: 20px; font-weight: 700; }}
</style>
</head>
<body>
<div class="card">
  <div class="status">Job {html.escape(job_id)} — {html.escape(str(status.get('status')))}</div>
  <p><b>Goal:</b> {html.escape(str(status.get('goal') or ''))}</p>
  <p><b>Workspace:</b> {html.escape(str(status.get('workspace') or ''))}</p>
  <p><a href="/jobs/{html.escape(job_id)}/json">JSON</a> · <a href="/jobs/{html.escape(job_id)}/events">events.ndjson</a></p>
</div>
<div class="card">
  <h2>Final summary</h2>
  <pre>{final_summary}</pre>
</div>
<div class="card">
  <h2>Planner thinking / reasoning raw</h2>
  <p>Mostra solo ciò che 11434 emette nello stream: thinking, reasoning o blocchi &lt;think&gt;...&lt;/think&gt;.</p>
  <pre>{planner_thinking_html}</pre>
</div>

<div class="card">
  <h2>Planner emitted content</h2>
  <pre>{planner_content_html}</pre>
</div>

<div class="card">
  <h2>Planner full raw combined</h2>
  <p><a href="/jobs/{html.escape(job_id)}/planner-stream">full planner stream</a></p>
  <pre>{planner_all_html}</pre>
</div>
<div class="card">
  <h2>Events</h2>
  <table>
    <thead><tr><th>Time</th><th>Step</th><th>Type</th><th>Message</th></tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
</div>
</body>
</html>"""


def planner_tools_manifest() -> list[dict[str, Any]]:
    allowed = {
    "repo_capabilities",
    "repo_status",
    "repo_tree",
    "repo_search",
    "repo_read",
    "repo_apply_patch",
    "repo_write_file",
    "repo_validate",
    "repo_command",
    "repo_list_files",
    "repo_apply_patch",


}
    manifest: list[dict[str, Any]] = []
    for item in TOOLS_SCHEMA:
        fn = item.get("function") if isinstance(item.get("function"), dict) else {}
        name = str(fn.get("name") or "")
        if name in allowed:
            manifest.append({
                "name": name,
                "description": fn.get("description", ""),
                "parameters": fn.get("parameters", {}),
            })
    return manifest


def extract_json_object(text: str) -> dict[str, Any]:
    raw = str(text or "").strip()
    if not raw:
        return {}
    # Remove common markdown fences without trusting any prose around them.
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE).strip()
    raw = re.sub(r"\s*```$", "", raw).strip()
    try:
        decoded = json.loads(raw)
        return decoded if isinstance(decoded, dict) else {}
    except Exception:
        pass
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        try:
            decoded = json.loads(raw[start : end + 1])
            return decoded if isinstance(decoded, dict) else {}
        except Exception:
            return {}
    return {}

def planner_text_is_safe_for_vulkan_repair(raw_text: str) -> tuple[bool, str]:
    text = str(raw_text or "").strip()
    if not text:
        return False, "empty_planner_output"

    poisoned_markers = (
        "<|endoftext|>",
        "<|im_start|>",
        "<|im_end|>",
        "\nHuman:",
        "\nAssistant:",
        "\nSystem:",
        "Human:",
        "Assistant:",
        "System:",
    )
    if any(marker in text for marker in poisoned_markers):
        return False, "role_boundary_contaminated_output"

    lowered = text.lower().strip("` \r\n\t")
    dead_outputs = {
        "halted",
        "temps",
        "stopped",
        "stop",
        "done",
        "```",
    }
    if lowered in dead_outputs:
        return False, "dead_or_stop_token_output"

    # Non inviare a 11435 testo che non contiene nemmeno un possibile oggetto JSON.
    # Vulkan deve riparare JSON sporco, non interpretare frasi libere o stop-token.
    if "{" not in text or "}" not in text:
        return False, "no_json_object_candidate"

    return True, "repairable_json_candidate"
def recover_plaintext_file_intent(raw_text: str) -> dict[str, Any]:
    text = str(raw_text or "").strip()
    if not text:
        return {}

    # Non recuperare output contaminato o degenerato.
    blocked_markers = (
        "<|endoftext|>",
        "<|im_start|>",
        "<|im_end|>",
        "Human:",
        "Assistant:",
        "System:",
    )
    if any(marker in text for marker in blocked_markers):
        return {}

    # Cerca path tra apici o backtick.
    quoted = re.findall(r"[`'“\"]([^`'”\"]+\.(?:py|ps1|md|json|toml|yml|yaml|txt))[`'”\"]", text)

    # Cerca anche path non quotati.
    unquoted = re.findall(
        r"([A-Za-z0-9_./\\-]+?\.(?:py|ps1|md|json|toml|yml|yaml|txt))",
        text,
    )

    candidates = []
    for item in quoted + unquoted:
        normalized = item.strip().replace("\\", "/").lstrip("./")
        if normalized and normalized not in candidates:
            candidates.append(normalized)

    if not candidates:
        return {}

    lowered = text.lower()

    for candidate in candidates:
        try:
            rel = safe_rel_path(candidate)
            full = (LAB_REPO / rel).resolve(strict=False)
            full.relative_to(LAB_REPO)
        except Exception:
            continue

        if full.exists() and full.is_file():
            return {
                "action": "tool",
                "tool": "repo_read",
                "arguments": {"path": rel},
                "reason": (
                    "Deterministic 3572 recovery: planner emitted plaintext mentioning an existing file path; "
                    "converted to repo_read without using Vulkan."
                ),
                "recovered_by_3572": "plaintext_existing_file_to_repo_read",
                "raw_planner_text": text[:1000],
            }

        if "search" in lowered or "find" in lowered or "cerca" in lowered:
            return {
                "action": "tool",
                "tool": "repo_search",
                "arguments": {"query": candidate, "path": "."},
                "reason": (
                    "Deterministic 3572 recovery: planner emitted plaintext search intent for a file path; "
                    "converted to repo_search without using Vulkan."
                ),
                "recovered_by_3572": "plaintext_file_search_intent_to_repo_search",
                "raw_planner_text": text[:1000],
            }

    return {}

def normalize_planner_decision(raw_text: str, goal: str, step: int, state: dict[str, Any]) -> dict[str, Any]:
    decoded = extract_json_object(raw_text)
    if decoded:
        return decoded

    repairable, reject_reason = planner_text_is_safe_for_vulkan_repair(raw_text)
    if not repairable:
        if reject_reason == "no_json_object_candidate":
            recovered = recover_plaintext_file_intent(raw_text)
            if recovered:
                return recovered

        return {
            "action": "block",
            "reason": f"planner emitted non-repairable non-json output: {reject_reason}",
            "final_answer": (
                "Il planner 11434 ha emesso output non JSON non riparabile. "
                f"Motivo: {reject_reason}. "
                "La risposta non è stata inviata a 11435/Vulkan per evitare contaminazione o loop del normalizzatore."
            ),
            "raw_planner_text": raw_text[:4000],
        }

    # Vulkan/11435 is used only as a JSON normalizer when the 30B planner emits dirty JSON.
    response = post_json(
        OLLAMA_TASK_URL,
        {
            "model": OLLAMA_TASK_MODEL,
            "stream": False,
            "keep_alive": OLLAMA_KEEP_ALIVE,
            "think": False,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Sei un normalizzatore JSON. Converti il testo del planner in un solo oggetto JSON valido. "
                        "Schema: {\"action\":\"tool|final|block\", \"tool\":\"repo_status|repo_tree|repo_search|repo_read|repo_apply_patch|repo_validate|repo_command|repo_capabilities\", "
                        "\"arguments\":{}, \"reason\":\"...\", \"final_answer\":\"...\"}. "
                        "Non aggiungere markdown."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "goal": goal,
                            "step": step,
                            "planner_text": raw_text[:12000],
                            "job_id": state.get("job_id"),
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                },
            ],
            "options": ollama_options(num_predict=600),
        },
        timeout=90,
    )
    message = response.get("message") if isinstance(response.get("message"), dict) else {}
    content = str(message.get("content") or response.get("response") or "")
    decoded = extract_json_object(content)
    if decoded:
        decoded["normalized_by_vulkan"] = True
        action = str(decoded.get("action") or "").strip().lower()
        if action == "tool":
            decoded.pop("final_answer", None)
            decoded.pop("answer", None)
            decoded.pop("summary", None)
        return decoded
    return {
        "action": "block",
        "reason": "planner emitted non-json and Vulkan repair failed",
        "final_answer": (
            "Il planner 11434 ha prodotto output non JSON e 11435/Vulkan "
            "non è riuscito a riparare la tool-call in modo valido. "
            "Nessun fallback operativo è stato eseguito."
        ),
        "raw_planner_text": raw_text[:4000],
    }


def compact_tool_result_for_planner(tool: str, result: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "tool": tool,
        "ok": bool(result.get("ok")),
        "summary": summary_from_result(result)[:AGENTIC_RESULT_COMPACT_CHARS],
    }
    for key in ("path", "paths", "count", "matches", "returncode", "stderr_tail", "stdout_tail", "artifact", "changed", "replacements", "line_count_before", "line_count_after"):
        if key in result:
            value = result.get(key)
            if isinstance(value, str):
                payload[key] = value[:AGENTIC_RESULT_COMPACT_CHARS]
            else:
                payload[key] = value
    if isinstance(result.get("items"), list):
        payload["items"] = [
            {
                "ok": item.get("ok"),
                "path": item.get("path"),
                "line_count": item.get("line_count"),
                "truncated": item.get("truncated"),
                "content_preview": str(item.get("content") or "")[:2000],
            }
            for item in result.get("items", [])[:5]
            if isinstance(item, dict)
        ]
    return payload


def agentic_tool_allowed(tool: str, args: dict[str, Any], approval_mode: str) -> tuple[bool, str]:
    mode = str(approval_mode or "safe_write_lab").lower()
    if tool in {"repo_apply_patch", "repo_write_file"} and mode in {"read_only", "readonly", "no_write", "dry_run"}:
        return False, f"{tool} blocked by read_only approval_mode"
    if tool == "repo_command":
        command = str(args.get("command") or "")
        if mode in {"read_only", "readonly", "no_write", "dry_run"} and dangerous_command(command):
            return False, "dangerous repo_command blocked by read_only approval_mode"
    return True, ""
def planner_history_ledger(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ledger: list[dict[str, Any]] = []

    for item in history:
        if not isinstance(item, dict):
            continue

        decision = item.get("decision") if isinstance(item.get("decision"), dict) else {}
        result = item.get("tool_result") if isinstance(item.get("tool_result"), dict) else {}

        row: dict[str, Any] = {
            "step": item.get("step"),
            "action": decision.get("action"),
            "tool": result.get("tool") or decision.get("tool"),
            "ok": result.get("ok"),
            "reason": str(decision.get("reason") or "")[:600],
            "path": result.get("path"),
            "paths": result.get("paths"),
            "count": result.get("count"),
            "returncode": result.get("returncode"),
            "artifact": result.get("artifact"),
        }

        if isinstance(result.get("matches"), list):
            row["match_count"] = len(result.get("matches") or [])
            row["matches_preview"] = result.get("matches", [])[:8]
        if isinstance(result.get("entries"), list):
            row["entry_count"] = len(result.get("entries") or [])
            row["entries_preview"] = [
                {
                    "path": sub.get("path"),
                    "kind": sub.get("kind"),
                    "size_bytes": sub.get("size_bytes"),
                }
                for sub in result.get("entries", [])[:30]
                if isinstance(sub, dict)
            ]
        if isinstance(result.get("paths"), list):
            row["path_count"] = len(result.get("paths") or [])
            row["paths_preview"] = result.get("paths", [])[:30]
        if isinstance(result.get("entries"), list):
            row["entry_count"] = len(result.get("entries") or [])
            row["entries_preview"] = [
                {
                    "path": sub.get("path"),
                    "kind": sub.get("kind"),
                    "size_bytes": sub.get("size_bytes"),
                }
                for sub in result.get("entries", [])[:20]
                if isinstance(sub, dict)
            ]
        if isinstance(result.get("items"), list):
            row["items"] = [
                {
                    "path": sub.get("path"),
                    "line_count": sub.get("line_count"),
                    "truncated": sub.get("truncated"),
                }
                for sub in result.get("items", [])[:8]
                if isinstance(sub, dict)
            ]

        ledger.append({k: v for k, v in row.items() if v not in (None, "", [], {})})

    return ledger


def planner_last_result_digest(last_tool_result: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(last_tool_result, dict):
        return {}

    digest = {
        "tool": last_tool_result.get("tool"),
        "ok": last_tool_result.get("ok"),
        "path": last_tool_result.get("path"),
        "count": last_tool_result.get("count"),
        "returncode": last_tool_result.get("returncode"),
        "artifact": last_tool_result.get("artifact"),
        "stderr_tail": str(last_tool_result.get("stderr_tail") or "")[:800],
        "stdout_tail": str(last_tool_result.get("stdout_tail") or "")[:800],
    }
    if isinstance(last_tool_result.get("paths"), list):
        digest["path_count"] = len(last_tool_result.get("paths") or [])
        digest["paths_preview"] = last_tool_result.get("paths", [])[:30]
    if isinstance(last_tool_result.get("matches"), list):
        digest["match_count"] = len(last_tool_result.get("matches") or [])
        digest["matches_preview"] = last_tool_result.get("matches", [])[:10]
    if isinstance(last_tool_result.get("entries"), list):
        digest["entry_count"] = len(last_tool_result.get("entries") or [])
        digest["entries_preview"] = [
            {
                "path": item.get("path"),
                "kind": item.get("kind"),
                "size_bytes": item.get("size_bytes"),
            }
            for item in last_tool_result.get("entries", [])[:30]
            if isinstance(item, dict)
        ]
    if isinstance(last_tool_result.get("entries"), list):
        digest["entry_count"] = len(last_tool_result.get("entries") or [])
        digest["entries_preview"] = [
            {
                "path": item.get("path"),
                "kind": item.get("kind"),
                "size_bytes": item.get("size_bytes"),
            }
            for item in last_tool_result.get("entries", [])[:20]
            if isinstance(item, dict)
        ]    
    if isinstance(last_tool_result.get("items"), list):
        digest["items"] = [
            {
                "path": item.get("path"),
                "line_count": item.get("line_count"),
                "truncated": item.get("truncated"),
            }
            for item in last_tool_result.get("items", [])[:8]
            if isinstance(item, dict)
        ]
    
    return {k: v for k, v in digest.items() if v not in (None, "", [], {})}
def coerce_path_search_to_read(decision: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(decision, dict):
        return decision

    tool = normalize_tool_name(str(decision.get("tool") or ""))
    args = decision.get("arguments") if isinstance(decision.get("arguments"), dict) else {}

    if tool != "repo_search":
        return decision

    query = str(args.get("query") or "").strip().strip("\"'")
    path = str(args.get("path") or "").strip().strip("\"'")

    candidates = []
    if query:
        candidates.append(query)
    if path and query:
        candidates.append(str(Path(path) / query))

    for raw in candidates:
        normalized = raw.replace("\\", "/").lstrip("./")
        if not normalized.endswith((".py", ".ps1", ".md", ".json", ".toml", ".yml", ".yaml")):
            continue

        try:
            rel = safe_rel_path(normalized)
            full = (LAB_REPO / rel).resolve(strict=False)
            full.relative_to(LAB_REPO)
        except Exception:
            continue

        if full.exists() and full.is_file():
            fixed = dict(decision)
            fixed["tool"] = "repo_read"
            fixed["arguments"] = {"path": rel}
            fixed["reason"] = (
                "Deterministic 3572 repair: planner selected repo_search for an existing file path; "
                "converted to repo_read."
            )
            fixed["coerced_by_3572"] = "repo_search_existing_file_to_repo_read"
            return fixed

    return decision
def coerce_path_search_to_read(decision: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(decision, dict):
        return decision

    tool = normalize_tool_name(str(decision.get("tool") or ""))
    args = decision.get("arguments") if isinstance(decision.get("arguments"), dict) else {}

    if tool != "repo_search":
        return decision

    query = str(args.get("query") or "").strip().strip("\"'")
    path = str(args.get("path") or "").strip().strip("\"'")

    candidates: list[str] = []

    if query:
        candidates.append(query)

    if path and query:
        candidates.append(str(Path(path.replace("\\", "/")) / query.replace("\\", "/")))

    for raw in candidates:
        normalized = raw.replace("\\", "/").lstrip("./")

        if not normalized.endswith((".py", ".ps1", ".md", ".json", ".toml", ".yml", ".yaml", ".txt")):
            continue

        try:
            rel = safe_rel_path(normalized)
            full = (LAB_REPO / rel).resolve(strict=False)
            full.relative_to(LAB_REPO)
        except Exception:
            continue

        if full.exists() and full.is_file():
            fixed = dict(decision)
            fixed["tool"] = "repo_read"
            fixed["arguments"] = {"path": rel}
            fixed["reason"] = (
                "Deterministic 3572 repair: planner selected repo_search for an existing file path; "
                "converted to repo_read."
            )
            fixed["coerced_by_3572"] = "repo_search_existing_file_to_repo_read"
            return fixed

    return decision
def repeated_tool_call_count(history: list[dict[str, Any]], tool: str, args: dict[str, Any]) -> int:
    wanted = json.dumps(
        {
            "tool": normalize_tool_name(tool),
            "arguments": args,
        },
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )

    count = 0
    for item in history:
        decision = item.get("decision") if isinstance(item, dict) else {}
        if not isinstance(decision, dict):
            continue

        current = json.dumps(
            {
                "tool": normalize_tool_name(str(decision.get("tool") or "")),
                "arguments": decision.get("arguments") if isinstance(decision.get("arguments"), dict) else {},
            },
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )

        if current == wanted:
            count += 1

    return count
def compact_history_for_role_repair(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compact: list[dict[str, Any]] = []

    for item in history:
        if not isinstance(item, dict):
            continue

        decision = item.get("decision") if isinstance(item.get("decision"), dict) else {}
        result = item.get("tool_result") if isinstance(item.get("tool_result"), dict) else {}

        row: dict[str, Any] = {
            "step": item.get("step"),
            "decision_action": decision.get("action"),
            "decision_tool": decision.get("tool"),
            "decision_reason": str(decision.get("reason") or "")[:500],
            "result_tool": result.get("tool"),
            "result_ok": result.get("ok"),
            "result_path": result.get("path"),
            "result_count": result.get("count"),
            "result_returncode": result.get("returncode"),
            "artifact": result.get("artifact"),
        }

        if isinstance(result.get("items"), list):
            row["items"] = [
                {
                    "path": sub.get("path"),
                    "line_count": sub.get("line_count"),
                    "truncated": sub.get("truncated"),
                }
                for sub in result.get("items", [])[:8]
                if isinstance(sub, dict)
            ]

        if isinstance(result.get("matches"), list):
            row["match_count"] = len(result.get("matches") or [])
            row["matches_preview"] = result.get("matches", [])[:8]

        compact.append({k: v for k, v in row.items() if v not in (None, "", [], {})})

    return compact


def repair_role_boundary_planner_output(
    job_id: str,
    state: dict[str, Any],
    step: int,
    history: list[dict[str, Any]],
    raw_text: str,
) -> dict[str, Any] | None:
    goal = str(state.get("goal") or "")
    repair_payload = {
        "job_id": job_id,
        "goal": goal,
        "step": step,
        "history": compact_history_for_role_repair(history),
        "bad_output": raw_text[:6000],
        "repair_contract": {
            "task": "Convert the bad_output into exactly one valid planner JSON decision.",
            "allowed_actions": ["tool", "final", "block"],
            "allowed_tools": [
                "repo_status",
                "repo_tree",
                "repo_list_files",
                "repo_search",
                "repo_read",
                "repo_apply_patch",
                "repo_validate",
                "repo_command",
                "repo_capabilities",
            ],
            "rules": [
                "Do not emit Human:, Assistant:, User:, <|endoftext|>, <|im_start|>, <|im_end|>.",
                "Do not continue the transcript.",
                "If bad_output says to read/examine a known file and that file is not already read, choose repo_read.",
                "If enough evidence exists, choose final and provide final_answer.",
                "If no safe progress is possible, choose block.",
                "Return only JSON. No markdown.",
            ],
        },
    }

    repair_system = (
        "Sei il repair pass del planner 11434. Devi correggere un output contaminato da role boundary. "
        "Non sei un fallback operativo e non devi inventare. "
        "Rispondi solo con JSON valido: "
        "{\"action\":\"tool|final|block\",\"tool\":\"...\",\"arguments\":{},\"reason\":\"...\",\"final_answer\":\"...\"}. "
        "Non usare markdown, non usare testo libero, non emettere Human/Assistant/<|endoftext|>."
    )

    append_agent_event(
        job_id,
        "planner_role_boundary_repair_started",
        "Planner emitted role-boundary contaminated text; starting local 11434 repair decision.",
        {
            "raw_preview": raw_text[:1000],
            "history_count": len(history),
        },
        step=step,
    )

    repair_stream_path = agent_job_planner_stream_dir(job_id) / f"step-{int(step):03d}-role-repair.txt"

    response = post_json_stream_to_file(
        PLANNER_URL,
        {
            "model": PLANNER_MODEL,
            "stream": False,
            "keep_alive": OLLAMA_KEEP_ALIVE,
            "think": False,
            "messages": [
                {"role": "system", "content": repair_system},
                {"role": "user", "content": json.dumps(repair_payload, ensure_ascii=False, indent=2, default=str)},
            ],
            "options": {
                "temperature": float(os.environ.get("AICARMINE_AGENTIC_PLANNER_TEMPERATURE", "0")),
                "num_ctx": AGENTIC_PLANNER_NUM_CTX,
                "num_predict": AGENTIC_PLANNER_NUM_PREDICT,
            },
        },
        timeout=AGENTIC_PLANNER_FORCED_DECISION_TIMEOUT,
        job_id=job_id,
        step=step,
        stream_path=repair_stream_path,
    )
    if response.get("planner_degenerate_output"):
        return {
            "action": "block",
            "reason": "planner stream degenerate output",
            "final_answer": (
                "Il planner 11434 ha prodotto output degenerato/ripetitivo/non JSON durante lo stream. "
                "3572 ha interrotto lo step e NON ha inviato il testo a 11435/Vulkan."
            ),
            "backend_response": response,
        }
    if response.get("backend_unreachable") or response.get("backend_timeout"):
        append_agent_event(
            job_id,
            "planner_role_boundary_repair_failed",
            "Role-boundary repair failed because planner backend errored/timed out.",
            response,
            step=step,
        )
        return None

    message = response.get("message") if isinstance(response.get("message"), dict) else {}
    repaired_text = str(message.get("content") or response.get("response") or "")
    repaired = extract_json_object(repaired_text)

    if not repaired:
        append_agent_event(
            job_id,
            "planner_role_boundary_repair_failed",
            "Role-boundary repair emitted non-JSON.",
            {
                "repair_text_preview": repaired_text[:2000],
                "stream_path": response.get("stream_path"),
            },
            step=step,
        )
        return None

    action = str(repaired.get("action") or "").strip().lower()
    if action not in {"tool", "final", "block"}:
        append_agent_event(
            job_id,
            "planner_role_boundary_repair_failed",
            "Role-boundary repair emitted invalid action.",
            repaired,
            step=step,
        )
        return None

    if action == "tool":
        tool = normalize_tool_name(str(repaired.get("tool") or ""))
        if tool not in VALID_INTERNAL_TOOLS or tool == "vulkan_helper":
            append_agent_event(
                job_id,
                "planner_role_boundary_repair_failed",
                "Role-boundary repair emitted invalid tool.",
                repaired,
                step=step,
            )
            return None

        if not isinstance(repaired.get("arguments"), dict):
            repaired["arguments"] = {}

    repaired["repaired_from_role_boundary_contamination"] = True
    repaired["raw_planner_text_preview"] = raw_text[:2000]

    append_agent_event(
        job_id,
        "planner_role_boundary_repair_succeeded",
        f"Role-boundary repair produced action={repaired.get('action')} tool={repaired.get('tool', '')}",
        repaired,
        step=step,
    )

    return repaired
def planner_done_token(raw_text: str) -> bool:
    text = str(raw_text or "").strip().strip("` \r\n\t.。").lower()
    return text in {
        "done",
        "completed",
        "complete",
        "finished",
        "terminato",
        "completato",
        "fatto",
        "eseguito",
        "выполнено",
    }


def goal_has_write_intent(goal: str) -> bool:
    text = str(goal or "").lower()
    return any(
        token in text
        for token in (
            "applica",
            "applicare",
            "patch",
            "modifica",
            "modificare",
            "scrivi",
            "write",
            "apply",
            "edit",
            "change",
        )
    )


def history_has_tool(history: list[dict[str, Any]], tool_name: str) -> bool:
    for item in history:
        result = item.get("tool_result") if isinstance(item, dict) else {}
        decision = item.get("decision") if isinstance(item, dict) else {}
        if isinstance(result, dict) and result.get("tool") == tool_name:
            return True
        if isinstance(decision, dict) and decision.get("tool") == tool_name:
            return True
    return False


def summarize_history_artifacts(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    for item in history:
        if not isinstance(item, dict):
            continue
        result = item.get("tool_result") if isinstance(item.get("tool_result"), dict) else {}
        if not result:
            continue
        artifact = result.get("artifact")
        tool = result.get("tool")
        if artifact or tool:
            artifacts.append(
                {
                    "step": item.get("step"),
                    "tool": tool,
                    "ok": result.get("ok"),
                    "artifact": artifact,
                    "path": result.get("path"),
                    "count": result.get("count"),
                }
            )
    return artifacts[-10:]
def planner_decision(job_id: str, state: dict[str, Any], step: int, history: list[dict[str, Any]]) -> dict[str, Any]:
    goal = str(state.get("goal") or "")
    tool_manifest = planner_tools_manifest()
    system = (
        "Sei il planner principale 30B dell'agente locale AI-Carmine. Il runtime controllato eseguira' i tool; "
        "tu devi scegliere il prossimo passo operativo. Rispondi SOLO con JSON valido. Non usare markdown. "
        "Azioni consentite: tool, final, block. "
        "CONTRATTO DI CHIUSURA: quando hai abbastanza evidenza devi rispondere con action='final' e final_answer completo. "
        "Rispondi SOLO con JSON valido. Non usare markdown. "
        "Lavora in sequenza: dopo ogni tool_result valuta l'evidenza ottenuta e decidi se serve un altro tool mirato. "
        "Non chiudere con final se l'evidenza e' generica, se hai letto zero file rilevanti, o se hai solo status/search non conclusivi. "
        "Per modificare file devi prima avere evidenza da repo_read o old_text esatto. "
        "Per richieste naturali tipo 'mostra/stampa/lista i primi N file Python/core/.py' usa repo_list_files, non repo_search e non repo_tree. "
        "repo_search serve per cercare testo/simboli nel contenuto dei file, non per glob come *.py. "
        "Per modificare file esistenti preferisci repo_apply_patch con old_text esatto letto da repo_read. "
        "Se ricevi nella history un tool_result con tool='controller_guard', devi correggere il comportamento indicato: "
        "non ripetere la stessa tool-call, non chiudere final senza patch quando il goal chiede patch, "
        "e scegli il prossimo passo operativo valido. "
        "Usa repo_write_file solo per creare nuovi file, test, documentazione o piccoli helper, oppure per overwrite esplicito in LAB_REPO. "
        "Dopo ogni repo_apply_patch o repo_write_file devi chiamare repo_validate o repo_command con una validazione pertinente. "
        "Puoi usare repo_command per comandi lab-safe come rg, git diff --check, python -m compileall, pytest, ninja, cmake, powershell -File, o validazioni locali. "
        "Non usare comandi distruttivi come git reset, git clean, git push, git commit, merge/rebase o cancellazioni senza consenso esplicito. "
        "Usa repo_apply_patch solo con path, old_text esatto e new_text. "
        "Usa repo_validate dopo una modifica. Non inventare file, path o risultati. "
        "CONTRATTO DI TEMPO: ogni chiamata planner deve produrre una decisione JSON entro il timeout operativo. "
        "Se serve approfondire, scegli subito action='tool'. "
        "Se l'evidenza è sufficiente, scegli subito action='final'. "
        "Se mancano dati indispensabili o la richiesta è ambigua, scegli action='block'. "
        "Non restare in ragionamento aperto e non attendere altri input dentro la stessa chiamata. "
        "Se un tool_result e' vuoto o non conclusivo, scegli un altro tool o una query migliore invece di finalizzare. "
        "Se la richiesta contiene 'proponi patch' il final_answer deve contenere una sezione PATCH_PLAN. "
        "PATCH_PLAN deve includere: target_file, problema verificato, modifica proposta, rischio, validazione consigliata. "
        "Se non hai abbastanza evidenza per una patch, non finalizzare: leggi il file principale rilevante con repo_read. "
        "Non proporre refactoring generico senza nominare file e funzioni lette realmente. "
        "Non leggere __init__.py come file principale di analisi salvo richiesta esplicita o salvo che contenga logica reale; preferisci cli.py, runner.py, provider.py, executor.py, common.py. "
    )
    last_step = history[-1] if history else {}
    last_tool_result = last_step.get("tool_result") if isinstance(last_step, dict) else {}
    history_ledger = planner_history_ledger(history)
    user_payload = {
        "job_id": job_id,
        "goal": goal,
        "approval_mode": state.get("approval_mode"),
        "write_policy": {
            "lab_repo_only": str(LAB_REPO),
            "can_write": str(state.get("approval_mode") or "safe_write_lab").lower() not in {"read_only", "readonly", "no_write", "dry_run"},
            "preferred_existing_file_edit_tool": "repo_apply_patch",
            "preferred_new_file_tool": "repo_write_file",
            "must_validate_after_write": True,
        },
        "max_steps": state.get("max_steps"),
        "current_step": step,
        "lab_repo": str(LAB_REPO),
        "available_tools": tool_manifest,
        "history": history_ledger,
        "history_count": len(history),
        "last_tool_result": planner_last_result_digest(last_tool_result),
        "artifact_policy": {
            "rule": "Full tool outputs are stored in artifact files. Use artifact paths for reference; do not require raw blobs in planner context.",
            "closure": "When evidence in history is sufficient, return action=final with final_answer.",
        },
        "sequential_tool_policy": {
            "goal": "Use one tool per step, inspect the result in the next step, then decide whether to continue.",
            "continue_when": [
                "a write was performed and validation has not run yet",
                "the user asked to apply/correct/implement/write and only a patch plan has been produced",
                "the last tool result is empty or inconclusive",
                "the request is broad and only repo_status/search evidence exists",
                "a relevant file path was found but not read yet",
                "a patch is requested but old_text/new_text evidence is missing",
                "a patch was applied and validation has not run yet",
                "a repo_search found a main implementation file such as cli.py, runner.py, provider.py, executor.py and it has not been read yet",
            ],
            "final_allowed_when": [
                "you have enough concrete evidence from tool results",
                "you can name the relevant file paths or explain why none were found",
                "for proposal-only patch/refactor tasks, you have produced a patch plan",
                "for apply/correct/implement/write tasks, you have applied the change and run validation",
            ],
            "avoid": [
                "do not repeat the exact same repo_search query unless the previous result was truncated",
                "do not final after a single generic status result for broad repo-analysis tasks",
                "do not invent files not present in tool results",
                "do not repeat the same repo_search query if it already returned the same relevant file list; read the main file instead",
            ],
        },
        "required_response_schema": {
            "action": "tool|final|block",
            "tool": "repo_status|repo_tree|repo_list_files|repo_search|repo_read|repo_apply_patch|repo_validate|repo_command|repo_capabilities|repo_write_file",
            "arguments": {},
            "reason": "short operational reason explaining why this is the next step after the previous tool result",
            "final_answer": (
                "required when action=final or block. "
                "For refactoring/patch requests, include PATCH_PLAN with target_file, verified_problem, proposed_change, risk, validation."
            ),
        },
    }
    planner_payload = {
        "model": PLANNER_MODEL,
        "stream": False,
        "keep_alive": OLLAMA_KEEP_ALIVE,
        "think": False,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False, indent=2, default=str)},
        ],
        "options": {
            "temperature": float(os.environ.get("AICARMINE_AGENTIC_PLANNER_TEMPERATURE", "0")),
            "num_ctx": AGENTIC_PLANNER_NUM_CTX,
            "num_predict": AGENTIC_PLANNER_NUM_PREDICT,
        },
    }

    append_agent_event(
        job_id,
        "planner_request_started",
        f"Planner 11434 request started. Timeout={AGENTIC_PLANNER_STEP_TIMEOUT}s.",
        {
            "planner_url": PLANNER_URL,
            "planner_model": PLANNER_MODEL,
            "step_timeout_seconds": AGENTIC_PLANNER_STEP_TIMEOUT,
            "num_ctx": AGENTIC_PLANNER_NUM_CTX,
            "num_predict": AGENTIC_PLANNER_NUM_PREDICT,
            "history_count": len(history),
        },
        step=step,
    )

    planner_stream_path = agent_job_planner_stream_path(job_id, step)

    response = post_json_stream_to_file(
        PLANNER_URL,
        planner_payload,
        timeout=AGENTIC_PLANNER_STEP_TIMEOUT,
        job_id=job_id,
        step=step,
        stream_path=planner_stream_path,
    )

    if response.get("planner_degenerate_output"):
        partial = str(response.get("partial_content") or "")

        decoded_partial = extract_json_object(partial)
        if decoded_partial:
            decoded_partial["recovered_by_3572"] = "degenerate_stream_partial_json"
            decoded_partial["planner_stream_error"] = response.get("error")
            decoded_partial.setdefault("raw_planner_text_preview", partial[:2000])
            return decoded_partial

        recovered = recover_plaintext_file_intent(partial)
        if recovered:
            recovered["planner_stream_error"] = response.get("error")
            return recovered

        return {
            "action": "block",
            "reason": f"planner stream degenerate output: {response.get('error')}",
            "final_answer": (
                "Il planner 11434 ha prodotto output degenerato/non JSON non recuperabile. "
                "3572 ha interrotto lo step senza inviare il testo a 11435/Vulkan."
            ),
            "backend_response": response,
            "raw_planner_text": partial[:4000],
        }

    if response.get("backend_timeout"):
        append_agent_event(
            job_id,
            "planner_timeout",
            f"Planner 11434 timed out after {AGENTIC_PLANNER_STEP_TIMEOUT}s. Forcing immediate decision retry.",
            {
                "planner_url": PLANNER_URL,
                "planner_model": PLANNER_MODEL,
                "error": response.get("error"),
                "error_type": response.get("error_type"),
            },
            step=step,
        )

        forced_payload = dict(user_payload)
        forced_payload["forced_decision_after_timeout"] = {
            "rule": "You must now answer with exactly one JSON object.",
            "allowed_actions": ["tool", "final", "block"],
            "tool_when": "Choose tool if one more repository action is needed.",
            "final_when": "Choose final if current evidence is enough.",
            "block_when": "Choose block only if the task cannot progress safely.",
            "no_prose": True,
            "no_markdown": True,
        }

        forced_system = (
            system
            + " DECISIONE FORZATA: la richiesta precedente ha superato il timeout. "
            "Ora devi rispondere immediatamente SOLO JSON valido con action='tool', action='final' oppure action='block'. "
            "Non ragionare in testo libero. Non usare markdown."
        )

        append_agent_event(
            job_id,
            "planner_forced_decision_started",
            f"Forced planner decision started. Timeout={AGENTIC_PLANNER_FORCED_DECISION_TIMEOUT}s.",
            {
                "planner_url": PLANNER_URL,
                "planner_model": PLANNER_MODEL,
                "forced_timeout_seconds": AGENTIC_PLANNER_FORCED_DECISION_TIMEOUT,
            },
            step=step,
        )

        forced_planner_payload = {
            "model": PLANNER_MODEL,
            "stream": False,
            "keep_alive": OLLAMA_KEEP_ALIVE,
            "think": False,
            "messages": [
                {"role": "system", "content": forced_system},
                {"role": "user", "content": json.dumps(forced_payload, ensure_ascii=False, indent=2, default=str)},
            ],
            "options": {
                "temperature": float(os.environ.get("AICARMINE_AGENTIC_PLANNER_TEMPERATURE", "0")),
                "num_ctx": AGENTIC_PLANNER_NUM_CTX,
                "num_predict": AGENTIC_PLANNER_NUM_PREDICT,
            },
        }

        forced_stream_path = agent_job_planner_stream_path(job_id, step, "forced")

        response = post_json_stream_to_file(
            PLANNER_URL,
            forced_planner_payload,
            timeout=AGENTIC_PLANNER_FORCED_DECISION_TIMEOUT,
            job_id=job_id,
            step=step,
            stream_path=forced_stream_path,
        )
        if response.get("planner_degenerate_output"):
            return {
                "action": "block",
                "reason": f"planner forced stream degenerate output: {response.get('error')}",
                "final_answer": (
                    "Il planner 11434 ha prodotto output degenerato anche nella decisione forzata. "
                    "3572 ha bloccato il job senza usare fallback operativo GPU0."
                ),
                "backend_response": response,
                "raw_planner_text": str(response.get("partial_content") or "")[:4000],
            }
    if response.get("backend_unreachable") or response.get("backend_timeout"):
        return {
            "action": "block",
            "reason": "planner backend timeout_or_error",
            "final_answer": (
                f"Planner 30B non ha prodotto una decisione valida entro i timeout configurati "
                f"su {PLANNER_URL}: {response.get('error')}. "
                "Nessun fallback operativo GPU0 è stato usato."
            ),
            "backend_response": response,
        }
    message = response.get("message") if isinstance(response.get("message"), dict) else {}
    raw_text = str(message.get("content") or response.get("response") or "")
    if planner_done_token(raw_text):
        if goal_has_write_intent(goal) and not history_has_tool(history, "repo_apply_patch"):
            return {
                "action": "block",
                "reason": "planner emitted done token without applying requested patch",
                "final_answer": (
                    "Il planner 11434 ha emesso un token di completamento senza JSON "
                    f"({raw_text.strip()!r}), ma il goal richiedeva una modifica/patch e nella history "
                    "non risulta alcun repo_apply_patch. Il job è stato bloccato per evitare una falsa chiusura."
                ),
                "history_artifacts": summarize_history_artifacts(history),
                "raw_planner_text": raw_text[:1000],
            }

        return {
            "action": "final",
            "final_answer": (
                "Il planner 11434 ha emesso un token di completamento senza JSON "
                f"({raw_text.strip()!r}). 3572 ha chiuso il job usando la history dei tool già eseguiti. "
                "Controllare gli artifact per i dettagli."
            ),
            "history_artifacts": summarize_history_artifacts(history),
            "raw_planner_text": raw_text[:1000],
        }
    decision = normalize_planner_decision(raw_text, goal, step, state)
    decision.setdefault("raw_planner_text_preview", raw_text[:2000])
    return decision
def finalize_agentic_job(job_id: str, state: dict[str, Any], status: str, final_summary: str, result: dict[str, Any] | None = None) -> dict[str, Any]:
    root = agent_job_root(job_id)
    final = {
        "ok": status == "completed",
        "job_id": job_id,
        "status": status,
        "goal": state.get("goal"),
        "final_summary": final_summary,
        "result": result or {},
        "events_path": str(agent_job_events_path(job_id)),
    }
    write_json(root / "final.json", final)
    (root / "final.md").write_text(final_summary, encoding="utf-8")
    state = load_agent_job_state(job_id) or state
    state["status"] = status
    state["final_path"] = str(root / "final.json")
    state["final_markdown_path"] = str(root / "final.md")
    state["final_summary"] = final_summary[:12000]
    state["result"] = result or {}
    write_agent_job_state(state)
    append_agent_event(job_id, "job_finished", f"Agentic job finished with status={status}.", {"status": status}, step=state.get("current_step"))
    return final

def recoverable_planner_block(decision: dict[str, Any]) -> bool:
    reason = str(decision.get("reason") or "").lower()
    final_answer = str(decision.get("final_answer") or "").lower()
    raw_text = str(decision.get("raw_planner_text") or decision.get("raw_planner_text_preview") or "").lower()

    markers = (
        "planner stream degenerate output",
        "planner forced stream degenerate output",
        "planner emitted non-repairable non-json output",
        "no_json_object_candidate",
        "dead_or_stop_token_output",
        "role_boundary_marker",
        "role-boundary",
        "<|endoftext|>",
        ".readbyte",
    )

    return any(marker in reason or marker in final_answer or marker in raw_text for marker in markers)


def controller_guard_count(history: list[dict[str, Any]], kind: str) -> int:
    count = 0
    for item in history:
        result = item.get("tool_result") if isinstance(item, dict) else {}
        if not isinstance(result, dict):
            continue
        if result.get("tool") == "controller_guard" and kind in str(result.get("summary") or ""):
            count += 1
    return count
def extract_existing_goal_path(goal: str) -> str:
    text = str(goal or "")
    candidates = re.findall(
        r"([A-Za-z0-9_./\\-]+?\.(?:py|ps1|md|json|toml|yml|yaml|txt))",
        text,
    )

    for candidate in candidates:
        normalized = candidate.replace("\\", "/").lstrip("./")
        try:
            rel = safe_rel_path(normalized)
            full = (LAB_REPO / rel).resolve(strict=False)
            full.relative_to(LAB_REPO)
        except Exception:
            continue

        if full.exists() and full.is_file():
            return rel

    return ""
def run_agentic_planner_job(job_id: str) -> dict[str, Any]:
    state = load_agent_job_state(job_id)
    if not state:
        return {"ok": False, "error": "job_not_found", "job_id": job_id}
    root = agent_job_root(job_id)
    max_steps = max(1, min(int(state.get("max_steps") or AGENT_DEFAULT_MAX_STEPS), AGENT_MAX_STEPS))
    approval_mode = str(state.get("approval_mode") or "safe_write_lab")
    original_args = dict(state.get("original_args") or {})
    public_tool_name = str(state.get("public_tool_name") or "vulkan_helper")
    history: list[dict[str, Any]] = []

    state["status"] = "running_agentic"
    state["planner_url"] = PLANNER_URL
    state["planner_model"] = PLANNER_MODEL
    state["selector_url"] = OLLAMA_TASK_URL
    state["selector_model"] = OLLAMA_TASK_MODEL
    write_agent_job_state(state)
    append_agent_event(
        job_id,
        "agentic_loop_started",
        "Started controlled 30B planner loop. 11435/Vulkan repairs malformed planner tool-calls only; it is not planner and not operational fallback.",
        {"planner_url": PLANNER_URL, "planner_model": PLANNER_MODEL, "max_steps": max_steps},
        step=0,
    )

    for step in range(1, max_steps + 1):
        state = load_agent_job_state(job_id) or state
        if str(state.get("status") or "") == "cancel_requested":
            return finalize_agentic_job(job_id, state, "cancelled", "Job cancelled by user.", {"history": history})
        state["current_step"] = step
        state["status_message"] = "planning next action"
        write_agent_job_state(state)
        if step == 1:
            goal_path = extract_existing_goal_path(str(state.get("goal") or ""))
            if goal_path:
                decision = {
                    "action": "tool",
                    "tool": "repo_read",
                    "arguments": {"path": goal_path},
                    "reason": "Deterministic 3572 controller: goal contains an existing repo file path; read it before planning patch.",
                    "selected_by_3572": "initial_goal_path_read",
                }
            else:
                decision = planner_decision(job_id, state, step, history)
        else:
            decision = planner_decision(job_id, state, step, history)
        decision = planner_decision(job_id, state, step, history)
        if decision.get("recovered_by_3572"):
            append_agent_event(
                job_id,
                "planner_plaintext_recovered",
                f"3572 recovered planner plaintext into {decision.get('tool')}.",
                {
                    "recovered_by_3572": decision.get("recovered_by_3572"),
                    "tool": decision.get("tool"),
                    "arguments": decision.get("arguments"),
                    "raw_planner_text": str(decision.get("raw_planner_text") or "")[:1000],
                },
                step=step,
            )
        append_agent_event(job_id, "planner_decision", f"Planner decision: {decision.get('action')} {decision.get('tool', '')}", decision, step=step)

        action = str(decision.get("action") or "tool").strip().lower()
        if action in {"final", "done", "complete", "completed"}:
            if goal_has_write_intent(state.get("goal") or "") and not history_has_tool(history, "repo_apply_patch"):
                append_agent_event(
                    job_id,
                    "final_blocked_missing_patch",
                    "Planner tried to finalize a write/patch task without repo_apply_patch.",
                    {
                        "goal": state.get("goal"),
                        "history_artifacts": summarize_history_artifacts(history),
                    },
                    step=step,
                )
                if goal_has_write_intent(state.get("goal") or "") and not history_has_tool(history, "repo_apply_patch"):
                    append_agent_event(
                        job_id,
                        "planner_final_rejected_missing_patch",
                        "Planner tried to finalize a write/refactor task without repo_apply_patch; continuing loop.",
                        {
                            "goal": state.get("goal"),
                            "final_answer_preview": final_answer[:2000],
                        },
                        step=step,
                    )

                    history.append({
                        "step": step,
                        "decision": {
                            "action": "continue_required",
                            "reason": "final rejected because patch/refactor was requested but repo_apply_patch was not executed",
                            "final_answer_preview": final_answer[:2000],
                        },
                        "tool_result": {
                            "tool": "controller_guard",
                            "ok": True,
                            "summary": (
                                "The user requested a structural refactor/patch. You may not final yet. "
                                "Choose repo_read if exact old_text is missing, repo_apply_patch if old_text/new_text are available, "
                                "repo_validate after applying, or block only if no safe patch can be produced."
                            ),
                        },
                    })

                    state["history"] = planner_history_ledger(history)
                    state["history_count"] = len(history)
                    write_agent_job_state(state)
                    continue
                return finalize_agentic_job(
                    job_id,
                    state,
                    "blocked_needs_attention",
                    (
                        "Il planner ha provato a chiudere un task che richiedeva patch/modifica, "
                        "ma non risulta alcun repo_apply_patch nella history. Chiusura bloccata."
                    ),
                    {"history": history, "planner_decision": decision},
                )            
            final_answer = str(decision.get("final_answer") or decision.get("answer") or decision.get("summary") or "Job completed.")
            if goal_has_write_intent(state.get("goal") or "") and not history_has_tool(history, "repo_apply_patch"):
                append_agent_event(
                    job_id,
                    "planner_final_rejected_missing_patch",
                    "Planner tried to finalize a write task without repo_apply_patch; continuing loop.",
                    {
                        "goal": state.get("goal"),
                        "final_answer_preview": final_answer[:2000],
                    },
                    step=step,
                )

                history.append({
                    "step": step,
                    "decision": {
                        "action": "continue_required",
                        "reason": "final rejected because patch was requested but repo_apply_patch was not executed",
                        "final_answer_preview": final_answer[:2000],
                    },
                    "tool_result": {
                        "tool": "controller_guard",
                        "ok": True,
                        "summary": (
                            "The user requested a structural patch. You may not final yet. "
                            "Choose repo_read if exact old_text is missing, repo_apply_patch if old_text/new_text are available, "
                            "or block only if no safe patch can be produced."
                        ),
                    },
                })
                state["history"] = planner_history_ledger(history)
                state["history_count"] = len(history)
                write_agent_job_state(state)
                continue
            return finalize_agentic_job(job_id, state, "completed", final_answer, {"history": history, "planner_decision": decision})
        if action in {"block", "blocked", "need_user", "needs_user"}:
            if recoverable_planner_block(decision):
                retry_count = controller_guard_count(history, "recoverable_planner_block")

                if retry_count < 2:
                    append_agent_event(
                        job_id,
                        "controller_guard_recoverable_planner_block",
                        "Planner produced recoverable bad output; injecting controller correction instead of blocking.",
                        {
                            "retry_count": retry_count,
                            "planner_reason": decision.get("reason"),
                            "raw_planner_text": str(decision.get("raw_planner_text") or decision.get("raw_planner_text_preview") or "")[:2000],
                        },
                        step=step,
                    )

                    history.append({
                        "step": step,
                        "decision": {
                            "action": "continue_required",
                            "reason": "recoverable planner block converted to controller_guard",
                            "planner_decision": {
                                k: v for k, v in decision.items()
                                if k not in {"raw_planner_text"}
                            },
                        },
                        "tool_result": {
                            "tool": "controller_guard",
                            "ok": True,
                            "summary": (
                                "recoverable_planner_block: previous planner output was invalid/non-json/degenerate, "
                                "but this is not a safety block. Continue the agentic loop. "
                                "You must now output exactly one JSON object. "
                                "If the goal contains a concrete file path, use repo_read on that path. "
                                "If old_text is known and the user asked to apply a patch, use repo_apply_patch. "
                                "If more evidence is needed, choose one targeted tool. "
                                "Do not output prose, .ReadByte, halted, done, or role-boundary text."
                            ),
                        },
                    })

                    state["history"] = planner_history_ledger(history)
                    state["history_count"] = len(history)
                    write_agent_job_state(state)
                    continue

            final_answer = str(decision.get("final_answer") or decision.get("reason") or "Job blocked by planner.")
            return finalize_agentic_job(
                job_id,
                state,
                "blocked_needs_attention",
                final_answer,
                {"history": history, "planner_decision": decision},
            )

        tool = normalize_tool_name(str(decision.get("tool") or ""))
        args = decision.get("arguments") if isinstance(decision.get("arguments"), dict) else {}
        if repeated_tool_call_count(history, tool, args) >= 2:
            append_agent_event(
                job_id,
                "planner_repeated_tool_call_rejected",
                "Planner repeated the same tool call; injecting controller correction instead of blocking.",
                {
                    "tool": tool,
                    "arguments": args,
                    "repeat_count": repeated_tool_call_count(history, tool, args),
                },
                step=step,
            )

            history.append({
                "step": step,
                "decision": {
                    "action": "continue_required",
                    "reason": "repeated tool call rejected by 3572 controller",
                    "rejected_tool": tool,
                    "rejected_arguments": args,
                },
                "tool_result": {
                    "tool": "controller_guard",
                    "ok": True,
                    "summary": (
                        "You repeated the same tool call without progress. Do not repeat it. "
                        "Use a different tool, read a specific file from prior results, apply a patch if evidence is ready, "
                        "or final if the task is complete."
                    ),
                },
            })
            state["history"] = planner_history_ledger(history)
            state["history_count"] = len(history)
            write_agent_job_state(state)
            continue
        if not tool or tool not in VALID_INTERNAL_TOOLS or tool == "vulkan_helper":
            tool = "repo_capabilities"
            args = {"reason": "planner selected missing/invalid/recursive tool", "planner_decision": decision}

        allowed, block_reason = agentic_tool_allowed(tool, args, approval_mode)
        if not allowed:
            append_agent_event(job_id, "tool_blocked", block_reason, {"tool": tool, "arguments": args}, step=step)
            return finalize_agentic_job(job_id, state, "blocked_needs_consent", block_reason, {"history": history, "blocked_tool": tool})

        internal_args = sanitize_tool_args(tool, dict(args), original_args, public_tool_name)
        state["status_message"] = f"executing {tool}"
        write_agent_job_state(state)
        append_agent_event(job_id, "tool_start", f"Executing {tool}", {"tool": tool, "arguments": internal_args}, step=step)
        result = dispatch_tool(
            tool,
            internal_args,
            root,
            allow_command=True,
            user_consent=str(original_args.get("user_consent") or state.get("user_consent") or ""),
        )
        tool_result_path = root / "tool-results" / f"step-{step:03d}-{tool}.json"
        write_json(tool_result_path, result)
        compact_result = compact_tool_result_for_planner(tool, result if isinstance(result, dict) else {"result": result})
        compact_result["artifact"] = str(tool_result_path)
        append_agent_event(job_id, "tool_result", f"{tool} ok={bool(result.get('ok'))}", compact_result, step=step)
        history.append({
            "step": step,
            "decision": {k: v for k, v in decision.items() if k != "raw_planner_text_preview"},
            "tool_result": compact_result,
        })
        state["history"] = planner_history_ledger(history)
        state["history_count"] = len(history)
        write_agent_job_state(state)

    return finalize_agentic_job(
        job_id,
        state,
        "max_steps_reached",
        f"Max steps reached ({max_steps}) before planner produced a final answer.",
        {"history": history},
    )


def agent_job_worker(job_id: str) -> None:
    state = load_agent_job_state(job_id)
    if not state:
        return
    state["status"] = "running"
    write_agent_job_state(state)
    append_agent_event(job_id, "job_started", "Background agent job started.", {"job_id": job_id}, step=0)

    try:
        if AGENTIC_PLANNER_ENABLED:
            final = run_agentic_planner_job(job_id)
            return

        run_payload = dict(state.get("request_payload") or {})
        run_args = dict(run_payload.get("arguments") or {})
        for key in ("action", "job_action", "job_id"):
            run_payload.pop(key, None)
            run_args.pop(key, None)
        run_payload["arguments"] = run_args
        run_payload["mode"] = "tool_helper"
        run_payload["session_id"] = job_id

        append_agent_event(job_id, "agent_call", "Running legacy one-shot broker pipeline in background.", {"payload_keys": sorted(run_payload.keys())}, step=1)
        result = agent(run_payload)
        root = agent_job_root(job_id)
        write_json(root / "final.json", result)
        final_summary = summary_from_result(result if isinstance(result, dict) else {"result": result})
        (root / "final.md").write_text(final_summary, encoding="utf-8")

        state = load_agent_job_state(job_id) or state
        state["status"] = "completed" if bool(result.get("ok")) else "failed"
        state["result_ok"] = bool(result.get("ok"))
        state["final_path"] = str(root / "final.json")
        state["final_markdown_path"] = str(root / "final.md")
        state["final_summary"] = final_summary[:12000]
        state["result"] = {
            "ok": bool(result.get("ok")),
            "verdict": result.get("verdict"),
            "internal_tool": ((result.get("internal_vulkan") or {}).get("tool_called_by_vulkan") if isinstance(result.get("internal_vulkan"), dict) else None),
            "artifacts": result.get("artifacts"),
        }
        write_agent_job_state(state)
        append_agent_event(job_id, "job_finished", f"Job finished with status={state['status']}.", state.get("result", {}), step=2)
    except Exception as exc:
        root = agent_job_root(job_id)
        error_text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        (root / "error.txt").write_text(error_text, encoding="utf-8")
        state = load_agent_job_state(job_id) or state
        state["status"] = "failed"
        state["error"] = error_text[-12000:]
        state["final_path"] = str(root / "error.txt")
        state["final_summary"] = f"Agent job failed: {type(exc).__name__}: {exc}"
        write_agent_job_state(state)
        append_agent_event(job_id, "job_failed", state["final_summary"], {"error_type": type(exc).__name__}, step=999)

def start_agent_job(payload: dict[str, Any], public_tool_name: str, original_args: dict[str, Any], task: str) -> dict[str, Any]:
    init_agent_job_db()
    requested_job_id = str(original_args.get("job_id") or payload.get("job_id") or "").strip()
    job_id = make_session_id(requested_job_id) if requested_job_id else make_session_id("job-" + uuid.uuid4().hex[:8])
    root = agent_job_root(job_id)
    state = {
        "job_id": job_id,
        "status": "queued",
        "goal": task,
        "public_tool_name": public_tool_name,
        "created_at": time.time(),
        "updated_at": time.time(),
        "workspace": str(root),
        "request_payload": payload,
        "original_args": original_args,
        "max_steps": int(original_args.get("max_steps") or payload.get("max_steps") or AGENT_DEFAULT_MAX_STEPS),
        "approval_mode": str(
    original_args.get("approval_mode")
    or payload.get("approval_mode")
    or os.environ.get("AICARMINE_AGENT_APPROVAL_MODE")
    or "safe_write_lab"
),
        "return_mode": str(original_args.get("return_mode") or payload.get("return_mode") or "compact"),
        "agentic_planner_enabled": AGENTIC_PLANNER_ENABLED,
        "planner_url": PLANNER_URL,
        "planner_model": PLANNER_MODEL,
        "selector_url": OLLAMA_TASK_URL,
        "selector_model": OLLAMA_TASK_MODEL,
    }
    write_agent_job_state(state)
    append_agent_event(job_id, "job_queued", "Agent job queued.", {"goal": task}, step=0)

    with AGENT_JOB_LOCK:
        existing = AGENT_JOB_BACKGROUND_THREADS.get(job_id)
        if not existing or not existing.is_alive():
            thread = threading.Thread(target=agent_job_worker, args=(job_id,), daemon=True, name=f"aicarmine-agent-job-{job_id}")
            AGENT_JOB_BACKGROUND_THREADS[job_id] = thread
            thread.start()

    started = {
        "ok": True,
        "service": "vulkan_agent",
        "mode": "agent_job_started",
        "verdict": "AGENT_JOB_STARTED",
        "tool_name": public_tool_name,
        "tool_result_for": public_tool_name,
        "operation_id": public_tool_name,
        "called_by_30b": public_tool_name,
        "job_id": job_id,
        "status": "queued",
        "workspace": str(root),
        "job_url": job_url(job_id),
        "message_for_30b": (
            f"Agent job started internally: {job_id}. "
            "The tool call will wait for a terminal state before returning to OpenWebUI."
        ),
        "summary_for_30b": f"Agent job started internally: {job_id}. Waiting for terminal state.",
        "content": f"Agent job started internally: {job_id}\nDashboard: {job_url(job_id)}",
    }

    return_mode = str(original_args.get("return_mode") or payload.get("return_mode") or "wait").strip().lower()
    wait_seconds = int(original_args.get("wait_seconds") or payload.get("wait_seconds") or AGENT_RETURN_WAIT_SECONDS)

    if return_mode in {"background", "async", "fire_and_forget"}:
        return started

    waited = wait_for_agent_terminal(job_id, wait_seconds)
    waited["started_job"] = started
    waited["job_id"] = job_id
    waited["job_url"] = job_url(job_id)
    waited["workspace"] = str(root)
    waited["tool_name"] = public_tool_name
    waited["tool_result_for"] = public_tool_name
    waited["operation_id"] = public_tool_name
    waited["called_by_30b"] = public_tool_name
    return waited

def list_agent_jobs(limit: int = 50) -> list[dict[str, Any]]:
    init_agent_job_db()
    with sqlite3.connect(str(AGENT_JOB_DB)) as db:
        db.row_factory = sqlite3.Row
        rows = db.execute(
            "SELECT job_id, status, goal, created_at, updated_at, workspace, final_path, error FROM jobs ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def post_json(url: str, payload: dict[str, Any], timeout: int = 120) -> dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except Exception as exc:
        return {
            "ok": False,
            "backend_unreachable": True,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
    try:
        decoded = json.loads(raw)
        return decoded if isinstance(decoded, dict) else {"ok": True, "data": decoded}
    except Exception as exc:
        return {"ok": False, "error_type": type(exc).__name__, "error": str(exc), "raw": raw[:4000]}
def planner_stream_repetition_reason(text: str) -> str:
    raw = str(text or "")

    poisoned_markers = (
        "<|endoftext|>",
        "<|im_start|>",
        "<|im_end|>",
        "\nHuman:",
        "\nAssistant:",
        "\nSystem:",
        "Human:",
        "Assistant:",
        "System:",
    )
    for marker in poisoned_markers:
        if marker in raw:
            return f"role_boundary_marker:{marker}"

    stripped = raw.strip().strip("` \r\n\t").lower()
    if stripped in {"halted", "temps", "stopped", "stop", "done"}:
        return f"dead_stop_token:{stripped}"

    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    if len(lines) < 3:
        return ""

    # Same line repeated.
    if len(lines) >= 3 and lines[-1] == lines[-2] == lines[-3]:
        return f"repeated_line:{lines[-1][:120]}"

    # Same block repeated, e.g. 3 import lines repeated over and over.
    max_block = min(8, len(lines) // 3)
    for block_size in range(2, max_block + 1):
        block = lines[-block_size:]
        prev1 = lines[-2 * block_size : -block_size]
        prev2 = lines[-3 * block_size : -2 * block_size]
        if block == prev1 == prev2:
            return f"repeated_block_{block_size}_lines:{' | '.join(block)[:240]}"

    # Planner must emit JSON. If it starts emitting code/imports with no JSON object,
    # stop before it wastes 11434/11435 time.
    if "{" not in raw and len(raw) > 600:
        code_markers = (
            "from ",
            "import ",
            "def ",
            "class ",
            "#!/usr/bin",
        )
        lowered = raw.lower()
        if any(marker in lowered for marker in code_markers):
            return "non_json_code_like_stream_without_object"

    return ""


def planner_stream_block_response(reason: str, content: str, stream_path: Path) -> dict[str, Any]:
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
def post_json_stream_to_file(
    url: str,
    payload: dict[str, Any],
    timeout: int,
    *,
    job_id: str,
    step: int,
    stream_path: Path,
) -> dict[str, Any]:
    started = time.time()
    chunks: list[str] = []
    guard_chunks: list[str] = []
    stream_payload = dict(payload)
    stream_payload["stream"] = True

    data = json.dumps(stream_payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )

    stream_path.parent.mkdir(parents=True, exist_ok=True)
    stream_path.write_text("", encoding="utf-8")

    append_agent_event(
        job_id,
        "planner_stream_started",
        f"Planner 11434 stream started for step {step}.",
        {
            "planner_url": url,
            "stream_path": str(stream_path),
            "timeout_seconds": timeout,
        },
        step=step,
    )

    last_progress_at = 0.0
    last_waiting_at = 0.0
    deadline = started + max(1, int(timeout or 1))
    read_timeout = max(1, min(5, int(timeout or 5)))

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
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
                            job_id,
                            "planner_stream_waiting",
                            f"Planner stream waiting for tokens. chars={sum(len(x) for x in chunks)}",
                            {
                                "stream_path": str(stream_path),
                                "chars": sum(len(x) for x in chunks),
                                "elapsed_seconds": round(now_ts - started, 3),
                                "timeout_seconds": timeout,
                            },
                            step=step,
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

                raw_path = stream_path.with_suffix(".raw.ndjson")
                thinking_path = stream_path.with_suffix(".thinking.txt")
                content_path = stream_path.with_suffix(".content.txt")
                all_path = stream_path.with_suffix(".all.txt")

                with raw_path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(item, ensure_ascii=False, default=str) + "\n")

                thinking_parts = [
                    message.get("thinking"),
                    item.get("thinking"),
                    message.get("reasoning"),
                    item.get("reasoning"),
                ]

                content_parts = [
                    message.get("content"),
                    item.get("response"),
                    item.get("content"),
                ]

                thinking_text = "".join(str(part) for part in thinking_parts if part)
                content_text = "".join(str(part) for part in content_parts if part)

                # Alcuni modelli mettono <think>...</think> dentro content.
                think_blocks = re.findall(r"<think>(.*?)</think>", content_text, flags=re.DOTALL | re.IGNORECASE)
                if think_blocks:
                    extracted_thinking = "\n\n".join(block.strip() for block in think_blocks if block.strip())
                    if extracted_thinking:
                        thinking_text += ("\n" if thinking_text else "") + extracted_thinking

                if thinking_text:
                    guard_chunks.append(thinking_text)
                    with thinking_path.open("a", encoding="utf-8") as f:
                        f.write(thinking_text)
                    with all_path.open("a", encoding="utf-8") as f:
                        f.write(thinking_text)

                if content_text:
                    chunks.append(content_text)
                    guard_chunks.append(content_text)
                    with content_path.open("a", encoding="utf-8") as f:
                        f.write(content_text)
                    with all_path.open("a", encoding="utf-8") as f:
                        f.write(content_text)

                guard_text = "".join(guard_chunks)

                decoded_now = extract_json_object(guard_text)
                if decoded_now:
                    append_agent_event(
                        job_id,
                        "planner_stream_json_detected",
                        "Planner stream produced a valid JSON object; using it before degeneration guard.",
                        {
                            "stream_path": str(stream_path),
                            "chars": len(guard_text),
                            "action": decoded_now.get("action"),
                            "tool": decoded_now.get("tool"),
                            "elapsed_seconds": round(time.time() - started, 3),
                        },
                        step=step,
                    )
                    return {
                        "ok": True,
                        "planner_json_detected": True,
                        "message": {
                            "role": "assistant",
                            "content": guard_text,
                        },
                        "response": guard_text,
                        "stream_path": str(stream_path),
                        "elapsed_seconds": round(time.time() - started, 3),
                    }

                degenerate_reason = planner_stream_repetition_reason(guard_text)
                if degenerate_reason:
                    append_agent_event(
                        job_id,
                        "planner_stream_degenerate_output",
                        f"Planner stream stopped because output became degenerate: {degenerate_reason}",
                        {
                            "stream_path": str(stream_path),
                            "reason": degenerate_reason,
                            "chars": len(guard_text),
                            "preview": guard_text[-2000:],
                        },
                        step=step,
                    )
                    return planner_stream_block_response(degenerate_reason, guard_text, stream_path)

                now_ts = time.time()
                if now_ts - last_progress_at >= 5:
                    last_progress_at = now_ts
                    append_agent_event(
                        job_id,
                        "planner_stream_progress",
                        f"Planner stream active. chars={sum(len(x) for x in chunks)}",
                        {
                            "stream_path": str(stream_path),
                            "chars": sum(len(x) for x in chunks),
                            "elapsed_seconds": round(now_ts - started, 3),
                        },
                        step=step,
                    )

                if item.get("done") is True:
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

    append_agent_event(
        job_id,
        "planner_stream_finished",
        f"Planner stream finished. chars={len(content)}",
        {
            "stream_path": str(stream_path),
            "chars": len(content),
            "elapsed_seconds": round(time.time() - started, 3),
        },
        step=step,
    )

    return {
        "ok": True,
        "message": {
            "role": "assistant",
            "content": content,
        },
        "response": content,
        "stream_path": str(stream_path),
        "raw_stream_path": str(raw_path),
        "thinking_stream_path": str(thinking_path),
        "content_stream_path": str(content_path),
        "all_stream_path": str(all_path),
        "elapsed_seconds": round(time.time() - started, 3),
    }
def ollama_options(num_predict: int | None = None) -> dict[str, Any]:
    options = {
        "temperature": float(os.environ.get("AICARMINE_VULKAN_TEMPERATURE", "0")),
        "num_ctx": int(os.environ.get("AICARMINE_VULKAN_NUM_CTX", "4096")),
    }
    if num_predict is not None:
        options["num_predict"] = int(num_predict)
    return options


def run_ps(command: str, timeout: int = COMMAND_TIMEOUT_SECONDS) -> dict[str, Any]:
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        cwd=str(LAB_REPO),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return {
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "stdout_tail": completed.stdout[-4000:],
        "stderr_tail": completed.stderr[-4000:],
    }


def safe_rel_path(value: str) -> str:
    raw = str(value or "").strip().strip("\"'").replace("\\", "/")
    if not raw:
        raise ValueError("empty path")
    if raw.startswith("/") or raw.startswith("../") or "/../" in raw or ":" in raw:
        raise ValueError(f"path must be repo-relative: {raw}")
    return raw
def repo_rel(path: Path, root: Path) -> str:
    try:
        return path.resolve(strict=False).relative_to(root.resolve(strict=False)).as_posix()
    except Exception:
        return str(path)

def dangerous_command(command: str) -> bool:
    low = command.lower()
    patterns = [
        r"\bgit\s+reset\b",
        r"\bgit\s+clean\b",
        r"\bgit\s+push\b",
        r"\bgit\s+commit\b",
        r"\bgit\s+merge\b",
        r"\bgit\s+rebase\b",
        r"\bremove-item\b",
        r"\brm\s+-",
        r"\bdel\s+",
        r"\brmdir\b",
        r"\bformat\b",
        r"\bshutdown\b",
    ]
    return any(re.search(pattern, low) for pattern in patterns)


def detect_stack() -> dict[str, Any]:
    excluded = {".git", "__pycache__", ".venv", "node_modules", "output", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
    py_count = 0
    csproj_count = 0
    sln_count = 0
    for root, dirs, files in os.walk(LAB_REPO):
        dirs[:] = [d for d in dirs if d not in excluded]
        for filename in files:
            lower = filename.lower()
            if lower.endswith(".py"):
                py_count += 1
            elif lower.endswith(".csproj"):
                csproj_count += 1
            elif lower.endswith(".sln"):
                sln_count += 1
    canonical = ["git status --short --branch", "git diff --check"]
    if py_count:
        canonical.append("python -m compileall -q ia_carmine; python -m compileall -q Tools")
    if csproj_count or sln_count:
        canonical.append("dotnet build")
    if (LAB_REPO / "package.json").exists():
        canonical.append("type package.json")
    return {
        "lab_repo": str(LAB_REPO),
        "real_repo": str(REAL_REPO),
        "python_file_count": py_count,
        "csproj_count": csproj_count,
        "sln_count": sln_count,
        "canonical_commands": canonical,
    }


def repo_capabilities(args: dict[str, Any], root: Path) -> dict[str, Any]:
    capabilities = [
        {
            "name": "repo_capabilities",
            "risk": "read_only",
            "when_to_use": "Use when the model is unsure which repo/file/tool action to call next.",
            "required_args": [],
            "example": {"function": "repo_capabilities", "request": "Quali tool repo posso usare?"},
        },
        {
            "name": "repo_status",
            "risk": "read_only",
            "when_to_use": "Use for git status, branch, diff stat, changed files, diff --check and stack detection.",
            "required_args": [],
            "example": {"function": "repo_status", "request": "Controlla stato repo e diff check"},
        },
        {
            "name": "repo_tree",
            "risk": "read_only",
            "when_to_use": "Use to list files/directories under a repo-relative path. Prefer this over repo_search when the task asks for directory structure, file inventory, key files or module layout.",
            "required_args": ["path"],
            "example": {"function": "repo_tree", "parameters": {"path": "ia_carmine/runtime/heap_context_closure", "max_depth": 2, "max_files": 200}},
        },
        {
            "name": "repo_list_files",
            "risk": "read_only",
            "when_to_use": "Use to list files by suffix/path/limit, for natural requests like 'show the first 20 Python core files'. Prefer this over repo_search for file listings and glob-like requests.",
            "required_args": [],
            "example": {
                "function": "repo_list_files",
                "parameters": {
                    "path": "ia_carmine",
                    "suffix": ".py",
                    "limit": 20,
                    "core": True,
                },
            },
        },
        {
            "name": "repo_search",
            "risk": "read_only",
            "when_to_use": "Use to find symbols, paths, functions, errors, TODO/FIXME, traceback text, docs or config keys.",
            "required_args": ["query"],
            "example": {"function": "repo_search", "parameters": {"query": "tool_calls|dispatcher|repo_read", "path": ".", "mode": "rg"}},
        },
        {
            "name": "repo_read",
            "risk": "read_only",
            "when_to_use": "Use when a repo-relative path is known and exact file content or line context is needed.",
            "required_args": ["path"],
            "example": {"function": "repo_read", "parameters": {"path": "AGENTS.md", "max_chars": 20000}},
        },
        {
            "name": "repo_apply_patch",
            "risk": "write_safe_guarded",
            "when_to_use": "Use to modify one repo-relative file by replacing exact old_text with new_text. Requires prior repo_read evidence or exact old_text from the user.",
            "required_args": ["path", "old_text", "new_text"],
            "example": {"function": "repo_apply_patch", "parameters": {"path": "docs/example.md", "old_text": "old exact block", "new_text": "new exact block", "max_replacements": 1}},
        },
        {
            "name": "repo_write_file",
            "risk": "write_safe_guarded",
            "when_to_use": (
                "Use to create, overwrite or append small repo-relative text files in LAB_REPO. "
                "Prefer repo_apply_patch for modifying existing source files when exact old_text is available."
            ),
            "required_args": ["path", "content"],
            "example": {
                "function": "repo_write_file",
                "parameters": {
                    "path": "docs/example.md",
                    "content": "# Example\n",
                    "mode": "overwrite"
                },
            },
        },
        {
            "name": "repo_validate",
            "risk": "diagnostic",
            "when_to_use": "Use after changes to run git diff --check and Python compile validation.",
            "required_args": [],
            "example": {"function": "repo_validate", "parameters": {}},
        },
        {
            "name": "repo_command",
            "risk": "diagnostic_or_write_guarded",
            "when_to_use": "Use for safe validation, compile, smoke, grep/status commands. Dangerous git/fs commands require user_consent.",
            "required_args": ["command"],
            "example": {"function": "repo_command", "parameters": {"command": "git diff --check", "timeout_seconds": 120}},
        },
        {
            "name": "vulkan_helper",
            "risk": "composite_read_helper",
            "when_to_use": "Use for generic repo analysis, problem finding, patch planning, and multi-step evidence gathering.",
            "required_args": ["task"],
            "example": {"function": "vulkan_helper", "parameters": {"task": "Analizza la repo e riporta solo problemi verificati"}},
        },
    ]
    payload = {
        "ok": True,
        "tool": "repo_capabilities",
        "available_tools": capabilities,
        "valid_internal_tools": sorted(VALID_INTERNAL_TOOLS),
        "router_policy": [
            "Agentic jobs use 11434 as planner and 3572 as deterministic dispatcher.",
            "11435/Vulkan is used as legacy direct tool-caller and JSON normalizer fallback when planner output is malformed.",
            "If unsure which tool to use, choose repo_capabilities instead of greeting or inventing.",
            "For directory structure, module layout or file inventory use repo_tree, not repo_search.",
            "For known paths use repo_read; for unknown symbols/text use repo_search.",
            "After edits or patch plans, use repo_validate or repo_command with validation/smoke commands.",
        ],
        "safety_policy": {
            "read_only_tools": [
                "repo_capabilities",
                "repo_status",
                "repo_tree",
                "repo_search",
                "repo_read",
                "repo_validate",
                "vulkan_helper",
            ],
            "commands_allowed": True,
            "dangerous_commands_require_user_consent": True,
            "blocked_without_consent": ["git reset", "git clean", "git push", "git commit", "git merge", "git rebase", "Remove-Item", "rm -", "del", "rmdir"],
        },
        "stack": detect_stack(),
        "input_args": args,
    }
    write_json(root / "tool-results" / f"{now()}-repo_capabilities.json", payload)
    return payload


def repo_status(args: dict[str, Any], root: Path) -> dict[str, Any]:
    commands = {
        "status": "git status --short --branch",
        "diff_stat": "git diff --stat HEAD",
        "diff_name_status": "git diff --name-status HEAD",
        "diff_check": "git diff --check",
        "branch": "git branch --show-current",
    }
    results: dict[str, Any] = {}
    for name, command in commands.items():
        result = run_ps(command, timeout=120)
        artifact = root / "commands" / f"{name}.json"
        write_json(artifact, {"command": command, "result": result})
        results[name] = {
            "command": command,
            "returncode": result["returncode"],
            "stdout_tail": result["stdout_tail"],
            "stderr_tail": result["stderr_tail"],
            "artifact": str(artifact),
        }
    payload = {"ok": True, "tool": "repo_status", "stack": detect_stack(), "results": results}
    write_json(root / "tool-results" / f"{now()}-repo_status.json", payload)
    return payload

def repo_list_files(args: dict[str, Any], root: Path) -> dict[str, Any]:
    path = str(args.get("path") or ".").strip()
    suffix = str(args.get("suffix") or args.get("extension") or "").strip().lower()
    limit = max(1, min(int(args.get("limit") or args.get("max_files") or 20), 1000))
    max_depth = max(0, min(int(args.get("max_depth") or 50), 100))
    core = bool(args.get("core", False))

    if core and path in {"", "."}:
        path = "ia_carmine"
    if core and not suffix:
        suffix = ".py"

    exclude_dirs = set(str(item) for item in (args.get("exclude_dirs") or []))
    exclude_dirs.update({
        ".git",
        ".venv",
        "venv",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        "node_modules",
        "output",
        "indexAI",
    })

    try:
        rel = "." if path in {"", "."} else safe_rel_path(path)
        base = (LAB_REPO / rel).resolve(strict=False)
        base.relative_to(LAB_REPO)
    except Exception as exc:
        return {
            "ok": False,
            "tool": "repo_list_files",
            "path": path,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }

    if not base.exists():
        return {
            "ok": False,
            "tool": "repo_list_files",
            "path": rel,
            "error": "path_not_found",
        }

    files: list[dict[str, Any]] = []

    def accept_file(file_path: Path) -> bool:
        if suffix and file_path.suffix.lower() != suffix:
            return False
        return True

    if base.is_file():
        if accept_file(base):
            files.append({
                "path": repo_rel(base, LAB_REPO),
                "size_bytes": base.stat().st_size,
            })
    else:
        base_depth = len(base.relative_to(LAB_REPO).parts)
        for current, dirs, filenames in os.walk(base):
            current_path = Path(current)
            depth = len(current_path.relative_to(LAB_REPO).parts) - base_depth
            dirs[:] = [dirname for dirname in dirs if dirname not in exclude_dirs]

            if depth > max_depth:
                dirs[:] = []
                continue

            for filename in filenames:
                file_path = current_path / filename
                if not accept_file(file_path):
                    continue

                files.append({
                    "path": repo_rel(file_path, LAB_REPO),
                    "size_bytes": file_path.stat().st_size,
                })

    files = sorted(files, key=lambda item: str(item.get("path") or "").lower())
    selected = files[:limit]

    payload = {
        "ok": True,
        "tool": "repo_list_files",
        "path": rel,
        "suffix": suffix,
        "core": core,
        "limit": limit,
        "count": len(selected),
        "total_matches": len(files),
        "files": selected,
        "paths": [str(item["path"]) for item in selected],
        "truncated": len(files) > limit,
    }

    artifact = root / "tool-results" / f"{now()}-repo_list_files.json"
    write_json(artifact, payload)
    payload["artifact"] = str(artifact)
    return payload

def repo_tree(args: dict[str, Any], root: Path) -> dict[str, Any]:
    path = str(args.get("path") or ".").strip()
    max_files = max(1, min(int(args.get("max_files") or 200), 1000))
    max_depth = max(0, min(int(args.get("max_depth") or 3), 20))

    try:
        rel = "." if path in {"", "."} else safe_rel_path(path)
        base = (LAB_REPO / rel).resolve(strict=False)
        base.relative_to(LAB_REPO)
    except Exception as exc:
        return {
            "ok": False,
            "tool": "repo_tree",
            "path": path,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }

    if not base.exists():
        return {"ok": False, "tool": "repo_tree", "path": rel, "error": "path_not_found"}

    excluded_dirs = {".git", "__pycache__", ".venv", "node_modules", "output", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
    entries: list[dict[str, Any]] = []

    if base.is_file():
        entries.append({
            "path": repo_rel(base, LAB_REPO),
            "kind": "file",
            "size_bytes": base.stat().st_size,
        })
    else:
        base_depth = len(base.relative_to(LAB_REPO).parts)
        for current, dirs, files in os.walk(base):
            current_path = Path(current)
            depth = len(current_path.relative_to(LAB_REPO).parts) - base_depth
            dirs[:] = [d for d in dirs if d not in excluded_dirs]
            if depth > max_depth:
                dirs[:] = []
                continue
            for dirname in dirs:
                p = current_path / dirname
                entries.append({"path": repo_rel(p, LAB_REPO), "kind": "dir"})
                if len(entries) >= max_files:
                    break
            for filename in files:
                p = current_path / filename
                entries.append({
                    "path": repo_rel(p, LAB_REPO),
                    "kind": "file",
                    "size_bytes": p.stat().st_size,
                })
                if len(entries) >= max_files:
                    break
            if len(entries) >= max_files:
                break

    payload = {
        "ok": True,
        "tool": "repo_tree",
        "path": rel,
        "count": len(entries),
        "entries": entries,
        "truncated": len(entries) >= max_files,
    }
    artifact = root / "tool-results" / f"{now()}-repo_tree.json"
    write_json(artifact, payload)
    payload["artifact"] = str(artifact)
    return payload

def repo_search(args: dict[str, Any], root: Path) -> dict[str, Any]:
    query = str(args.get("query") or "").strip()
    if re.fullmatch(r"\*\.[A-Za-z0-9_]+", query.strip()):
        return {
            "ok": False,
            "tool": "repo_search",
            "error": "glob_pattern_is_not_text_search",
            "query": query,
            "hint": "Use repo_list_files with suffix instead of repo_search for glob-like file listing.",
            "suggested_tool": "repo_list_files",
            "suggested_arguments": {
                "path": "ia_carmine",
                "suffix": query.strip()[1:],
                "limit": 20,
                "core": True,
            },
        }
    mode = str(args.get("mode") or "rg").strip()
    path = str(args.get("path") or ".").strip()
    max_results = max(1, min(int(args.get("max_results") or 80), 200))
    if not query:
        return {"ok": False, "tool": "repo_search", "error": "missing query"}
    q = json.dumps(query)
    target = json.dumps(path)
    if mode == "git_grep":
        command = f"git grep -n -- {q}"
    elif mode == "fd":
        command = f"fd {q} {target}"
    else:
        command = f"rg -n --hidden --glob '!**/__pycache__/**' --glob '!output/**' {q} {target}"
    result = run_ps(command, timeout=120)
    payload = {
        "ok": result["returncode"] in (0, 1),
        "tool": "repo_search",
        "mode": mode,
        "query": query,
        "command": command,
        "returncode": result["returncode"],
        "matches": result["stdout"].splitlines()[:max_results],
        "stderr_tail": result["stderr_tail"],
    }
    artifact = root / "tool-results" / f"{now()}-repo_search.json"
    write_json(artifact, payload)
    payload["artifact"] = str(artifact)
    return payload


def repo_read(args: dict[str, Any], root: Path) -> dict[str, Any]:
    paths: list[str] = []
    if isinstance(args.get("paths"), list):
        paths.extend(str(p) for p in args["paths"])
    if args.get("path"):
        paths.append(str(args["path"]))
    max_chars = int(args.get("max_chars") or 80000)
    line = args.get("line")
    before = int(args.get("before") or 40)
    after = int(args.get("after") or 120)
    items: list[dict[str, Any]] = []
    for raw in paths[:40]:
        try:
            rel = safe_rel_path(raw)
            full = (LAB_REPO / rel).resolve(strict=False)
            full.relative_to(LAB_REPO)
            if not full.exists() or not full.is_file():
                items.append({"ok": False, "path": rel, "error": "file_not_found"})
                continue
            text = full.read_text(encoding="utf-8-sig", errors="replace")
            if line:
                lines = text.splitlines()
                n = max(1, min(int(line), max(1, len(lines))))
                start = max(1, n - before)
                end = min(len(lines), n + after)
                content = "\n".join(f"{i}: {lines[i - 1]}" for i in range(start, end + 1))
            else:
                content = text
            item = {
                "ok": True,
                "path": rel,
                "size_bytes": full.stat().st_size,
                "line_count": len(text.splitlines()),
                "content": content[:max_chars],
                "truncated": len(content) > max_chars,
            }
            safe_name = rel.replace("/", "__").replace("\\", "__")
            artifact = root / "reads" / f"{safe_name}.json"
            write_json(artifact, item)
            item["artifact"] = str(artifact)
            items.append(item)
        except Exception as exc:
            items.append({"ok": False, "path": raw, "error_type": type(exc).__name__, "error": str(exc)})
    payload = {"ok": True, "tool": "repo_read", "count": len(items), "items": items}
    write_json(root / "tool-results" / f"{now()}-repo_read.json", payload)
    return payload



def repo_apply_patch(args: dict[str, Any], root: Path) -> dict[str, Any]:
    path = str(args.get("path") or "").strip()
    old_text = args.get("old_text")
    new_text = args.get("new_text")
    max_replacements = int(args.get("max_replacements") or 1)

    if not path:
        return {"ok": False, "tool": "repo_apply_patch", "error": "missing path"}
    if not isinstance(old_text, str) or old_text == "":
        return {"ok": False, "tool": "repo_apply_patch", "error": "missing old_text"}
    if not isinstance(new_text, str):
        return {"ok": False, "tool": "repo_apply_patch", "error": "missing new_text"}
    max_replacements = max(1, min(max_replacements, 20))

    try:
        rel = safe_rel_path(path)
        full = (LAB_REPO / rel).resolve(strict=False)
        full.relative_to(LAB_REPO)
    except Exception as exc:
        return {"ok": False, "tool": "repo_apply_patch", "path": path, "error_type": type(exc).__name__, "error": str(exc)}

    if not full.exists() or not full.is_file():
        return {"ok": False, "tool": "repo_apply_patch", "path": rel, "error": "file_not_found"}

    original = full.read_text(encoding="utf-8-sig", errors="replace")
    occurrences = original.count(old_text)
    if occurrences < 1:
        return {
            "ok": False,
            "tool": "repo_apply_patch",
            "path": rel,
            "error": "old_text_not_found",
            "old_text_preview": old_text[:1000],
        }

    replacements = min(occurrences, max_replacements)
    updated = original.replace(old_text, new_text, replacements)

    safe_name = rel.replace("/", "__").replace("\\", "__")
    backup_artifact = root / "artifacts" / f"{safe_name}.{now()}.before.txt"
    backup_artifact.parent.mkdir(parents=True, exist_ok=True)
    backup_artifact.write_text(original, encoding="utf-8")
    full.write_text(updated, encoding="utf-8")

    payload = {
        "ok": True,
        "tool": "repo_apply_patch",
        "path": rel,
        "changed": updated != original,
        "occurrences_found": occurrences,
        "replacements": replacements,
        "line_count_before": len(original.splitlines()),
        "line_count_after": len(updated.splitlines()),
        "backup_artifact": str(backup_artifact),
    }
    write_json(root / "tool-results" / f"{now()}-repo_apply_patch.json", payload)
    return payload

def repo_write_file(args: dict[str, Any], root: Path) -> dict[str, Any]:
    path = str(args.get("path") or "").strip()
    content = args.get("content")
    mode = str(args.get("mode") or "overwrite").strip().lower()
    encoding = str(args.get("encoding") or "utf-8").strip() or "utf-8"

    if not path:
        return {"ok": False, "tool": "repo_write_file", "error": "missing path"}

    if not isinstance(content, str):
        return {"ok": False, "tool": "repo_write_file", "path": path, "error": "missing string content"}

    if mode not in {"overwrite", "create", "append"}:
        return {
            "ok": False,
            "tool": "repo_write_file",
            "path": path,
            "error": "mode must be overwrite, create or append",
        }

    try:
        rel = safe_rel_path(path)
        full = (LAB_REPO / rel).resolve(strict=False)
        full.relative_to(LAB_REPO)
    except Exception as exc:
        return {
            "ok": False,
            "tool": "repo_write_file",
            "path": path,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }

    if full.exists() and full.is_dir():
        return {"ok": False, "tool": "repo_write_file", "path": rel, "error": "target_is_directory"}

    if mode == "create" and full.exists():
        return {"ok": False, "tool": "repo_write_file", "path": rel, "error": "file_exists"}

    backup_path = ""
    before_sha256 = ""
    before_size = 0

    if full.exists() and full.is_file():
        old_bytes = full.read_bytes()
        before_size = len(old_bytes)
        before_sha256 = hashlib.sha256(old_bytes).hexdigest()

        safe_backup_name = rel.replace("/", "__").replace("\\", "__")
        backup = root / "backups" / f"{now()}-{safe_backup_name}.bak"
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.write_bytes(old_bytes)
        backup_path = str(backup)

    full.parent.mkdir(parents=True, exist_ok=True)

    if mode == "append":
        with full.open("a", encoding=encoding, errors="replace", newline="") as f:
            f.write(content)
    else:
        full.write_text(content, encoding=encoding, errors="replace", newline="")

    after_bytes = full.read_bytes()
    after_sha256 = hashlib.sha256(after_bytes).hexdigest()

    payload = {
        "ok": True,
        "tool": "repo_write_file",
        "path": rel,
        "mode": mode,
        "backup_path": backup_path,
        "before_size": before_size,
        "after_size": len(after_bytes),
        "before_sha256": before_sha256,
        "after_sha256": after_sha256,
        "line_count_after": len(full.read_text(encoding=encoding, errors="replace").splitlines()),
    }

    artifact = root / "tool-results" / f"{now()}-repo_write_file.json"
    write_json(artifact, payload)
    payload["artifact"] = str(artifact)
    return payload
def repo_validate(args: dict[str, Any], root: Path) -> dict[str, Any]:
    commands = [
        "git diff --check",
        "python -m compileall -q ia_carmine; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; python -m compileall -q Tools",
    ]
    if isinstance(args.get("commands"), list) and args["commands"]:
        commands = [str(command) for command in args["commands"][:10] if str(command).strip()] or commands
    results = []
    ok = True
    for index, command in enumerate(commands, start=1):
        result = run_ps(command, timeout=int(args.get("timeout_seconds") or 300))
        item = {
            "index": index,
            "command": command,
            "returncode": result["returncode"],
            "stdout_tail": result["stdout_tail"],
            "stderr_tail": result["stderr_tail"],
            "ok": result["returncode"] == 0,
        }
        results.append(item)
        ok = ok and item["ok"]
        if not item["ok"] and not bool(args.get("continue_on_failure", False)):
            break
    payload = {"ok": ok, "tool": "repo_validate", "results": results}
    write_json(root / "tool-results" / f"{now()}-repo_validate.json", payload)
    return payload

def repo_command(args: dict[str, Any], root: Path, allow_command: bool, user_consent: str) -> dict[str, Any]:
    if not allow_command:
        return {"ok": False, "tool": "repo_command", "error": "commands disabled by request"}
    command = str(args.get("command") or "").strip()
    timeout = int(args.get("timeout_seconds") or COMMAND_TIMEOUT_SECONDS)
    if not command:
        return {"ok": False, "tool": "repo_command", "error": "missing command"}
    if command.lower() in {"compile", "build", "compila"}:
        command = "python -m compileall -q ia_carmine; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; python -m compileall -q Tools"
    if dangerous_command(command) and "confirm" not in user_consent.lower() and "confermo" not in user_consent.lower():
        return {
            "ok": False,
            "tool": "repo_command",
            "needs_consent": True,
            "command": command,
            "error": "dangerous command blocked without user_consent",
        }
    result = run_ps(command, timeout=timeout)
    artifact = root / "commands" / f"command-{now()}.json"
    write_json(artifact, {"command": command, "result": result})
    return {
        "ok": result["returncode"] == 0,
        "tool": "repo_command",
        "command": command,
        "returncode": result["returncode"],
        "stdout_tail": result["stdout_tail"],
        "stderr_tail": result["stderr_tail"],
        "artifact": str(artifact),
    }


TOOLS_SCHEMA: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "repo_capabilities",
            "description": "Return available local repo/file tools, when to use them, required arguments, examples and safety policy. Use this when unsure which tool to call.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "repo_status",
            "description": "Read real git status, diff stat, changed files, diff check and stack.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "repo_tree",
            "description": "List repo-relative files and directories under a path. Use for directory structure, module layout, file inventory or key files. Do not use repo_search for directory listing.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "default": "."},
                    "max_depth": {"type": "integer", "default": 3},
                    "max_files": {"type": "integer", "default": 200},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "repo_list_files",
            "description": (
                "List repo-relative files by path, suffix and limit. "
                "Use for natural file inventory requests such as first N Python files, core files, or list .py files. "
                "Do not use repo_search for glob patterns like *.py."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "default": "."},
                    "suffix": {"type": "string", "default": ""},
                    "extension": {"type": "string", "default": ""},
                    "limit": {"type": "integer", "default": 20},
                    "max_files": {"type": "integer", "default": 20},
                    "max_depth": {"type": "integer", "default": 50},
                    "core": {"type": "boolean", "default": False},
                    "exclude_dirs": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "repo_search",
            "description": "Search repo code/docs by query/pattern/symbol. Requires query.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "path": {"type": "string", "default": "."},
                    "mode": {"type": "string", "enum": ["rg", "git_grep", "fd"], "default": "rg"},
                    "max_results": {"type": "integer", "default": 80},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "repo_read",
            "description": "Read one or more repo-relative files. Requires path or paths.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "paths": {"type": "array", "items": {"type": "string"}},
                    "max_chars": {"type": "integer", "default": 80000},
                    "line": {"type": "integer"},
                    "before": {"type": "integer", "default": 40},
                    "after": {"type": "integer", "default": 120},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "repo_apply_patch",
            "description": "Modify one repo-relative file by replacing exact old_text with new_text. Use only when exact old_text is known from repo_read or user input.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "old_text": {"type": "string"},
                    "new_text": {"type": "string"},
                    "max_replacements": {"type": "integer", "default": 1},
                },
                "required": ["path", "old_text", "new_text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "repo_write_file",
            "description": (
                "Create, overwrite or append a small repo-relative text file in LAB_REPO. "
                "Use for new helper files, tests, docs or generated artifacts. "
                "Prefer repo_apply_patch for editing existing source with exact old_text."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                    "mode": {
                        "type": "string",
                        "enum": ["overwrite", "create", "append"],
                        "default": "overwrite",
                    },
                    "encoding": {"type": "string", "default": "utf-8"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "repo_validate",
            "description": "Run standard validation after changes: git diff --check and Python compileall.",
            "parameters": {
                "type": "object",
                "properties": {
                    "commands": {"type": "array", "items": {"type": "string"}},
                    "timeout_seconds": {"type": "integer", "default": 300},
                    "continue_on_failure": {"type": "boolean", "default": False},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "repo_command",
            "description": "Run a safe diagnostic command. Requires command. Dangerous commands require explicit consent.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string"},
                    "timeout_seconds": {"type": "integer", "default": 120},
                    "user_consent": {"type": "string"},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "vulkan_helper",
            "description": "Operational composite helper for generic local repo/helper/multi-task requests.",
            "parameters": {
                "type": "object",
                "properties": {
                    "public_tool_name": {"type": "string"},
                    "task": {"type": "string"},
                    "reason": {"type": "string"},
                    "arguments": {"type": "object"},
                },
                "required": ["public_tool_name", "task", "reason"],
            },
        },
    },
]


TOOL_ALIASES = {
    "capabilities": "repo_capabilities",
    "tool_help": "repo_capabilities",
    "tools": "repo_capabilities",
    "help_tools": "repo_capabilities",
    "repo_help": "repo_capabilities",
    "status": "repo_status",
    "git_status": "repo_status",
    "get_git_status": "repo_status",
    "diff": "repo_status",
    "git_diff": "repo_status",
    "analyze_repo": "repo_status",
    "analyze_repository": "repo_status",
    "find_issues": "repo_status",
    "detect_problems": "repo_status",
    "search": "repo_search",
    "grep": "repo_search",
    "rg": "repo_search",
    "search_code": "repo_search",
    "read": "repo_read",
    "read_file": "repo_read",
    "get_file_content": "repo_read",
    "apply_patch": "repo_apply_patch",
    "patch": "repo_apply_patch",
    "patch_file": "repo_apply_patch",
    "edit": "repo_apply_patch",
    "edit_file": "repo_apply_patch",
    "modify_file": "repo_apply_patch",
    "write_file": "repo_write_file",
    "repo_write_file": "repo_write_file",
    "create_file": "repo_write_file",
    "overwrite_file": "repo_write_file",
    "save_file": "repo_write_file",
    "validate": "repo_validate",
    "validation": "repo_validate",
    "smoke": "repo_validate",
    "command": "repo_command",
    "run": "repo_command",
    "compile": "repo_command",
    "tree": "repo_tree",
    "repo_tree": "repo_tree",
    "list_files": "repo_tree",
    "list_dir": "repo_tree",
    "directory": "repo_tree",
    "directory_structure": "repo_tree",
    "file_inventory": "repo_tree",
    "diff_check": "repo_command",
    "helper": "vulkan_helper",
    "helper_for_all": "vulkan_helper",
    "help_for_all": "vulkan_helper",
}


def parse_tool_call(call: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    function = call.get("function") if isinstance(call.get("function"), dict) else {}
    name = str(function.get("name") or call.get("name") or "").strip()
    raw_args = function.get("arguments", call.get("arguments", {}))
    if isinstance(raw_args, str):
        try:
            decoded = json.loads(raw_args) if raw_args.strip() else {}
        except Exception:
            decoded = {}
        raw_args = decoded
    return name, dict(raw_args or {}) if isinstance(raw_args, dict) else {}


def normalize_tool_name(value: str) -> str:
    name = re.sub(r"[^a-zA-Z0-9_]+", "_", str(value or "").strip()).strip("_").lower()
    return TOOL_ALIASES.get(name, name)


def dispatch_tool(name: str, args: dict[str, Any], root: Path, allow_command: bool, user_consent: str) -> dict[str, Any]:
    tool = normalize_tool_name(name)
    if tool == "repo_capabilities":
        return repo_capabilities(args, root)
    if tool == "repo_status":
        return repo_status(args, root)
    if tool == "repo_tree":
        return repo_tree(args, root)
    if tool == "repo_list_files":
        return repo_list_files(args, root)
    if tool == "repo_search":
        return repo_search(args, root)
    if tool == "repo_read":
        return repo_read(args, root)
    if tool == "repo_apply_patch":
        return repo_apply_patch(args, root)
    if tool == "repo_write_file":
        return repo_write_file(args, root)
    if tool == "repo_validate":
        return repo_validate(args, root)
    if tool == "repo_command":
        return repo_command(args, root, allow_command=allow_command, user_consent=user_consent)
    if tool == "vulkan_helper":
        return vulkan_helper(args, root)
    return {"ok": False, "tool": tool, "error": "unknown internal tool"}


def compact(value: Any, limit: int = MAX_TOOL_RESULT_CHARS) -> str:
    text = json.dumps(value, ensure_ascii=False, indent=2, default=str) if not isinstance(value, str) else value
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text[:limit] + ("\n... <truncated>" if len(text) > limit else "")


def helper_text(args: dict[str, Any]) -> str:
    for key in ("task", "request", "query", "prompt", "instruction", "reason", "context"):
        value = args.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    original = args.get("original_30b_arguments")
    if isinstance(original, dict):
        for key in ("request", "task", "query", "prompt", "instruction", "context"):
            value = original.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    nested = args.get("arguments")
    if isinstance(nested, dict):
        for key in ("request", "task", "query", "prompt", "instruction", "context"):
            value = nested.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return compact(args, 4000)


def helper_search_queries(task: str, public_tool: str) -> list[str]:
    low = (task + " " + public_tool).lower()
    queries: list[str] = []
    if any(token in low for token in ("bridge", "broker", "wrapper", "3571", "3572", "vulkan", "tool_call", "dispatcher")):
        queries.extend([
            "vulkan|bridge|broker|wrapper|tool_call|dispatcher|3571|3572",
            "tool_result_for|called_by_30b|internal_vulkan|bridge_forwarding_mode|public_tool_x",
        ])
    if any(token in low for token in ("patch", "fix", "bug", "errore", "error", "problema", "problemi", "issue", "issues")):
        queries.extend([
            "TODO|FIXME|HACK|BUG|error|exception|traceback|raise |except ",
            "patch|diff|backup|py_compile|smoke|validator|test",
        ])
    if any(token in low for token in ("analizza", "analyze", "analyse", "review", "repo", "repository", "worktree")):
        queries.extend([
            "TODO|FIXME|HACK|BUG|problem|problema|issue|failure|failed|blocked",
            "not proven|evidence missing|blocked|diagnostic only|not tested",
            "raise |except |pass|return None|return \\{\\}",
        ])
    queries.extend(["vulkan_helper", "repo_search|repo_read|repo_status|repo_apply_patch|repo_validate|repo_command"])
    out: list[str] = []
    for query in queries:
        if query and query not in out:
            out.append(query)
    return out[:8]


def evidence_from_search(search_result: dict[str, Any], limit: int = 12) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    matches = search_result.get("matches") if isinstance(search_result, dict) else []
    if not isinstance(matches, list):
        return evidence
    for raw in matches[:limit]:
        text = str(raw)
        item: dict[str, Any] = {"raw": text, "text": text}
        parts = text.split(":", 2)
        if len(parts) >= 3 and parts[1].isdigit():
            item["path"] = parts[0]
            item["line"] = int(parts[1])
            item["text"] = parts[2]
        evidence.append(item)
    return evidence


def changed_files_from_status(status: dict[str, Any]) -> list[str]:
    try:
        text = status["results"]["diff_name_status"]["stdout_tail"]
    except Exception:
        return []
    files: list[str] = []
    for line in str(text).splitlines():
        parts = line.split()
        if len(parts) >= 2:
            files.append(parts[-1])
    return files


def review_docs(task: str, root: Path) -> list[dict[str, Any]]:
    low = task.lower()
    if not any(token in low for token in ("analizza", "analyze", "review", "problema", "problemi", "issue", "repo", "repository")):
        return []
    docs = []
    for rel in ("problems.md", "AGENTS.md", "README.md", "CONTEXT_INDEX.md"):
        if (LAB_REPO / rel).exists():
            docs.append(repo_read({"path": rel, "max_chars": 12000}, root))
    return docs


def first_read_item(docs: list[dict[str, Any]], path: str) -> dict[str, Any] | None:
    for doc in docs:
        for item in doc.get("items") or []:
            if item.get("ok") and item.get("path") == path:
                return item
    return None


def fenced_field(block: str, label: str, limit: int = 1400) -> str:
    pattern = re.compile(rf"{re.escape(label)}:\s*\n\s*```text\s*\n(.*?)\n```", re.DOTALL)
    match = pattern.search(block)
    if not match:
        return ""
    text = "\n".join(line.rstrip() for line in match.group(1).strip().splitlines())
    return compact(text, limit)


def extract_open_problems(docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    item = first_read_item(docs, "problems.md")
    if not item:
        return []
    content = str(item.get("content") or "")
    if "## Open problems" in content:
        content = content.split("## Open problems", 1)[1]
    if "## Closed problems" in content:
        content = content.split("## Closed problems", 1)[0]

    headings = list(re.finditer(r"^###\s+(P-\d+)\s+(.+)$", content, re.MULTILINE))
    problems: list[dict[str, Any]] = []
    for index, match in enumerate(headings):
        block_start = match.end()
        block_end = headings[index + 1].start() if index + 1 < len(headings) else len(content)
        block = content[block_start:block_end].strip()
        status_match = re.search(r"^Status:\s*(.+?)\s*$", block, re.MULTILINE)
        status = status_match.group(1).strip() if status_match else "unknown"
        if status.lower().startswith("closed"):
            continue
        title = re.sub(r"^[^\w`]+", "", match.group(2).strip()).strip()
        problems.append({
            "id": match.group(1),
            "title": title,
            "status": status,
            "source": {
                "path": "problems.md",
                "line_count": item.get("line_count"),
                "artifact": item.get("artifact"),
            },
            "evidence": fenced_field(block, "Evidence from code/document review"),
            "why_it_matters": fenced_field(block, "Why it matters"),
            "expected_fix": fenced_field(block, "Expected fix", limit=1800),
        })
    return problems


def verified_problem_evidence(problems: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for problem in problems:
        rows.append({
            "problem_id": problem.get("id"),
            "path": problem.get("source", {}).get("path"),
            "text": problem.get("evidence") or problem.get("title"),
            "status": problem.get("status"),
        })
    return rows


def patch_targets_from_verified_problems(problems: list[dict[str, Any]]) -> list[dict[str, Any]]:
    targets: dict[str, dict[str, Any]] = {}
    for problem in problems:
        text = "\n".join(str(problem.get(key) or "") for key in ("title", "evidence", "expected_fix"))
        for ref in re.findall(r"`([^`]+)`", text):
            if "/" not in ref and "\\" not in ref and "." not in ref:
                continue
            path = ref.replace("\\", "/")
            rec = targets.setdefault(path, {"path": path, "problem_ids": [], "reason": "verified open problem target"})
            if problem.get("id") not in rec["problem_ids"]:
                rec["problem_ids"].append(problem.get("id"))
    return list(targets.values())


def compact_review_docs(docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compact_docs: list[dict[str, Any]] = []
    for doc in docs:
        compact_items: list[dict[str, Any]] = []
        for item in doc.get("items") or []:
            compact_items.append({
                "ok": item.get("ok"),
                "path": item.get("path"),
                "size_bytes": item.get("size_bytes"),
                "line_count": item.get("line_count"),
                "truncated": item.get("truncated"),
                "artifact": item.get("artifact"),
                "content_excerpt": compact(item.get("content"), 1800 if item.get("path") == "problems.md" else 700),
            })
        compact_docs.append({
            "ok": doc.get("ok"),
            "tool": doc.get("tool"),
            "count": doc.get("count"),
            "items": compact_items,
        })
    return compact_docs


def repo_non_findings(status: dict[str, Any]) -> list[str]:
    changed = changed_files_from_status(status)
    lines = [f"{len(changed)} changed files are worktree state, not automatic problems."]
    try:
        diff_check = status["results"]["diff_check"]
        lines.append(f"git diff --check returncode={diff_check.get('returncode')}; stderr={compact(diff_check.get('stderr_tail'), 300)}")
    except Exception:
        lines.append("git diff --check evidence missing.")
    return lines


def helper_call_payload(
    *,
    purpose: str,
    request: str,
    function: str,
    parameters: dict[str, Any] | None = None,
    expected_output: str = "",
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "request": request,
        "function": function,
        "parameters": parameters or {},
        "expected_output": expected_output or "Return compact evidence only; do not invent missing files or conclusions.",
    }
    return {
        "tool": function,
        "fallback_tool": "helper_for_all",
        "purpose": purpose,
        "payload": {
            **payload,
            "tool_name": function,
            "operation_id": function,
        },
    }

def useful_next_calls(
    *,
    verified_problems: list[dict[str, Any]],
    patch_targets: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = [
        helper_call_payload(
            purpose="Read the verified problem register before reporting or patching.",
            request="Leggi problems.md e restituisci solo problemi aperti, evidenza e fix atteso.",
            function="repo_read",
            parameters={"path": "problems.md", "max_chars": 20000},
            expected_output="Only open P-* problems with evidence, impact and expected fix.",
        )
    ]

    target_paths = [str(target.get("path")) for target in patch_targets if target.get("path")]
    for path in target_paths[:4]:
        calls.append(helper_call_payload(
            purpose=f"Read exact target file for verified problem context: {path}.",
            request=f"Leggi il file {path} e riporta le sezioni rilevanti per i problemi verificati.",
            function="repo_read",
            parameters={"path": path, "max_chars": 24000},
            expected_output="Relevant current source/document excerpts with line-oriented context.",
        ))

    if any("AI_REFERENCE_SOURCE_MAP.md" in str(path) for path in target_paths):
        calls.append(helper_call_payload(
            purpose="Find stale PR/branch markers inside the exact target file.",
            request="Cerca solo in docs/AI_REFERENCE_SOURCE_MAP.md i riferimenti stale PR/branch indicati dai problemi aperti.",
            function="repo_search",
            parameters={
                "query": "Current branch phase|PR #187|PR #193|PR #192|PR #191",
                "path": "docs/AI_REFERENCE_SOURCE_MAP.md",
                "mode": "rg",
                "max_results": 40,
            },
            expected_output="Only matching lines from docs/AI_REFERENCE_SOURCE_MAP.md.",
        ))

    if verified_problems:
        ids = ", ".join(str(problem.get("id")) for problem in verified_problems)
        calls.append(helper_call_payload(
            purpose="Ask for a scoped patch plan, not a generic repo analysis.",
            request=f"Prepara un piano patch minimo per risolvere solo {ids}; non modificare file.",
            function="vulkan_helper",
            parameters={"task": f"Scoped patch plan only for verified problems: {ids}"},
            expected_output="Target files, exact intended edits, validation command; no source writes.",
        ))

    calls.append(helper_call_payload(
        purpose="Re-check repository whitespace/conflict status after any edit.",
        request="Esegui git diff --check e riporta solo returncode e stderr.",
        function="repo_status",
        parameters={},
        expected_output="git diff --check status only.",
    ))
    return calls[:8]


def answer_for_30b(
    *,
    task: str,
    verified_problems: list[dict[str, Any]],
    status: dict[str, Any],
    useful_calls: list[dict[str, Any]],
) -> str:
    lines = [
        "RISPOSTA FINALE VINCOLATA ALL'EVIDENZA DEL TOOL.",
        "Non aggiungere file, moduli o problemi che non compaiono in verified_problems.",
        f"Richiesta: {task}",
        "",
    ]
    if verified_problems:
        lines.append("Problemi verificati:")
        for index, problem in enumerate(verified_problems, 1):
            lines.append(f"{index}. {problem.get('id')} - {problem.get('title')} ({problem.get('status')})")
            if problem.get("evidence"):
                lines.append(f"   Evidenza: {compact(problem.get('evidence'), 700)}")
            if problem.get("why_it_matters"):
                lines.append(f"   Impatto: {compact(problem.get('why_it_matters'), 700)}")
            if problem.get("expected_fix"):
                lines.append(f"   Fix atteso: {compact(problem.get('expected_fix'), 900)}")
    else:
        lines.append("Problemi verificati: insufficient evidence.")

    lines.append("")
    lines.append("Non-problemi / limiti della lettura:")
    for item in repo_non_findings(status):
        lines.append(f"- {item}")
    lines.append("- Broad repo searches are secondary evidence only; do not convert every match or changed file into a problem.")
    lines.append("- Do not mention any file, module or config path that is absent from verified_problems.")
    if useful_calls:
        lines.append("")
        lines.append("Chiamate utili successive tramite il tool pubblico indicato in `tool`:")
        for index, call in enumerate(useful_calls[:5], 1):
            payload = call.get("payload") or {}
            function = payload.get("function") or ""
            params = compact(payload.get("parameters") or {}, 500)
            lines.append(f"{index}. {call.get('purpose')} function={function}; parameters={params}")
    return compact("\n".join(lines), 9000)


def helper_summary(
    public_tool: str,
    task: str,
    status: dict[str, Any],
    searches: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    patch_targets: list[dict[str, Any]],
    docs: list[dict[str, Any]],
    verified_problems: list[dict[str, Any]],
) -> str:
    changed = changed_files_from_status(status)
    lines = [
        f"Operational helper result for public tool X `{public_tool}`.",
        "STRICT_EVIDENCE_ONLY: final answer must use verified_problems first and must not invent files/modules.",
        f"Task: {task}",
        f"Verified open problems: {len(verified_problems)}",
        f"Changed files from git diff --name-status: {len(changed)} (state only, not automatic findings)",
        f"Secondary search evidence rows: {len(evidence)}",
        f"Verified patch target files: {len(patch_targets)}",
    ]
    for problem in verified_problems:
        lines.append(f"- {problem.get('id')}: {problem.get('title')} [{problem.get('status')}]")
        if problem.get("evidence"):
            lines.append(f"  evidence: {compact(problem.get('evidence'), 500)}")
    try:
        diff_check = status["results"]["diff_check"]
        lines.append(f"git diff --check rc={diff_check.get('returncode')} stderr={compact(diff_check.get('stderr_tail'), 600)}")
    except Exception:
        pass
    for doc in docs:
        for item in (doc.get("items") or [])[:2]:
            lines.append(
                f"Read `{item.get('path')}` ok={item.get('ok')} lines={item.get('line_count')} "
                f"excerpt={compact(item.get('content'), 900)}"
            )
    for search in searches[:5]:
        lines.append(f"Search `{search.get('query')}` -> matches={search.get('match_count')} rc={search.get('returncode')}")
    return compact("\n".join(lines), 9000)


def vulkan_helper(args: dict[str, Any], root: Path) -> dict[str, Any]:
    args = dict(args or {})
    public_tool = str(args.get("public_tool_name") or args.get("public_tool_x") or args.get("tool_name") or "helper_for_all").strip()
    task = helper_text(args)
    status = repo_status({}, root)
    searches: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    for query in helper_search_queries(task, public_tool):
        result = repo_search({"query": query, "mode": "rg", "path": ".", "max_results": 40}, root)
        searches.append({
            "query": query,
            "ok": result.get("ok"),
            "returncode": result.get("returncode"),
            "match_count": len(result.get("matches") or []),
            "stderr_tail": result.get("stderr_tail"),
            "command": result.get("command"),
        })
        for item in evidence_from_search(result, limit=8):
            item["query"] = query
            evidence.append(item)
        if len(evidence) >= 30:
            break
    docs = review_docs(task, root)
    verified_problems = extract_open_problems(docs)
    patch_targets = patch_targets_from_verified_problems(verified_problems)
    verified_evidence = verified_problem_evidence(verified_problems)
    summary = helper_summary(public_tool, task, status, searches, evidence, patch_targets, docs, verified_problems)
    useful_calls = useful_next_calls(verified_problems=verified_problems, patch_targets=patch_targets)
    answer = answer_for_30b(task=task, verified_problems=verified_problems, status=status, useful_calls=useful_calls)
    result = {
        "ok": True,
        "tool": "vulkan_helper",
        "kind": "operational_helper_result",
        "public_tool_name": public_tool,
        "task": task,
        "instruction_for_30b": (
            "Use answer_for_30b as the final answer unless the user asked for raw JSON. "
            "Only list verified_problems as problems. Changed files, search matches and review_docs are evidence/status, "
            "not automatic findings. Do not invent files, modules, config files or manager files."
        ),
        "answer_for_30b": answer,
        "verified_problems": verified_problems,
        "useful_next_calls": useful_calls,
        "wrapper_call_contract": {
            "public_tool": public_tool,
            "fallback_tool": "helper_for_all",
            "rule": "For follow-up context, prefer the specific public tool named in useful_next_calls[*].tool; use helper_for_all only as fallback.",
            "valid_function_hints": sorted(VALID_INTERNAL_TOOLS),
            "avoid": "Do not repeat a generic analyze-repo request after verified_problems are already returned.",
        },
        "non_findings": repo_non_findings(status),
        "summary": summary,
        "context_for_30b": answer,
        "evidence": verified_evidence,
        "secondary_search_evidence": evidence[:30],
        "patch_targets": patch_targets,
        "review_docs": compact_review_docs(docs),
        "searches": searches,
        "repo_status": status,
        "next_actions": [
            "Report only verified_problems as problems.",
            "If more detail is needed, call the specific public tool from useful_next_calls[*].tool; helper_for_all is fallback only.",
            "Do not create notes, calendar events, automations, or patch files for a diagnostic-only request.",
        ],
        "input_args": args,
    }
    artifact = root / "tool-results" / f"{now()}-vulkan_helper.json"
    artifact_payload = dict(result)
    artifact_payload["raw_review_docs"] = docs
    write_json(artifact, artifact_payload)
    result["artifact"] = str(artifact)
    return result


def public_tool(payload: dict[str, Any]) -> str:
    for key in ("tool_name", "function", "operation_id", "requested_function", "bridge_public_tool_x"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "helper_for_all"


def public_args(payload: dict[str, Any]) -> dict[str, Any]:
    for key in ("arguments", "parameters", "requested_parameters", "raw_bridge_payload"):
        value = payload.get(key)
        if isinstance(value, dict) and value:
            args = dict(value)
            break
    else:
        args = {}
    if "file" in args and "path" not in args:
        args["path"] = args["file"]
    if "files" in args and "paths" not in args:
        args["paths"] = args["files"]
    if "pattern" in args and "query" not in args:
        args["query"] = args["pattern"]
    if "symbol" in args and "query" not in args:
        args["query"] = args["symbol"]
    return args


def text_from_payload(payload: dict[str, Any], args: dict[str, Any], public_tool_name: str) -> str:
    for source in (payload, args):
        for key in ("request", "task", "query", "prompt", "instruction", "command", "context"):
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return f"PUBLIC_TOOL_X={public_tool_name}; ARGUMENTS={compact(args, 4000)}"


def bad_path(value: object) -> bool:
    raw = str(value or "").strip().replace("\\", "/")
    if not raw:
        return True
    low = raw.lower()
    if low in {"/path/to/repository", "path/to/repository", "repository", "repo", "<repo>", "<path>", "your/repository/path"}:
        return True
    return raw.startswith("/") or ":" in raw or raw.startswith("../") or "/../" in raw


def original_text(original_args: dict[str, Any]) -> str:
    for key in ("request", "task", "query", "prompt", "instruction", "context"):
        value = original_args.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def sanitize_tool_args(tool_name: str, call_args: dict[str, Any], original_args: dict[str, Any], public_tool_name: str) -> dict[str, Any]:
    args = dict(call_args or {})
    args.setdefault("public_tool_name", public_tool_name)
    args.setdefault("public_tool_x", public_tool_name)
    args.setdefault("original_30b_arguments", original_args)
    if tool_name == "repo_search":
        query = args.get("query") or original_args.get("query") or original_args.get("request") or original_args.get("task") or original_args.get("context")
        if query not in (None, ""):
            args["query"] = str(query)
        args["mode"] = str(args.get("mode") or "rg")
        if bad_path(args.get("path")):
            args["path"] = "."
        args["max_results"] = max(1, min(int(args.get("max_results") or 80), 120))
    elif tool_name == "repo_read":
        if bad_path(args.get("path")) and not args.get("paths"):
            if original_args.get("path") and not bad_path(original_args.get("path")):
                args["path"] = original_args.get("path")
            elif original_args.get("paths"):
                args["paths"] = original_args.get("paths")
        args.setdefault("max_chars", 20000)
    elif tool_name == "repo_apply_patch":
        if bad_path(args.get("path")) and original_args.get("path") and not bad_path(original_args.get("path")):
            args["path"] = original_args.get("path")
        args.setdefault("max_replacements", 1)
    elif tool_name == "repo_write_file":
        if bad_path(args.get("path")) and original_args.get("path") and not bad_path(original_args.get("path")):
            args["path"] = original_args.get("path")
        args.setdefault("mode", "overwrite")
        args.setdefault("encoding", "utf-8")
    elif tool_name == "repo_command":
        if not str(args.get("command") or "").strip() and original_args.get("command"):
            args["command"] = original_args.get("command")
    elif tool_name == "vulkan_helper":
        text = original_text(original_args)
        if not str(args.get("task") or "").strip() or str(args.get("task")).strip().lower() in {"repo", "repository", "analyze_repo"}:
            args["task"] = text or args.get("task") or ""
        args.setdefault("reason", "public tool X is generic or needs composite local evidence")
        args.setdefault("arguments", original_args)
    return args


def is_generic_repo_analysis(public_tool_name: str, task: str, original_args: dict[str, Any]) -> bool:
    low = " ".join(str(part or "").lower() for part in (
        public_tool_name,
        task,
        original_args.get("request"),
        original_args.get("task"),
        original_args.get("query"),
        original_args.get("prompt"),
        original_args.get("instruction"),
    ))
    has_repo = any(token in low for token in ("repo", "repository", "worktree", "progetto", "codice", "locale"))
    has_review = any(token in low for token in ("analizza", "analyze", "analyse", "review", "problema", "problemi", "issue", "issues", "bug"))
    return has_repo and has_review


def needs_composite_review(
    public_tool_name: str,
    task: str,
    original_args: dict[str, Any],
    internal_tool: str,
    internal_args: dict[str, Any],
) -> bool:
    if not is_generic_repo_analysis(public_tool_name, task, original_args):
        return False
    if internal_tool == "vulkan_helper":
        return False
    if internal_tool == "repo_status":
        return True
    if internal_tool == "repo_search":
        query = str(internal_args.get("query") or "").strip().lower()
        return query in {"", "repo", "repository", "problem", "problems", "problema", "problemi", "issue", "issues", "bug", "bugs"}
    return False

def selector_fallback_tool(public_tool_name: str, task: str, original_args: dict[str, Any], selector_response: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    if isinstance(selector_response, dict) and selector_response.get("backend_unreachable"):
        return "", {}
    if isinstance(selector_response, dict) and selector_response.get("backend_timeout"):
        return "", {}

    low = " ".join(str(part or "").lower() for part in (
        public_tool_name,
        task,
        original_args.get("request"),
        original_args.get("query"),
        original_args.get("function"),
        original_args.get("tool_name"),
    ))

    if any(token in low for token in ("tool", "tools", "capabilities", "capability", "quale tool", "che tool", "non so quale")):
        return "repo_capabilities", {
            "public_tool_name": public_tool_name,
            "task": task,
            "reason": "Vulkan was consulted but emitted no usable native tool_call; return tool capability map instead of greeting.",
            "arguments": original_args,
            "selector_response_preview": compact(selector_response, 4000),
        }

    if any(token in low for token in ("repo", "repository", "file", "codice", "progetto", "patch", "test", "smoke", "valid")):
        return "vulkan_helper", {
            "public_tool_name": public_tool_name,
            "task": task,
            "reason": "Vulkan was consulted but emitted no usable native tool_call; fallback to composite helper.",
            "arguments": original_args,
            "selector_response_preview": compact(selector_response, 4000),
        }

    return "", {}
def select_internal_tool(
    *,
    public_tool_name: str,
    task: str,
    original_args: dict[str, Any],
    timeout_seconds: int,
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    system = (
    "Sei Vulkan GPU0 tool-call repair/JSON normalizer. Non sei planner. "
    "Devi solo riparare output sporco del planner 11434 in una decisione JSON valida già implicita nel testo. "
    "Non aggiungere strategia nuova. Non inventare file. Non produrre final_answer se action=tool. "
    "Se non è chiara una action/tool/arguments, restituisci action=block. "
    "Schema: {\"action\":\"tool|final|block\", \"tool\":\"repo_status|repo_tree|repo_search|repo_read|repo_apply_patch|repo_validate|repo_command|repo_capabilities\", "
    "\"arguments\":{}, \"reason\":\"...\", \"final_answer\":\"...\"}. "
    "Non aggiungere markdown."
    )
    user = (
        f"PUBLIC_TOOL_X={public_tool_name}\n"
        f"REQUEST={task}\n"
        f"ARGUMENTS_FROM_30B={json.dumps(original_args, ensure_ascii=False, indent=2, default=str)}\n"
        "Fase richiesta: emetti una sola native tool_call interna L."
    )
    response = post_json(
        OLLAMA_TASK_URL,
        {
            "model": OLLAMA_TASK_MODEL,
            "stream": False,
            "keep_alive": OLLAMA_KEEP_ALIVE,
            "think": False,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "tools": TOOLS_SCHEMA,
            "options": ollama_options(
                num_predict=int(os.environ.get("AICARMINE_VULKAN_INTERPRETER_NUM_PREDICT", "1024"))
            ),
        },
        timeout=max(15, min(timeout_seconds, 240)),
    )
    if response.get("backend_unreachable") or response.get("backend_timeout"):
        return "", {}, response
    message = response.get("message") if isinstance(response.get("message"), dict) else {}
    calls = message.get("tool_calls") if isinstance(message.get("tool_calls"), list) else []
    if not calls:
        return "", {}, response
    raw_name, raw_args = parse_tool_call(calls[0])
    tool_name = normalize_tool_name(raw_name)
    if tool_name not in VALID_INTERNAL_TOOLS:
        return "vulkan_helper", {
            "public_tool_name": public_tool_name,
            "task": task,
            "reason": f"unsupported internal tool emitted by Vulkan: {raw_name}",
            "arguments": original_args,
        }, response
    return tool_name, raw_args, response


def summary_from_result(result: dict[str, Any]) -> str:
    for key in ("answer_for_30b", "context_for_30b", "summary", "content", "text", "message", "stdout_tail"):
        value = result.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:MAX_TOOL_RESULT_CHARS]
    return compact(result, MAX_TOOL_RESULT_CHARS)


def deterministic_public_wrapper(
    *,
    public_tool_name: str,
    original_args: dict[str, Any],
    internal_tool: str,
    internal_args: dict[str, Any],
    dispatcher_result: dict[str, Any],
    selector_response: dict[str, Any],
    root: Path,
) -> dict[str, Any]:
    dispatcher_result = dict(dispatcher_result or {})
    dispatcher_result.setdefault("called_by_vulkan", internal_tool)
    ok = bool(dispatcher_result.get("ok", False))
    summary = summary_from_result(dispatcher_result)
    artifacts = [str(dispatcher_result.get("artifact"))] if dispatcher_result.get("artifact") else []
    return {
        "ok": ok,
        "service": "vulkan_agent",
        "mode": V6_MARKER,
        "verdict": "PUBLIC_TOOL_X_RESULT_READY" if ok else "PUBLIC_TOOL_X_RESULT_FAILED",
        "tool_name": public_tool_name,
        "tool_result_for": public_tool_name,
        "operation_id": public_tool_name,
        "called_by_30b": public_tool_name,
        "arguments_from_30b": original_args,
        "result": dispatcher_result,
        "summary_for_30b": summary,
        "message_for_30b": summary,
        "content": summary,
        "text": summary,
        "final": summary,
        "tool_context_for_30b": summary,
        "verified_problems": dispatcher_result.get("verified_problems") if isinstance(dispatcher_result.get("verified_problems"), list) else [],
        "useful_next_calls": dispatcher_result.get("useful_next_calls") if isinstance(dispatcher_result.get("useful_next_calls"), list) else [],
        "wrapper_call_contract": dispatcher_result.get("wrapper_call_contract") or {
            "public_tool": public_tool_name,
            "rule": "Call the public wrapper tool again with specific parameters when more local context is needed.",
        },
        "session_id": root.name,
        "workspace": str(root),
        "artifacts": artifacts,
        "dispatcher_tool_result_l": dispatcher_result,
        "wrapper_contract": {
            "type": "deterministic_field_mapping",
            "public_tool_x": public_tool_name,
            "internal_tool_l": internal_tool,
            "mapping": {
                "tool_name": "public_tool_x",
                "tool_result_for": "public_tool_x",
                "called_by_30b": "public_tool_x",
                "arguments_from_30b": "original public arguments",
                "result": "raw/structured dispatcher result L",
                "summary_for_30b": "dispatcher summary/context/content or compact JSON",
                "ok": "dispatcher result ok",
            },
        },
        "internal_vulkan": {
            "public_tool_x": public_tool_name,
            "pipeline": "3571 -> 3572 -> 11435(select L) -> 3572(dispatch L + deterministic wrap X) -> 3571 -> 30B",
            "selector_backend_tool_call": (selector_response.get("message") or {}).get("tool_calls", [None])[0] if isinstance(selector_response.get("message"), dict) else None,
            "tool_called_by_vulkan": internal_tool,
            "tool_arguments_by_vulkan": internal_args,
            "dispatcher_executed_internal_tool": True,
            "wrapper_generated_by": "3572 deterministic broker mapping",
            "vulkan_wrapped_dispatcher_result": False,
        },
        "broker_pipeline_contract": (
            "30B/OpenWebUI -> 3571 bridge -> 3572 broker -> 11435 selects internal L -> "
            "3572 dispatcher executes L -> 3572 deterministic wrapper maps L result as public X -> 3571 -> 30B"
        ),
    }


def fail_selector(public_tool_name: str, task: str, original_args: dict[str, Any], root: Path, selector_response: dict[str, Any]) -> dict[str, Any]:
    content = "Vulkan/11435 did not emit a native internal tool_call; dispatcher was not executed."
    return {
        "ok": False,
        "service": "vulkan_agent",
        "mode": V6_MARKER,
        "verdict": "PUBLIC_TOOL_X_RESULT_FAILED",
        "tool_name": public_tool_name,
        "tool_result_for": public_tool_name,
        "operation_id": public_tool_name,
        "called_by_30b": public_tool_name,
        "arguments_from_30b": original_args,
        "result": {"ok": False, "error": content, "selector_response": selector_response},
        "summary_for_30b": content,
        "message_for_30b": content,
        "content": content,
        "text": content,
        "final": content,
        "tool_context_for_30b": content,
        "session_id": root.name,
        "workspace": str(root),
        "internal_vulkan": {
            "public_tool_x": public_tool_name,
            "pipeline": "3571 -> 3572 -> 11435(select L) failed before dispatcher",
            "dispatcher_executed_internal_tool": False,
            "vulkan_wrapped_dispatcher_result": False,
        },
    }


def agent(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        payload = {"payload": payload}
    public_tool_name = public_tool(payload)
    original_args = public_args(payload)
    session_id = make_session_id(str(payload.get("session_id") or original_args.get("session_id") or ""))
    root = session_root(session_id)
    task = text_from_payload(payload, original_args, public_tool_name)
    allow_command = bool(payload.get("allow_command", original_args.get("allow_command", True)))
    user_consent = str(payload.get("user_consent") or original_args.get("user_consent") or "")
    try:
        timeout_seconds = int(payload.get("timeout_seconds") or original_args.get("timeout_seconds") or 120)
    except Exception:
        timeout_seconds = 120
    timeout_seconds = max(15, min(timeout_seconds, 240))

    raw_job_action = str(
        original_args.get("job_action")
        or payload.get("job_action")
        or original_args.get("action")
        or payload.get("action")
        or ""
    ).strip().lower()

    job_id = str(original_args.get("job_id") or payload.get("job_id") or "").strip()

    start_actions = {"", "start", "job_start", "async", "background", "run", "execute"}
    status_actions = {"status", "job_status"}
    result_actions = {"result", "job_result", "final"}
    cancel_actions = {"cancel", "job_cancel"}

    # OpenWebUI often fills action=function-style values such as status/search_text/read_file.
    # For the single public vulkan_helper surface, any call without job_id is a new agent job.
    if public_tool_name == "vulkan_helper" and not job_id:
        job_action = "start"
    elif raw_job_action in start_actions:
        job_action = "start"
    elif raw_job_action in status_actions:
        job_action = "status"
    elif raw_job_action in result_actions:
        job_action = "result"
    elif raw_job_action in cancel_actions:
        job_action = "cancel"
    elif public_tool_name == "vulkan_helper":
        job_action = "start"
    else:
        job_action = raw_job_action

    if job_action == "start":
        return start_agent_job(payload, public_tool_name, original_args, task)
    if job_action == "status":
        return compact_agent_status(job_id, include_events=True)
    if job_action == "result":
        return compact_agent_status(job_id, include_events=True)
    if job_action == "cancel":
        state = load_agent_job_state(job_id)
        if not state:
            return compact_agent_status(job_id, include_events=True)
        state["status"] = "cancel_requested"
        write_agent_job_state(state)
        append_agent_event(job_id, "cancel_requested", "Cancel requested by user.", {}, step=None)
        return compact_agent_status(job_id, include_events=True)

    internal_tool, raw_internal_args, selector_response = select_internal_tool(
        public_tool_name=public_tool_name,
        task=task,
        original_args=original_args,
        timeout_seconds=timeout_seconds,
    )
    if not internal_tool:
        fallback_tool, fallback_args = selector_fallback_tool(
            public_tool_name,
            task,
            original_args,
            selector_response if isinstance(selector_response, dict) else {},
        )
        if fallback_tool:
            internal_tool = fallback_tool
            raw_internal_args = fallback_args
            selector_response = dict(selector_response or {}) if isinstance(selector_response, dict) else {}
            selector_response["aicarmine_selector_fallback"] = {
                "forced_internal_tool": fallback_tool,
                "reason": "11435/Vulkan was called but did not emit a usable native tool_call.",
            }
        else:
            envelope = fail_selector(public_tool_name, task, original_args, root, selector_response if isinstance(selector_response, dict) else {})
            write_json(root / "broker-session.json", envelope)
            return envelope

    internal_args = sanitize_tool_args(internal_tool, raw_internal_args, original_args, public_tool_name)
    if needs_composite_review(public_tool_name, task, original_args, internal_tool, internal_args):
        selector_response = dict(selector_response or {})
        selector_response["aicarmine_selector_guard"] = {
            "reason": "generic_repo_analysis_requires_composite_evidence",
            "selected_tool_from_vulkan": internal_tool,
            "selected_args_from_vulkan": internal_args,
            "forced_internal_tool": "vulkan_helper",
        }
        internal_tool = "vulkan_helper"
        internal_args = {
            "public_tool_name": public_tool_name,
            "public_tool_x": public_tool_name,
            "task": task,
            "reason": "generic repo analysis must gather composite repo evidence, not a single broad search",
            "arguments": original_args,
            "original_30b_arguments": original_args,
            "force_composite_review": True,
        }

    dispatcher_result = dispatch_tool(internal_tool, internal_args, root, allow_command, user_consent)
    dispatcher_result = dict(dispatcher_result or {})
    dispatcher_result.setdefault("called_by_vulkan", internal_tool)
    dispatcher_artifact = root / "tool-results" / f"{now()}-{internal_tool}-dispatcher-v6.json"
    write_json(dispatcher_artifact, dispatcher_result)
    dispatcher_result.setdefault("artifact", str(dispatcher_artifact))

    envelope = deterministic_public_wrapper(
        public_tool_name=public_tool_name,
        original_args=original_args,
        internal_tool=internal_tool,
        internal_args=internal_args,
        dispatcher_result=dispatcher_result,
        selector_response=selector_response if isinstance(selector_response, dict) else {},
        root=root,
    )
    write_json(root / "broker-session.json", envelope)
    return envelope


@app.get("/jobs", include_in_schema=False)
def jobs_index(limit: int = 50) -> HTMLResponse:
    jobs = list_agent_jobs(limit=max(1, min(int(limit or 50), 200)))
    rows = []
    for job in jobs:
        job_id = html.escape(str(job.get("job_id") or ""))
        status = html.escape(str(job.get("status") or ""))
        goal = html.escape(str(job.get("goal") or ""))
        updated = html.escape(str(job.get("updated_at") or ""))
        workspace = html.escape(str(job.get("workspace") or ""))
        rows.append(
            "<tr>"
            f"<td><a href='/jobs/{job_id}'>{job_id}</a></td>"
            f"<td>{status}</td>"
            f"<td><pre>{goal}</pre></td>"
            f"<td>{updated}</td>"
            f"<td><pre>{workspace}</pre></td>"
            "</tr>"
        )
    return HTMLResponse(
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta http-equiv='refresh' content='5'>"
        "<title>AI-Carmine Agent Jobs</title>"
        "<style>"
        "body{font-family:Segoe UI,Arial,sans-serif;margin:20px;background:#111;color:#ddd}"
        "a{color:#8fd3ff} table{border-collapse:collapse;width:100%}"
        "td,th{border-bottom:1px solid #333;padding:8px;vertical-align:top}"
        "pre{white-space:pre-wrap;margin:0}"
        "</style></head><body>"
        "<h1>AI-Carmine Agent Jobs</h1>"
        "<p>Auto-refresh ogni 5 secondi.</p>"
        "<table><thead><tr><th>Job</th><th>Status</th><th>Goal</th><th>Updated</th><th>Workspace</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
        "</body></html>"
    )


@app.get("/jobs.json", include_in_schema=False)
def jobs_json(limit: int = 50) -> dict[str, Any]:
    return {
        "ok": True,
        "jobs": list_agent_jobs(limit=max(1, min(int(limit or 50), 200))),
    }


@app.get("/jobs/{job_id}", include_in_schema=False)
def job_dashboard(job_id: str) -> HTMLResponse:
    return HTMLResponse(agent_job_html(job_id))


@app.get("/jobs/{job_id}/json", include_in_schema=False)
def job_dashboard_json(job_id: str) -> dict[str, Any]:
    return compact_agent_status(job_id, include_events=True)


@app.get("/jobs/{job_id}/events", include_in_schema=False)
def job_dashboard_events(job_id: str) -> PlainTextResponse:
    path = agent_job_events_path(job_id)
    if not path.exists():
        return PlainTextResponse("", media_type="text/plain; charset=utf-8")
    return PlainTextResponse(path.read_text(encoding="utf-8", errors="replace"), media_type="text/plain; charset=utf-8")
@app.get("/health", include_in_schema=False)
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "service": "aicarmine-vulkan-tool-broker",
        "mode": V6_MARKER,
        "ollama_task_url": OLLAMA_TASK_URL,
        "ollama_task_model": OLLAMA_TASK_MODEL,
        "planner_url": PLANNER_URL,
        "planner_model": PLANNER_MODEL,
        "agentic_planner_enabled": AGENTIC_PLANNER_ENABLED,
        "agent_job_root": str(AGENT_JOB_ROOT),
        "agent_job_db": str(AGENT_JOB_DB),
        "job_endpoints": [
            "/jobs",
            "/jobs.json",
            "/jobs/{job_id}",
            "/jobs/{job_id}/json",
            "/jobs/{job_id}/events",
        ],
        "lab_repo": str(LAB_REPO),
        "workspace": str(WORKSPACE),
    }
@app.get("/jobs/{job_id}/planner-stream", include_in_schema=False)
def job_planner_stream_index(job_id: str) -> PlainTextResponse:
    root = agent_job_planner_stream_dir(job_id)
    files = sorted(root.glob("step-*.*"))

    if not files:
        return PlainTextResponse("", media_type="text/plain; charset=utf-8")

    parts: list[str] = []
    for path in files:
        parts.append(f"\n\n===== {path.name} =====\n")
        parts.append(path.read_text(encoding="utf-8", errors="replace"))

    return PlainTextResponse("".join(parts), media_type="text/plain; charset=utf-8")

@app.post(
    "/vulkan/agent",
    operation_id="ask_vulkan_agent",
    summary="Internal Vulkan public-X provider",
    description=(
        "Receives public X from 3571. 11435/Vulkan selects internal tool L. "
        "3572 executes L and deterministically maps dispatcher result L into public-X tool_result."
    ),
)
def ask_vulkan_agent(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    return agent(payload)


def custom_openapi() -> dict[str, Any]:
    from fastapi.openapi.utils import get_openapi

    schema = get_openapi(title=app.title, version=app.version, description=app.description, routes=app.routes)
    schema["paths"] = {path: methods for path, methods in schema.get("paths", {}).items() if path == "/vulkan/agent"}
    schema["x-aicarmine-internal"] = True
    schema["x-aicarmine-mode"] = V6_MARKER
    schema["x-aicarmine-contract"] = (
        "3572: public X from 3571 -> 11435 selects internal L -> 3572 dispatcher executes L -> "
        "3572 deterministic field mapping wraps L result as public X -> 3572 returns wrapper."
    )
    return schema


app.openapi_schema = None
app.openapi = custom_openapi
