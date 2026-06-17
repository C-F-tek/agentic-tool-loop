# Implementation Plan

## Overview

Fix quality regressions introduced in job view optimization by correcting renderMetrics(), renderResultRows(), renderStructureRows(), restoring lost operator surfaces, fixing escaping issues, and updating documentation. This implementation addresses P1 (high priority) issues while preserving the 3571/3572 contracts.

## Types

### renderMetrics() Function (P1)
```javascript
function renderMetrics(metrics) {
  if (!metrics || typeof metrics !== "object") {
    return "";
  }

  const rows = Object.entries(metrics).filter(
    ([key]) => key !== "warnings"
  );

  if (!rows.length) {
    return "<p class='muted'>No readiness metrics.</p>";
  }

  return `
    <div class="metric-row">
      ${rows.map(([key, value]) => `
        <div class="metric">
          <span>${htmlEscape(key)}</span>
          <b>${htmlEscape(
            typeof value === "object" ? pretty(value) : String(value)
          )}</b>
        </div>
      `).join("")}
    </div>
  `;
}
```

### renderResultRows() Function (P1)
```javascript
function renderResultRows(rows) {
  if (!Array.isArray(rows) || !rows.length) {
    return "<p class='muted'>No concrete results.</p>";
  }

  return rows.map(row => {
    const accepted =
      row.ok !== false &&
      row.validator_accepted !== false &&
      row.payload_is_complete !== false;

    const kind =
      row.kind ||
      row.payload_type ||
      row.tool ||
      "result";

    const path =
      row.path ||
      row.target_file ||
      row.repo_path ||
      "";

    const locationValue =
      row.primary_location ??
      row.full_context_location ??
      row.metadata_location ??
      "";

    const location =
      typeof locationValue === "object"
        ? pretty(locationValue)
        : String(locationValue);

    return `
      <div class="step-card ${accepted ? "ok" : "warn"}">
        <b>${htmlEscape(kind)}</b>

        <div class="muted">
          tool=${htmlEscape(row.tool || "")}
          step=${htmlEscape(row.step ?? "")}
          complete=${htmlEscape(row.payload_is_complete)}
          validator=${htmlEscape(row.validator_accepted)}
        </div>

        ${
          path
            ? `<div><code>${htmlEscape(path)}</code></div>`
            : ""
        }

        ${
          location
            ? `<details>
                 <summary>Payload location</summary>
                 <pre>${htmlEscape(location)}</pre>
               </details>`
            : ""
        }
      </div>
    `;
  }).join("");
}
```

### renderStructureRows() Function (P1)
```javascript
function renderStructureRows(value) {
  const rows = Array.isArray(value)
    ? value
    : Array.isArray(value?.rows)
      ? value.rows
      : [];

  if (!rows.length) {
    return "<p class='muted'>No structure map.</p>";
  }

  const visible = rows.slice(0, 260);

  return `
    <table>
      <thead>
        <tr>
          <th>Depth</th>
          <th>Path</th>
          <th>Role</th>
          <th>Type / size</th>
          <th>Inline</th>
        </tr>
      </thead>
      <tbody>
        ${visible.map(row => {
          const size =
            row.chars ??
            row.items ??
            row.keys ??
            row.size ??
            "";

          return `
            <tr>
              <td>${htmlEscape(row.depth ?? "")}</td>
              <td>${htmlEscape(row.path || "")}</td>
              <td>${htmlEscape(row.role || "")}</td>
              <td>${htmlEscape(
                `${row.type || ""}${size !== "" ? ` ${size}` : ""}`
              )}</td>
              <td>${htmlEscape(row.inline_payload_candidate)}</td>
            </tr>
          `;
        }).join("")}
      </tbody>
    </table>
  `;
}
```

### renderChainItem() Function (P2 - Escaping Fix)
```javascript
function renderChainItem(stepIndex, role, kind, text) {
  const roleLabel = role === "user" ? "Operator" : role === "assistant" ? "Assistant" : role;
  const kindLabel = kind === "followup" ? "Follow-up" : kind === "compose" ? "Compose Answer" : kind;
  return `<div class="planner-lab-chain-item">
    <div class="planner-lab-chain-label">${stepIndex}. ${htmlEscape(roleLabel)}: ${htmlEscape(kindLabel)}</div>
    <div class="planner-lab-chain-text">${htmlEscape(text)}</div>
  </div>`;
}
```

### renderPreBlock() Function (P2 - Escaping Fix)
```python
def render_pre_block(value: Any, language: str = "json") -> str:
    """Render a pre-formatted code block with HTML escaping."""
    text = _json_pretty(value) if isinstance(value, (dict, list)) else str(value)
    return f'<pre class="{html.escape(language)}">{html.escape(text)}</pre>'
```

