"""Shared HTML assets for job views: CSS, JS utilities, and common render helpers."""
from __future__ import annotations

import html
import json
from typing import Any


# Base CSS shared across all job views
BASE_CSS = """
* { box-sizing: border-box; }
body { font-family: Segoe UI, Arial, sans-serif; margin: 18px; background: #101112; color: #e3e3e3; overflow-x: hidden; }
a { color: #8fd3ff; }
.grid { display: grid; grid-template-columns: minmax(280px, 0.82fr) minmax(0, 1.42fr); gap: 14px; align-items: start; min-width: 0; }
.card { border: 1px solid #3a3a3a; border-radius: 8px; padding: 14px; margin-bottom: 14px; background: #1b1c1f; min-width: 0; max-width: 100%; overflow: hidden; overflow-wrap: anywhere; }
textarea, input { width: 100%; box-sizing: border-box; background: #0f1012; color: #eee; border: 1px solid #444; border-radius: 6px; padding: 8px; }
input[type="checkbox"] { width: auto; margin-right: 6px; }
label { display: block; margin-top: 8px; color: #c8c8c8; }
textarea { min-height: 145px; resize: vertical; }
button { background: #2b6ca3; color: white; border: 0; border-radius: 6px; padding: 8px 11px; margin: 4px 4px 4px 0; cursor: pointer; }
button.secondary { background: #3d4651; }
button.danger { background: #9a3d3d; }
button:disabled { opacity: 0.45; cursor: not-allowed; }
pre { white-space: pre-wrap; overflow-wrap: anywhere; overflow-x: auto; max-width: 100%; margin: 0; font-size: 12px; line-height: 1.35; }
table { border-collapse: collapse; width: 100%; table-layout: fixed; }
td, th { border-bottom: 1px solid #333; padding: 7px; vertical-align: top; overflow-wrap: anywhere; }
.metric-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 150px), 1fr)); gap: 8px; min-width: 0; }
.metric { border: 1px solid #333; border-radius: 6px; padding: 8px; background: #141519; }
.metric span { color: #aaa; display: block; font-size: 11px; }
.metric b { display: block; margin-top: 4px; overflow-wrap: anywhere; }
.pill { display: inline-block; border: 1px solid #3c4d5f; border-radius: 999px; padding: 3px 8px; margin: 2px 4px 2px 0; background: #131820; color: #dbeeff; font-size: 12px; }
.shell-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.shell-title { margin: 0; }
.toolbar { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
.toolbar a, .toolbar button { margin: 0; }
.job-actions { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.job-actions a { display: inline-block; border: 1px solid #3d5368; border-radius: 6px; padding: 7px 9px; background: #13202a; color: #d8efff; text-decoration: none; }
.active-job { border-left: 4px solid #6fb3e8; }
.status-line { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.status-line b { color: #f0f0f0; }
.recent-actions { white-space: nowrap; }
.recent-actions button, .recent-actions a { margin: 2px; }
.mini-link { display: inline-block; color: #bfe5ff; text-decoration: none; border-bottom: 1px solid #44657d; }
.recent-job-list { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 260px), 1fr)); gap: 8px; max-height: min(52vh, 620px); overflow: auto; padding-right: 2px; }
.recent-job { border: 1px solid #303a43; border-radius: 7px; background: #14171b; padding: 9px; min-width: 0; }
.recent-job-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 8px; flex-wrap: wrap; }
.recent-job-id { font-family: Consolas, monospace; overflow-wrap: anywhere; }
.recent-job-goal { color: #c9d1d8; margin: 7px 0; display: -webkit-box; -webkit-line-clamp: 4; -webkit-box-orient: vertical; overflow: hidden; }
.recent-job-actions { display: flex; flex-wrap: wrap; gap: 6px; }
.recent-job-actions button, .recent-job-actions a { margin: 0; }
.chat-grid { display: grid; grid-template-columns: 1fr; gap: 10px; }
.bubble { border-radius: 8px; padding: 11px; border: 1px solid #333; }
.bubble.user { background: #182331; border-left: 4px solid #6fb3e8; }
.bubble.assistant { background: #18281f; border-left: 4px solid #64b773; }
.bubble.warn { background: #2a2417; border-left: 4px solid #d0a34d; }
.timeline { display: grid; gap: 8px; }
.step-card { border: 1px solid #333; border-radius: 7px; padding: 9px; background: #141519; }
.step-card b { color: #f0f0f0; }
.ok { border-left: 4px solid #45a75a; }
.warn { border-left: 4px solid #d0a34d; }
.bad { border-left: 4px solid #d15b5b; }
.muted { color: #aaa; }
@media (max-width: 980px) {
  body { margin: 10px; }
  .grid { grid-template-columns: minmax(0, 1fr); }
  .recent-job-list { max-height: none; }
}
"""

