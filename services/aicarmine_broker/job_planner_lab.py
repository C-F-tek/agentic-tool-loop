"""Operator-only planner payload lab HTML."""

from __future__ import annotations

import html
import json
from typing import Any

from .job_html_assets import BASE_CSS, BASE_JS, PLANNER_LAB_EXTRA_CSS, PLANNER_LAB_JS
from .job_store import list_agent_jobs


def _json_pretty(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def _html_page(title: str, body: str,  initial_job_id: str = "") -> str:
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


def planner_lab_index_html( limit: int = 20) -> str:
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
