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
BASE_JS = r"""
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

# Planner Lab extra JavaScript (specific to the lab UI) - COMPLETE OPERATIONAL SURFACE
PLANNER_LAB_JS = r"""
let guidedConversation = [];
let guidedTurnCounter = 0;
let guidedDraftText = "";
let guidedComposeInFlight = false;

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
    setStatus("stopped");
    const panel = document.getElementById("active-job-panel");
    if (panel) {
      panel.innerHTML = "<div class='muted'>Polling stopped. Use 'Load' or 'Poll' to resume.</div>";
    }
  }
}

function updateActiveJob(jobId, status) {
  const panel = document.getElementById("active-job-panel");
  if (!panel) return;
  
  if (!jobId) {
    panel.innerHTML = "<div class='muted'>No job loaded. Use 'Load' or enter a job ID above.</div>";
    return;
  }
  
  const statusEl = document.getElementById("lab-status");
  if (statusEl) statusEl.textContent = status || "loading";
  
  // Load job data
  fetch(`/jobs/${encodeURIComponent(jobId)}/planner-lab.json`)
    .then(res => res.json())
    .then(data => {
      if (data.ok) {
        renderLab(jobId, data);
      } else {
        panel.innerHTML = `<div class='bad'>Error loading job: ${data.error || 'Unknown error'}</div>`;
      }
    })
    .catch(err => {
      panel.innerHTML = `<div class='bad'>Failed to load job: ${err.message}</div>`;
    });
}

function selectJob(jobId, autoPoll) {
  const input = document.getElementById("job-id");
  if (input) input.value = jobId;
  
  currentJobId = cleanJob || jobId;
  
  if (autoPoll) {
    updateActiveJob(jobId, "polling");
    startPolling();
  } else {
    updateActiveJob(jobId, "loaded");
  }
}

function setLaunchBusy(isBusy) {
  const btns = document.querySelectorAll('[data-launch-button]');
  btns.forEach(btn => {
    btn.disabled = isBusy;
    btn.setAttribute('data-busy', String(isBusy));
  });
}

async function startPlannerJob(mode) {
  const requestEl = document.getElementById("planner-request");
  const waitSecsEl = document.getElementById("wait-seconds");
  const resultEl = document.getElementById("start-result");
  
  if (!requestEl || !waitSecsEl || !resultEl) return {ok: false, error: "Missing UI elements"};
  
  const request = requestEl.value.trim();
  const waitSeconds = parseInt(waitSecsEl.value, 10);
  
  if (!request) {
    resultEl.innerHTML = "<div class='bad'>Enter a request first.</div>";
    return {ok: false, error: "Empty request"};
  }
  
  setLaunchBusy(true);
  setStatus("starting");
  
  const payload = {
    task: request,
    request: request,
    return_mode: mode || "background",
    wait_seconds: waitSeconds,
  };
  
  let data = {ok: false, error: "Request failed"};
  
  try {
    const res = await fetch(`/planner-lab/start`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload),
    });
    
    data = await res.json();
    
    if (data.ok) {
      const jobId = data.job_id;
      resultEl.innerHTML = `<div class='ok'>Job started: <b>${jobId}</b></div>`;
      
      if (mode === "wait") {
        await new Promise(r => setTimeout(r, waitSeconds * 1000));
        updateActiveJob(jobId, "polling");
        startPolling();
      } else {
        updateActiveJob(jobId, "background");
      }
    } else {
      resultEl.innerHTML = `<div class='bad'>${data.error || 'Failed to start job'}</div>`;
    }
  } catch (err) {
    data = {ok: false, error: err.message};
    resultEl.innerHTML = `<div class='bad'>Error: ${err.message}</div>`;
  } finally {
    setLaunchBusy(false);
  }
  
  return data;
}

