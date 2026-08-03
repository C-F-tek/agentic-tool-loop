# Implementation Plan

## Overview

Fix the agentic loop job failure where the controller's preplanner RAG query planner cannot reach Ollama (HTTP 500 Internal Server Error), causing the job to fail immediately after RAG reindex succeeds. The root cause is the controller's `controller_preplanner_rag_query_plan` function failing to reach the Ollama endpoint at `http://127.0.0.1:11434/api/chat` when the planner model is `mio-qwen-code3:latest`.

## Types

- `RAGQueryPlanStatus` — enum-like status values: `unavailable`, `failed`, `ready`, `invalid_semantic_intent`, `skipped`
- `RAGReindexStatus` — enum-like status values: `ready`, `failed`, `skipped`
- `ControllerRAGHTTPError` — typed exception for HTTP errors from the optional controller RAG reranker (status, reason, body_preview)
- `ControllerRagIndexerLoadError` — typed exception for indexer load failures with diagnostics

## Files

### New files to be created:

1. `services/aicarmine_broker/application/controller/rag_query_plan_fix.py` — extracted query plan repair logic with better error handling and fallback strategies.

### Existing files to be modified:

1. `services/aicarmine_broker/application/controller/rag_preseed.py` — improve the `controller_preplanner_rag_query_plan` function to handle HTTP 500 errors better and provide better fallback behavior.
2. `services/codex_bridge/ovms_mcp_server.py` — ensure the OVMS reranker is properly configured and healthy before starting the agentic loop.

## Functions

### New functions:

- `services/aicarmine_broker/application/controller/rag_query_plan_fix.py:build_fallback_query_plan()` — build a deterministic fallback query plan when the planner model is unavailable.
- `services/codex_bridge/ovms_mcp_server.py:ensure_ovms_reranker_ready()` — ensure the OVMS reranker is ready before starting the agentic loop.

### Modified functions:

- `services/aicarmine_broker/application/controller/rag_preseed.py:controller_preplanner_rag_query_plan()` — add better error handling for HTTP 500 errors and provide a deterministic fallback.
- `services/codex_bridge/agentic_loop_client_mcp_server.py:ensure_broker_and_reranker()` — ensure the OVMS reranker is ready before starting the agentic loop.

## Classes

### New classes:

- `RAGQueryPlanRepairService` — handles query plan repair with better error handling and fallback strategies.
- `OVMSRerankerHealthService` — manages OVMS reranker health checks and readiness.

### Modified classes:

- `RAGRouter` — improve error handling and provide better fallback strategies.
- `MCPRAGRouter` — improve error handling and provide better fallback strategies.

## Dependencies

No new external dependencies required. All fixes use existing Python standard library modules.

## Testing

- Verify that the OVMS reranker is healthy before starting the agentic loop.
- Verify that the controller's RAG query planner can reach Ollama successfully.
- Verify that the agentic loop job completes successfully.
- Run existing test suite to verify no behavioral changes.

## Implementation Order

1. Improve error handling in `controller_preplanner_rag_query_plan` to handle HTTP 500 errors better.
2. Add deterministic fallback query plan when the planner model is unavailable.
3. Ensure the OVMS reranker is healthy before starting the agentic loop.
4. Verify that the agentic loop job completes successfully.