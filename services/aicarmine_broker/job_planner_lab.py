"""Operator-only planner payload lab HTML."""

from __future__ import annotations

import html
import json
from typing import Any

from .job_html_assets import BASE_CSS, BASE_JS, PLANNER_LAB_EXTRA_CSS, PLANNER_LAB_JS
from .job_store import list_agent_jobs


def _json_pretty(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def _html_page(title: str, body: str, *, initial_job_id: str = "") -> str:
    initial = json.dumps(str(initial_job_id or ""))
    css = BASE_CSS + PLANNER_LAB_EXTRA_CSS
    js = BASE_JS + PLANNER_LAB_JS
    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>{html.escape(title)}</title>
<style>
{css}
</style>
</head>
<body>
{body}
<script>
const initialJobId = {initial};
let currentJobId = initialJobId || "";
let pollTimer = null;
let activeRequestText = "";
{js}
</script>
</body>
</html>"""
  target.innerHTML = `<div class="card active-job">
    <div class="shell-header">
      <div>
        <h2 class="shell-title">Active loop</h2>
        <div class="status-line"><span>job</span><b>${{htmlEscape(cleanJob)}}</b><span class="muted">${{htmlEscape(statusText || "")}}</span></div>
      </div>
      <div class="toolbar">
        <button onclick="loadJob(true)">Load</button>
        <button class="secondary" onclick="startPolling()">Poll</button>
        <button class="secondary" onclick="stopPolling()">Stop poll</button>
      </div>
    </div>
    <div class="job-actions">
      <a href="${{jobPath(cleanJob, "/planner-lab")}}">job lab</a>
      <a href="${{jobPath(cleanJob, "/ia-view")}}">IA view</a>
      <a href="${{jobPath(cleanJob, "/events")}}">events</a>
      <a href="${{jobPath(cleanJob, "/planner-stream")}}">planner stream</a>
      <a href="${{jobPath(cleanJob, "/final.json")}}">final json</a>
      <a href="${{jobPath(cleanJob, "/json")}}">status json</a>
    </div>
  </div>`;
}}
function selectJob(jobId, poll = true) {{
  const cleanJob = String(jobId || "").trim();
  if (!cleanJob) {{
    setStatus("job_id_missing");
    return;
  }}
  if (currentJobId && currentJobId !== cleanJob) {{
    guidedConversation = [];
    guidedDraftText = "";
  }}
  currentJobId = cleanJob;
  const input = document.getElementById("job-id");
  if (input) input.value = cleanJob;
  updateActiveJob(cleanJob, poll ? "polling" : "selected");
  if (poll) startPolling();
  else loadJob(true);
}}
function setLaunchBusy(busy) {{
  document.querySelectorAll("[data-launch-button]").forEach(button => {{
    button.disabled = !!busy;
  }});
}}
async function startPlannerJob(returnMode = "background") {{
  const task = document.getElementById("planner-request").value.trim();
  if (!task) {{
    setStatus("request_missing");
    return;
  }}
  activeRequestText = task;
  document.getElementById("lab-output").innerHTML = renderPendingChat(task);
  setStatus("starting");
  guidedConversation = [];
  guidedDraftText = "";
  setLaunchBusy(true);
  try {{
    const response = await fetch("/planner-lab/start", {{
      method: "POST",
      headers: {{"Content-Type": "application/json"}},
      body: JSON.stringify({{
        task,
        return_mode: returnMode,
        wait_seconds: returnMode === "wait" ? Number(document.getElementById("wait-seconds")?.value || 30) : 1
      }})
    }});
    const data = await response.json();
    document.getElementById("start-result").textContent = pretty(data);
    if (data.job_id) {{
      selectJob(data.job_id, true);
      setStatus(returnMode === "wait" ? "started_wait_result_loaded" : "started_polling");
    }} else {{
      setStatus("start_failed");
      updateActiveJob("", "");
    }}
  }} catch (err) {{
    document.getElementById("start-result").textContent = pretty({{ok: false, error: String(err && err.message ? err.message : err)}});
    setStatus("start_failed");
  }} finally {{
    setLaunchBusy(false);
  }}
}}
async function loadJob(force = false) {{
  captureGuidedDraft();
  const guidedPrompt = document.getElementById("guided-operator-prompt");
  const guidedInputFocused = guidedPrompt && document.activeElement === guidedPrompt;
  if (!force && (guidedComposeInFlight || guidedInputFocused || guidedDraftText.trim())) {{
    setStatus(guidedComposeInFlight ? "poll_paused_composing" : "poll_paused_guided_input");
    return;
  }}
  const jobId = (document.getElementById("job-id").value || currentJobId || "").trim();
  if (!jobId) {{
    setStatus("job_id_missing");
    return;
  }}
  const previousJobId = currentJobId;
  if (previousJobId && previousJobId !== jobId) {{
    guidedConversation = [];
    guidedDraftText = "";
  }}
  currentJobId = jobId;
  updateActiveJob(jobId, "loading");
  const params = labLimitParams();
  try {{
    const response = await fetch(`/jobs/${{encodeURIComponent(jobId)}}/planner-lab.json?${{params.toString()}}`);
    const data = await response.json();
    if (!response.ok || data.ok === false) {{
      document.getElementById("lab-output").innerHTML = `<div class="card bad"><h2>Load failed</h2><pre>${{htmlEscape(pretty(data))}}</pre></div>`;
      setStatus("load_failed");
      updateActiveJob(jobId, "load failed");
      return;
    }}
    renderLab(data);
  }} catch (err) {{
    document.getElementById("lab-output").innerHTML = `<div class="card bad"><h2>Load failed</h2><pre>${{htmlEscape(String(err && err.message ? err.message : err))}}</pre></div>`;
    setStatus("load_failed");
    updateActiveJob(jobId, "load failed");
  }}
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
  loadJob(true);
  pollTimer = setInterval(loadJob, 2500);
}}
function renderMetrics(readiness) {{
  const rows = Object.entries(readiness || {{}}).filter(([k, v]) => k !== "warnings");
  return `<div class="metric-row">${{rows.map(([k, v]) => `<div class="metric"><span>${{htmlEscape(k)}}</span><b>${{htmlEscape(v)}}</b></div>`).join("")}}</div>`;
}}
function renderTopLevelSurface(data) {{
  const visible = data.model_visible_text || {{}};
  const audit = data.redundancy_audit || {{}};
  const present = audit.top_level_narrative_fields_present || [];
  const duplicated = audit.duplicated_top_level_aliases || [];
  const contextAliases = audit.tool_context_root_aliases || [];
  return `<div class="card ${{audit.ok === false ? "bad" : "ok"}}">
    <h2>30B top-level surface</h2>
    <p class="muted">One global guide above structured payload. This panel checks that answer/message/summary/content aliases are not duplicated.</p>
    <div>${{present.map(name => `<span class="pill">${{htmlEscape(name)}}</span>`).join("") || "<span class='muted'>No narrative fields detected.</span>"}}</div>
    ${{duplicated.length ? `<p><b>Duplicated top-level aliases</b></p><pre>${{htmlEscape(duplicated.join("\\n"))}}</pre>` : ""}}
    ${{contextAliases.length ? `<p><b>tool_context root aliases</b></p><pre>${{htmlEscape(contextAliases.join("\\n"))}}</pre>` : ""}}
    <details open><summary>evidence_guide_for_30b</summary><pre>${{htmlEscape(visible.evidence_guide_for_30b || "")}}</pre></details>
    <details><summary>Redundancy audit JSON</summary><pre>${{htmlEscape(pretty(audit))}}</pre></details>
  </div>`;
}}
function renderInlineFields(fields) {{
  if (!Array.isArray(fields) || fields.length === 0) return "<p class='muted'>No inline payload fields detected here.</p>";
  return fields.map(field => {{
    const size = field.chars ?? field.items ?? field.keys ?? "";
    const label = `${{field.path || field.field || ""}} · ${{field.type || ""}} ${{size}}`;
    const body = field.preview ? field.preview : pretty(field);
    return `<details><summary>${{htmlEscape(label)}}</summary><pre>${{htmlEscape(body)}}</pre></details>`;
  }}).join("");
}}
function renderResultRows(rows) {{
  if (!Array.isArray(rows) || rows.length === 0) return "<p class='muted'>None.</p>";
  return `<table><thead><tr><th>kind</th><th>path/tool</th><th>complete</th><th>primary location</th></tr></thead><tbody>${{
    rows.map(row => `<tr>
      <td>${{htmlEscape(row.kind || row.payload_type || "")}}</td>
      <td>${{htmlEscape(row.path || row.tool || "")}}</td>
      <td>${{htmlEscape(row.payload_is_complete)}}</td>
      <td>${{htmlEscape(typeof row.primary_location === "object" ? pretty(row.primary_location) : (row.primary_location || row.full_context_location || ""))}}</td>
    </tr>`).join("")
  }}</tbody></table>`;
}}
function renderOwnerPayloadFocus(focus) {{
  if (!focus || !focus.primary_field) return "<p class='muted'>No owner-specific payload focus.</p>";
  const field = focus.primary_field || {{}};
  const body = field.text || field.json_preview || field.preview || pretty(field);
  const supporting = Array.isArray(focus.supporting_fields) ? focus.supporting_fields : [];
  return `<div class="step-card ok">
    <h3>Owner useful payload</h3>
    <div class="metric-row">
      <div class="metric"><span>owner</span><b>${{htmlEscape(focus.owner || field.owner || "")}}</b></div>
      <div class="metric"><span>request_type</span><b>${{htmlEscape(focus.request_type || field.request_type || "")}}</b></div>
      <div class="metric"><span>payload_kind</span><b>${{htmlEscape(field.payload_kind || "")}}</b></div>
      <div class="metric"><span>field</span><b>${{htmlEscape(field.field || "")}}</b></div>
    </div>
    <p class="muted">${{htmlEscape(field.reason || "")}}</p>
    <details open><summary>${{htmlEscape(field.path || "")}}</summary><pre>${{htmlEscape(body)}}</pre></details>
    ${{supporting.length ? `<details><summary>supporting inline fields</summary><pre>${{htmlEscape(pretty(supporting))}}</pre></details>` : ""}}
    <details><summary>owner focus JSON</summary><pre>${{htmlEscape(pretty(focus))}}</pre></details>
  </div>`;
}}
function renderPriorityRows(rows) {{
  if (!Array.isArray(rows) || rows.length === 0) return "<p class='muted'>No priority evidence items.</p>";
  return rows.map(row => `<div class="step-card">
    <b>#${{htmlEscape(row.index)}} ${{htmlEscape(row.kind || "")}}</b>
    <div class="muted">${{htmlEscape(row.path || "")}}</div>
    <div>tool=${{htmlEscape(row.tool || "")}} path=${{htmlEscape(row.repo_path || "")}} complete=${{htmlEscape(row.payload_is_complete)}} accepted=${{htmlEscape(row.validator_accepted)}}</div>
    ${{renderInlineFields(row.inline_fields || [])}}
    <details><summary>keys</summary><pre>${{htmlEscape((row.keys || []).join("\\n"))}}</pre></details>
  </div>`).join("");
}}
function renderArtifactRows(rows) {{
  if (!Array.isArray(rows) || rows.length === 0) return "<p class='muted'>No tool_context artifacts.</p>";
  return rows.map(row => `<div class="step-card">
    <b>#${{htmlEscape(row.index)}} ${{htmlEscape(row.tool || "")}} · ${{htmlEscape(row.kind || "")}}</b>
    <div class="muted">${{htmlEscape(row.path || "")}}</div>
    <div>ok=${{htmlEscape(row.ok)}} path=${{htmlEscape(row.repo_path || "")}} complete=${{htmlEscape(row.payload_is_complete)}}</div>
    ${{renderInlineFields(row.inline_fields || [])}}
    <details><summary>artifact keys</summary><pre>${{htmlEscape((row.artifact_keys || []).join("\\n"))}}</pre></details>
  </div>`).join("");
}}
function renderStructureRows(rows) {{
  if (!Array.isArray(rows) || rows.length === 0) return "<p class='muted'>No structure map.</p>";
  const visible = rows.slice(0, 260);
  return `<table><thead><tr><th>depth</th><th>path</th><th>role</th><th>type/size</th><th>inline</th></tr></thead><tbody>${{
    visible.map(row => {{
      const size = row.chars ?? row.items ?? row.keys ?? "";
      return `<tr>
        <td>${{htmlEscape(row.depth)}}</td>
        <td>${{htmlEscape(row.path || "")}}</td>
        <td>${{htmlEscape(row.role || "")}}</td>
        <td>${{htmlEscape(`${{row.type || ""}} ${{size}}`)}}</td>
        <td>${{htmlEscape(row.inline_payload_candidate)}}</td>
      </tr>`;
    }}).join("")
  }}</tbody></table>`;
}}
function renderPublicToolResponse(data) {{
  const view = data.public_tool_response_view || {{}};
  if (!view.schema) return "";
  const topFields = Array.isArray(view.top_level_fields) ? view.top_level_fields : [];
  const nav = view.navigation || {{}};
  const shape = view.structure_map || {{}};
  const focus = view.owner_payload_focus || data.owner_payload_focus || {{}};
  return `<div class="card">
    <h2>3571 public tool response</h2>
    <div class="metric-row">
      <div class="metric"><span>status</span><b>${{htmlEscape(view.status || "")}}</b></div>
      <div class="metric"><span>job_completed</span><b>${{htmlEscape(view.job_completed)}}</b></div>
      <div class="metric"><span>top_level_fields</span><b>${{htmlEscape(topFields.length)}}</b></div>
      <div class="metric"><span>structure_nodes</span><b>${{htmlEscape(shape.rendered_nodes || 0)}}</b></div>
    </div>
    <details open><summary>human answer from $.evidence_guide_for_30b</summary><pre>${{htmlEscape((view.human_answer || {{}}).text || "")}}</pre></details>
    ${{renderOwnerPayloadFocus(focus)}}
    <details open><summary>top-level returned fields</summary>
      <table><thead><tr><th>field</th><th>role</th><th>type</th><th>size</th></tr></thead><tbody>${{
        topFields.map(row => `<tr>
          <td>${{htmlEscape(row.field || "")}}</td>
          <td>${{htmlEscape(row.role || "")}}</td>
          <td>${{htmlEscape(row.type || "")}}</td>
          <td>${{htmlEscape(row.chars ?? row.items ?? row.keys ?? "")}}</td>
        </tr>`).join("")
      }}</tbody></table>
    </details>
    <details open><summary>payload_index concrete results</summary>${{renderResultRows(nav.concrete_results || [])}}</details>
    <details><summary>payload_index partial / descriptive</summary>
      <h3>partial_results</h3>${{renderResultRows(nav.partial_results || [])}}
      <h3>descriptive_only</h3><pre>${{htmlEscape(pretty(nav.descriptive_only || []))}}</pre>
      <h3>search_order</h3><pre>${{htmlEscape((nav.search_order || []).join("\\n"))}}</pre>
    </details>
    <details open><summary>priority_evidence_for_30b items</summary>${{renderPriorityRows(view.priority_evidence_items || [])}}</details>
    <details><summary>tool_context_for_30b artifacts</summary>${{renderArtifactRows(view.tool_context_artifacts || [])}}</details>
    <details><summary>nesting / field-depth map</summary>
      <p class="muted">Deep inline locations</p>
      <pre>${{htmlEscape((shape.deep_inline_locations || []).join("\\n"))}}</pre>
      ${{renderStructureRows(shape.rows || [])}}
    </details>
  </div>`;
}}
function renderPendingChat(task) {{
  return `<div class="card">
    <h2>Chat + Thinking Step Summary</h2>
    <div class="chat-grid">
      <div class="bubble user"><b>User</b><pre>${{htmlEscape(task)}}</pre></div>
      <div class="bubble warn"><b>Planner</b><pre>Job starting. Waiting for the terminal 30B payload extracted by the internal loop.</pre></div>
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
      <div class="bubble ${{assistantMessage ? "assistant" : "warn"}}"><b>Terminal 30B assistant payload</b><span class="muted"> status=${{htmlEscape(status)}}</span><pre>${{htmlEscape(assistantMessage || "No assistant text extracted yet.")}}</pre></div>
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
    const applyCall = item.apply_tool_call ? `<details open><summary>repo_apply_patch tool call</summary><pre>${{htmlEscape(pretty(item.apply_tool_call))}}</pre></details>` : "";
    return `<div class="card ${{item.apply_supported ? "ok" : "warn"}}">
      <h3>${{htmlEscape(title)}}</h3>
      <p class="muted">candidate_id=${{htmlEscape(item.candidate_id)}} source=${{htmlEscape(item.source_path)}}</p>
      <button class="secondary" onclick='copyCandidate(${{JSON.stringify(item.candidate_id)}})'>Copy candidate JSON</button>
      <button class="secondary" ${{applyDisabled}} onclick='copyApplyToolCall(${{JSON.stringify(item.candidate_id)}})'>Copy repo_apply_patch call</button>
      <button class="danger" ${{applyDisabled}} onclick='applyCandidate(${{JSON.stringify(item.candidate_id)}})'>Apply exact old/new patch</button>
      <p>${{htmlEscape(item.apply_block_reason || "")}}</p>
      ${{applyCall}}${{diff}}${{oldNew}}
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
async function copyApplyToolCall(candidateId) {{
  const params = labLimitParams();
  const response = await fetch(`/jobs/${{encodeURIComponent(currentJobId)}}/planner-lab.json?${{params.toString()}}`);
  const data = await response.json();
  const item = (data.code_products || []).find(row => row.candidate_id === candidateId);
  await navigator.clipboard.writeText(pretty((item || {{}}).apply_tool_call || {{}}));
  setStatus("apply_tool_call_copied");
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
  loadJob(true);
}}
function captureGuidedDraft() {{
  const input = document.getElementById("guided-operator-prompt");
  if (input) guidedDraftText = input.value || "";
}}
async function composeFromPayload() {{
  if (!currentJobId) {{
    setStatus("job_id_missing");
    return;
  }}
  if (guidedComposeInFlight) {{
    setStatus("compose_already_running");
    return;
  }}
  captureGuidedDraft();
  const instruction = guidedDraftText.trim();
  if (!instruction) {{
    setStatus("operator_prompt_missing");
    return;
  }}
  const turnId = `turn-${{Date.now()}}-${{guidedTurnCounter++}}`;
  const priorConversation = guidedConversation.filter(turn => turn.status !== "waiting").slice(-8);
  guidedConversation.push({{
    role: "operator",
    turn_id: turnId,
    content: instruction,
    ts: new Date().toISOString()
  }});
  guidedConversation.push({{
    role: "assistant",
    turn_id: `${{turnId}}-waiting`,
    waiting_for: turnId,
    status: "waiting",
    content: "Waiting for an internal Ollama structured response from the current terminal 30B payload...",
    ts: new Date().toISOString()
  }});
  guidedDraftText = "";
  guidedComposeInFlight = true;
  renderGuidedConversation();
  setStatus("compose_waiting_for_ollama");
  try {{
    const params = labLimitParams();
    const body = {{
      instruction,
      conversation: priorConversation,
      think: Boolean(document.getElementById("compose-think")?.checked),
      summary_chars: Number(params.get("summary_chars") || 4000),
      step_limit: Number(params.get("step_limit") || 80),
      code_product_limit: Number(params.get("code_product_limit") || 40),
      max_payload_chars: Number(document.getElementById("compose-payload-chars")?.value || 30000),
      timeout_seconds: Number(document.getElementById("compose-timeout")?.value || 60)
    }};
    const response = await fetch(`/jobs/${{encodeURIComponent(currentJobId)}}/planner-lab/compose`, {{
      method: "POST",
      headers: {{"Content-Type": "application/json"}},
      body: JSON.stringify(body)
    }});
    const data = await response.json();
    guidedConversation = guidedConversation.filter(turn => turn.waiting_for !== turnId);
    const result = (data || {{}}).result || {{}};
    const structured = result.structured_answer || {{}};
    guidedConversation.push({{
      role: "assistant",
      turn_id: `${{turnId}}-assistant`,
      status: data.ok ? "ok" : "failed",
      content: structured.answer_markdown || result.content || data.error || "No structured answer returned.",
      structured_answer: structured,
      thinking: result.thinking || "",
      raw: data,
      ts: new Date().toISOString()
    }});
    renderGuidedConversation();
    setStatus(data.ok ? "compose_done" : "compose_failed");
  }} catch (err) {{
    guidedConversation = guidedConversation.filter(turn => turn.waiting_for !== turnId);
    guidedConversation.push({{
      role: "assistant",
      turn_id: `${{turnId}}-assistant-error`,
      status: "failed",
      content: String(err && err.message ? err.message : err),
      raw: {{error: String(err && err.message ? err.message : err)}},
      ts: new Date().toISOString()
    }});
    renderGuidedConversation();
    setStatus("compose_failed");
  }} finally {{
    guidedComposeInFlight = false;
  }}
}}
function renderGuidedConversation() {{
  const target = document.getElementById("guided-conversation");
  if (!target) return;
  const prompt = document.getElementById("guided-operator-prompt");
  if (prompt) prompt.value = guidedDraftText;
  if (!guidedConversation.length) {{
    target.innerHTML = "<p class='muted'>No guided turns yet. Ask a follow-up prompt to test what the payload can support.</p>";
    return;
  }}
  target.innerHTML = `<div class="chat-grid">${{
    guidedConversation.map((turn, index) => renderGuidedTurn(turn, index + 1)).join("")
  }}</div>`;
}}
function renderGuidedTurn(turn, index) {{
  const isOperator = turn.role === "operator";
  const css = isOperator ? "user" : (turn.status === "failed" ? "warn" : "assistant");
  const title = isOperator ? `Operator prompt #${{index}}` : `Payload assistant #${{index}}`;
  const structured = turn.structured_answer || {{}};
  const details = isOperator ? "" : `
    <details ${{turn.status === "waiting" ? "open" : ""}}><summary>answer_markdown</summary><pre>${{htmlEscape(turn.content || "")}}</pre></details>
    <details><summary>payload assessment</summary><pre>${{htmlEscape(pretty(structured.payload_assessment || {{}}))}}</pre></details>
    <details><summary>missing payload</summary><pre>${{htmlEscape(pretty(structured.missing_payload || []))}}</pre></details>
    <details><summary>code products / apply readiness</summary><pre>${{htmlEscape(pretty({{code_products: structured.code_products || [], apply_readiness: structured.apply_readiness || {{}}}}))}}</pre></details>
    <details><summary>thinking trace / raw result</summary><pre>${{htmlEscape(pretty({{thinking: turn.thinking || "", raw: turn.raw || {{}}}}))}}</pre></details>
  `;
  return `<div class="bubble ${{css}}">
    <b>${{htmlEscape(title)}}</b> <span class="muted">${{htmlEscape(turn.status || "")}} ${{htmlEscape(turn.ts || "")}}</span>
    ${{isOperator ? `<pre>${{htmlEscape(turn.content || "")}}</pre>` : details}}
  </div>`;
}}
function renderLab(data) {{
  const readiness = data.payload_readiness || {{}};
  const statusClass = data.ok && readiness.tool_context_parse_ok ? "ok" : "bad";
  const jobInfo = data.job || {{}};
  const loadedJobId = jobInfo.job_id || currentJobId || "";
  if (loadedJobId) {{
    currentJobId = loadedJobId;
    const input = document.getElementById("job-id");
    if (input) input.value = loadedJobId;
    updateActiveJob(loadedJobId, jobInfo.status || "loaded");
  }}
  document.getElementById("lab-output").innerHTML = `
    ${{renderChatTurn(data)}}
    ${{renderTopLevelSurface(data)}}
    ${{renderPublicToolResponse(data)}}
    <div class="card ${{statusClass}}">
      <h2>Payload readiness</h2>
      ${{renderMetrics(readiness)}}
      <pre>${{htmlEscape((readiness.warnings || []).join("\\n"))}}</pre>
    </div>
    <div class="card"><h2>Thinking step summary</h2>${{renderSteps(data.thinking_step_summary || data.step_summaries || [])}}</div>
    <div class="card"><h2>Code products from payload</h2>${{renderCodeProducts(data.code_products || [])}}</div>
    <div class="card">
      <h2>Guided payload conversation</h2>
      <p class="muted">Wait-mode operator chat over the current terminal 30B payload. It uses internal Ollama /api/chat with JSON schema and optional thinking, does not call tools, and keeps each follow-up bounded.</p>
      <textarea id="guided-operator-prompt" oninput="captureGuidedDraft()" placeholder="Chiedi un follow-up sul payload: descrivi dettagliatamente, verifica cosa manca, prepara una risposta diff, o controlla se una patch e applicabile..."></textarea>
      <label><input id="compose-think" type="checkbox" /> request Ollama thinking trace</label>
      <label>max_payload_chars</label>
      <input id="compose-payload-chars" type="number" min="5000" max="80000" value="30000" />
      <label>timeout_seconds</label>
      <input id="compose-timeout" type="number" min="15" max="180" value="60" />
      <button onclick="composeFromPayload()">Ask payload composer (wait)</button>
      <button class="secondary" onclick="guidedConversation = []; guidedDraftText = ''; renderGuidedConversation(); setStatus('guided_chat_cleared')">Clear guided chat</button>
    </div>
    <div id="guided-conversation"></div>
    <div class="card"><h2>Payload index</h2><pre>${{htmlEscape(pretty(data.payload_index_for_30b || {{}}))}}</pre></div>
    <div class="card"><h2>Priority evidence</h2><pre>${{htmlEscape(pretty(data.priority_evidence_for_30b || {{}}))}}</pre></div>
  `;
  renderGuidedConversation();
  setStatus(`loaded ${{currentJobId || ""}}`);
}}
if (initialJobId) {{
  document.getElementById("job-id").value = initialJobId;
  updateActiveJob(initialJobId, "polling");
  startPolling();
}} else {{
  updateActiveJob("", "");
}}
</script>
</body>
</html>"""


def planner_lab_index_html(*, limit: int = 20) -> str:
    recent_cards = []
    for job in list_agent_jobs(limit=max(1, min(int(limit or 20), 100))):
        job_id_raw = str(job.get("job_id") or "")
        job_id = html.escape(job_id_raw)
        job_js = html.escape(json.dumps(job_id_raw), quote=True)
        status = html.escape(str(job.get("status") or ""))
        goal = html.escape(str(job.get("goal") or ""))
        recent_cards.append(
            "<article class=\"recent-job\">"
            "<div class=\"recent-job-head\">"
            f"<a class=\"recent-job-id\" href=\"/jobs/{job_id}/planner-lab\">{job_id}</a>"
            f"<span class=\"pill\">{status}</span>"
            "</div>"
            f"<div class=\"recent-job-goal\">{goal}</div>"
            "<div class=\"recent-job-actions\">"
            f"<button onclick=\"selectJob({job_js}, true)\">Load</button>"
            f"<a class=\"mini-link\" href=\"/jobs/{job_id}/ia-view\">IA</a>"
            f"<a class=\"mini-link\" href=\"/jobs/{job_id}/events\">events</a>"
            f"<a class=\"mini-link\" href=\"/jobs/{job_id}/planner-stream\">stream</a>"
            "</div>"
            "</article>"
        )
    body = f"""
<div class="card">
  <div class="shell-header">
    <div>
      <h1 class="shell-title">Internal Loop Lab</h1>
      <p class="muted">Operator-only 3572 console: start an internal planner loop, follow its terminal 30B payload, and continue with a bounded diagnostic chat inside the loop.</p>
    </div>
    <div class="toolbar">
      <a class="mini-link" href="/jobs">jobs</a>
      <a class="mini-link" href="/jobs.json">jobs json</a>
    </div>
  </div>
</div>
<div class="grid">
  <div>
    <div class="card">
      <h2>Launch internal loop</h2>
      <textarea id="planner-request" placeholder="analizza la repo e proponi diff concreti..."></textarea>
      <label>wait_seconds for Start + wait</label>
      <input id="wait-seconds" type="number" min="1" max="30" value="30" />
      <div class="toolbar">
        <button data-launch-button="1" onclick="startPlannerJob('background')">Start loop</button>
        <button data-launch-button="1" class="secondary" onclick="startPlannerJob('wait')">Start + wait</button>
      </div>
      <div class="muted">Status: <span id="lab-status">idle</span></div>
      <pre id="start-result"></pre>
    </div>
    <div id="active-job-panel"></div>
    <div class="card">
      <h2>Load existing job</h2>
      <input id="job-id" placeholder="job-..." />
      <div class="toolbar">
        <button onclick="selectJob(document.getElementById('job-id').value, false)">Load once</button>
        <button class="secondary" onclick="selectJob(document.getElementById('job-id').value, true)">Poll</button>
        <button class="secondary" onclick="stopPolling()">Stop poll</button>
      </div>
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
      <p class="muted">These values affect only this operator lab view, not planner gates or the public tool schema.</p>
    </div>
    <div class="card">
      <h2>Recent jobs</h2>
      <div class="recent-job-list">{''.join(recent_cards) if recent_cards else '<p class="muted">No recent jobs.</p>'}</div>
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
  <div class="shell-header">
    <div>
      <h1 class="shell-title">Internal Loop Lab - {safe_job}</h1>
      <p class="muted">Chat + thinking-step-summary view for the terminal 30B payload. Use it to verify whether a detailed repo answer or diff request contains enough inline evidence before a 30B answer is composed internally.</p>
    </div>
    <div class="toolbar">
      <a class="mini-link" href="/planner-lab">lab home</a>
      <a class="mini-link" href="/jobs/{safe_job}/ia-view">IA view</a>
      <a class="mini-link" href="/jobs/{safe_job}/events">events</a>
      <a class="mini-link" href="/jobs/{safe_job}/final.json">final json</a>
    </div>
  </div>
</div>
<div class="grid">
  <div>
    <div class="card">
      <h2>Launch internal loop</h2>
      <textarea id="planner-request" placeholder="analizza la repo e proponi diff concreti..."></textarea>
      <label>wait_seconds for Start + wait</label>
      <input id="wait-seconds" type="number" min="1" max="30" value="30" />
      <div class="toolbar">
        <button data-launch-button="1" onclick="startPlannerJob('background')">Start loop</button>
        <button data-launch-button="1" class="secondary" onclick="startPlannerJob('wait')">Start + wait</button>
      </div>
      <p class="muted">Starts a new normal 3572 planner job and then renders the terminal 30B payload in this internal lab.</p>
      <pre id="start-result"></pre>
    </div>
    <div id="active-job-panel"></div>
    <div class="card">
      <h2>Job</h2>
      <input id="job-id" value="{safe_job}" />
      <div class="toolbar">
        <button onclick="selectJob(document.getElementById('job-id').value, false)">Load once</button>
        <button class="secondary" onclick="selectJob(document.getElementById('job-id').value, true)">Poll</button>
        <button class="secondary" onclick="stopPolling()">Stop poll</button>
      </div>
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
      <p class="muted">These values affect only this operator lab view, not planner gates or the public tool schema.</p>
    </div>
  </div>
  <div id="lab-output"><div class="card"><p class="muted">Loading...</p></div></div>
</div>
"""
    return _html_page(f"Planner Payload Lab {job_id}", body, initial_job_id=job_id)
