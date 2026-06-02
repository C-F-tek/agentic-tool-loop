# Agentic Tool Loop

Repository for the local OpenWebUI agentic tool loop runtime.

This project contains the service code, contracts, launch scripts, model
templates, and documentation needed to run the local tool bridge and broker.
Machine-local data, generated artifacts, model binaries, virtual environments,
OpenWebUI data, and job outputs are intentionally excluded from Git.

## Initial Reading Index

Start from these documents before changing runtime behavior:

1. [AGENTS.md](AGENTS.md)
   - Workspace operating rules and non-negotiable runtime contract notes.
2. [services/VALIDATOR_ONLY_AGENTIC_LOOP_CONTRACT.md](services/VALIDATOR_ONLY_AGENTIC_LOOP_CONTRACT.md)
   - Core validator/controller contract for the agentic loop.
3. [services/END_TO_END_AGENTIC_FLOW.md](services/END_TO_END_AGENTIC_FLOW.md)
   - End-to-end flow between OpenWebUI, 3571, 3572, planner, tools, and final
     payload.
4. [services/SERVICES_MODULE_TECHNICAL_REFERENCE.md](services/SERVICES_MODULE_TECHNICAL_REFERENCE.md)
   - Service-level technical map and module references.
5. [services/MODULE_TECHNICAL_DESCRIPTIONS.md](services/MODULE_TECHNICAL_DESCRIPTIONS.md)
   - File-by-file technical descriptions for the `services/` tree.
6. [services/CODEX_OPENWEBUI_PAYLOAD_LIMITATION.md](services/CODEX_OPENWEBUI_PAYLOAD_LIMITATION.md)
   - Operational limit for Codex when inspecting large OpenWebUI payloads.
7. [services/aicarmine_broker/MODULE_REFERENCE.md](services/aicarmine_broker/MODULE_REFERENCE.md)
   - Broker module reference.
8. [services/vulkan_bridge/MODULE_REFERENCE.md](services/vulkan_bridge/MODULE_REFERENCE.md)
   - Public bridge module reference.
9. [services/codex_bridge/MODULE_REFERENCE.md](services/codex_bridge/MODULE_REFERENCE.md)
   - Codex bridge module reference.
10. [services/launch/MODULE_REFERENCE.md](services/launch/MODULE_REFERENCE.md)
    - Launch-script module reference.
11. [services/model_export/MODULE_REFERENCE.md](services/model_export/MODULE_REFERENCE.md)
    - Model export module reference.

Core code entry points:

- [services/vulkan_bridge/app.py](services/vulkan_bridge/app.py)
  - Public OpenWebUI wrapper surface.
- [services/vulkan_bridge/agentic_v9.py](services/vulkan_bridge/agentic_v9.py)
  - Agentic bridge integration surface.
- [services/aicarmine_broker/app.py](services/aicarmine_broker/app.py)
  - Internal broker application.
- [services/aicarmine_broker/planner.py](services/aicarmine_broker/planner.py)
  - Planner/controller contract and validation loop.
- [services/aicarmine_broker/repo_tools.py](services/aicarmine_broker/repo_tools.py)
  - Repository inspection, command, validation, and code-product tool
    implementations.
- [services/aicarmine_broker/tool_registry.py](services/aicarmine_broker/tool_registry.py)
  - Internal tool registry.
- [services/aicarmine_broker/tool_dispatch.py](services/aicarmine_broker/tool_dispatch.py)
  - Tool dispatch layer.
- [services/aicarmine_broker/job_store.py](services/aicarmine_broker/job_store.py)
  - Job state and artifact persistence.
- [services/aicarmine_broker/public_wrapper.py](services/aicarmine_broker/public_wrapper.py)
  - Public result packaging support.
- [services/aicarmine_broker/planner_intrinsic_context.py](services/aicarmine_broker/planner_intrinsic_context.py)
  - Intrinsic planner context builder.
- [services/aicarmine_broker/code_edit_proposal_contract.py](services/aicarmine_broker/code_edit_proposal_contract.py)
  - Report-only code edit proposal contract.
- [services/aicarmine_broker/memory_tools.py](services/aicarmine_broker/memory_tools.py)
  - Runtime memory tool support.

Supporting runtime surfaces:

- [services/launch/](services/launch/)
  - PowerShell helpers for service startup and environment setup.
- [services/codex_bridge/](services/codex_bridge/)
  - Codex/Ollama bridge helpers.
- [services/model_export/](services/model_export/)
  - Model export helpers.
- [modelfiles/](modelfiles/)
  - Ollama model templates.
- [codex_ollama_bridge_applied/](codex_ollama_bridge_applied/)
  - Applied bridge/tool material used by the local integration.

Local-only descriptor directories:

