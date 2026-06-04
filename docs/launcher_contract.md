# Launcher Contract

Launcher scripts are operational boundaries, not refactor scratch space. This
contract records the process expectations that code extraction must preserve.

Current refactoring progress and launcher split gaps are tracked in
`docs/refactoring_status_current.md`. This document remains the launcher
runtime contract to preserve during the split.

## Primary Launch Chain

`openwebui.ps1` delegates to `services/launch/openwebui_runtime.ps1`.

The launcher family may start or check:

- 11435 task Ollama for repair/selector work;
- 3572 broker on `127.0.0.1:3572`;
- 3571 public bridge on `127.0.0.1:3571`;
- Open Terminal/executor helper surfaces;
- foreground OpenWebUI.

## Stable Boundaries

- 3571 and 3572 use labtools Python unless an explicit launcher env override is
  active.
- OpenWebUI uses the OpenWebUI venv, not labtools.
- 11434 main Ollama is separate from 11435 task Ollama.
- Process cleanup must verify port ownership and command line before stopping
  anything.

## Refactor Rule

Do not change launcher env, model, context, port, max-step, unload or process
cleanup behavior while extracting Python modules. If a launcher behavior must be
changed, prove the active process/file/env edge first and record the reason in
the relevant module reference.
