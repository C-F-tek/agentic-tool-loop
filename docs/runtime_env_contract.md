# Runtime Environment Contract

This document records the verified runtime boundaries that the refactor must
preserve.

Current refactoring progress and remaining gaps are tracked in
`docs/refactoring_status_current.md`. That status document is audit metadata;
the runtime boundaries below remain authoritative.

## Process Roles

| Role | Endpoint | Owner | Expected runtime |
| --- | --- | --- | --- |
| Public OpenWebUI tool bridge | `127.0.0.1:3571` | `services/vulkan_bridge/app.py` | `venvs/labtools` |
| Internal agent broker | `127.0.0.1:3572` | `services/aicarmine_broker/app.py` | `venvs/labtools` |
| Main planner Ollama | `127.0.0.1:11434` | external Ollama Desktop/main process | external Ollama |
| Repair/task Ollama | `127.0.0.1:11435` | `ollama-task-vulkan.ps1` | external Ollama task instance |
| OpenWebUI UI | usually `127.0.0.1:8080` | `services/aicarmine-openwebui-serve.py` | `venvs/openwebui` |

## Environment Sources

The broker/bridge Python services use values parsed in
`services/aicarmine_broker/config.py` and `services/vulkan_bridge/app.py`.
Launcher scripts may set process/user env before startup, but live behavior is
determined by the environment inherited by the running process.

Critical planner defaults documented in the current code/docs:

- `AICARMINE_AGENTIC_PLANNER_NUM_CTX=12288`
- `AICARMINE_AGENTIC_PLANNER_NUM_CTX_CAP=12288`
- `AICARMINE_AGENTIC_PLANNER_PROMPT_CHAR_BUDGET=48000`
- `AICARMINE_AGENTIC_PLANNER_PROMPT_COMPACT_RATIO=0.5`

The refactor must not change model, context, launcher order or service venv as
part of code-structure cleanup. Those changes require separate runtime proof.

## Repository Root Variables

The runtime has multiple filesystem roots. They are not interchangeable.

| Variable | Owner/consumer | Meaning | Must not be used as |
| --- | --- | --- | --- |
| `AICARMINE_LAB_REPO` | 3572 planner, repo tools, validator, code-product tools, Open Terminal cwd | Active repository/worktree being analyzed, read, patched or validated. All `repo_*` paths are repo-relative to this root. | Job storage, OpenWebUI data, RAG source root unless explicitly configured. |
| `AICARMINE_REAL_REPO` | memory/RAG/index helpers | Canonical source/index repository for memory and RAG paths. | Validator root for `repo_read` unless it is also the active lab repo. |
| `AICARMINE_VULKAN_WORKSPACE` | broker job storage | Workspace containing agent job directories and dashboard artifacts. | Repo path root for planner/tool decisions. |
| `AICARMINE_AGENT_JOB_ROOT` | job store/dashboard | Concrete `agent-jobs` directory under the Vulkan workspace. | Content source for OpenWebUI or `repo_read`. |
| `OPEN_TERMINAL_CWD` / `AICARMINE_OPEN_TERMINAL_WORKDIR` | Open Terminal launcher/runtime | User terminal working directory. It must resolve to the same effective workspace as `AICARMINE_LAB_REPO` unless deliberately overridden with proof. | Validator or repo-tool root when it drifts from `AICARMINE_LAB_REPO`. |

Hard invariant:

- `candidate_next_actions[*].tool == "repo_read"` paths are interpreted
  relative to `AICARMINE_LAB_REPO`.
- `validator_admissible_repo_read_paths` must be built from the same
  `AICARMINE_LAB_REPO` root and must include any readable candidate
  `repo_read` path that the controller exposes to the planner.
- If a RAG/core-discovery path exists under `AICARMINE_LAB_REPO` and is
  exposed as a candidate read, the validator must accept that same path. If it
  is not readable/admissible, remove it from `candidate_next_actions`; do not
  prompt the planner with a call the validator will reject.
- Never validate planner candidate paths against `C:\Users\carmi\AI`, the job
  workspace, or `AICARMINE_REAL_REPO` unless that is the configured
  `AICARMINE_LAB_REPO` for the active process.

Diagnostic rule:

- For any path mismatch, first inspect
  `planner-prompts/step-*-planner-payload.json -> user_payload.lab_repo`.
  That value is the runtime root used by the job and is more relevant than the
  Codex thread cwd.

## Payload Isolation

OpenWebUI receives only the public 3571 response. It cannot inspect:

- `C:\Users\...` local paths;
- job workspaces;
- SQLite prompt documents;
- `reads/*.json` or `tool-results/*.json`;
- 3572-only dashboards.

Any payload required by OpenWebUI must be expanded inline before the 3571
response leaves the bridge.