- [lab-worktrees](lab-worktrees/README.md)
- [openwebui-data](openwebui-data/README.md)
- [services/openwebui-data](services/openwebui-data/README.md)
- [qwen-agent-workspace](qwen-agent-workspace/README.md)
- [qwen-agent](qwen-agent/README.md)
- [qwen-context](qwen-context/README.md)
- [code-interpreter-workdir](code-interpreter-workdir/README.md)
- [executor-runs](executor-runs/README.md)
- [payloads](payloads/README.md)
- [logs](logs/README.md)
- [cache](cache/README.md)
- [state](state/README.md)
- [venvs](venvs/README.md)
- [lab-patches](lab-patches/README.md)
- [knowledge-bad-md](knowledge-bad-md/README.md)
- [knowledge-code-packs](knowledge-code-packs/README.md)
- [knowledge-md](knowledge-md/README.md)
- [knowledge-md-parts](knowledge-md-parts/README.md)
- [knowledge-small-md](knowledge-small-md/README.md)
- [knowledge-sync](knowledge-sync/README.md)
- [knowledge-tiny-md](knowledge-tiny-md/README.md)
- [knowledge-upload-batches](knowledge-upload-batches/README.md)
- [models-cpu](models-cpu/README.md)
- [models-ovms-rerank](models-ovms-rerank/README.md)
- [models-task](models-task/README.md)
- [ovms-runtime](ovms-runtime/README.md)

## Agentic Tool Runtime

This repository implements a local agentic tool loop for OpenWebUI. The public
model does not call every internal tool directly. It calls one public bridge
tool, and the internal broker runs the controlled multi-step loop.

Canonical runtime chain:

```text
OpenWebUI / external 30B
  -> 3571 public bridge /vulkan_helper
  -> 3572 internal broker /vulkan/agent
  -> 11434 planner Ollama turn
  -> 3572 validator-only controller
      -> valid tool call: internal tool dispatch
      -> invalid planner output: controller guard or typed rejection
      -> dirty JSON when applicable: optional 11435 repair/task pass
      -> valid final: terminal job result
  -> 3571 terminal wrapper
  -> OpenWebUI content + inline tool_context_for_30b
```

### Public Surface

`3571` is the OpenWebUI-facing service. Its public tool surface is
`vulkan_helper`. It forwards work to the internal broker and shapes terminal
responses for OpenWebUI.

The public response must remain model-usable without local filesystem access:

- `content` contains the compact final answer or terminal message.
- `priority_evidence_for_30b` indexes important complete evidence when present.
- `tool_context_for_30b` is a pretty-printed JSON string containing successful
  internal tool results inline.

OpenWebUI cannot open local paths such as `C:\Users\...`, `reads/*.json`,
`tool-results/*.json` or SQLite document IDs. Those can exist internally only
as audit/storage surfaces. If a successful tool result is needed by OpenWebUI,
3571 must expand the real payload inline.

### Internal Broker

`3572` owns the agentic loop. It creates jobs, stores state and events, builds
planner prompts, validates model decisions, dispatches tools, writes final
artifacts, and exposes job dashboards.

The central rule is:

```text
the planner decides; the controller validates; the controller does not replace
planner reasoning with hidden hard-coded tool sequences or hidden auto-final
behavior.
```

Ollama `done_reason` closes a model turn. It does not complete the job by
itself. A job reaches `completed` only after the planner emits a valid final
decision and the 3572 validator accepts it.

### Planner And Repair Endpoints

- `11434` is the main planner endpoint. It receives the measured planner prompt
  pack, chooses the next action, and returns strict JSON or a native tool call.
- `11435` is the task/repair endpoint. It is support for selector, repair or
  normalization flows. It is not the main planner and does not decide job
  completion.

Semantic contract failures, such as a missing complete diff for a code-product
goal, are controller guard feedback for the next planner turn. They are not
papered over by GPU/task repair.

### Internal Tool Surface

The planner can select internal tools only through the 3572 registry and
dispatch layer. Important tool families include:

- repository inspection: `repo_status`, `repo_tree`, `repo_search`,
  `repo_list_files`, `repo_read`;
- report-only code products: `repo_propose_code_edit`;
- explicit write/apply lane: `repo_apply_patch`, `repo_write_file`;
- validation and terminal support: `repo_validate`, `repo_command`,
  `terminal_run_command_wait`, `terminal_search_files`, `terminal_list_files`;
- planner-local memory: `planner_scratchpad_read`,
  `planner_scratchpad_write`;
- selective runtime memory: `runtime_sqlite_memory_search`,
  `runtime_sqlite_memory_write`, `runtime_sqlite_memory_cleanup`.

Write-guarded tools remain separate from analysis and report-only tools. A
request for a concrete diff or refactor proposal does not imply source writes.
A request to apply/edit/fix/write does.

