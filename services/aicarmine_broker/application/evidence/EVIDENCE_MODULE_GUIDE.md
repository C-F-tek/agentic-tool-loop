# Evidence Module - AICarmine Broker

## Overview

The `application/evidence/` package implements the evidence collection, verification, and working-set management for the AICarmine broker agentic loop. It ensures that all tool results include real useful output (not just metadata) and maintains the evidence contract for finalization gates.

## Components

### Evidence Builder (`builder.py`)

Collects concrete file/diff/text windows with offsets, chars and hashes from successful tool calls. It rehydrates same-job artifacts through injected helpers and stores oversized windows through prompt-window storage.

- Reads: planner history, evidence contract, file memory
- Writes: no files directly; uses injected storage callbacks
- Risk: must never replace required text/diff evidence with path-only metadata

### Required Working Set (`required_working_set.py`)

Collects concrete file, diff and tool-result windows needed for the next planner decision. Rehydrates same-job repo-read/code-product artifacts through injected helpers.

- Reads: planner history, evidence contract, file memory
- Writes: prompt-window documents via injected storage only
- Risk: must never replace required text/diff evidence with path-only metadata

### Repo Path Policy (`repo_path_policy.py`)

Determines which repository paths are valid for evidence collection and validates that all tool results include real useful output.

- Reads: repo status, file existence checks
- Writes: none (read-only policy)

### Goal Scope & Classifier (`goal_scope.py`, `goal_classifier.py`)

Classifies the intent of user requests into file-specific vs generic analysis. Detects when agentic flow is needed versus direct tool calls.

- Reads: public request payload, task text
- Writes: classification result for routing decisions

### Initial Orientation (`initial_orientation.py`)

Provides deterministic initial repo orientation before the first planner turn. Collects basic repository structure and hints for subsequent evidence gathering.

- Reads: repo status, file listing
- Writes: no files; returns orientation metadata

### Core Discovery (`core_discovery.py`)

Discovers core repository patterns, import relationships and module boundaries. Used to build understanding of codebase architecture before planning.

- Reads: file contents, import statements
- Writes: pattern analysis results

## Evidence Contract Rules

1. **Real output requirement**: All tool results must include actual useful content (stdout, file diffs, structured data), not just metadata or paths.

2. **Code-product completeness**: Code-product results must include the full diff/operations inline, not only previews or summaries.

3. **Working-set entries**: Must include concrete text/diff windows with offsets, chars and hashes - not just artifact paths.

4. **No path-only fallbacks**: Evidence must never be replaced by path-only metadata when real content exists.

## Verification

- Check that tool results contain `content`, `entries`, `paths`, `stdout`, `stderr` or complete `unified_diff`
- Verify code-product jobs show `repo_read -> repo_propose_code_edit -> final` flow
- Confirm working-set entries include offsets and hashes, not just paths