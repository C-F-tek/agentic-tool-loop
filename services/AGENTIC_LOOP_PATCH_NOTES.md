<!-- AICARMINE_NON_NEGOTIABLE_CONTRACT_START -->
Regole operative non negoziabili:
1. Il contratto non va modificato se non richiesto da Carmine esplicitamente.
2. Il prodotto finale puo' essere arricchito come gia' viene fatto; non cambiare logica senza richiesta esplicita.
3. Non devi presupporre nulla: non e' il tuo compito.
<!-- AICARMINE_NON_NEGOTIABLE_CONTRACT_END -->
# Agentic Loop Tool patch notes

## 2026-06-02 operational update

Current planner sizing defaults are `AICARMINE_AGENTIC_PLANNER_NUM_CTX=12288`,
`AICARMINE_AGENTIC_PLANNER_NUM_CTX_CAP=12288` and
`AICARMINE_AGENTIC_PLANNER_PROMPT_CHAR_BUDGET=48000`. The prompt compaction
threshold remains 50%, so the soft compact threshold is 24000 serialized prompt
characters. This is not the hard no-headroom blocker. The hard generation
headroom budget is the prompt char budget minus the reserved generation margin
(with these defaults, 48000 - 8000 = 40000).

Large required file/diff/result sections are not replaced by metadata. They are
stored in job-local SQLite prompt documents and surfaced to the planner as real
`planner_prompt_context_window.v1` text windows with offsets, hashes and
`has_more_after`. When the controller explicitly marks a window continuation as
required, it requires
`planner_scratchpad_read(kind=prompt_context_window, ...)`; other actions are
rejected with `prompt_context_continuation_required`. Large `repo_read` windows
without that explicit continuation remain optional adjacent context, not a
linear EOF gate.

The public OpenWebUI payload is unchanged: `tool_context_for_30b` must still
contain the reconstructed real successful tool payloads inline. SQLite document
ids, local JSON paths and job-local artifact paths are internal only.

Operational stop rule: if jobs keep launching or GPU0 keeps pulsing, prove port
ownership first. Stop `ollama-task-vulkan.ps1`/child `ollama.exe` only for
`11435` GPU0/task repair, and stop `aicarmine-vulkan-tool-broker.ps1`/3571 only
when the bridge itself must stop accepting OpenWebUI job requests. Do not kill
the main `11434` Ollama instance unless explicitly required. `11435` is the
GPU0 Intel task lane through Ollama/Vulkan using `models-task`; diagnose it by
port/process ownership and Vulkan/Intel env (`OLLAMA_HOST`, `OLLAMA_MODELS`,
`OLLAMA_VULKAN`, `GGML_VK_VISIBLE_DEVICES`), while 3571/3572 are the labtools
Python services.

## Symptom

OpenWebUI sees only the public helper tool. The helper launches the internal
agentic loop, but terminal results can come back as a very large nested JSON
object containing events, history, tool results and tree/list payload previews.
This can pollute the next OpenWebUI turn, trigger context pressure, and make the
visible answer look truncated.

The observed job `job-3d244d81` also blocked because the planner repeated the
same `repo_tree` call with the same arguments after already having tree/list
information.

## Confirmed cause

The loop did not have a deterministic escape hatch for generic repository review
requests such as `anlizza la repo`. It let the planner start with exploratory
repo tools, then the repeat guard converted the repeated `repo_tree` into
`blocked_needs_attention`.

The broker also returned compact status with full-ish nested `result` and event
payloads. Even when raw artifacts existed on disk, OpenWebUI still received more
JSON than it needed for chat continuation.

## Historical fixes included

1. Generic repo analysis now starts with the bounded composite `vulkan_helper`
   instead of `repo_tree`.
2. Repeat guard recovery converts repeated exploratory calls into a bounded
   `vulkan_helper` review once, instead of immediately blocking.
3. Planner history now receives previews and counts, not full tree/match/list
   arrays.