async function loadJob(reset) {
  const input = document.getElementById("job-id");
  const jobId = input ? input.value.trim() : "";
  const resultEl = document.getElementById("apply-result");
  
  if (!jobId) {
    if (resultEl) resultEl.innerHTML = "<div class='bad'>Enter a job ID first.</div>";
    return {ok: false, error: "No job ID"};
  }
  
  let data = {ok: false, error: "Request failed"};
  
  try {
    const res = await fetch(`/jobs/${encodeURIComponent(jobId)}/planner-lab.json`);
    data = await res.json();
    
    if (data.ok) {
      renderLab(jobId, data);
      if (reset) {
        const activePanel = document.getElementById("active-job-panel");
        if (activePanel) activePanel.innerHTML = "";
      }
      return {ok: true, job_id: jobId};
    } else {
      if (resultEl) resultEl.innerHTML = `<div class='bad'>${data.error || 'Failed to load'}</div>`;
    }
  } catch (err) {
    data = {ok: false, error: err.message};
    if (resultEl) resultEl.innerHTML = `<div class='bad'>Error: ${err.message}</div>`;
  }
  
  return data;
}

function labLimitParams() {
  const params = new URLSearchParams();
  params.set("summary_chars", document.getElementById("summary-chars")?.value || "4000");
  params.set("step_limit", document.getElementById("step-limit")?.value || "80");
  params.set("code_product_limit", document.getElementById("code-product-limit")?.value || "40");
  return params;
}

async function startPolling() {
  if (pollTimer) clearInterval(pollTimer);
  
  loadJob(true);
  pollTimer = setInterval(() => loadJob(false), 2500);
}

function renderMetrics(metrics) {
  if (!metrics) return "";
  const rows = [];
  for (const [key, value] of Object.entries(metrics)) {
    rows.push(`<div class="metric-row"><span>${htmlEscape(key)}</span><b>${htmlEscape(String(value))}</b></div>`);
  }
  return rows.join("");
}

function renderTopLevelSurface(payload) {
  const div = document.createElement("div");
  div.className = "planner-lab-content";
  div.innerHTML = `
    <h3>Job Overview</h3>
    <pre>${pretty(payload)}</pre>
  `;
  return div.outerHTML;
}

function renderInlineFields(fields) {
  if (!fields) return "";
  const items = [];
  for (const [key, value] of Object.entries(fields)) {
    items.push(`<div class="pill">${htmlEscape(key)}: ${htmlEscape(String(value))}</div>`);
  }
  return items.join("");
}

function renderResultRows(rows) {
  if (!rows || !Array.isArray(rows)) return "";
  const html = rows.map(row => {
    const ok = row.ok ?? true;
    const statusClass = ok ? "ok" : "bad";
    const statusIcon = ok ? "✓" : "✗";
    return `<div class="step-card ${statusClass}">
      <b>${statusIcon} ${row.tool || 'unknown'}</b>
      <div>${htmlEscape(row.reason || '')}</div>
      ${row.output ? `<pre>${pretty(row.output)}</pre>` : ''}
    </div>`;
  }).join("");
  return html;
}

function renderOwnerPayloadFocus(payload) {
  if (!payload) return "";
  const owner = payload.owner || "unknown";
  const status = payload.status || "unknown";
  return `<div class="pill">${owner}</div> <span class="muted">(${status})</span>`;
}

function renderPriorityRows(items) {
  if (!items) return "";
  return items.map(item => {
    const priority = item.priority ?? "normal";
    const priorityClass = priority === "high" ? "bad" : priority === "low" ? "ok" : "";
    return `<div class="step-card ${priorityClass}">
      <b>${item.tool || 'unknown'}</b>
      <span class="muted">priority: ${priority}</span>
    </div>`;
  }).join("");
}

function renderArtifactRows(artifacts) {
  if (!artifacts) return "";
  return artifacts.map(a => {
    const path = a.path || "unknown";
    const size = a.size_bytes ?? 0;
    return `<div class="pill">📄 ${htmlEscape(path)} (${size} bytes)</div>`;
  }).join("");
}

