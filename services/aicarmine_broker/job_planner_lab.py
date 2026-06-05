"""Operator-only planner payload lab HTML."""

from __future__ import annotations

import html
import json
from typing import Any

from .job_store import list_agent_jobs


def _json_pretty(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def _html_page(title: str, body: str, *, initial_job_id: str = "") -> str:
    initial = json.dumps(str(initial_job_id or ""))
    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>{html.escape(title)}</title>
<style>
body {{ font-family: Segoe UI, Arial, sans-serif; margin: 18px; background: #101112; color: #e3e3e3; }}
a {{ color: #8fd3ff; }}
.grid {{ display: grid; grid-template-columns: minmax(320px, 0.9fr) minmax(420px, 1.4fr); gap: 14px; align-items: start; }}
.card {{ border: 1px solid #3a3a3a; border-radius: 8px; padding: 14px; margin-bottom: 14px; background: #1b1c1f; }}
textarea, input {{ width: 100%; box-sizing: border-box; background: #0f1012; color: #eee; border: 1px solid #444; border-radius: 6px; padding: 8px; }}
textarea {{ min-height: 145px; resize: vertical; }}
button {{ background: #2b6ca3; color: white; border: 0; border-radius: 6px; padding: 8px 11px; margin: 4px 4px 4px 0; cursor: pointer; }}
button.secondary {{ background: #3d4651; }}
button.danger {{ background: #9a3d3d; }}
button:disabled {{ opacity: 0.45; cursor: not-allowed; }}
pre {{ white-space: pre-wrap; overflow-wrap: anywhere; margin: 0; font-size: 12px; line-height: 1.35; }}
table {{ border-collapse: collapse; width: 100%; }}
td, th {{ border-bottom: 1px solid #333; padding: 7px; vertical-align: top; }}
.metric-row {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 8px; }}
.metric {{ border: 1px solid #333; border-radius: 6px; padding: 8px; background: #141519; }}
.metric span {{ color: #aaa; display: block; font-size: 11px; }}
.metric b {{ display: block; margin-top: 4px; overflow-wrap: anywhere; }}
.chat-grid {{ display: grid; grid-template-columns: 1fr; gap: 10px; }}
.bubble {{ border-radius: 8px; padding: 11px; border: 1px solid #333; }}
.bubble.user {{ background: #182331; border-left: 4px solid #6fb3e8; }}
.bubble.assistant {{ background: #18281f; border-left: 4px solid #64b773; }}
.bubble.warn {{ background: #2a2417; border-left: 4px solid #d0a34d; }}
.timeline {{ display: grid; gap: 8px; }}
.step-card {{ border: 1px solid #333; border-radius: 7px; padding: 9px; background: #141519; }}
.step-card b {{ color: #f0f0f0; }}
.ok {{ border-left: 4px solid #45a75a; }}
.warn {{ border-left: 4px solid #d0a34d; }}
.bad {{ border-left: 4px solid #d15b5b; }}
.muted {{ color: #aaa; }}
</style>
</head>
<body>
{body}
<script>
const initialJobId = {initial};
let currentJobId = initialJobId || "";
let pollTimer = null;
let activeRequestText = "";

function htmlEscape(value) {{
  return String(value ?? "").replace(/[&<>"']/g, ch => ({{"&":"&amp;","<":"&lt;",">":"&gt;","\\"":"&quot;","'":"&#39;"}}[ch]));
}}
function pretty(value) {{
  return JSON.stringify(value ?? {{}}, null, 2);
}}
function setStatus(text) {{
  document.getElementById("lab-status").textContent = text;
}}
async function startPlannerJob() {{
  const task = document.getElementById("planner-request").value.trim();
  if (!task) {{
    setStatus("request_missing");
    return;
  }}
  activeRequestText = task;
  document.getElementById("lab-output").innerHTML = renderPendingChat(task);
  setStatus("starting");
  const response = await fetch("/planner-lab/start", {{
    method: "POST",
    headers: {{"Content-Type": "application/json"}},
    body: JSON.stringify({{
      task,
      return_mode: "background",
      wait_seconds: 1
    }})
  }});
  const data = await response.json();
  document.getElementById("start-result").textContent = pretty(data);
  if (data.job_id) {{
    currentJobId = data.job_id;
    document.getElementById("job-id").value = currentJobId;
    startPolling();
  }} else {{
    setStatus("start_failed");
  }}
}}
async function loadJob() {{
  const jobId = (document.getElementById("job-id").value || currentJobId || "").trim();
  if (!jobId) {{
    setStatus("job_id_missing");
    return;
  }}
  currentJobId = jobId;
  const params = labLimitParams();
  const response = await fetch(`/jobs/${{encodeURIComponent(jobId)}}/planner-lab.json?${{params.toString()}}`);
  const data = await response.json();
  renderLab(data);
}}
function labLimitParams() {{
  const params = new URLSearchParams();
  params.set("summary_chars", document.getElementById("summary-chars")?.value || "4000");
  params.set("step_limit", document.getElementById("step-limit")?.value || "80");
  params.set("code_product_limit", document.getElementById("code-product-limit")?.value || "40");
  return params;
}}
function startPolling() {{
  if (pollTimer) clearInterval(pollTimer);
  loadJob();
  pollTimer = setInterval(loadJob, 2500);
}}
function renderMetrics(readiness) {{
  const rows = Object.entries(readiness || {{}}).filter(([k, v]) => k !== "warnings");
  return `<div class="metric-row">${{rows.map(([k, v]) => `<div class="metric"><span>${{htmlEscape(k)}}</span><b>${{htmlEscape(v)}}</b></div>`).join("")}}</div>`;
}}
function renderPendingChat(task) {{
  return `<div class="card">
    <h2>Chat + Thinking Step Summary</h2>
    <div class="chat-grid">
      <div class="bubble user"><b>User</b><pre>${{htmlEscape(task)}}</pre></div>
      <div class="bubble warn"><b>Planner</b><pre>Job starting. Waiting for payload extracted from the OpenWebUI-bound response.</pre></div>
    </div>
  </div>`;
}}
function renderChatTurn(data) {{
  const chat = data.chat_turn || {{}};
  const userMessage = chat.user_message || activeRequestText || (data.job || {{}}).goal || "";
  const assistantMessage = chat.assistant_message || "";
  const gaps = Array.isArray(chat.payload_gaps) ? chat.payload_gaps : [];
  const visibleFields = chat.assistant_visible_fields || data.model_visible_text || {{}};
  const status = chat.status || (data.job || {{}}).status || "";
  return `<div class="card">
    <h2>Chat + Thinking Step Summary</h2>
    <div class="chat-grid">
      <div class="bubble user"><b>User request</b><pre>${{htmlEscape(userMessage)}}</pre></div>
      <div class="bubble ${{assistantMessage ? "assistant" : "warn"}}"><b>OpenWebUI-bound assistant payload</b><span class="muted"> status=${{htmlEscape(status)}}</span><pre>${{htmlEscape(assistantMessage || "No assistant text extracted yet.")}}</pre></div>
      ${{gaps.length ? `<div class="bubble warn"><b>Payload gaps</b><pre>${{htmlEscape(gaps.join("\\n"))}}</pre></div>` : ""}}
    </div>
    <details><summary>Visible fields sent toward 30B</summary><pre>${{htmlEscape(pretty(visibleFields))}}</pre></details>
  </div>`;
}}
function renderSteps(steps) {{
  if (!Array.isArray(steps) || steps.length === 0) return "<p class='muted'>No steps yet.</p>";
  return `<div class="timeline">${{
    steps.map(step => `<div class="step-card">
      <b>Step ${{htmlEscape(step.step)}} · ${{htmlEscape(step.planner_action || "")}} ${{htmlEscape(step.planner_tool || "")}}</b>
      <div class="muted">tool_result=${{htmlEscape(step.tool_result_tool || "")}} ok=${{htmlEscape(step.tool_result_ok)}} events=${{htmlEscape(step.events || 0)}} coverage=${{htmlEscape(step.coverage_score ?? "")}}</div>
      <div>${{htmlEscape(step.validator_guard || (step.violations || []).join(", "))}}</div>
      <pre>${{htmlEscape(step.required_next_progress || "")}}</pre>
    </div>`).join("")
  }}</div>`;
}}
function renderCodeProducts(products) {{
  if (!Array.isArray(products) || products.length === 0) return "<p class='muted'>No code product extracted from payload.</p>";
  return products.map(item => {{
    const applyDisabled = item.apply_supported ? "" : "disabled";
    const title = item.target_file || item.edit_kind || item.candidate_id;
    const diff = item.unified_diff ? `<details open><summary>Unified diff</summary><pre>${{htmlEscape(item.unified_diff)}}</pre></details>` : "";
    const oldNew = item.has_old_new_text ? `<details><summary>old_text / new_text</summary><pre>${{htmlEscape(item.old_text)}}\\n\\n--- new_text ---\\n${{htmlEscape(item.new_text)}}</pre></details>` : "";
    return `<div class="card ${{item.apply_supported ? "ok" : "warn"}}">
      <h3>${{htmlEscape(title)}}</h3>
      <p class="muted">candidate_id=${{htmlEscape(item.candidate_id)}} source=${{htmlEscape(item.source_path)}}</p>
      <button class="secondary" onclick='copyCandidate(${{JSON.stringify(item.candidate_id)}})'>Copy candidate JSON</button>
      <button class="danger" ${{applyDisabled}} onclick='applyCandidate(${{JSON.stringify(item.candidate_id)}})'>Apply exact old/new patch</button>
      <p>${{htmlEscape(item.apply_block_reason || "")}}</p>
      ${{diff}}${{oldNew}}
    </div>`;
  }}).join("");
}}
async function copyCandidate(candidateId) {{
  const params = labLimitParams();
  const response = await fetch(`/jobs/${{encodeURIComponent(currentJobId)}}/planner-lab.json?${{params.toString()}}`);
  const data = await response.json();
  const item = (data.code_products || []).find(row => row.candidate_id === candidateId);
  await navigator.clipboard.writeText(pretty(item || {{}}));
  setStatus("candidate_copied");
}}
async function applyCandidate(candidateId) {{
  if (!currentJobId) return;
  const message = "Confermi apply interno repo_apply_patch solo per old_text/new_text esatti?";
  if (!window.confirm(message)) return;
  const response = await fetch(`/jobs/${{encodeURIComponent(currentJobId)}}/planner-lab/apply`, {{
    method: "POST",
    headers: {{"Content-Type": "application/json"}},
    body: JSON.stringify({{
      candidate_id: candidateId,
      confirm_apply: true,
      user_consent: "confirm planner-lab exact old_text/new_text patch"
    }})
  }});
  const data = await response.json();
  document.getElementById("apply-result").textContent = pretty(data);
  setStatus(data.ok ? "apply_done" : "apply_blocked");
  loadJob();
}}
function renderLab(data) {{
  const readiness = data.payload_readiness || {{}};
  const statusClass = data.ok && readiness.tool_context_parse_ok ? "ok" : "bad";
  document.getElementById("lab-output").innerHTML = `
    ${{renderChatTurn(data)}}
    <div class="card ${{statusClass}}">
      <h2>Payload readiness</h2>
      ${{renderMetrics(readiness)}}
      <pre>${{htmlEscape((readiness.warnings || []).join("\\n"))}}</pre>
    </div>
    <div class="card"><h2>Thinking step summary</h2>${{renderSteps(data.thinking_step_summary || data.step_summaries || [])}}</div>
    <div class="card"><h2>Code products from payload</h2>${{renderCodeProducts(data.code_products || [])}}</div>
    <div class="card"><h2>Payload index</h2><pre>${{htmlEscape(pretty(data.payload_index_for_30b || {{}}))}}</pre></div>
    <div class="card"><h2>Priority evidence</h2><pre>${{htmlEscape(pretty(data.priority_evidence_for_30b || {{}}))}}</pre></div>
  `;
  setStatus(`loaded ${{currentJobId || ""}}`);
}}
if (initialJobId) {{
  document.getElementById("job-id").value = initialJobId;
  startPolling();
}}
</script>
</body>
</html>"""


def planner_lab_index_html(*, limit: int = 20) -> str:
    rows = []
    for job in list_agent_jobs(limit=max(1, min(int(limit or 20), 100))):
        job_id = html.escape(str(job.get("job_id") or ""))
        rows.append(
            "<tr>"
            f"<td><a href=\"/jobs/{job_id}/planner-lab\">{job_id}</a></td>"
            f"<td>{html.escape(str(job.get('status') or ''))}</td>"
            f"<td>{html.escape(str(job.get('goal') or ''))}</td>"
            "</tr>"
        )
    body = f"""
<div class="card">
  <h1>Planner Payload Lab</h1>
  <p class="muted">Operator-only 3572 view. It starts normal planner jobs and reads the same terminal payload that goes toward OpenWebUI.</p>
  <p><a href="/jobs">jobs home</a></p>
</div>
<div class="grid">
  <div>
    <div class="card">
      <h2>Direct planner request</h2>
      <textarea id="planner-request" placeholder="analizza la repo e proponi diff concreti..."></textarea>
      <button onclick="startPlannerJob()">Start planner job</button>
      <div class="muted">Status: <span id="lab-status">idle</span></div>
      <pre id="start-result"></pre>
    </div>
    <div class="card">
      <h2>Load existing job</h2>
      <input id="job-id" placeholder="job-..." />
      <button onclick="loadJob()">Load once</button>
      <button class="secondary" onclick="startPolling()">Poll</button>
      <pre id="apply-result"></pre>
    </div>
    <div class="card">
      <h2>Operator limits</h2>
      <label>summary_chars</label>
      <input id="summary-chars" type="number" min="500" max="50000" value="4000" />
      <label>step_limit</label>
      <input id="step-limit" type="number" min="1" max="500" value="80" />
      <label>code_product_limit</label>
      <input id="code-product-limit" type="number" min="1" max="200" value="40" />
      <p class="muted">These values affect only this operator lab view, not planner gates or OpenWebUI public schema.</p>
    </div>
    <div class="card">
      <h2>Recent jobs</h2>
      <table><thead><tr><th>Job</th><th>Status</th><th>Goal</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
    </div>
  </div>
  <div id="lab-output"><div class="card"><p class="muted">Start or load a job.</p></div></div>
</div>
"""
    return _html_page("Planner Payload Lab", body)


def agent_job_planner_lab_html(job_id: str) -> str:
    safe_job = html.escape(job_id)
    body = f"""
<div class="card">
  <h1>Planner Payload Lab - {safe_job}</h1>
  <p><a href="/planner-lab">planner lab home</a> &middot; <a href="/jobs/{safe_job}/ia-view">IA view</a> &middot; <a href="/jobs/{safe_job}/final.json">final json</a></p>
</div>
<div class="grid">
  <div>
    <div class="card">
      <h2>Job</h2>
      <input id="job-id" value="{safe_job}" />
      <button onclick="loadJob()">Load once</button>
      <button class="secondary" onclick="startPolling()">Poll</button>
      <div class="muted">Status: <span id="lab-status">idle</span></div>
      <pre id="apply-result"></pre>
    </div>
    <div class="card">
      <h2>Operator limits</h2>
      <label>summary_chars</label>
      <input id="summary-chars" type="number" min="500" max="50000" value="4000" />
      <label>step_limit</label>
      <input id="step-limit" type="number" min="1" max="500" value="80" />
      <label>code_product_limit</label>
      <input id="code-product-limit" type="number" min="1" max="200" value="40" />
      <p class="muted">These values affect only this operator lab view, not planner gates or OpenWebUI public schema.</p>
    </div>
  </div>
  <div id="lab-output"><div class="card"><p class="muted">Loading...</p></div></div>
</div>
"""
    return _html_page(f"Planner Payload Lab {job_id}", body, initial_job_id=job_id)