4. Historical terminal output returned to OpenWebUI was compact: one
   `summary_for_30b`, short pointer fields, digest events, and artifact paths.
   This behavior is superseded by the current 3571 contract below.
5. Full untruncated results remain available in `final.json`, `final.md`, and
   `events.ndjson` under the job workspace.
6. Dashboard routes now expose `/jobs/{job_id}/final.json` and
   `/jobs/{job_id}/final.md`.
7. The 3571 bridge has a final shaping guard, so even an older/verbose 3572
   response is normalized before returning to OpenWebUI.
8. Optional package list added for token budgeting, JSON schema validation,
   retry/backoff, and faster artifact serialization.

## Current 3571 contract

The current contract is not "artifact paths plus summary". OpenWebUI cannot read
local paths. The public `vulkan_helper` response must carry successful internal
tool results inline:

- top-level `content`: final planner answer or compact terminal message only;
- top-level `tool_context_for_30b`: pretty-printed JSON string;
- `tool_context_for_30b.artifacts[*].artifact`: the real result produced by the
  successful internal tool;
- no `continuation_surface`, `call_protocol`, `call_examples`, raw events,
  transport diagnostics or local filesystem artifact paths in the public
  evidence surface.

For `repo_read`, the useful result is the file text in
`artifact.content`. `artifact.repo_path` is only logical metadata. For
`repo_tree`, the useful result is `artifact.entries`. For `repo_list_files`, it
is `artifact.paths`. For command tools, it is `returncode`, `stdout`, `stderr`
and tails if produced.

If a compact 3572 result points to a JSON file under `reads/` or
`tool-results/`, 3571 may load it only to expand that same successful tool
result. The local path is internal and must not be returned as evidence.

## Current code-product tool surface

Diff/refactoring/code-product goals use the internal 3572 tool
`repo_propose_code_edit`. It is report-only and must not write source files or
apply patches.

The successful payload must stay inline in `tool_context_for_30b`:

- `kind=code_edit_proposal`;
- `target_file`, `edit_kind`, `rationale`;
- full `unified_diff` or full `structured_operations` or explicit `no_op`;
- `validation_commands`, `errors`, `warnings`;
- `source_writes_performed=false`,
  `patch_application_performed=false`, `manual_review_required=true`;
- optional AST evidence from Tree-sitter, Python AST anchors or `ast-grep`.

Preview fields, summaries and local artifact paths do not satisfy the code
product contract. Code-product validator failures are controller guards for the
next planner turn, not GPU0/11435 repair prompts. Apply/edit/fix/write goals
remain separate and still require `repo_apply_patch` plus validation.

## Verification performed

```powershell
python -m compileall -q aicarmine_broker aicarmine_vulkan_bridge_server.py `
  aicarmine_vulkan_tool_broker.py aicarmine-openwebui-serve.py `
  aicarmine_codex_mcp_server.py aicarmine_codex_ollama_responses_bridge.py `
  aicarmine-executor-server.py export_model.py
```

Result: `rc=0` in the patched archive build environment.

Historical local checks verified at that time:

- `deterministic_initial_decision('anlizza la repo')` selects `vulkan_helper`.
- `goal_has_write_intent('risolvi problemi noti nel repo')` is `True`.
- `compact_tool_result_for_planner('repo_tree', ...)` returns `entries_preview`
  and `entries_total`, not the full tree.
- `wait_for_agent_terminal(...)` returned compact final output with artifact
  path references. Current 3571 behavior supersedes this: OpenWebUI receives
  real successful tool results in `tool_context_for_30b`.
- `_compact_for_openwebui(...)` on a deliberately huge bridge payload returned a
  bounded envelope. Current 3571 behavior must not reduce successful tool
  results to local artifact paths.

## Install optional public packages

```powershell
python -m pip install -r requirements-agentic-optional.txt
```

These packages are optional. The patched code does not require them at import
time, so the current runtime behavior stays minimal and reversible.