# Base JavaScript utilities shared across all job views
BASE_JS = """
function htmlEscape(value) {
  return String(value ?? "").replace(/[&<>"']/g, ch => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  })[ch]);
}

function pretty(value) {
  return JSON.stringify(value ?? {}, null, 2);
}

function setStatus(text) {
  const target = document.getElementById("lab-status");
  if (!target) return;
  target.textContent = text;
  target.setAttribute("data-status", text);
}

function jobPath(jobId, suffix = "") {
  return `/jobs/${encodeURIComponent(jobId)}${suffix}`;
}

function stopPolling() {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = null;
  setStatus(currentJobId ? `poll_stopped ${currentJobId}` : "poll_stopped");
}

function updateActiveJob(jobId = "", statusText = "") {
  const target = document.getElementById("active-job-panel");
  if (!target) return;
  const cleanJob = String(jobId || "").trim();
  if (!cleanJob) {
    target.innerHTML = `<div class="card active-job">
      <h2>Active loop</h2>
      <p class="muted">No job selected.</p>
    </div>`;
    return;
  }
  target.innerHTML = `<div class="card active-job">
    <div class="shell-header">
      <div>
        <h2 class="shell-title">Active loop</h2>
        <div class="status-line"><span>job</span><b>${htmlEscape(cleanJob)}</b><span class="muted">${htmlEscape(statusText || "")}</span></div>
      </div>
      <div class="toolbar">
        <button onclick="loadJob(true)">Load</button>
        <button class="secondary" onclick="startPolling()">Poll</button>
        <button class="secondary" onclick="stopPolling()">Stop poll</button>
      </div>
    </div>
    <div class="job-actions">
      <a href="${jobPath(cleanJob, "/planner-lab")}">job lab</a>
      <a href="${jobPath(cleanJob, "/ia-view")}">IA view</a>
      <a href="${jobPath(cleanJob, "/events")}">events</a>
      <a href="${jobPath(cleanJob, "/planner-stream")}">planner stream</a>
      <a href="${jobPath(cleanJob, "/final.json")}">final json</a>
      <a href="${jobPath(cleanJob, "/json")}">status json</a>
    </div>
  </div>`;
}

function selectJob(jobId, poll = true) {
  const cleanJob = String(jobId || "").trim();
  if (!cleanJob) {
    setStatus("job_id_missing");
    return;
  }
  if (currentJobId && currentJobId !== cleanJob) {
    guidedConversation = [];
    guidedDraftText = "";
  }
  currentJobId = cleanJob;
  const input = document.getElementById("job-id");
  if (input) input.value = cleanJob;
  updateActiveJob(cleanJob, poll ? "polling" : "selected");
  if (poll) startPolling();
  else loadJob(true);
}

function setLaunchBusy(busy) {
  document.querySelectorAll("[data-launch-button]").forEach(button => {
    button.disabled = !!busy;
  });
}
"""