### renderJsonPage() Function (P2 - Escaping Fix)
```python
def render_json_page(title: str, payload: Any, *, section_url: str = "", max_chars: int = 300_000) -> str:
    """Render a JSON diagnostic page with title and pretty JSON."""
    json_text = _json_pretty(payload, max_chars=max_chars)
    body = f"""
<div class="card">
  <h2>{html.escape(title)}</h2>
  <pre>{html.escape(json_text)}</pre>
</div>
"""
    if section_url:
        body += f'<a href="{html.escape(section_url)}">← Back</a>'
    return render_page_shell(title, body)
```

### renderJsonSection() Function (P2 - Escaping Fix)
```python
def render_json_section(title: str, payload: Any, *, parent_url: str = "", max_chars: int = 300_000) -> str:
    """Render a JSON section (child of a parent page)."""
    json_text = _json_pretty(payload, max_chars=max_chars)
    body = f"""
<h3>{html.escape(title)}</h3>
<pre>{html.escape(json_text)}</pre>
"""
    if parent_url:
        body += f'<a href="{html.escape(parent_url)}">↑ Parent</a>'
    return body
```

### renderTopLevelSurface() Function (P1 - Lost Surface)
```javascript
function renderTopLevelSurface(payload) {
  const div = document.createElement("div");
  div.className = "planner-lab-content";
  div.innerHTML = `
    <h3>Job Overview</h3>
    <pre>${htmlEscape(pretty(payload))}</pre>
  `;
  return div.outerHTML;
}
```

### renderRedundancyAudit() Function (P1 - Lost Surface)
```javascript
function renderRedundancyAudit(payload) {
  const items = [];
  for (const [key, value] of Object.entries(payload)) {
    if (key === "redundancy_audit") {
      items.push(`<div class="pill">${htmlEscape(key)}: ${htmlEscape(value)}</div>`);
    }
  }
  return items.join("");
}
```

### renderPartialResults() Function (P1 - Lost Surface)
```javascript
function renderPartialResults(payload) {
  const partial = payload.partial_results || [];
  if (!partial.length) return "";
  
  return `<details>
    <summary>Partial results</summary>
    <pre>${htmlEscape(pretty(partial))}</pre>
  </details>`;
}
```

### renderDescriptiveOnly() Function (P1 - Lost Surface)
```javascript
function renderDescriptiveOnly(payload) {
  const desc = payload.descriptive_only || [];
  if (!desc.length) return "";
  
  return `<details>
    <summary>Descriptive only fields</summary>
    <pre>${htmlEscape(pretty(desc))}</pre>
  </details>`;
}
```

### renderSearchOrder() Function (P1 - Lost Surface)
```javascript
function renderSearchOrder(payload) {
  const order = payload.search_order || [];
  if (!order.length) return "";
  
  return `<details>
    <summary>Search order</summary>
    <pre>${htmlEscape(pretty(order))}</pre>
  </details>`;
}
```

### renderDeepInlineLocations() Function (P1 - Lost Surface)
```javascript
function renderDeepInlineLocations(payload) {
  const locations = payload.deep_inline_locations || [];
  if (!locations.length) return "";
  
  return `<details>
    <summary>Deep inline locations</summary>
    <pre>${htmlEscape(pretty(locations))}</pre>
  </details>`;
}
```

### renderPayloadIndex() Function (P1 - Lost Surface)
```javascript
function renderPayloadIndex(payload) {
  const index = payload.payload_index || {};
  if (!index || Object.keys(index).length === 0) return "";
  
  return `<details>
    <summary>Payload index raw</summary>
    <pre>${htmlEscape(pretty(index))}</pre>
  </details>`;
}
```

### renderPriorityEvidence() Function (P1 - Lost Surface)
```javascript
function renderPriorityEvidence(payload) {
  const evidence = payload.priority_evidence || [];
  if (!evidence.length) return "";
  
  return `<details>
    <summary>Priority evidence raw</summary>
    <pre>${htmlEscape(pretty(evidence))}</pre>
  </details>`;
}
```

### renderClearGuidedChat() Function (P1 - Lost Surface)
```javascript
function renderClearGuidedChat() {
  return `<button onclick="guidedConversation = []; guidedDraftText = ''; renderGuidedConversation()">Clear guided chat</button>`;
}
```

## Files

### New Files
- None (all fixes are in-place modifications)

### Modified Files
1. **services/aicarmine_broker/job_html_assets.py**
   - Fix `renderMetrics()` to produce `.metric` cards inside `.metric-row` containers and filter out warnings
   - Fix `renderResultRows()` to use actual fields: kind, payload_type, path, tool, step, validator_accepted, payload_is_complete
   - Fix `renderStructureRows()` to handle array rows correctly and render as table
   - Add lost surfaces: `renderTopLevelSurface()`, `renderRedundancyAudit()`, `renderPartialResults()`, `renderDescriptiveOnly()`, `renderSearchOrder()`, `renderDeepInlineLocations()`, `renderPayloadIndex()`, `renderPriorityEvidence()`, `renderClearGuidedChat()`
   - Fix escaping in `renderChainItem()` for `role_label` and `kind_label`
   - Line count change: ~+200 lines (adding lost functions)

