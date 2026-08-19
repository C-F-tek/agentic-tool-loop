# Implementation Plan: Agentic Loop Pointer Memory & Chunk Integration

[Overview]
This implementation plan details the integration of pointer memory systems, chunk management components, and agent memory models from the "code to inject on projects" directory into the existing agentic loop infrastructure. The integration will enable dynamic chunk reconstruction, heap block navigation via pointer graphs, resume context management for continuation after rewrite/back-refinement operations, and state packet generation using MemoryRecord and AgentMicroTask models. These components fit into the existing aicarmine MCP server ecosystem by providing memory persistence, context reloading, and semantic chunk concatenation capabilities that enhance the agentic loop's ability to maintain execution history and resume operations seamlessly.

[Types]
This implementation introduces pointer graph node types, resume context structures, revision pointers, code/evidence/proposal chunk types, and agent memory record models with their associated validation rules and relationships.

Detailed type definitions:

**PointerNode**: Represents a node in the pointer graph representing a heap block or proposal chunk.
- block_id: str - Unique identifier for the block
- previous_block_id: str - Previous block ID for backward navigation
- next_block_id: str - Next block ID for forward continuation
- refines_block_id: str - Refines block ID for back-refinement
- resume_from_block_id: str - Resume from block ID for continuation after rewrite
- pointer_action: str - Pointer action metadata
- exit_decision: str - Exit decision metadata
- quality_passed: bool - Quality pass flag
- role: str - Role classification
- block_type: str - Block type classification
- target_files: list[str] - Target files list
- proposal_block_id: str - Proposal block identifier

**PointerGraph**: A directed graph of pointer nodes representing heap execution history.
- nodes: dict[str, PointerNode] - Node dictionary mapping block_id to PointerNode
- latest_block_id: str - Latest block identifier
- proposal_block_id: str - Proposal block identifier

**ResumeContext**: Context for resuming heap execution after a rewrite or back-refinement.
- resume_from_block_id: str - Resume anchor block ID
- latest_block_id: str - Latest block identifier
- proposal_block_id: str - Proposal block identifier
- closure_evidence_block_id: str - Closure evidence block identifier
- soft_lock_state: str - Soft lock state string
- continuation_required: bool - Continuation required flag
- product_blocked_reason: str - Product blocked reason string

**RevisionPointer**: Revision pointer structure for context management.
- revision_id: str - Revision identifier
- block_id: str - Block identifier
- timestamp: str - Timestamp string

**CodeChunk**: A semantic code chunk with navigation and concatenation support.
- chunk_id: str - Chunk identifier
- path: str - File path
- symbol: str - Symbol name
- kind: str - Chunk kind (default: "semantic_code_chunk")
- line_start: int - Starting line number
- line_end: int - Ending line number
- domain: list[str] - Domain classifications
- risk: str - Risk level ("low", "medium", "high")
- risk_signals: list[str] - Risk signal indicators
- compatibility_notes: list[str] - Compatibility notes
- dependencies: list[str] - Dependency lists
- blender_api: list[str] - Blender API references
- summary_short: str - Short summary string
- content_preview: str - Content preview string
- do_not_change: bool - Do not change flag
- sha256: str - SHA256 hash
- score: int - Score value
- matched_terms: list[str] - Matched terms list

**EvidenceChunk**: Evidence chunk structure for semantic evidence management.
- chunk_id: str - Chunk identifier
- source: str - Source identifier
- content: str - Content string
- confidence: float - Confidence score

**ProposalChunk**: Proposal chunk structure for proposal management.
- chunk_id: str - Chunk identifier
- proposal_id: str - Proposal identifier
- target_files: list[str] - Target files list
- changes: dict[str, Any] - Change specifications

**MemoryRecord**: A generic memory item selected into an agent state packet.
- record_id: str - Record identifier
- kind: str - Record kind
- scope: str - Scope identifier
- source: str - Source identifier
- summary: str - Summary string
- content: str - Content string
- tags: tuple[str, ...] - Tag tuples
- confidence: float - Confidence score (0.0 to 1.0)
- created_at: str - Creation timestamp ISO format
- updated_at: str | None - Update timestamp
- expires_at: str | None - Expiration timestamp
- metadata: dict[str, Any] - Metadata dictionary

**AgentMicroTask**: A planned unit of work for an app or specialized agent lane.
- task_id: str - Task identifier
- title: str - Task title
- lane: str - Lane identifier
- purpose: str - Purpose description
- priority: int - Priority level (1-10)
- blocking: bool - Blocking flag
- status: str - Status string ("planned", "running", "completed", "failed")
- inputs: tuple[str, ...] - Input identifiers
- expected_outputs: tuple[str, ...] - Expected output identifiers
- depends_on: tuple[str, ...] - Dependency task IDs
- metadata: dict[str, Any] - Metadata dictionary

[Files]
This implementation creates new integration modules in the services/codex_bridge directory and modifies existing MCP server files to incorporate pointer memory, chunk management, and agent memory models.

