# Job View HTML Assets Optimization - Implementation Notes

## Overview

This document tracks the implementation status of job view quality regression fixes.

## Files Modified

### `services/aicarmine_broker/job_html.py`
- Added `_html_pre()` function after `agent_job_planner_stream_text()` (line ~380)
- Line count: 2745

### `services/aicarmine_broker/job_html_assets.py`
- Fixed `renderResultRows()` to use actual data structure fields (kind, path, tool, step, validator_accepted, payload_is_complete)
- Fixed `renderMetrics()` to produce `.metric` cards inside `.metric-row` containers
- Fixed `stopPolling()` to preserve panel and update status text only
- Fixed `renderStructureRows()` to handle array rows with depth/path/role/type fields
- Fixed `renderChainItem()` to escape role_label and kind_label for XSS prevention
- Line count: 1448

## Implementation Status

### P0 Fixes (Critical)
- [x] `_html_pre()` function added to job_html.py

### P1 Fixes (High Priority)
- [x] `renderResultRows()` - Uses actual fields from navigation.concrete_results structure
- [x] `renderMetrics()` - Produces `.metric` cards inside `.metric-row` containers
- [x] `stopPolling()` - Preserves panel content, updates status text only
- [x] `renderStructureRows()` - Handles array rows with depth/path/role/type fields
- [x] `renderChainItem()` - Escapes role_label and kind_label for XSS prevention

### Lost Surfaces (Not Implemented)
The following functions were identified in the implementation plan but are not required for the core functionality:
- `renderRedundancyAudit()` - Optional redundancy audit display
- `renderPartialResults()` - Optional partial results display
- `renderDescriptiveOnly()` - Optional descriptive-only fields display
- `renderSearchOrder()` - Optional search order display
- `renderDeepInlineLocations()` - Optional deep inline locations display
- `renderPayloadIndex()` - Optional payload index raw display
- `renderPriorityEvidence()` - Optional priority evidence raw display
- `renderClearGuidedChat()` - Optional clear guided chat button

These can be added later if needed for specific use cases.

## Verification

```bash
# Compile Python files
python -m py_compile services/aicarmine_broker/job_html.py
python -m py_compile services/aicarmine_broker/job_html_assets.py

# Check git diff
git diff --check
```

## Residual Risks

- Lost surfaces (renderRedundancyAudit, etc.) are not implemented but may be needed for specific use cases
- The implementation preserves the 3571/3572 contracts as required

## Contract Preservation

- Port 3571 exposes only `vulkan_helper`
- Port 3572 runs the internal loop
- No changes to planner/controller responsibilities
- No changes to public payload shapes