### Evidence And Finalization

Finalization is evidence-gated.

For repository reads, a `repo_read ok=true` is useful only when the result has
real `content` available from the same successful tool result or its own
rehydratable artifact. A path, count, `content_preview`, local JSON path or
artifact pointer is not enough.

Useful successful evidence by tool type:

- `repo_read`: real file `content`, logical `repo_path`, line count and
  truncation metadata.
- `repo_tree`: real explored `entries`.
- `repo_list_files`: real listed `paths`.
- `repo_command` and terminal tools: `returncode`, `stdout`, `stderr` and tails
  when produced.
- `repo_propose_code_edit`: complete code edit proposal payload.

Failed tools, validator guards, blocked states and diagnostics are job history.
They are not successful evidence for final answers.

### Code Product Lane

Diff, patch proposal, unified diff, concrete refactoring and code-product goals
use `repo_propose_code_edit`.

This tool is report-only:

- it must not write source files;
- it must not apply patches;
- it must run after the target was read with `repo_read`;
- it must return `kind=code_edit_proposal`;
- it must include `target_file`, `edit_kind`, `rationale`,
  `validation_commands`, `errors`, `warnings`;
- it must set `source_writes_performed=false`,
  `patch_application_performed=false`,
  `manual_review_required=true`;
- for `edit_kind=unified_diff`, it must carry the complete `unified_diff`
  inline;
- for `edit_kind=structured_edit`, it must carry complete
  `structured_operations`;
- for `edit_kind=no_op`, it must carry an explicit rationale and no patch
  content.

Preview fields, summaries and local artifact paths do not satisfy the
code-product contract. While a valid code proposal is missing,
`final_allowed=false` for code-product goals.

### Prompt Pack, Memory And RAG

Before each 11434 planner call, 3572 builds a measured prompt pack. It separates:

- `required_working_set`: real file, diff or result windows needed for the next
  decision;
- `optional_context`: intrinsic context, history digest, memory, RAG/chunks,
  failure patterns and tool-purpose context;
- `prompt_budget_report`: the real serialized prompt count and budget data.

Memory, RAG and chunks are an internal pre-turn substrate. They are not public
OpenWebUI tools and are not automatically planner-selectable tool surfaces.

When prompt size crosses the configured compaction threshold, large sections are
stored in job-local SQLite and exposed to the planner as real recursive windows
with text, offsets, full size, hash and `has_more_after`. The planner can then
consume the next window through `planner_scratchpad_read` with
`kind=prompt_context_window`.

This compaction applies to the planner prompt sent to 11434. It must not degrade
the terminal `tool_context_for_30b` sent to OpenWebUI: successful tool payloads
still need to be reconstructed inline.

### IA Live Control View

3572 also exposes an operator-only read-only dashboard:

- `/jobs/{job_id}/ia-view`
- `/jobs/{job_id}/ia-view.json`

This view is not part of the 3571 public surface and is not a planner tool. It
shows what the planner saw and what the controller fed back: prompt payload,
required working set, intrinsic context, evidence contract, compact tool result,
raw rehydrated tool result, validator guard and terminal `tool_context_for_30b`.

It exists to make payload transport violations visible, especially preview-only,
metadata-only or artifact-path-only regressions.

## Top-Level Tree

- [AGENTS.md](AGENTS.md)
- [README.md](README.md)
- [.gitignore](.gitignore)
- [services/](services/)
- [codex_ollama_bridge_applied/](codex_ollama_bridge_applied/)
- [modelfiles/](modelfiles/)
- [lab-worktrees/](lab-worktrees/)
- [openwebui-data/](openwebui-data/)
- [qwen-agent-workspace/](qwen-agent-workspace/)
- [qwen-agent/](qwen-agent/)
- [qwen-context/](qwen-context/)
- [code-interpreter-workdir/](code-interpreter-workdir/)
- [executor-runs/](executor-runs/)
- [payloads/](payloads/)
- [logs/](logs/)
- [cache/](cache/)
- [state/](state/)
- [knowledge-bad-md/](knowledge-bad-md/)
- [knowledge-code-packs/](knowledge-code-packs/)
- [knowledge-md/](knowledge-md/)
- [knowledge-md-parts/](knowledge-md-parts/)
- [knowledge-small-md/](knowledge-small-md/)
- [knowledge-sync/](knowledge-sync/)
- [knowledge-tiny-md/](knowledge-tiny-md/)
- [knowledge-upload-batches/](knowledge-upload-batches/)
- [models-cpu/](models-cpu/)
- [models-ovms-rerank/](models-ovms-rerank/)
- [models-task/](models-task/)
- [ovms-runtime/](ovms-runtime/)
- [lab-patches/](lab-patches/)
- [venvs/](venvs/)