New files to be created:
- `services/codex_bridge/pointer_memory.py` - Pointer graph, resume context, and revision pointer integration module
- `services/codex_bridge/chunk_management.py` - Code chunk, evidence chunk, proposal chunk concatenation and reconstruction module
- `services/codex_bridge/agent_memory_models.py` - MemoryRecord and AgentMicroTask model definitions with SQLite storage
- `services/codex_bridge/context_reload_utils.py` - Context reloading utilities from heap_context_memory_reload

Existing files to be modified:
- `services/codex_bridge/agentic_loop_client_mcp_server.py` - Add integration points for pointer memory and chunk management
- `services/codex_bridge/project_memory_mcp_server.py` - Extend with agent memory models support
- `services/codex_bridge/rag_mcp_server.py` - Integrate chunk management for RAG index building
- `services/codex_bridge/build_embedding_index.py` - Update to use new chunk patterns

Configuration file updates:
- No configuration file updates required; existing MCP server configurations will accommodate the new modules.

[Functions]
This implementation introduces new functions for pointer graph navigation, resume context building, chunk concatenation, and agent memory record management, while extending existing MCP server functions to support these capabilities.

New functions:
- `get_previous_block_id(node: PointerNode | dict[str, Any]) -> str` - Extract previous block ID from a pointer node or dictionary (file: services/codex_bridge/pointer_memory.py)
- `get_next_block_id(node: PointerNode | dict[str, Any]) -> str` - Extract next block ID from a pointer node or dictionary (file: services/codex_bridge/pointer_memory.py)
- `get_refines_block_id(node: PointerNode | dict[str, Any]) -> str` - Extract refines block ID from a pointer node or dictionary (file: services/codex_bridge/pointer_memory.py)
- `get_resume_from_block_id(node: PointerNode | dict[str, Any]) -> str` - Extract resume from block ID from a pointer node or dictionary (file: services/codex_bridge/pointer_memory.py)
- `has_previous(block_id: str, graph: PointerGraph) -> bool` - Check if a block has a previous block in the pointer graph (file: services/codex_bridge/pointer_memory.py)
- `has_next(block_id: str, graph: PointerGraph) -> bool` - Check if a block has a next block in the pointer graph (file: services/codex_bridge/pointer_memory.py)
- `has_refines(block_id: str, graph: PointerGraph) -> bool` - Check if a block has a refines target in the pointer graph (file: services/codex_bridge/pointer_memory.py)
- `resume_anchor(revision_context: dict[str, Any], latest_report: dict[str, Any] | None = None) -> str` - Extract the resume anchor block ID from revision context or latest report (file: services/codex_bridge/pointer_memory.py)
- `can_resume_forward(context: ResumeContext | dict[str, Any]) -> bool` - Check if forward continuation is possible from the given context (file: services/codex_bridge/pointer_memory.py)
- `build_resume_context(revision_context: dict[str, Any], latest_report: dict[str, Any] | None = None) -> ResumeContext` - Build a ResumeContext from revision context and latest report data (file: services/codex_bridge/pointer_memory.py)
- `build_code_chunk_sequence(chunks: list[dict[str, Any] | CodeChunk]) -> list[CodeChunk]` - Build a sequence of code chunks from dictionary data (file: services/codex_bridge/chunk_management.py)
- `concat_code_chunks(chunks: list[CodeChunk | dict[str, Any]]) -> str` - Concatenate code chunks to form complete text (file: services/codex_bridge/chunk_management.py)
- `build_evidence_chunk_sequence(chunks: list[dict[str, Any] | EvidenceChunk]) -> list[EvidenceChunk]` - Build a sequence of evidence chunks (file: services/codex_bridge/chunk_management.py)
- `concat_evidence_chunks(chunks: list[EvidenceChunk | dict[str, Any]]) -> str` - Concatenate evidence chunks (file: services/codex_bridge/chunk_management.py)
- `build_proposal_chunk_sequence(chunks: list[dict[str, Any] | ProposalChunk]) -> list[ProposalChunk]` - Build a sequence of proposal chunks (file: services/codex_bridge/chunk_management.py)
- `concat_proposal_chunks(chunks: list[ProposalChunk | dict[str, Any]]) -> str` - Concatenate proposal chunks (file: services/codex_bridge/chunk_management.py)
- `memory_record_from_text(kind: str, scope: str, source: str, text: str, tags: Iterable[str] = (), confidence: float = 1.0, max_record_chars: int = DEFAULT_MAX_RECORD_CHARS, metadata: dict[str, Any] | None = None) -> MemoryRecord` - Create a memory record from raw text (file: services/codex_bridge/agent_memory_models.py)
- `build_state_packet(records: list[MemoryRecord], objective: str, query: str = "") -> dict[str, Any]` - Build an agent state packet from memory records (file: services/codex_bridge/agent_memory_models.py)

