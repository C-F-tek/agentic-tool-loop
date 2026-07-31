# Implementation Plan

## Overview

Reduce cyclomatic complexity (CC) in the three critical hotspots identified by the wily report: `services/aicarmine_broker/planner.py` (CC=1154), `services/vulkan_bridge/app_refactored.py` (CC=1064), and `services/aicarmine_broker/application/evidence/builder.py` (CC=619, with a single function at CC=566). The plan focuses on extracting nested control flow, decomposing monolithic functions, and introducing intermediate abstractions that preserve the existing contract while lowering per-file and per-function complexity.

## Types

- `ComplexityBudget` — dataclass holding per-file and per-function CC targets (e.g., max 200 per file, max 50 per function).
- `ExtractionPoint` — named tuple describing a function to extract, its target module, and the replacement stub.
- `DecompositionPlan` — immutable record linking a complex function to its extracted sub-functions.

## Files

### New files to be created:

1. `services/aicarmine_broker/application/evidence/builder_extracted.py` — extracted sub-functions from `builder.py` (lines 1-620, 620-1420, 1420-2053).
2. `services/aicarmine_broker/application/evidence/builder_stubs.py` — stub functions that replace the inline complexity in `build()` method.
3. `services/aicarmine_broker/planner/decision_simplifier.py` — extracted decision logic from `planner.py`.
4. `services/vulkan_bridge/bridge_config_simplifier.py` — extracted configuration logic from `app_refactored.py`.

### Existing files to be modified:

1. `services/aicarmine_broker/application/evidence/builder.py` — replace monolithic `build()` method with calls to extracted functions.
2. `services/aicarmine_broker/planner.py` — extract nested decision logic into `decision_simplifier.py`.
3. `services/vulkan_bridge/app_refactored.py` — extract bridge configuration into `bridge_config_simplifier.py`.

## Functions

### New functions:

- `services/aicarmine_broker/application/evidence/builder_extracted.py:compute_coverage_gates()` — extract coverage gate logic (lines 882-974).
- `services/aicarmine_broker/application/evidence/builder_extracted.py:compute_final_allowed_reason()` — extract final_allowed computation (lines 361-443).
- `services/aicarmine_broker/application/evidence/builder_extracted.py:compute_code_product_contract()` — extract code product contract logic (lines 742-862).
- `services/aicarmine_broker/application/evidence/builder_extracted.py:compute_validation_rejections()` — extract validation rejection processing (lines 1018-1143).
- `services/aicarmine_broker/application/evidence/builder_extracted.py:compute_required_next_progress()` — extract required_next_progress computation (lines 1795-1817).

### Modified functions:

- `services/aicarmine_broker/application/evidence/builder.py:build()` — replace inline complexity with calls to extracted functions.
- `services/aicarmine_broker/planner.py:run_agentic_planner_job()` — extract nested decision logic.
- `services/vulkan_bridge/app_refactored.py:main()` — extract bridge configuration logic.

## Classes

### New classes:

- `EvidenceBuilderExtracted` — holds extracted sub-functions for evidence building.
- `DecisionSimplifier` — holds extracted decision logic for planner.
- `BridgeConfigSimplifier` — holds extracted bridge configuration logic.

### Modified classes:

- `EvidenceBuilder` — replace monolithic `build()` method with calls to `EvidenceBuilderExtracted`.
- `PlannerFacade` — extract nested decision logic into `DecisionSimplifier`.
- `VulkanBridgeApp` — extract bridge configuration into `BridgeConfigSimplifier`.

## Dependencies

No new external dependencies required. All extractions use existing Python standard library modules.

## Testing

- Run existing test suite to verify no behavioral changes.
- Verify wily complexity report shows reduced CC for modified files.
- Verify that extracted functions maintain the same input/output contracts.

## Implementation Order

1. Extract `compute_coverage_gates()` from `builder.py` into `builder_extracted.py`.
2. Extract `compute_final_allowed_reason()` from `builder.py` into `builder_extracted.py`.
3. Extract `compute_code_product_contract()` from `builder.py` into `builder_extracted.py`.
4. Extract `compute_validation_rejections()` from `builder.py` into `builder_extracted.py`.
5. Extract `compute_required_next_progress()` from `builder.py` into `builder_extracted.py`.
6. Replace monolithic `build()` method with calls to extracted functions.
7. Extract decision logic from `planner.py` into `decision_simplifier.py`.
8. Extract bridge configuration from `app_refactored.py` into `bridge_config_simplifier.py`.
9. Run wily complexity report to verify reductions.
10. Run existing test suite to verify no behavioral changes.