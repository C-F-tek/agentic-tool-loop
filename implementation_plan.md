# Implementation Plan

## Overview

Fix JavaScript runtime issues in `services/aicarmine_broker/job_html_assets.py` by updating the planner-lab UI to correctly handle code product candidates and their associated fields.

## Types

No type system changes required. The fix involves adding a new helper function `findCodeProduct(candidateId)` and updating four JavaScript functions (`copyCandidate`, `copyApplyToolCall`, `applyCandidate`, `renderPriorityRows`, `renderArtifactRows`) to use the correct payload structure from `currentPlannerLabPayload`.

## Files

- **Modified**: `services/aicarmine_broker/job_html_assets.py` (1432 lines)
  - Add `findCodeProduct(candidateId)` helper function before `renderLab()`
  - Update `copyCandidate()`, `copyApplyToolCall()`, `applyCandidate()` to use `findCodeProduct()`
  - Update `renderPriorityRows()` to use correct fields (`tool`, `kind`, `ok`, `payload_is_complete`, `validator_accepted`)
  - Update `renderArtifactRows()` to use correct fields (`tool`, `kind`, `ok`, `payload_is_complete`, `artifact_keys`)

## Functions

### New Functions

| Name | Signature | File Path | Purpose |
|------|-----------|-----------|---------|
| `findCodeProduct` | `function findCodeProduct(candidateId)` | `services/aicarmine_broker/job_html_assets.py` | Find a code product by candidate_id from `currentPlannerLabPayload.code_products` |

### Modified Functions

| Name | Current File Path | Required Changes |
|------|-------------------|------------------|
| `copyCandidate` | `services/aicarmine_broker/job_html_assets.py:773` | Accept `candidateId` string, use `findCodeProduct()` to lookup, handle missing candidate gracefully |
| `copyApplyToolCall` | `services/aicarmine_broker/job_html_assets.py:788` | Accept `candidateId` string, use `findCodeProduct()` to lookup, extract `apply_tool_call`, handle missing tool call |
| `applyCandidate` | `services/aicarmine_broker/job_html_assets.py:804` | Accept `candidateId` string, use `findCodeProduct()` to lookup, validate `apply_supported`, make POST request with correct payload |
| `renderPriorityRows` | `services/aicarmine_broker/job_html_assets.py:462` | Use `item.tool`, `item.kind`, `item.ok`, `item.payload_is_complete`, `item.validator_accepted`, `item.repo_path`, `item.inline_fields` |
| `renderArtifactRows` | `services/aicarmine_broker/job_html_assets.py:503` | Use `item.tool`, `item.kind`, `item.ok`, `item.payload_is_complete`, `item.repo_path`, `item.inline_fields`, `item.artifact_keys` |

## Classes

No class modifications required.

## Dependencies

No new dependencies. The fix uses existing payload structure from `currentPlannerLabPayload`.

## Testing

Manual verification using the verification commands specified in the task:
1. Run ripgrep to confirm bad patterns are absent from the modified functions
2. Run ripgrep to confirm required patterns are present
3. Run Python syntax validation on the modified file
4. Run Node.js syntax validation on the extracted JavaScript
5. Verify `git diff --check` passes

## Implementation Order

1. Add `findCodeProduct(candidateId)` helper function before `renderLab()` (line ~1084)
2. Update `copyCandidate()` signature and implementation to use `findCodeProduct()`
3. Update `copyApplyToolCall()` signature and implementation to use `findCodeProduct()`
4. Update `applyCandidate()` signature and implementation to use `findCodeProduct()`
5. Update `renderPriorityRows()` to use correct payload fields
6. Update `renderArtifactRows()` to use correct payload fields
7. Verify syntax with Python and Node.js
8. Verify with git diff check

---

## Detailed Implementation Steps

### Step 1: Add findCodeProduct helper function

Insert before `function renderLab(data)` (around line 1084):

```javascript
function findCodeProduct(candidateId) {
  const cleanId = String(candidateId || "").trim();

  const products = Array.isArray(currentPlannerLabPayload?.code_products)
    ? currentPlannerLabPayload.code_products
    : [];

  return products.find(
    item => String(item?.candidate_id || "") === cleanId
  ) || null;
}
```

### Step 2: Update copyCandidate()

Replace current implementation (lines 773-786):

```javascript
async function copyCandidate(candidateId) {
  const candidate = findCodeProduct(candidateId);
  if (!candidate) {
    setStatus("candidate_not_found");
    return;
  }
  try {
    await navigator.clipboard.writeText(pretty(candidate));
    setStatus("candidate_copied");
  } catch (err) {
    setStatus("candidate_copy_failed");
    console.error("Copy candidate failed:", err);
  }
}
```

### Step 3: Update copyApplyToolCall()

Replace current implementation (lines 788-802):

```javascript
async function copyApplyToolCall(candidateId) {
  const candidate = findCodeProduct(candidateId);
  const toolCall = candidate?.apply_tool_call;
  if (!toolCall) {
    setStatus("apply_tool_call_missing");
    return;
  }
  try {
    await navigator.clipboard.writeText(pretty(toolCall));
    setStatus("apply_tool_call_copied");
  } catch (err) {
    setStatus("apply_tool_call_copy_failed");
    console.error("Copy apply call failed:", err);
  }
}
```

### Step 4: Update applyCandidate()

Replace current implementation (lines 804-855):

