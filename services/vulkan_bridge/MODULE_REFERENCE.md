<!-- AICARMINE_NON_NEGOTIABLE_CONTRACT_START -->
Regole operative non negoziabili:
1. Il contratto non va modificato se non richiesto da Carmine esplicitamente.
2. Il prodotto finale puo' essere arricchito come gia' viene fatto; non cambiare logica senza richiesta esplicita.
3. Non devi presupporre nulla: non e' il tuo compito.
<!-- AICARMINE_NON_NEGOTIABLE_CONTRACT_END -->
# vulkan_bridge Module Reference

Updated: 2026-06-15

`vulkan_bridge` is the 3571 OpenWebUI-facing bridge. It must expose a stable
public helper surface and hide internal 3572 implementation details. Its core
job is to forward work to 3572, wait for terminal state when requested and
return model-usable evidence inline.

Read before edits:

- `C:\Users\sanit\agentic-tool-loop\AGENTS.md`
- `C:\Users\sanit\agentic-tool-loop\services\VALIDATOR_ONLY_AGENTIC_LOOP_CONTRACT.md`
- `C:\Users\sanit\agentic-tool-loop\services\END_TO_END_AGENTIC_FLOW.md`
- `C:\Users\sanit\agentic-tool-loop\services\SERVICES_MODULE_TECHNICAL_REFERENCE.md`

## Runtime Contract

- Process owner: 3571 public bridge.
- Uvicorn target: `aicarmine_vulkan_bridge_server:app`.
- Expected Python: `C:\Users\sanit\agentic-tool-loop\venvs\labtools\Scripts\python.exe`.
- Public OpenWebUI tool: `vulkan_helper`.
- Internal backend: 3572 broker/runtime.
- 3571 must not expose 3572 internal routes as public OpenWebUI tools.
- Compatibility alias routes may exist in the FastAPI app, but the generated
  OpenWebUI OpenAPI schema must expose only `/vulkan_helper`.
- When 3572 returns a successful `repo_propose_code_edit`, 3571 must preserve
  the complete code proposal payload in `tool_context_for_30b`; it must not
  substitute an artifact path, preview or summary for the diff/operations.
- `final_path`, `reads/*.json`, `tool-results/*.json`, job workspaces and
  SQLite document ids are internal/operator pointers. 3571 may read them only
  to rehydrate the terminal payload before returning to OpenWebUI. They are
  never model-usable public locations.

## Module Map

| Module | Technical description |
| --- | --- |
| `__init__.py` | Package marker with no expected runtime behavior. |
| `app.py` | Main 3571 FastAPI app. It defines request models, health, compatibility alias POST routes, backend forwarding, wait/result handling, model unload handoff logic and OpenWebUI payload shaping. The app code still has legacy aliases, but the generated OpenAPI schema filters the OpenWebUI-visible public surface to `/vulkan_helper` only. It preserves complete `repo_propose_code_edit` payloads in `tool_context_for_30b`. It is the authority for the public result shape, not for internal planner validation. |
| `agentic_v9.py` | Compatibility facade that re-exports v9 agentic/OpenWebUI shaping helpers from `app.py`. Keep thin unless the v9 code is intentionally extracted. |
| `client.py` | Compatibility facade for HTTP client/helper functions currently implemented in `app.py`. Keep thin so old imports remain valid. |
| `compact.py` | Compatibility facade for compaction helpers currently implemented in `app.py`. Keep thin unless compaction is intentionally split. |

## application Subpackage

| Module | Technical description |
| --- | --- |
| `application/__init__.py` | Package marker for 3571 application helpers extracted from `app.py`. |
| `application/materialization_report.py` | Diagnostic-only fallback builder for top-level `materialization_report` when 3572 did not already provide a valid `owner=3572_broker` report. It certifies the current 3571 public payload without duplicating payload content: `tool_context_for_30b` JSON-object parseability, artifact materialization counts and payload-index resolution status. |
| `application/payload_index_resolver.py` | Pure resolver for public payload-index field paths such as `tool_context_for_30b.artifacts[0].artifact.content` and `tool_context_for_30b.artifacts[0].artifact.unified_diff`. It reports missing and empty targets for linter/report diagnostics. |
| `application/request_payload.py` | Pure request-payload normalization helpers for public agent arguments, model/dict payload conversion and first text/dict extraction. `app.py` keeps compatibility wrappers for existing call sites. |
| `application/response_values.py` | Pure response value helpers for text compaction, JSON size measurement and compact bridge result digests. `app.py` keeps compatibility wrappers for existing call sites. |
| `application/public_payload_linter.py` | Warn-only public payload linter for OpenWebUI responses. It detects local path leaks, artifact/final path keys outside operator diagnostics, non-JSON `tool_context_for_30b` strings, narrative aliases in the tool-context root, concrete payload copies inside `payload_index_for_30b`, dangling/empty index targets and terminal payloads missing `materialization_report`. |

