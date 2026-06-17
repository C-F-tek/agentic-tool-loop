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

function updateActiveJob(jobId = "", statusText = "") {
  const panel = document.getElementById("active-job-panel");
  if (!panel) return;
  
  const cleanJob = String(jobId || "").trim();
  
  if (!cleanJob) {
    panel.innerHTML = `
      <div class="card active-job">
        <h2>Active loop</h2>
        <p class="muted">No job selected.</p>
      </div>
    `;
    return;
  }
  
  panel.innerHTML = `
    <div class="card active-job">
      <div class="shell-header">
        <div>
          <h2 class="shell-title">Active loop</h2>
          <div class="status-line">
            <span>job</span>
            <b>${htmlEscape(cleanJob)}</b>
            <span class="muted">${htmlEscape(statusText)}</span>
          </div>
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
    </div>
  `;
}

function selectJob(jobId, autoPoll = true) {
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
  
  updateActiveJob(cleanJob, autoPoll ? "polling" : "selected");
  
  if (autoPoll) {
    startPolling();
  } else {
    loadJob(true);
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
    
    if (data.ok && data.job_id) {
      const jobId = String(data.job_id).trim();
      
      resultEl.textContent = pretty(data);
      selectJob(jobId, true);
      
      setStatus(
        mode === "wait"
          ? "started_wait_result_loaded"
          : "started_polling"
      );
    } else {
      resultEl.textContent = pretty(data);
      setStatus("start_failed");
    }
  } catch (err) {
    data = {ok: false, error: err.message};
    resultEl.textContent = pretty(data);
    setStatus("start_failed");
  } finally {
    setLaunchBusy(false);
  }
  
  return data;
}

async function loadJob(force = false) {
  captureGuidedDraft();
  
  const guidedPrompt = document.getElementById("guided-operator-prompt");
  const guidedInputFocused =
    guidedPrompt && document.activeElement === guidedPrompt;
  
  if (
    !force &&
    (guidedComposeInFlight ||
      guidedInputFocused ||
      guidedDraftText.trim())
  ) {
    setStatus(
      guidedComposeInFlight
        ? "poll_paused_composing"
        : "poll_paused_guided_input"
    );
    return;
  }
  
  const input = document.getElementById("job-id");
  const jobId = String(input?.value || currentJobId || "").trim();
  
  if (!jobId) {
    setStatus("job_id_missing");
    return;
  }
  
  currentJobId = jobId;
  updateActiveJob(jobId, "loading");
  
  const params = labLimitParams();
  
  try {
    const response = await fetch(
      `/jobs/${encodeURIComponent(jobId)}/planner-lab.json?${params.toString()}`
    );
    const data = await response.json();
    
    if (!response.ok || data.ok === false) {
      document.getElementById("lab-output").innerHTML =
        `<div class="card bad"><h2>Load failed</h2>` +
        `<pre>${htmlEscape(pretty(data))}</pre></div>`;
      setStatus("load_failed");
      updateActiveJob(jobId, "load failed");
      return;
    }
    
    renderLab(data);
    updateActiveJob(jobId, data.job?.status || "loaded");
  } catch (err) {
    document.getElementById("lab-output").innerHTML =
      `<div class="card bad"><h2>Load failed</h2>` +
      `<pre>${htmlEscape(String(err?.message || err))}</pre></div>`;
    setStatus("load_failed");
    updateActiveJob(jobId, "load failed");
  }
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
  if (!currentJobId || guidedComposeInFlight) return;
  
  captureGuidedDraft();
  const instruction = guidedDraftText.trim();
  
  if (!instruction) {
    setStatus("operator_prompt_missing");
    return;
  }
  
  const turnId = `turn-${Date.now()}-${guidedTurnCounter++}`;
  const priorConversation = guidedConversation
    .filter(turn => turn.status !== "waiting")
    .slice(-8);
  
  guidedConversation.push({
    role: "operator",
    turn_id: turnId,
    content: instruction,
    status: "ok",
    ts: new Date().toISOString(),
  });
  
  guidedConversation.push({
    role: "assistant",
    turn_id: `${turnId}-waiting`,
    waiting_for: turnId,
    status: "waiting",
    content: "Waiting for structured response...",
    ts: new Date().toISOString(),
  });
  
  guidedDraftText = "";
  guidedComposeInFlight = true;
  renderGuidedConversation();
  setStatus("compose_waiting_for_ollama");
  
  try {
    const payload = {
      instruction,
      conversation: priorConversation,
      think: Boolean(
        document.getElementById("compose-think")?.checked
      ),
      summary_chars: Number(
        document.getElementById("summary-chars")?.value || 4000
      ),
      step_limit: Number(
        document.getElementById("step-limit")?.value || 80
      ),
      code_product_limit: Number(
        document.getElementById("code-product-limit")?.value || 40
      ),
      max_payload_chars: Number(
        document.getElementById("compose-payload-chars")?.value || 30000
      ),
      timeout_seconds: Number(
        document.getElementById("compose-timeout")?.value || 60
      ),
    };
    
    const response = await fetch(
      `/jobs/${encodeURIComponent(currentJobId)}/planner-lab/compose`,
      {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(payload),
      }
    );
    
    const data = await response.json();
    
    guidedConversation = guidedConversation.filter(
      turn => turn.waiting_for !== turnId
    );
    
    const result = data.result || {};
    const structured = result.structured_answer || {};
    
    guidedConversation.push({
      role: "assistant",
      turn_id: `${turnId}-assistant`,
      status: data.ok ? "ok" : "failed",
      content:
        structured.answer_markdown ||
        result.content ||
        data.error ||
        "No structured answer returned.",
      structured_answer: structured,
      thinking: result.thinking || "",
      raw: data,
      ts: new Date().toISOString(),
    });
    
    setStatus(data.ok ? "compose_done" : "compose_failed");
  } catch (err) {
    guidedConversation = guidedConversation.filter(
      turn => turn.waiting_for !== turnId
    );
    
    guidedConversation.push({
      role: "assistant",
      turn_id: `${turnId}-error`,
      status: "failed",
      content: String(err?.message || err),
      ts: new Date().toISOString(),
    });
    
    setStatus("compose_failed");
  } finally {
    guidedComposeInFlight = false;
    renderGuidedConversation();
  }
}

