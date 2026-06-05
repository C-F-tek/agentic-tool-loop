# Launch Order Contract

This is a static contract for component-level tests. It documents the expected
ordering; it is not an executable launcher.

1. Prepare process/user environment for the selected runtime.
2. Validate venv boundaries:
   - 3571/3572 use `venvs/labtools`.
   - OpenWebUI uses `venvs/openwebui`.
   - 11435 is an external Ollama task instance.
3. Start or verify task Ollama on `127.0.0.1:11435` when enabled.
4. Start or verify internal broker on `127.0.0.1:3572`.
5. Start or verify public bridge on `127.0.0.1:3571`.
6. Register only `http://127.0.0.1:3571/openapi.json` as the OpenWebUI tool
   source.
7. Start foreground OpenWebUI.
8. On shutdown, verify process ownership before stopping managed processes.

Do not infer live state from this file. Live diagnostics must inspect process
command lines, port owners and health endpoints.