## Public Result Contract

For terminal jobs returned to OpenWebUI:

- primary metadata: `ok`, `service`, `mode`, `required_top_level_keys`.
  Tool identity fields such as `tool_name`, `tool_result_for` and
  `called_by_30b` are internal/routing metadata and must not be promoted as
  primary OpenWebUI top-level result fields.
- `payload_index_for_30b`: first navigation surface for concrete payload fields.
- `priority_evidence_for_30b`: pointer-first high-priority navigation metadata
  and compact analysis evidence. It must not duplicate large concrete payloads
  already present under `tool_context_for_30b.artifacts[*].artifact`.
- `materialization_report`: diagnostic-only report with schema
  `public_evidence_materialization.v1`. It states whether inline JSON evidence
  was materialized, whether `tool_context_for_30b` is JSON-object parseable and
  whether `payload_index_for_30b` resolves to real non-empty public fields. It
  is not a duplicate answer or payload layer.
- `openwebui_usage`: runtime instructions for reading the indexed fields.
  Internal 3572 completion/block status lives under
  `openwebui_usage.internal_job_status`; it is not a primary top-level field.
- `payload_index_for_30b.internal_job_status`: mirrored internal job status for
  navigation and diagnostics.
- `tool_context_for_30b`: a pretty-printed JSON string whose public useful
  payload is `tool_context_for_30b.artifacts[*].artifact`. It is an artifact
  mirror, not a full job dump and not the primary reading surface.
- `result`: carried from the terminal/final payload as the public result source
  after the primary evidence fields. OpenWebUI can stringify tool results, so
  `result` must not appear before `payload_index_for_30b`,
  `priority_evidence_for_30b`, `openwebui_usage` and `tool_context_for_30b`.
  Terminal wrapping uses the compact digest only when the terminal payload has
  no `result`. Raw controller audit `result.history` is normalized to the
  public ledger schema instead of being inlined as raw transport history.
- Public terminal `result.history` is a bounded
  `agentic_terminal_public_history_ledger.v1`, not raw controller audit history.
  Keep complete file/diff payloads canonical in
  `tool_context_for_30b.artifacts[*].artifact`; `priority_evidence_for_30b`
  and `payload_index_for_30b` should point to those fields instead of copying
  them. Do not expose local job paths, SQLite document ids or artifact paths as
  locations OpenWebUI must open.
- `completed`, `max_steps_reached`, `blocked_needs_attention`,
  `blocked_needs_consent`, `failed`, `failed_tool_error`,
  `failed_planner_error` and `cancelled` must use the same top-level public
  shape. Internal status/warning metadata differs inside the payload index and
  usage blocks, not via a top-level `job_ok` field.
- When the internal job did not complete, rejected code-product attempts,
  action plans and repair text may be exposed in `priority_evidence_for_30b`
  and indexed under `payload_index_for_30b.partial_results`.
  These entries are explicitly `validator_accepted=false`; they are transported
  for OpenWebUI visibility, not counted as completed diffs or successful tool
  evidence.
- The JSON string must contain real tool outputs, not local artifact paths.
- If a compact 3572 terminal response references a readable `final_path` or
  final JSON artifact, 3571 may load it internally. The returned public payload
  must still contain inline evidence and must not expose that local path outside
  operator diagnostics.
- Do not include continuation instructions, call protocol, tool examples,
  transport diagnostics, raw events, hashes, failed/rejected/blocked evidence as
  useful evidence, or blocked/prose narrative as the primary answer.

Expected successful artifact shapes:

