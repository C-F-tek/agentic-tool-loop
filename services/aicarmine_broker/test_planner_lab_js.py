"""Test PLANNER_LAB_JS per verificare P0/P1."""
import re

with open('job_html_assets.py', 'r') as f:
    content = f.read()

match = re.search(r'PLANNER_LAB_JS = r"""(.*?)"""', content, re.DOTALL)
js_code = match.group(1) if match else ''

print('P0.1 initialJobId count:', js_code.count('const initialJobId'))
print('P0.2 cleanJob:', 'const cleanJob = String(jobId || "").trim()' in js_code)
print('P0.3 selectJob(jobId, true):', 'selectJob(jobId, true)' in js_code)
print('P0 setTimeout:', 'setTimeout(r, waitSeconds * 1000)' in js_code)
print('P1 loadJob(force):', 'async function loadJob(force = false)' in js_code)
print('P1 params.toString():', 'params.toString()' in js_code)
print('P0 guided-operator-prompt:', 'id="guided-operator-prompt"' in js_code)
print('P1 renderLab(data):', 'function renderLab(data)' in js_code)
print('P1 priority_evidence_for_30b.items:', 'priorityEvidence.items' in js_code)
print('P1 step_summaries:', 'step_summaries' in js_code)
print('P1 code_products:', 'code_products' in js_code)
print('P1 payload_readiness:', 'payload_readiness' in js_code)
print('P1 owner_payload_focus:', 'owner_payload_focus' in js_code)
print('P1 public_tool_response_view:', 'public_tool_response_view' in js_code)
print('P1 htmlEscape:', 'htmlEscape(' in js_code)