# Planner Lab extra CSS (specific to the lab UI)
PLANNER_LAB_EXTRA_CSS = """
.planner-lab-container { max-width: 1200px; margin: 0 auto; }
.planner-lab-section { margin-top: 16px; }
.planner-lab-section h3 { margin: 0 0 8px; color: #bfe5ff; font-size: 14px; }
.planner-lab-content { background: #141519; border: 1px solid #333; border-radius: 6px; padding: 10px; }
.planner-lab-followup-panel { margin-top: 12px; padding: 10px; background: #1a1c1e; border: 1px solid #3a3a3a; border-radius: 6px; }
.planner-lab-followup-panel h4 { margin: 0 0 8px; color: #8fd3ff; font-size: 13px; }
.planner-lab-followup-input { width: 100%; min-height: 60px; margin-bottom: 8px; }
.planner-lab-followup-btn { float: right; }
.planner-lab-chain { margin-top: 8px; padding: 8px; background: #0f1012; border-radius: 4px; font-size: 11px; color: #888; }
.planner-lab-chain-item { padding: 4px 0; border-bottom: 1px dashed #333; }
.planner-lab-chain-item:last-child { border-bottom: none; }
.planner-lab-chain-label { color: #6fb3e8; font-weight: bold; }
.planner-lab-chain-text { color: #c9d1d8; }
.planner-lab-assessment { margin-top: 8px; padding: 8px; background: #1a1c1e; border-radius: 4px; font-size: 12px; }
.planner-lab-assessment-item { margin: 4px 0; }
.planner-lab-missing { color: #d15b5b; }
.planner-lab-ready { color: #45a75a; }
.planner-lab-products { margin-top: 8px; padding: 8px; background: #1a1c1e; border-radius: 4px; font-size: 12px; }
.planner-lab-product { margin: 4px 0; word-break: break-all; }
.planner-lab-faq { margin-top: 8px; padding: 8px; background: #1a1c1e; border-radius: 4px; font-size: 12px; }
.planner-lab-faq-item { margin: 4px 0; }
"""

# Planner Lab extra JavaScript (specific to the lab UI)
PLANNER_LAB_JS = """
let guidedConversation = [];
let guidedTurnCounter = 0;
let guidedDraftText = "";
let guidedComposeInFlight = false;

function renderPendingChat(task) {
  return `<div class="bubble warn">
    <div>Launching planner job: <b>${htmlEscape(task)}</b></div>
    <div class="muted">Waiting for result...</div>
  </div>`;
}

function renderChatBubble(role, kind, text) {
  const bubbleClass = role === "user" ? "user" : role === "assistant" ? "assistant" : "";
  const kindClass = kind === "warn" ? "warn" : "";
  return `<div class="bubble ${bubbleClass} ${kindClass}">
    <div>${htmlEscape(text)}</div>
  </div>`;
}

function renderChainItem(stepIndex, role, kind, text) {
  const roleLabel = role === "user" ? "Operator" : role === "assistant" ? "Assistant" : role;
  const kindLabel = kind === "followup" ? "Follow-up" : kind === "compose" ? "Compose Answer" : kind;
  return `<div class="planner-lab-chain-item">
    <div class="planner-lab-chain-label">${stepIndex}. ${roleLabel}: ${kindLabel}</div>
    <div class="planner-lab-chain-text">${htmlEscape(text)}</div>
  </div>`;
}

function renderThread(thread) {
  if (!thread || !Array.isArray(thread)) {
    return "<div class='muted'>No thread available.</div>";
  }
  return thread.map((item, index) => {
    const role = item.role || "unknown";
    const kind = item.kind || "message";
    const text = item.text || item.content || "";
    return renderChainItem(index + 1, role, kind, text);
  }).join("");
}

function appendThreadItem(role, kind, text) {
  const newItem = {
    role,
    kind,
    text,
    created_at: new Date().toISOString(),
    turn_id: ++guidedTurnCounter,
  };
  guidedConversation.push(newItem);
  return newItem;
}

function submitFollowUp(instruction) {
  if (!instruction || !instruction.trim()) {
    setStatus("followup_empty");
    return;
  }
  if (guidedComposeInFlight) {
    setStatus("compose_in_flight");
    return;
  }
  guidedComposeInFlight = true;
  setStatus("sending_followup");
  
  const payload = {
    instruction: instruction.trim(),
    conversation: guidedConversation,
    summary_chars: 4000,
    step_limit: 80,
    code_product_limit: 40,
    think: false,
    persist_thread: true,
  };
  
  fetch(`/jobs/${encodeURIComponent(currentJobId)}/planner-lab/compose`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  })
  .then(res => res.json())
  .then(data => {
    guidedComposeInFlight = false;
    if (data.ok) {
      const threadDiv = document.getElementById("planner-lab-thread");
      if (threadDiv) {
        threadDiv.innerHTML = renderThread(data.thread || guidedConversation);
      }
      const resultDiv = document.getElementById("planner-lab-result");
      if (resultDiv) {
        resultDiv.innerHTML = renderChatBubble("assistant", "ok", data.answer_markdown || "");
      }
      if (data.follow_up_questions && data.follow_up_questions.length) {
        const faqDiv = document.getElementById("planner-lab-faq");
        if (faqDiv) {
          faqDiv.innerHTML = data.follow_up_questions.map(q => 
            `<div class="planner-lab-faq-item">❓ ${htmlEscape(q)}</div>`
          ).join("");
        }
      }
      setStatus("followup_sent_success");
    } else {
      const errorDiv = document.getElementById("planner-lab-error");
      if (errorDiv) {
        errorDiv.textContent = data.error || "Compose failed.";
      }
      setStatus("followup_sent_failed");
    }
  })
  .catch(err => {
    guidedComposeInFlight = false;
    setStatus("followup_send_error");
    console.error("Follow-up error:", err);
  });
}
"""