function renderStructureRows(structure) {
  if (!structure) return "";
  const lines = [];
  for (const [key, value] of Object.entries(structure)) {
    lines.push(`<div class="pill">${htmlEscape(key)}: ${pretty(value)}</div>`);
  }
  return lines.join("");
}

function renderPublicToolResponse(response) {
  if (!response) return "";
  const tool = response.tool || "unknown";
  const ok = response.ok ?? false;
  const statusClass = ok ? "ok" : "bad";
  return `<div class="step-card ${statusClass}">
    <b>${tool}</b>
    <div>${htmlEscape(response.reason || '')}</div>
  </div>`;
}

function renderPendingChat(task) {
  return `<div class="bubble warn">
    <div>Launching planner job: <b>${htmlEscape(task)}</b></div>
    <div class="muted">Waiting for result...</div>
  </div>`;
}

function renderChatTurn(role, kind, text) {
  const bubbleClass = role === "user" ? "user" : role === "assistant" ? "assistant" : "";
  const kindClass = kind === "warn" ? "warn" : "";
  return `<div class="bubble ${bubbleClass} ${kindClass}">
    <div>${htmlEscape(text)}</div>
  </div>`;
}

function renderSteps(steps) {
  if (!steps || !Array.isArray(steps)) return "";
  return steps.map((step, i) => {
    const stepId = step.step_id ?? `step-${i}`;
    const status = step.status ?? "unknown";
    return `<div class="step-card">
      <b>${stepId}</b>
      <span class="muted">${status}</span>
    </div>`;
  }).join("");
}

function renderCodeProducts(products) {
  if (!products) return "";
  return products.map(p => {
    const target = p.target_file || "unknown";
    const status = p.status ?? "unknown";
    return `<div class="pill">🔧 ${target} (${status})</div>`;
  }).join("");
}

async function copyCandidate(candidate) {
  if (!candidate) return;
  const text = candidate.text || "";
  try {
    await navigator.clipboard.writeText(text);
    setStatus("copied_candidate");
  } catch (err) {
    console.error("Copy failed:", err);
  }
}

async function copyApplyToolCall(toolCall) {
  if (!toolCall) return;
  const text = JSON.stringify(toolCall, null, 2);
  try {
    await navigator.clipboard.writeText(text);
    setStatus("copied_tool_call");
  } catch (err) {
    console.error("Copy failed:", err);
  }
}

async function applyCandidate(candidate) {
  if (!candidate) return {ok: false, error: "No candidate"};
  
  const candidateId = candidate.candidate_id || "";
  const confirmApply = candidate.confirm_apply ?? true;
  const userConsent = candidate.user_consent || "confirm planner-lab exact old_text/new_text patch";
  
  if (!candidateId) {
    return {ok: false, error: "Missing candidate_id"};
  }
  
  try {
    const res = await fetch(`/jobs/${encodeURIComponent(currentJobId)}/planner-lab/apply`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        candidate_id: candidateId,
        confirm_apply: confirmApply,
        user_consent: userConsent,
      }),
    });
    
    const data = await res.json();
    return data;
  } catch (err) {
    return {ok: false, error: err.message};
  }
}

function captureGuidedDraft() {
  const input = document.getElementById("guided-operator-prompt");
  if (input) guidedDraftText = input.value || "";
  return guidedDraftText;
}

async function composeFromPayload() {
  captureGuidedDraft();
  
  const instruction = guidedDraftText.trim();
  if (!instruction || !currentJobId) return;
  
  const payload = {
    instruction,
    conversation: guidedConversation.filter(
      turn => turn.status !== "waiting"
    ).slice(-8),
    think: Boolean(document.getElementById("compose-think")?.checked),
    summary_chars: Number(document.getElementById("summary-chars")?.value || 4000),
    step_limit: Number(document.getElementById("step-limit")?.value || 80),
    code_product_limit: Number(document.getElementById("code-product-limit")?.value || 40),
    max_payload_chars: Number(document.getElementById("compose-payload-chars")?.value || 30000),
    timeout_seconds: Number(document.getElementById("compose-timeout")?.value || 60),
  };
  
  try {
    const res = await fetch(`/jobs/${encodeURIComponent(currentJobId)}/planner-lab/compose`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload),
    });
    
    const data = await res.json();
    return data;
  } catch (err) {
    return {ok: false, error: err.message};
  }
}

