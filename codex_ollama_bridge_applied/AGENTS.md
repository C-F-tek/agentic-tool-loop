# AI-Carmine / Codex local agent rules

This workspace is intended to be used through the AI-Carmine Codex + Ollama bridge.

Operational rules:

1. Verify repository state before editing: use status/search/read before patch/write.
2. Prefer `aicarmine_repo_search` and `aicarmine_repo_read` for evidence-backed answers.
3. Use `aicarmine_memory_state_packet` when the task depends on prior operational memory, pointer-like state, or durable project context.
4. Use `aicarmine_vulkan_helper` for composite local repo analysis when the exact internal tool is unclear.
5. Use `aicarmine_repo_apply_patch`, `aicarmine_repo_write_file`, and `aicarmine_repo_command` only after approval and only for the requested task.
6. Do not invent files, symbols, repository status, command output, or validation results. Read or run the corresponding tool first.
7. Dangerous commands require explicit human consent in the `user_consent` argument.

Local services expected:

- Ollama: `http://127.0.0.1:11434`
- AI-Carmine broker: `http://127.0.0.1:3572/vulkan/agent`
- Optional Codex provider bridge: `http://127.0.0.1:3581/v1`