def render_page_shell(title: str, body: str, *, extra_css: str = "", extra_js: str = "") -> str:
    """Render a basic page shell with title and body."""
    extra_css_attr = f'<style>{extra_css}</style>' if extra_css else ""
    extra_js_script = f'<script>{extra_js}</script>' if extra_js else ""
    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>{html.escape(title)}</title>
{extra_css_attr}
</head>
<body>
{body}
{extra_js_script}
</body>
</html>"""


def render_json_page(title: str, payload: Any, *, section_url: str = "", max_chars: int = 300_000) -> str:
    """Render a JSON diagnostic page with title and pretty JSON."""
    json_text = _json_pretty(payload, max_chars=max_chars)
    body = f"""
<div class="card">
  <h2>{html.escape(title)}</h2>
  <pre>{json_text}</pre>
</div>
"""
    if section_url:
        body += f'<a href="{html.escape(section_url)}">← Back</a>'
    return render_page_shell(title, body)


def render_json_section(title: str, payload: Any, *, parent_url: str = "", max_chars: int = 300_000) -> str:
    """Render a JSON section (child of a parent page)."""
    json_text = _json_pretty(payload, max_chars=max_chars)
    body = f"""
<h3>{html.escape(title)}</h3>
<pre>{json_text}</pre>
"""
    if parent_url:
        body += f'<a href="{html.escape(parent_url)}">↑ Parent</a>'
    return body


def render_status_badge(ok: bool) -> str:
    """Render a status badge (ok/warn/bad)."""
    if ok:
        return '<span class="pill ok">✓ OK</span>'
    elif ok is False:
        return '<span class="pill bad">✗ Failed</span>'
    else:
        return '<span class="pill warn">⚠ Warning</span>'


def render_metric_grid(metrics: dict[str, Any]) -> str:
    """Render a grid of metrics."""
    if not metrics:
        return ""
    rows = []
    for key, value in sorted(metrics.items()):
        rows.append(f'<div class="metric-row"><span>{html.escape(key)}</span><b>{html.escape(str(value))}</b></div>')
    return "\n".join(rows)


def render_pre_block(value: Any, language: str = "json") -> str:
    """Render a pre-formatted code block."""
    text = _json_pretty(value) if isinstance(value, (dict, list)) else str(value)
    return f'<pre class="{html.escape(language)}">{text}</pre>'


def render_section_link(label: str, href: str) -> str:
    """Render a section link."""
    return f'<a href="{html.escape(href)}">{html.escape(label)}</a>'


def render_toolbar(actions: list[tuple[str, str]]) -> str:
    """Render a toolbar with action links/buttons."""
    if not actions:
        return ""
    parts = []
    for label, href in actions:
        btn_class = ""
        if "secondary" in str(label).lower():
            btn_class = " secondary"
        parts.append(f'<button class="btn{btn_class}" onclick="location.href=\'{html.escape(href)}\'">{html.escape(label)}</button>')
    return " ".join(parts)


def render_job_nav(job_id: str) -> str:
    """Render navigation links for a job."""
    actions = [
        ("job lab", f"{job_id}/planner-lab"),
        ("IA view", f"{job_id}/ia-view"),
        ("events", f"{job_id}/events"),
        ("planner stream", f"{job_id}/planner-stream"),
        ("final json", f"{job_id}/final.json"),
        ("status json", f"{job_id}/json"),
    ]
    return render_toolbar([(label, href) for label, href in actions])


def render_active_job_panel(job_id: str, status_text: str) -> str:
    """Render the active job panel."""
    return f"""
