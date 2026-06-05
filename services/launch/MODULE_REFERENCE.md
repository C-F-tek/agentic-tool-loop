<!-- AICARMINE_NON_NEGOTIABLE_CONTRACT_START -->
Regole operative non negoziabili:
1. Il contratto non va modificato se non richiesto da Carmine esplicitamente.
2. Il prodotto finale puo' essere arricchito come gia' viene fatto; non cambiare logica senza richiesta esplicita.
3. Non devi presupporre nulla: non e' il tuo compito.
<!-- AICARMINE_NON_NEGOTIABLE_CONTRACT_END -->
# launch Module Reference

Updated: 2026-06-01

`services\launch` contains the service launcher and shared PowerShell helpers.
This area is operationally sensitive because it writes environment variables and
starts the processes that connect OpenWebUI, 3571, 3572, Ollama and auxiliary
tools.

Read before edits:

- `C:\Users\carmi\AI\AGENTS.md`
- `C:\Users\carmi\AI\services\SERVICES_MODULE_TECHNICAL_REFERENCE.md`

## Required Runtime Order

The main launcher must preserve this order unless a proven bug requires a
minimal change:

1. Clean Python env and establish config.
2. Set OpenWebUI/OpenVINO base env and run OpenVINO diagnostics when the
   configured Python exists.
3. Check main Ollama 11434 and ensure/launch task Ollama 11435 when configured.
4. Set AI-Carmine env for 3571/3572/tool URLs, planner settings and task model.
5. Start 3572 broker/runtime with labtools Python.
6. Start 3571 public bridge with labtools Python.
7. Start OpenVINO provider process on 3550 if enabled.
8. Start Phi-3.5 NPU diagnostic sidecar on 3551 only if explicitly enabled.
9. Start executor with labtools Python.
10. Start Open Terminal through OpenWebUI venv.
11. Clean legacy LabTools/Qwen tool env values and ports.
12. Start lab mirror watchdog if enabled.
13. Print runtime summary and main GPU diagnostics.
14. Enforce localhost-only OpenWebUI policy.
15. Start OpenWebUI in foreground with OpenWebUI Python.
16. On exit, stop launcher-managed services except main Ollama Desktop/11434.

## Module Map

| Module | Technical description |
| --- | --- |
| `openwebui_runtime.ps1` | Main launcher. It sets user/process env, validates venv paths, starts or checks managed services, registers OpenAPI/tool URLs and starts OpenWebUI foreground. This file is the source of truth for runtime sequence. |
| `env.ps1` | Shared env helpers. It clears `PYTHONHOME`/`PYTHONPATH`, sets defaults and writes/clears user env values. Persistent user env writes can affect later shells. |
| `http.ps1` | Shared HTTP polling helpers. It should only check endpoints and format status, not start services. |
| `ollama.ps1` | Shared Ollama endpoint helpers. It distinguishes main planner Ollama and task/repair Ollama roles. Keep 11434 and 11435 separate. |
| `process.ps1` | Shared process/port helper functions. It detects port ownership and can stop unhealthy processes when invoked by the runtime. Verify command line ownership before stopping anything. |

## Venv Boundaries

| Component | Expected venv/runtime |
| --- | --- |
| 3571 public bridge | `C:\Users\carmi\AI\venvs\labtools` |
| 3572 broker/runtime | `C:\Users\carmi\AI\venvs\labtools` |
| safe command executor | `C:\Users\carmi\AI\venvs\labtools` unless `AICARMINE_EXECUTOR_PYTHON` overrides it |
| OpenWebUI | `C:\Users\carmi\AI\venvs\openwebui` |
| Open Terminal | `C:\Users\carmi\AI\venvs\openwebui` |
| OpenVINO reranker provider 3550 | `C:\Users\carmi\AI\venvs\openvino` through `OPENVINO_PYTHON_EXE` |
| Phi-3.5 NPU diagnostic sidecar 3551 | `C:\Users\carmi\AI\venvs\openvino` through `NPU_PHI_PYTHON_EXE`; disabled by default until the sidecar script exists |
| Ollama 11434/11435 | external `ollama.exe` process, not a Python venv |

## Repository Workdir Env Coupling

The launcher owns the initial coupling between the agentic repo tools and Open
Terminal:

| Env var | Meaning |
| --- | --- |
| `AICARMINE_LAB_REPO` | Active repository/worktree for 3572 repo tools, planner evidence, validator and code-product targets. |
| `OPEN_TERMINAL_CWD` | Open Terminal process cwd. Expected to resolve to the active lab repo. |
| `AICARMINE_OPEN_TERMINAL_WORKDIR` | Public/diagnostic alias for the Open Terminal workdir. Expected to match `OPEN_TERMINAL_CWD`. |
| `AICARMINE_REAL_REPO` | Canonical/index repository for RAG/memory, not the repo-tool validation root unless explicitly equal to `AICARMINE_LAB_REPO`. |
| `AICARMINE_VULKAN_WORKSPACE` / `AICARMINE_AGENT_JOB_ROOT` | Job/dashboard storage, not the active repository root. |

Before debugging a `repo_read_path_not_from_prior_file_evidence` rejection,
check the effective `AICARMINE_LAB_REPO` for the running 3572 process and the
job capture field `user_payload.lab_repo`. Do not validate candidate paths
against the launcher cwd, Codex cwd or OpenWebUI data directory.

## Safe Edit Checklist

1. Prove which launcher path is running: root `openwebui.ps1` wrapper or
   `launch/openwebui_runtime.ps1`.
2. Check active process command lines for 3571/3572 before changing venv logic.
3. Verify env values written to both user env and process env.
4. Do not change model, ctx or max steps while debugging venv/process issues.
5. After edits, parser-check PowerShell and run endpoint health checks only when
   the user wants runtime testing.