2. **services/aicarmine_broker/job_html.py**
   - No changes needed (P0 `_html_pre()` already exists)
   - Remove unused first `_html_page()` definition if present (shadowed by second one)

3. **services/aicarmine_broker/job_html_assets.py** (Python helpers)
   - Fix `render_pre_block()` to escape content
   - Fix `render_json_page()` to escape JSON text
   - Fix `render_json_section()` to escape JSON text
   - Line count change: +0 (just escaping fixes)

### Configuration Files
- **services/aicarmine_broker/JOB_VIEW_OPTIMIZATION_NOTES.md**
   - Update to reflect actual implementation state
   - Mark P1 items as still open until runtime verification
   - Document lost surfaces as operator-relevant (not optional)
   - Update asset size references

## Functions

### New Functions
| Name | File | Purpose |
|------|------|---------|
| `renderTopLevelSurface()` | job_html_assets.py | Restore lost job overview surface |
| `renderRedundancyAudit()` | job_html_assets.py | Restore redundancy audit display |
| `renderPartialResults()` | job_html_assets.py | Restore partial results display |
| `renderDescriptiveOnly()` | job_html_assets.py | Restore descriptive-only fields display |
| `renderSearchOrder()` | job_html_assets.py | Restore search order display |
| `renderDeepInlineLocations()` | job_html_assets.py | Restore deep inline locations display |
| `renderPayloadIndex()` | job_html_assets.py | Restore payload index raw display |
| `renderPriorityEvidence()` | job_html_assets.py | Restore priority evidence raw display |
| `renderClearGuidedChat()` | job_html_assets.py | Restore clear guided chat button |

### Modified Functions
| Name | File | Changes |
|------|------|---------|
| `renderMetrics()` | job_html_assets.py | Produce `.metric` cards inside `.metric-row` containers; filter out warnings |
| `renderResultRows()` | job_html_assets.py | Use actual fields: kind, payload_type, path, tool, step, validator_accepted, payload_is_complete |
| `renderStructureRows()` | job_html_assets.py | Handle array rows with depth/path/role/type fields; render as table |
| `renderChainItem()` | job_html_assets.py | Escape `role_label` and `kind_label` |
| `render_pre_block()` | job_html_assets.py | Escape content before inserting into `<pre>` |
| `render_json_page()` | job_html_assets.py | Escape JSON text before inserting into `<pre>` |
| `render_json_section()` | job_html_assets.py | Escape JSON text before inserting into `<pre>` |

### Removed Functions
- None (no functions removed, only fixes)

## Classes
- No classes modified

## Dependencies
- No new dependencies
- No version changes
- All fixes use existing Python standard library and JavaScript

## Testing
- Manual verification: Render each view type (dashboard, status_json, final_json, events, planner_stream, ia_view, planner_lab)
- Check HTML structure for proper escaping
- Verify metrics display correctly with `.metric` cards
- Confirm stopPolling preserves panel content
- Test renderResultRows with actual navigation.concrete_results data
- Run `python -m py_compile` on modified files
- Check `git diff --check` for syntax errors

## Implementation Order

1. **Patch A — P0 Immediate Fix**
   - Verify `_html_pre()` exists in correct location in job_html.py
   - No action needed if function is present (it is)

2. **Patch B — Planner-Lab Equivalence (P1 Fixes)**
   - Fix `renderResultRows()` to use actual data structure fields (kind, payload_type, path, tool, step, validator_accepted, payload_is_complete)
   - Fix `renderMetrics()` to produce proper `.metric` cards and filter out warnings
   - Fix `stopPolling()` to preserve panel and update status only
   - Fix `renderStructureRows()` to handle array rows correctly and render as table
   - Add lost surfaces: `renderTopLevelSurface()`, `renderRedundancyAudit()`, `renderPartialResults()`, `renderDescriptiveOnly()`, `renderSearchOrder()`, `renderDeepInlineLocations()`, `renderPayloadIndex()`, `renderPriorityEvidence()`, `renderClearGuidedChat()`
   - Fix escaping in `renderChainItem()` for `role_label` and `kind_label`
   - Fix escaping in Python helpers: `render_pre_block()`, `render_json_page()`, `render_json_section()`

3. **Patch C — Documentation Update**
   - Update `JOB_VIEW_OPTIMIZATION_NOTES.md` to reflect actual state
   - Mark P1 items as still open until runtime verification
   - Document lost surfaces as operator-relevant (not optional)
   - Update asset size references

4. **Verification**
   - Render all view types: job_dashboard, status_json, final_json, final_markdown, events, planner_stream, ia_view, planner_lab
   - Verify HTML structure and escaping
   - Confirm metrics display correctly with `.metric` cards
   - Check that stopPolling preserves panel content
   - Run `python -m py_compile` on modified files
   - Check `git diff --check` for syntax errors