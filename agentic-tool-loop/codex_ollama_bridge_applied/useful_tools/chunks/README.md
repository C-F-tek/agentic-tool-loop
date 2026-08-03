# codex_ollama_bridge_applied/useful_tools/chunks

`chunks/` contains package markers for code, evidence and proposal chunk
namespaces used by the applied bridge material.

## Initial Reading Index

Start from these documents before changing runtime behavior:

- [AGENTS.md](../../../AGENTS.md)
  - Workspace operating rules and non-negotiable runtime contract notes.
- [services/VALIDATOR_ONLY_AGENTIC_LOOP_CONTRACT.md](../../../services/VALIDATOR_ONLY_AGENTIC_LOOP_CONTRACT.md)
  - Core validator/controller contract for the agentic loop.
- [services/END_TO_END_AGENTIC_FLOW.md](../../../services/END_TO_END_AGENTIC_FLOW.md)
  - End-to-end flow between OpenWebUI, 3571, 3572, planner, tools, and final payload.
- [services/SERVICES_MODULE_TECHNICAL_REFERENCE.md](../../../services/SERVICES_MODULE_TECHNICAL_REFERENCE.md)
  - Service-level technical map and module references.
- [services/MODULE_TECHNICAL_DESCRIPTIONS.md](../../../services/MODULE_TECHNICAL_DESCRIPTIONS.md)
  - File-by-file technical descriptions for the `services/` tree.
- [services/CODEX_OPENWEBUI_PAYLOAD_LIMITATION.md](../../../services/CODEX_OPENWEBUI_PAYLOAD_LIMITATION.md)
  - Operational limit for Codex when inspecting large OpenWebUI payloads.

## Current Folder Structure

- [code_chunks/](code_chunks/)
  - Code chunk namespace marker.
- [evidence_chunks/](evidence_chunks/)
  - Evidence chunk namespace marker.
- [proposal_chunks/](proposal_chunks/)
  - Proposal chunk namespace marker.
