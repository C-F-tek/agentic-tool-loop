<!-- AICARMINE_NON_NEGOTIABLE_CONTRACT_START -->
Regole operative non negoziabili:
1. Il contratto non va modificato se non richiesto da Carmine esplicitamente.
2. Il prodotto finale puo' essere arricchito come gia' viene fatto; non cambiare logica senza richiesta esplicita.
3. Non devi presupporre nulla: non e' il tuo compito.
<!-- AICARMINE_NON_NEGOTIABLE_CONTRACT_END -->
# Agentic Loop v5 — operational memory and recovery

## Problem fixed

The previous patches exposed that the job had persisted files/events, but not a
usable operational memory loop. OpenWebUI/30B cannot read local paths such as
`final.json` or `events.ndjson`. The planner also repeated invalid actions even
when the evidence contract contained valid `candidate_next_actions`.

## Changes

- `planner.py`
  - filters core candidates so `repo_list_files` is only proposed for proven directories;
  - keeps code files such as `tools.py` as `repo_read` candidates, never directory-list candidates;
  - adds `working_memory_for_30b` in job state and final context;
  - adds 3572 operational-memory recovery: after an invalid/repeated planner action,
    the controller may select exactly one validator-compatible `candidate_next_actions`
    item derived from evidence;
  - no hard-coded project core path is introduced.

- `job_store.py`
  - status/result responses now expose `working_memory_for_30b` inline;
  - messages explicitly state that OpenWebUI cannot read local artifact paths;
  - continuation points to `action=result/status` with the same `job_id`.

## Current contract note

This historical note predates the current validator-only contract. The current
behavior is:

- 3572 validates planner decisions and may reject them with `controller_guard`;
- 3572 does not replace planner reasoning with hidden auto-final or hidden
  tool sequences;
- the planner receives prior turn memory, including `done_reason`,
  `tool_call`, and successful `tool_response`;
- finalization requires verified `repo_read` content, not just path metadata or
  `content_preview`;
- diff/refactoring/code-product finalization also requires a successful
  report-only `repo_propose_code_edit` payload after the target `repo_read`;
  preview/summary/artifact-path-only code proposals are invalid;
- 3571 returns successful tool results to OpenWebUI inline in
  `tool_context_for_30b`, as JSON text, because OpenWebUI cannot open local
  artifact paths.

When debugging current behavior, treat `services/VALIDATOR_ONLY_AGENTIC_LOOP_CONTRACT.md`
as authoritative.