```javascript
async function applyCandidate(candidateId) {
  const candidate = findCodeProduct(candidateId);
  if (!candidate) {
    setStatus("candidate_not_found");
    return {ok: false, error: "candidate_not_found"};
  }
  if (!candidate.apply_supported) {
    setStatus("candidate_apply_unsupported");
    return {
      ok: false,
      error: candidate.apply_block_reason || "apply_unsupported",
    };
  }
  if (!window.confirm(
    "Confermi apply interno repo_apply_patch per il candidato selezionato?"
  )) {
    setStatus("apply_cancelled");
    return {ok: false, error: "apply_cancelled"};
  }
  try {
    const response = await fetch(
      `/jobs/${encodeURIComponent(currentJobId)}/planner-lab/apply`,
      {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          candidate_id: String(candidate.candidate_id),
          confirm_apply: true,
          user_consent:
            "confirm planner-lab exact old_text/new_text patch",
        }),
      }
    );
    const data = await response.json();
    const output = document.getElementById("apply-result");
    if (output) output.textContent = pretty(data);
    setStatus(data.ok ? "apply_done" : "apply_blocked");
    if (data.ok) {
      await loadJob(true);
    }
    return data;
  } catch (err) {
    const data = {
      ok: false,
      error: String(err?.message || err),
    };
    const output = document.getElementById("apply-result");
    if (output) output.textContent = pretty(data);
    setStatus("apply_failed");
    return data;
  }
}
```

### Step 5: Update renderPriorityRows()

Replace current implementation (lines 462-501):

```javascript
function renderPriorityRows(items) {
  if (!items || !items.length) {
    return "<p class='muted'>No priority evidence.</p>";
  }

  return items.map(item => {
    const accepted =
      item.ok !== false &&
      item.validator_accepted !== false;

    const inlineFields = Array.isArray(item.inline_fields)
      ? item.inline_fields
      : [];

    return `
      <div class="step-card ${accepted ? "ok" : "warn"}">
        <b>
          ${htmlEscape(
            item.tool ||
            item.kind ||
            "evidence"
          )}
        </b>

        <div class="muted">
          kind=${htmlEscape(item.kind || "")}
          ok=${htmlEscape(item.ok)}
          complete=${htmlEscape(item.payload_is_complete)}
          validator=${htmlEscape(item.validator_accepted)}
        </div>

        <div>
          ${htmlEscape(item.repo_path || item.path || "")}
        </div>

        ${
          inlineFields.length
            ? `<details>
                 <summary>Inline fields</summary>
                 <pre>${htmlEscape(pretty(inlineFields))}</pre>
               </details>`
            : ""
        }
      </div>
    `;
  }).join("");
}
```

### Step 6: Update renderArtifactRows()

Replace current implementation (lines 503-545):

```javascript
function renderArtifactRows(artifacts) {
  if (!artifacts || !artifacts.length) {
    return "<p class='muted'>No tool-context artifacts.</p>";
  }

  return artifacts.map(item => {
    const inlineFields = Array.isArray(item.inline_fields)
      ? item.inline_fields
      : [];

    const artifactKeys = Array.isArray(item.artifact_keys)
      ? item.artifact_keys
      : [];

    return `
      <div class="step-card ${item.ok === false ? "warn" : "ok"}">
        <b>
          ${htmlEscape(
            item.tool ||
            item.kind ||
            "artifact"
          )}
        </b>

        <div class="muted">
          kind=${htmlEscape(item.kind || "")}
          ok=${htmlEscape(item.ok)}
          complete=${htmlEscape(item.payload_is_complete)}
        </div>

        <div>
          ${htmlEscape(item.repo_path || item.path || "")}
        </div>

        ${
          inlineFields.length
            ? `<details>
                 <summary>Inline fields</summary>
                 <pre>${htmlEscape(pretty(inlineFields))}</pre>
               </details>`
            : ""
        }

        ${
          artifactKeys.length
            ? `<details>
                 <summary>Artifact keys</summary>
                 <pre>${htmlEscape(pretty(artifactKeys))}</pre>
               </details>`
            : ""
        }
      </div>
    `;
  }).join("");
}
```

---

## Verification Commands

After applying the patch, run these verification commands:

### 1. Verify bad patterns are absent from modified functions

```powershell
$Path = "services/aicarmine_broker/job_html_assets.py"
Select-String -Path $Path -Pattern 'copyCandidate\(candidate\)|copyApplyToolCall\(toolCall\)|applyCandidate\(candidate\)|candidate\.candidate_id|item\.priority|size_bytes' -Path "services/aicarmine_broker/job_html_assets.py" | Select-Object -First 5
```

Expected: Only matches in unrelated code (not in the modified functions).

### 2. Verify required patterns are present

```powershell
Select-String -Path $Path -Pattern 'currentPlannerLabPayload|findCodeProduct\(candidateId\)|copyCandidate\(candidateId\)|copyApplyToolCall\(candidateId\)|applyCandidate\(candidateId\)|validator_accepted|artifact_keys|inline_fields'
```

Expected: Multiple matches in the modified file.

### 3. Python syntax check

```powershell
python -m py_compile services/aicarmine_broker/job_html_assets.py
```

### 4. Node.js syntax check

```powershell
$env:PLANNER_JS_OUT = "$env:TEMP\planner_lab_rendered.js"
# Extract JS from HTML and validate
node --check $env:PLANNER_JS_OUT
```

### 5. Git diff check

```powershell
git diff --check
```

Expected: No warnings.

### 6. Line count verification

```powershell
(Get-Content $Path).Count
```

Expected: 1432 lines (unchanged file size).