## Source And Runtime Code

### [services/](services/)

Main service surface for the agentic loop.

Important submodules:

- [services/vulkan_bridge/](services/vulkan_bridge/): public OpenWebUI-facing bridge surface, including
  the `vulkan_helper` wrapper flow.
- [services/aicarmine_broker/](services/aicarmine_broker/): internal broker and planner loop, job store,
  tool registry, repo tools, memory tools, planner contracts, and code-product
  proposal support.
- [services/codex_bridge/](services/codex_bridge/): Codex/Ollama bridge helpers.
- [services/model_export/](services/model_export/): local model export helpers.
- [services/launch/](services/launch/): PowerShell runtime launch helpers.

Important documentation:

- [services/VALIDATOR_ONLY_AGENTIC_LOOP_CONTRACT.md](services/VALIDATOR_ONLY_AGENTIC_LOOP_CONTRACT.md)
- [services/END_TO_END_AGENTIC_FLOW.md](services/END_TO_END_AGENTIC_FLOW.md)
- [services/SERVICES_MODULE_TECHNICAL_REFERENCE.md](services/SERVICES_MODULE_TECHNICAL_REFERENCE.md)
- [services/MODULE_TECHNICAL_DESCRIPTIONS.md](services/MODULE_TECHNICAL_DESCRIPTIONS.md)
- [services/CODEX_OPENWEBUI_PAYLOAD_LIMITATION.md](services/CODEX_OPENWEBUI_PAYLOAD_LIMITATION.md)

### [codex_ollama_bridge_applied/](codex_ollama_bridge_applied/)

Applied bridge scripts and copied tool/runtime material used as part of the
local Codex/Ollama/OpenWebUI integration.

### [modelfiles/](modelfiles/)

Ollama Modelfile templates and model configuration examples. Actual model
binaries are not committed.

## External Or Local-Only Work Areas

These directories are represented by committed `README.md` descriptors only.
Their runtime contents are ignored by `.gitignore`.

### [lab-worktrees/](lab-worktrees/)

Local controlled worktrees used by the agentic tool loop and OpenTerminal.
The worktree code itself is external and already versioned elsewhere.

### [openwebui-data/](openwebui-data/) and [services/openwebui-data/](services/openwebui-data/)

Local OpenWebUI data directories. They may contain chats, uploads, runtime
databases, caches, and generated state. Those contents are not source.

### [qwen-agent-workspace/](qwen-agent-workspace/)

Local job workspace for broker runs, tool results, planner streams, and final
artifacts.

### [qwen-agent/](qwen-agent/) and [qwen-context/](qwen-context/)

Local Qwen context, reports, patches, and runtime state.

### [code-interpreter-workdir/](code-interpreter-workdir/)

Scratch workspace for code-interpreter style executions.

### [executor-runs/](executor-runs/), [payloads/](payloads/), [logs/](logs/), [cache/](cache/), [state/](state/)

Runtime outputs, diagnostic captures, logs, caches, and local state.

### `knowledge-*/`

Generated knowledge packs, Markdown splits, upload batches, and synchronized
knowledge mirrors. Curated documentation should live in normal source docs
instead.

Preserved descriptors:

- [knowledge-bad-md](knowledge-bad-md/README.md)
- [knowledge-code-packs](knowledge-code-packs/README.md)
- [knowledge-md](knowledge-md/README.md)
- [knowledge-md-parts](knowledge-md-parts/README.md)
- [knowledge-small-md](knowledge-small-md/README.md)
- [knowledge-sync](knowledge-sync/README.md)
- [knowledge-tiny-md](knowledge-tiny-md/README.md)
- [knowledge-upload-batches](knowledge-upload-batches/README.md)

### `models-*/` and [ovms-runtime/](ovms-runtime/)

Local model stores and OpenVINO Model Server runtime files. Model binaries and
runtime state are not committed.

Preserved descriptors:

- [models-cpu](models-cpu/README.md)
- [models-ovms-rerank](models-ovms-rerank/README.md)
- [models-task](models-task/README.md)
- [ovms-runtime](ovms-runtime/README.md)

### [lab-patches/](lab-patches/)

Local patch experiments and proof artifacts.

### [venvs/](venvs/)

Local Python virtual environments.

## Git Import Policy

The repository keeps source, scripts, contracts, and documentation. It excludes:

- OpenWebUI user/runtime data.
- Agent job artifacts and planner/tool result outputs.
- Virtual environments and dependency caches.
- Model binaries and runtime backends.
- SQLite databases, generated knowledge stores, logs, payload captures, and
  temporary files.
- External lab worktree contents.

Directory descriptors are committed where useful so the project tree remains
understandable without importing private or generated data.