Modified functions:
- `aicarmine_rag_reindex()` in `services/codex_bridge/rag_mcp_server.py` - Add chunk management integration for RAG index building using concat_code_chunks and build_code_chunk_sequence
- `aicarmine_project_memory_upsert_verified()` in `services/codex_bridge/project_memory_mcp_server.py` - Extend to support AgentMicroTask model storage

Removed functions:
- No functions are removed; all existing functionality is preserved and extended.

[Classes]
This implementation introduces new classes for pointer graph management, resume context handling, chunk types, and agent memory models, integrating them with existing MCP server architectures.

New classes:
- `PointerNode` (file: services/codex_bridge/pointer_memory.py) - A node in the pointer graph representing a heap block or proposal chunk with methods: get_previous(), get_next(), get_refines(), get_resume_from()
- `PointerGraph` (file: services/codex_bridge/pointer_memory.py) - A directed graph of pointer nodes representing heap execution history with methods: add_node(), get_node(), has_previous(), get_previous_node(), has_next(), get_next_node(), has_refines(), get_refines_node(), get_resume_anchor()
- `ResumeContext` (file: services/codex_bridge/pointer_memory.py) - Context for resuming heap execution after a rewrite or back-refinement with methods: get_resume_anchor(), can_resume_forward()
- `RevisionPointer` (file: services/codex_bridge/pointer_memory.py) - Revision pointer structure for context management
- `CodeChunk` (file: services/codex_bridge/chunk_management.py) - A semantic code chunk with navigation and concatenation support with methods: get_previous_chunk_id(), get_next_chunk_id(), can_concat_with()
- `EvidenceChunk` (file: services/codex_bridge/chunk_management.py) - Evidence chunk structure for semantic evidence management
- `ProposalChunk` (file: services/codex_bridge/chunk_management.py) - Proposal chunk structure for proposal management
- `MemoryRecord` (file: services/codex_bridge/agent_memory_models.py) - A generic memory item selected into an agent state packet with methods: from_text(), from_mapping(), to_dict()
- `AgentMicroTask` (file: services/codex_bridge/agent_memory_models.py) - A planned unit of work for an app or specialized agent lane with method: to_dict()

Modified classes:
- No existing classes are modified; all new functionality is implemented in new modules.

Removed classes:
- No classes are removed; all existing functionality is preserved.

[Dependencies]
This implementation uses existing Python standard library components and existing MCP server infrastructure without requiring new external packages or version changes.

Details:
- Standard library dependencies: dataclasses, typing, collections.abc, hashlib (for sha256_text)
- Existing MCP server integration: aicarmine_project_memory, aicarmine_rag, aicarmine_sqlite_readonly
- No new external packages required; all functionality uses existing Python 3.10+ standard library and existing project dependencies
- Integration requirements: Must work with existing pointer memory MCP tools (aicarmine_repo_state_capabilities, aicarmine_project_memory_upsert_verified) and RAG indexing tools (aicarmine_rag_reindex)

[Testing]
This implementation will be validated through unit tests for pointer graph navigation, resume context building, chunk concatenation, and agent memory record management, ensuring compatibility with existing MCP server infrastructure.

Test file requirements:
- `services/codex_bridge/tests/test_pointer_memory.py` - Tests for PointerGraph, PointerNode, ResumeContext operations
- `services/codex_bridge/tests/test_chunk_management.py` - Tests for code chunk sequence building and concatenation
- `services/codex_bridge/tests/test_agent_memory_models.py` - Tests for MemoryRecord and AgentMicroTask model creation and serialization

Existing test modifications:
- No existing tests are modified; new tests are added for the new functionality.

Validation strategies:
- Verify pointer graph navigation returns correct previous/next/refines/resume anchors
- Verify chunk concatenation produces correct reconstructed text from code/evidence/proposal chunks
- Verify MemoryRecord creation from text and mapping sources
- Verify state packet generation includes proper memory records and metadata

[Implementation Order]
This implementation will be executed in a logical sequence that establishes foundational data structures first, then integrates chunk management, followed by agent memory models, and finally connects everything to the existing MCP server infrastructure.

Numbered steps:
1. Create `services/codex_bridge/pointer_memory.py` with PointerNode, PointerGraph, ResumeContext, RevisionPointer classes and navigation functions
2. Create `services/codex_bridge/chunk_management.py` with CodeChunk, EvidenceChunk, ProposalChunk classes and sequence building/concatenation functions
3. Create `services/codex_bridge/agent_memory_models.py` with MemoryRecord, AgentMicroTask classes and state packet generation functions
4. Create `services/codex_bridge/context_reload_utils.py` with context reloading utilities
5. Update `services/codex_bridge/agentic_loop_client_mcp_server.py` to integrate pointer memory and chunk management capabilities
6. Update `services/codex_bridge/project_memory_mcp_server.py` to extend with agent memory models support
7. Update `services/codex_bridge/rag_mcp_server.py` to integrate chunk management for RAG index building
8. Create test files: `test_pointer_memory.py`, `test_chunk_management.py`, `test_agent_memory_models.py`
9. Validate integration through existing MCP server health checks and tool inventory probes