function renderGuidedConversation(conversation) {
  if (!conversation || !Array.isArray(conversation)) return "";
  return conversation.map(turn => renderChatTurn(turn.role, turn.kind, turn.text)).join("");
}

function renderGuidedTurn(turn) {
  return renderChatTurn(turn.role, turn.kind, turn.text);
}

function renderLab(jobId, payload) {
  const labOutput = document.getElementById("lab-output");
  if (!labOutput) return;
  
  const div = document.createElement("div");
  div.className = "planner-lab-container";
  div.innerHTML = `
    <div class="planner-lab-section">
      <h3>Job: ${htmlEscape(jobId)}</h3>
      ${renderOwnerPayloadFocus(payload)}
      ${renderMetrics(payload.metrics || {})}
      ${renderInlineFields(payload.fields || {})}
      ${renderResultRows(payload.chat_turn || payload.repair_hints || payload.suggested_next_tool_calls || [])}
      ${renderPriorityRows(payload.priority_evidence_for_30b || payload.priority_items || [])}
      ${renderArtifactRows(payload.artifacts || [])}
      ${renderStructureRows(payload.payload_index_for_30b || payload.structure || {})}
      ${renderPublicToolResponse(payload.public_tool_response_view || payload.public_tool_response || {})}
    </div>
    
    <div class="planner-lab-section">
      <h3>Chat</h3>
      ${renderGuidedConversation(payload.chat_turn || payload.thread || guidedConversation)}
      ${renderPendingChat(payload.pending_task || "")}
    </div>
    
    <div class="planner-lab-section">
      <h3>Step Summaries</h3>
      ${renderSteps(payload.step_summaries || payload.steps || [])}
    </div>
    
    <div class="planner-lab-section">
      <h3>Code Products</h3>
      ${renderCodeProducts(payload.code_products || [])}
    </div>
    
    <div class="planner-lab-followup-panel">
      <h4>Follow-up</h4>
      <textarea id="planner-lab-followup" class="planner-lab-followup-input" placeholder="Enter follow-up instruction...">${guidedDraftText}</textarea>
      <button id="planner-lab-followup-btn" class="planner-lab-followup-btn" onclick="composeFromPayload()">Compose</button>
    </div>
    
    <div class="planner-lab-chain">
      <h4>Thread</h4>
      ${renderThread(payload.chat_turn || payload.thread || guidedConversation)}
    </div>
  `;
  
  labOutput.innerHTML = div.outerHTML;
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

function renderChainItem(stepIndex, role, kind, text) {
  const roleLabel = role === "user" ? "Operator" : role === "assistant" ? "Assistant" : role;
  const kindLabel = kind === "followup" ? "Follow-up" : kind === "compose" ? "Compose Answer" : kind;
  return `<div class="planner-lab-chain-item">
    <div class="planner-lab-chain-label">${stepIndex}. ${roleLabel}: ${kindLabel}</div>
    <div class="planner-lab-chain-text">${htmlEscape(text)}</div>
  </div>`;
}

// Bootstrap: handle initial job ID from URL or query param
const urlParams = new URLSearchParams(window.location.search);
const initialJobId = urlParams.get("job_id") || urlParams.get("id") || "";

if (initialJobId) {
  document.getElementById("job-id").value = initialJobId;
  updateActiveJob(initialJobId, "polling");
  startPolling();
} else {
  updateActiveJob("", "");
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


def _json_pretty(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)