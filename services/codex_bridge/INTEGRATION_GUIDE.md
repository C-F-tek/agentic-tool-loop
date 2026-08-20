# Agentic Loop Integration Guide: Pointer Memory, Chunk Management & Agent Memory Models

## Overview

This guide documents the integration of pointer memory, chunk management, and agent memory models into the agentic loop infrastructure. These modules enable dynamic context reconstruction, heap block navigation, and state packet generation within the aicarmine MCP server ecosystem.

---

## 1. Pointer Memory Module (`pointer_memory.py`)

### Purpose
Provides heap block navigation and anchoring capabilities for the agentic loop to maintain state across iterations without losing context or requiring full reprocessing.

### Core Components

#### `PointerNode`
Represents individual heap blocks with properties:
- `block_id`: Unique identifier for the block
- `previous_block_id`: Backward navigation reference
- `next_block_id`: Forward continuation reference
- `refines_block_id`: Back-refinement target
- `resume_from_block_id`: Continuation anchor after rewrite operations

#### `PointerGraph`
A directed graph maintaining heap execution history:
- `nodes`: Dictionary mapping block IDs to `PointerNode` instances
- `latest_block_id`: Tracks the most recent block in the sequence
- Navigation methods: `has_previous()`, `has_next()`, `has_refines()`

#### `ResumeContext`
Tracks continuation state after rewrite/back-refinement operations:
- `resume_from_block_id`: Anchor point for resuming execution
- `latest_block_id`: Current latest block identifier
- `continuation_required`: Boolean flag indicating if reprocessing is needed

#### `RevisionPointer`
Revision-level context with anchor information:
- Block identifiers and pointer navigation fields
- Closure and quorum state (`closure_evidence_block_id`, `soft_lock_state`)
- Pointer action types and exit decisions
- Continuation flags and product blocked reasons

### Navigation Functions
- `get_previous_block_id()`, `get_next_block_id()`, `get_refines_block_id()`, `get_resume_from_block_id()`
- `has_previous()`, `has_next()`, `has_refines()`
- `resume_anchor()`: Returns the resume anchor block ID for continuation after rewrite
- `can_resume_forward()`: Determines if the loop can continue forward without reprocessing

### Integration Points
- **`agentic_loop_client_mcp_server.py`**: Imports pointer memory modules with fallback handling to enable dedicated broker navigation during agentic loop execution
- **Heap Startup Phase**: The loop builds a `ResumeContext` from revision pointers to determine continuation requirements

---

## 2. Chunk Management Module (`chunk_management.py`)

### Purpose
Enables dynamic chunk reconstruction and concatenation following the "chunk + chunk = testo completo" principle for complete text recovery from semantic fragments.

### Core Components

#### `CodeChunk`
Represents semantic code chunks with:
- `chunk_id`, `path`, `symbol`: Identification fields
- `line_start`, `line_end`: Line range for reconstruction
- `domain`, `risk`, `risk_signals`: Domain and metadata classification
- `compatibility_notes`, `dependencies`, `blender_api`: Compatibility and dependency tracking
- `summary_short`, `content_preview`, `do_not_change`: Content and summary fields
- `sha256`, `score`, `matched_terms`: Hash and scoring information

#### `EvidenceChunk`
Tracks evidence with status flags:
- `passed`, `effective_passed`, `degraded`, `hard_failed`: Status indicators
- `useful_artifact_paths`: Paths to useful artifacts
- `summary_short`, `content_preview`: Metadata fields

#### `ProposalChunk`
Manages proposals with:
- `block_id`, `proposal_block_id`, `previous_block_id`, `refines_block_id`, `resume_from_block_id`: Block identifiers for pointer graph integration
- `quality_passed`, `exit_decision`, `pointer_action`: Content and status fields
- `target_files`: List of target files for the proposal

### Sequence Building & Concatenation Functions

#### Build Sequences
- `build_code_chunk_sequence()`: Converts dictionary data to typed code chunk objects
- `build_evidence_chunk_sequence()`: Converts command data to evidence chunk sequences
- `build_proposal_chunk_sequence()`: Builds proposal chunk sequences from dictionary data

#### Concatenation Functions
- `concat_code_chunks()`: Reconstructs complete text from code chunks grouped by path and sorted by line range
- `concat_evidence_chunks()`: Forms complete evidence summary with passed/failed counts
- `concat_proposal_chunks()`: Forms complete proposal text with status, exit decision, and pointer action

#### Merge Functions
- `merge_code_chunks()`, `merge_evidence_chunks()`, `merge_proposal_chunks()`: Unify multiple chunks into single representations

### Integration Points
- **`agentic_loop_client_mcp_server.py`**: Imports chunk management modules for proposal and evidence concatenation during agentic loop execution
- **`rag_mcp_server.py`**: Uses chunk management modules to build and update the SQLite/FTS5 index with semantic code chunks, evidence chunks, and proposal chunks

---

## 3. Agent Memory Models Module (`agent_memory_models.py`)

### Purpose
Provides memory record management and agent micro task representation for state packet generation within the agentic loop infrastructure.

### Core Components

#### `MemoryRecord`
Stores generic memory items with:
- `record_id`, `kind`, `scope`, `source`: Identification fields
- `summary`, `content`: Memory content fields
- `tags`, `confidence`: Classification and trust indicators
- `created_at`, `updated_at`, `expires_at`: Temporal metadata
- `metadata`: Additional contextual information

#### `AgentMicroTask`
Represents planned units of work with:
- `task_id`, `title`, `lane`, `purpose`: Task identification and classification
- `priority`, `blocking`, `status`: Execution state fields
- `inputs`, `expected_outputs`, `depends_on`: Dependency tracking
- `metadata`: Additional contextual information

### State Packet Generation