<div class="card active-job">
  <div class="shell-header">
    <div>
      <h2 class="shell-title">Active loop</h2>
      <div class="status-line"><span>job</span><b>{html.escape(job_id)}</b><span class="muted">{html.escape(status_text)}</span></div>
    </div>
    <div class="toolbar">
      <button onclick="loadJob(true)">Load</button>
      <button class="secondary" onclick="startPolling()">Poll</button>
      <button class="secondary" onclick="stopPolling()">Stop poll</button>
    </div>
  </div>
  <div class="job-actions">
    {render_job_nav(job_id)}
  </div>
</div>
"""


def render_pending_chat(task: str) -> str:
    """Render pending chat message."""
    return f"""<div class="bubble warn">
    <div>Launching planner job: <b>{html.escape(task)}</b></div>
    <div class="muted">Waiting for result...</div>
  </div>"""


def render_chat_bubble(role: str, kind: str, text: str) -> str:
    """Render a chat bubble."""
    bubble_class = role if role in ("user", "assistant") else ""
    kind_class = kind if kind == "warn" else ""
    return f"""<div class="bubble {bubble_class} {kind_class}">
    <div>{html.escape(text)}</div>
  </div>"""


def render_thread(thread: list[dict[str, Any]]) -> str:
    """Render operator thread."""
    if not thread or not isinstance(thread, list):
        return "<div class='muted'>No thread available.</div>"
    return "\n".join(render_chain_item(index + 1, item.get("role", "unknown"), item.get("kind", "message"), item.get("text", item.get("content", ""))) for index, item in enumerate(thread))


def render_chain_item(step_index: int, role: str, kind: str, text: str) -> str:
    """Render a chain item."""
    role_label = role if role in ("user", "assistant") else role
    kind_label = kind if kind in ("followup", "compose", "message") else kind
    return f"""<div class="planner-lab-chain-item">
    <div class="planner-lab-chain-label">{step_index}. {role_label}: {kind_label}</div>
    <div class="planner-lab-chain-text">{html.escape(text)}</div>
  </div>"""


def append_thread_item(role: str, kind: str, text: str) -> dict[str, Any]:
    """Append an item to the thread."""
    import datetime
    return {
        "role": role,
        "kind": kind,
        "text": text,
        "created_at": datetime.datetime.now().isoformat(),
        "turn_id": getattr(globals(), "_thread_counter", 0) + 1,
    }


def submit_follow_up(instruction: str, job_id: str, conversation: list, persist_thread: bool = True) -> dict[str, Any]:
    """Submit a follow-up instruction."""
    payload = {
        "instruction": instruction,
        "conversation": conversation,
        "summary_chars": 4000,
        "step_limit": 80,
        "code_product_limit": 40,
        "think": False,
        "persist_thread": persist_thread,
    }
    return payload