```json
{
  "artifacts": [
    {
      "producer_step": 1,
      "tool": "repo_read",
      "arguments": {"path": "AGENTS.md"},
      "ok": true,
      "artifact": {
        "kind": "repo_read",
        "repo_path": "AGENTS.md",
        "line_count": 42,
        "truncated": false,
        "content": "..."
      }
    }
  ],
  "limits": []
}
```

For a successful code-product proposal, the code payload is inline:

```json
{
  "artifacts": [
    {
      "producer_step": 3,
      "tool": "repo_propose_code_edit",
      "arguments": {
        "target_file": "README.md",
        "edit_kind": "unified_diff"
      },
      "ok": true,
      "artifact": {
        "kind": "code_edit_proposal",
        "target_file": "README.md",
        "edit_kind": "unified_diff",
        "rationale": "Report-only patch proposal.",
        "source_writes_performed": false,
        "patch_application_performed": false,
        "manual_review_required": true,
        "validation_commands": ["git diff --check"],
        "errors": [],
        "warnings": [],
        "unified_diff": "--- a/README.md\n+++ b/README.md\n@@ -1,1 +1,1 @@\n-old\n+new"
      }
    }
  ],
  "limits": []
}
```

`unified_diff` and `structured_operations` are full payload fields. They are not
limits, summaries or artifact references.

## Data Flow

1. OpenWebUI calls 3571 public `vulkan_helper`.
2. `app.py` normalizes the request and posts to 3572 `/vulkan/agent`.
3. 3572 runs the internal agentic loop with 11434 planner turns, optional 11435
   repair/selector support and internal tool dispatch.
4. 3571 waits for terminal state according to configured wait settings.
5. 3571 reads terminal job payload/final JSON from 3572 response.
6. 3572 normally materializes `payload_index_for_30b`,
   `priority_evidence_for_30b` and `materialization_report owner=3572_broker`.
   3571 preserves that materialization, adds transport usage/lint, and uses
   `owner=3571_bridge` only for explicit emergency rehydration/fallback.
7. 3571 carries terminal `result` after the primary evidence fields when
   present; compact previews are only
   fallback transport and must not shadow the payload. Raw `result.history` is
   exposed as the bounded public ledger, not raw audit history.
8. OpenWebUI receives only public metadata plus model-usable inline
   payload/context.

## Evidence Expansion Rules

- Use `successful_tool_turns[*].tool_response` as primary source when present;
  this is an internal wrapper source, not the public substitute for
  `artifacts[*].artifact`.
- If a successful tool result references a local JSON artifact, load it only to
  expand that same successful tool result.
- If a terminal response references `final_path`, load it only as a local
  rehydration source for the terminal/final JSON. Verify public output by
  checking that no `final_path`, `artifact_path`, `workspace`, SQLite path or
  job-local path remains in model-visible fields.
- Never expose `C:\Users\...`, `reads/*.json`, `tool-results/*.json` or other
  local storage paths as model-usable content.
- `content_preview` is allowed only when it is the only data actually produced
  by that successful tool and must be marked as preview-only.
- For `repo_propose_code_edit`, `content_preview`, `unified_diff_preview`,
  `summary` or local artifact paths are never substitutes for the complete
  inline `unified_diff` or `structured_operations`.
- `priority_evidence_for_30b` is a model-navigation index over complete
  successful artifacts. It may expose compact analysis evidence, hashes,
  lengths, line counts and primary payload locations, but large concrete fields
  such as `unified_diff`, `structured_operations` and full file `content`
  remain canonical under `tool_context_for_30b.artifacts[*].artifact`.
- Do not synthesize successful evidence for failed, rejected, blocked or guard
  entries. If a non-completed job contains useful rejected planner output,
  repair text or code-product attempts, expose them only as explicit partial
  products with `validator_accepted=false`.

## Safe Edit Checklist

1. Confirm whether the request path is public OpenWebUI or internal 3572.
2. Confirm the terminal job status and final payload source.
3. Inspect exact JSON returned by `POST /vulkan_helper`.
4. Verify all model-visible context is inline and does not require local file
   access.
5. Verify `public_payload_lint.ok=true`, and verify
   `materialization_report.ok=true` when a terminal payload has concrete inline
   evidence.
6. Verify non-ok terminal responses still contain the same primary keys as ok
   responses and that `result` is not reduced to `{ "preview": ... }` when a
   terminal `result` with public history ledger exists.
7. Re-run at least `python -m compileall -q services\vulkan_bridge`.