#### `build_state_packet()`
Creates compact agent state packets from memory records:
- Sorts records by confidence (descending)
- Limits to `max_memory_chars` total size
- Returns structured packet with:
  - `objective`: Task objective
  - `query`: Search query
  - `records_count`: Number of records included
  - `packet_content`: Concatenated memory content
  - `max_memory_chars`: Size limit applied

### Common Helper Utilities
- `utc_now_iso()`, `sha256_text()`, `clamp_confidence()`, `stable_tag_tuple()`
- `compact_text()`, `slugify()`, `keywords()`, `read_text()`
- `relative_path()`, `resolve_repo_path()`, `is_under()`, `read_arg_file()`
- `safe_identifier()`, `split_csv_values()`

### Integration Points
- **`project_memory_mcp_server.py`**: Extends with agent memory models support for project-local persistent memory operations and state packet generation

---

## 4. How It Works Together in the Agentic Loop

### Startup Phase
1. The loop builds a `ResumeContext` from revision pointers to determine if continuation is required or if it can resume forward from a specific block
2. `PointerGraph` navigation functions (`has_previous()`, `has_next()`, `has_refines()`) check available navigation capabilities

### Evidence Collection Phase
1. As the loop executes tools, evidence chunks are created with status flags (passed/effective_passed/degraded/hard_failed) and useful artifact paths
2. `concat_evidence_chunks()` forms complete evidence summaries with passed/failed counts for downstream processing

### Proposal Generation Phase
1. Proposal chunks track `quality_passed` status, `exit_decision` (PATCHABLE_TARGET/BLOCKED), and `pointer_action` (RESUME_FORWARD)
2. `concat_proposal_chunks()` forms the final proposals heap with status, exit decision, and target files

### Memory State Packet Generation
1. `MemoryRecord` and `AgentMicroTask` instances are compiled into state packets via `build_state_packet()`
2. Packets provide compact context for the planner/validator cycle with confidence-sorted records limited to `max_memory_chars`

### RAG Index Updates
1. The RAG server uses chunk management modules to build and update the SQLite/FTS5 index
2. Semantic code chunks, evidence chunks, and proposal chunks are indexed for retrieval-augmented generation queries

---

## 5. Benefits Obtained from Integration

### 1. Context Preservation Across Iterations
- **Before**: Agentic loops lost context between iterations, requiring full reprocessing of previous blocks
- **After**: `ResumeContext` and `RevisionPointer` maintain state across iterations via block identifiers and navigation fields

### 2. Efficient Heap Block Navigation
- **Before**: Linear scanning of execution history to find previous/next/refines blocks
- **After**: `PointerGraph` provides O(1) node retrieval and efficient navigation checks via `has_previous()`, `has_next()`, `has_refines()`

### 3. Dynamic Chunk Reconstruction
- **Before**: Incomplete text fragments required manual concatenation or full file reads
- **After**: `concat_code_chunks()`, `concat_evidence_chunks()`, `concat_proposal_chunks()` reconstruct complete text using the "chunk + chunk = testo completo" principle

### 4. Compact State Packet Generation
- **Before**: Large memory records sent to downstream MCP servers, exceeding context limits
- **After**: `build_state_packet()` sorts by confidence and limits to `max_memory_chars`, providing compact context for planner/validator cycles

### 5. Graceful Degradation via Fallback Handling
- **Before**: Missing modules caused import failures and loop termination
- **After**: Try-except import blocks in MCP servers set modules to `None` with fallback handling, ensuring continuous operation

### 6. Unified Chunk Management Across Servers
- **Before**: Chunk management logic duplicated across different server implementations
- **After**: Centralized `chunk_management.py` used by `agentic_loop_client_mcp_server.py`, `project_memory_mcp_server.py`, and `rag_mcp_server.py`

---

## 6. Testing and Validation

All integration tests pass successfully:

```
(.venv-py147) PS C:\Users\someo\agentic-tool-loop> python services/codex_bridge/tests/test_pointer_memory.py     
..................
----------------------------------------------------------------------
Ran 18 tests in 0.001s

OK

(.venv-py147) PS C:\Users\someo\agentic-tool-loop> python services/codex_bridge/tests/test_chunk_management.py   
............
----------------------------------------------------------------------
Ran 12 tests in 0.002s

OK

(.venv-py147) PS C:\Users\someo\agentic-tool-loop> python services/codex_bridge/tests/test_agent_memory_models.py
.....
----------------------------------------------------------------------
Ran 5 tests in 0.001s

OK
```

---

## 7. File Locations Summary

### Core Modules
- `services/codex_bridge/pointer_memory.py` - Pointer memory and navigation functions
- `services/codex_bridge/chunk_management.py` - Chunk management and concatenation functions
- `services/codex_bridge/agent_memory_models.py` - Memory records, micro tasks, and state packet generation

### Modified MCP Servers
- `services/codex_bridge/agentic_loop_client_mcp_server.py` - Integrated pointer memory and chunk management
- `services/codex_bridge/project_memory_mcp_server.py` - Extended with agent memory models support
- `services/codex_bridge/rag_mcp_server.py` - Integrated chunk management for RAG index building

### Test Files
- `services/codex_bridge/tests/test_pointer_memory.py` - Pointer memory unit tests
- `services/codex_bridge/tests/test_chunk_management.py` - Chunk management unit tests
- `services/codex_bridge/tests/test_agent_memory_models.py` - Agent memory models unit tests

---

## 8. Removal Notes

**Removed File:**
- `services/codex_bridge/context_reload_utils.py` - Deleted as requested (too tied to the old repository structure)

The implementation consolidates all pointer memory, chunk management, and agent memory models functionality into the `services/codex_bridge/` directory, which is the correct location for the agentic loop MCP server infrastructure within the aicarmine ecosystem.