function renderGuidedConversation(conversation) {
  if (!conversation || !Array.isArray(conversation)) return "";
  return conversation.map(turn => renderChatTurn(turn.role, turn.kind, turn.text)).join("");
}

function renderGuidedTurn(turn) {
  return renderChatTurn(turn.role, turn.kind, turn.text);
}

function renderLab(data) {
  const labOutput = document.getElementById("lab-output");
  if (!labOutput) return;
  
  const job = data.job || {};
  const jobId = String(job.job_id || currentJobId || "");
  const readiness = data.payload_readiness || {};
  const chat = data.chat_turn || {};
  const priorityEvidence = data.priority_evidence_for_30b || {};
  const priorityItems = Array.isArray(priorityEvidence.items)
    ? priorityEvidence.items
    : [];
  const steps = Array.isArray(data.step_summaries)
    ? data.step_summaries
    : [];
  const products = Array.isArray(data.code_products)
    ? data.code_products
    : [];
  
  labOutput.innerHTML = `
    <div class="planner-lab-container">
      <div class="planner-lab-section">
        <h3>Job: ${htmlEscape(jobId)}</h3>
        ${renderOwnerPayloadFocus(data.owner_payload_focus || {})}
        ${renderPublicToolResponse(data.public_tool_response_view || {})}
      </div>
      
      <div class="planner-lab-section">
        <h2>Payload readiness</h2>
        ${renderMetrics(readiness)}
        <pre>${htmlEscape((readiness.warnings || []).join("\n"))}</pre>
      </div>
      
      <div class="planner-lab-section">
        <h2>Priority evidence</h2>
        ${renderPriorityRows(priorityItems)}
      </div>
      
      <div class="planner-lab-section">
        <h2>Step summaries</h2>
        ${renderSteps(steps)}
      </div>
      
      <div class="planner-lab-section">
        <h2>Code products</h2>
        ${renderCodeProducts(products)}
      </div>
      
      <div class="planner-lab-section">
        <h2>Job conversation</h2>
        ${renderChatTurnSummary(chat)}
      </div>
      
      <div class="planner-lab-followup-panel">
        <h4>Operator follow-up</h4>
        <textarea
          id="guided-operator-prompt"
          class="planner-lab-followup-input"
          oninput="captureGuidedDraft()"
          placeholder="Chiedi dettagli, correzioni o integrazioni sulla risposta..."
        >${htmlEscape(guidedDraftText)}</textarea>
        
        <label>
          <input id="compose-think" type="checkbox">
          request thinking trace
        </label>
        
        <label>max_payload_chars</label>
        <input
          id="compose-payload-chars"
          type="number"
          min="5000"
          max="80000"
          value="30000"
        >
        
        <label>timeout_seconds</label>
        <input
          id="compose-timeout"
          type="number"
          min="15"
          max="180"
          value="60"
        >
        
        <button onclick="composeFromPayload()">Ask follow-up</button>
      </div>
      
      <div id="guided-conversation"></div>
    </div>
  `;
  
  renderGuidedConversation();
  updateActiveJob(jobId, job.status || "loaded");
  setStatus(`loaded ${jobId}`);
}

function renderChatTurnSummary(chat) {
  const gaps = Array.isArray(chat.payload_gaps)
    ? chat.payload_gaps
    : [];
  
  return `
    <div class="card">
      <h2>Job conversation</h2>
      
      <div class="chat-grid">
        <div class="bubble user">
          <b>User request</b>
          <pre>${htmlEscape(chat.user_message || "")}</pre>
        </div>
        
        <div class="bubble assistant">
          <b>Terminal assistant response</b>
          <pre>${htmlEscape(
            chat.assistant_message ||
            "No assistant response available."
          )}</pre>
        </div>
        
        ${
          gaps.length
            ? `<div class="bubble warn">
                 <b>Payload gaps</b>
                 <pre>${htmlEscape(gaps.join("\n"))}</pre>
               </div>`
            : ""
        }
      </div>
    </div>
  `;
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
if (initialJobId) {
  const input = document.getElementById("job-id");
  if (input) input.value = initialJobId;
  selectJob(initialJobId, true);
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