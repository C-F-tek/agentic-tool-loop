"""IA-Carmine chunk management with dynamic reconstruction capabilities."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CodeChunk:
    """A semantic code chunk with navigation and concatenation support."""
    
    chunk_id: str = ""
    path: str = ""
    symbol: str = ""
    kind: str = "semantic_code_chunk"
    
    # Line range for reconstruction
    line_start: int = 1
    line_end: int = -1
    
    # Domain and metadata
    domain: list[str] = field(default_factory=lambda: ["code_chunks"])
    risk: str = "low"
    risk_signals: list[str] = field(default_factory=list)
    
    # Compatibility and dependencies
    compatibility_notes: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    blender_api: list[str] = field(default_factory=list)
    
    # Content and summary
    summary_short: str = ""
    content_preview: str = ""
    do_not_change: bool = False
    
    # Hash and scoring
    sha256: str = ""
    score: int = 0
    matched_terms: list[str] = field(default_factory=list)
    
    def get_previous_chunk_id(self) -> str:
        """Return the previous chunk ID for sequential reconstruction."""
        return f"{self.chunk_id}:prev" if self.line_start > 1 else ""
    
    def get_next_chunk_id(self) -> str:
        """Return the next chunk ID for sequential reconstruction."""
        return f"{self.chunk_id}:next" if self.line_end < -1 or self.line_end > 0 else ""
    
    def can_concat_with(self, other: 'CodeChunk') -> bool:
        """Check if this chunk can be concatenated with another code chunk."""
        if self.path != other.path:
            return False
        # Check line continuity
        if other.line_start == self.line_end + 1 or other.line_start == self.line_end:
            return True
        return False


@dataclass
class EvidenceChunk:
    """An evidence chunk with navigation and concatenation support."""
    
    chunk_id: str = ""
    name: str = ""
    requirement: str = ""
    kind: str = "semantic_evidence_chunk"
    
    # Status flags
    passed: bool = False
    effective_passed: bool = False
    degraded: bool = False
    hard_failed: bool = False
    
    # Artifact paths
    useful_artifact_paths: list[str] = field(default_factory=list)
    
    # Metadata
    summary_short: str = ""
    content_preview: str = ""
    
    def get_previous_evidence_chunk_id(self) -> str:
        """Return the previous evidence chunk ID for sequential reconstruction."""
        return f"{self.chunk_id}:prev" if self.requirement else ""
    
    def get_next_evidence_chunk_id(self) -> str:
        """Return the next evidence chunk ID for sequential reconstruction."""
        return f"{self.chunk_id}:next" if self.effective_passed else ""
    
    def can_concat_with(self, other: 'EvidenceChunk') -> bool:
        """Check if this chunk can be concatenated with another evidence chunk."""
        # Evidence chunks from same requirement or related tools can be concatenated
        return True


@dataclass
class ProposalChunk:
    """A proposal chunk with navigation and concatenation support."""
    
    chunk_id: str = ""
    name: str = ""
    kind: str = "proposal_chunk"
    
    # Block identifiers for pointer graph integration
    block_id: str = ""
    proposal_block_id: str = ""
    previous_block_id: str = ""
    refines_block_id: str = ""
    resume_from_block_id: str = ""
    
    # Content and status
    quality_passed: bool = False
    exit_decision: str = ""
    pointer_action: str = ""
    
    # Target files
    target_files: list[str] = field(default_factory=list)
    
    # Metadata
    summary_short: str = ""
    content_preview: str = ""
    
    def get_previous_proposal_chunk_id(self) -> str:
        """Return the previous proposal chunk ID for sequential reconstruction."""
        return self.previous_block_id or f"{self.chunk_id}:prev"
    
    def get_next_proposal_chunk_id(self) -> str:
        """Return the next proposal chunk ID for sequential reconstruction."""
        return self.resume_from_block_id or f"{self.chunk_id}:next"
    
    def can_concat_with(self, other: 'ProposalChunk') -> bool:
        """Check if this chunk can be concatenated with another proposal chunk."""
        # Proposal chunks from same revision or related blocks can be concatenated
        if self.proposal_block_id and self.proposal_block_id == other.proposal_block_id:
            return True
        return False


def build_code_chunk_sequence(
    chunks: list[dict[str, Any] | CodeChunk],
) -> list[CodeChunk]:
    """Build a sequence of code chunks from dictionary data."""
    result = []
    for item in chunks:
        if isinstance(item, dict):
            chunk = CodeChunk(
                chunk_id=item.get("chunk_id", ""),
                path=item.get("path", ""),
                symbol=item.get("symbol", ""),
                kind=item.get("kind", "semantic_code_chunk"),
                line_start=int(item.get("line_start", 1)),
                line_end=int(item.get("line_end", -1)),
                domain=item.get("domain", ["code_chunks"]),
                risk=str(item.get("risk", "low")),
                risk_signals=item.get("risk_signals", []),
                compatibility_notes=item.get("compatibility_notes", []),
                dependencies=item.get("dependencies", []),
                blender_api=item.get("blender_api", []),
                summary_short=str(item.get("summary_short", "")),
                content_preview=str(item.get("content_preview", "")),
                do_not_change=bool(item.get("do_not_change", False)),
                sha256=str(item.get("sha256", "")),
                score=int(item.get("score", 0)),
                matched_terms=item.get("matched_terms", []),
            )
        else:
            chunk = item
        result.append(chunk)
    return result


def concat_code_chunks(chunks: list[CodeChunk | dict[str, Any]]) -> str:
    """Concatenate code chunks to form complete text (chunk + chunk = testo completo)."""
    sorted_chunks = sorted(
        [c if isinstance(c, CodeChunk) else CodeChunk(**c) for c in chunks],
        key=lambda c: (c.path, c.line_start),
    )
    
    # Group by path and sort by line range
    by_path: dict[str, list[CodeChunk]] = {}
    for chunk in sorted_chunks:
        if chunk.path not in by_path:
            by_path[chunk.path] = []
        by_path[chunk.path].append(chunk)
    
    # Concatenate chunks for each path
    full_text_parts: dict[str, str] = {}
    for path, path_chunks in by_path.items():
        path_chunks.sort(key=lambda c: c.line_start if c.line_start > 0 else 999999)
        
        # Reconstruct complete text from chunks
        reconstructed_lines: list[str] = []
        for chunk in path_chunks:
            preview = str(chunk.content_preview or "")
            if preview:
                lines = preview.splitlines()
                reconstructed_lines.extend(lines)
        
        full_text_parts[path] = "\n".join(reconstructed_lines)
    
    # Return concatenated result
    return "\n\n--- SEPARATED BY PATH ---\n\n".join(
        [f"## {path}\n{text}" for path, text in full_text_parts.items()]
    )


def merge_code_chunks(chunks: list[CodeChunk | dict[str, Any]]) -> CodeChunk:
    """Merge multiple code chunks into a single unified chunk representation."""
    if not chunks:
        return CodeChunk()
    
    # Get first chunk as base
    base = chunks[0] if isinstance(chunks[0], CodeChunk) else CodeChunk(**chunks[0])
    
    # Aggregate metadata
    all_paths = set(str(c.path if isinstance(c, CodeChunk) else c.get("path", "")) for c in chunks)
    all_symbols = set(str(c.symbol if isinstance(c, CodeChunk) else c.get("symbol", "")) for c in chunks if getattr(c, 'symbol', None) or (isinstance(c, dict) and c.get('symbol')))
    
    merged = CodeChunk(
        chunk_id=f"merged_code_chunks:{len(chunks)}_chunks",
        path="/".join(list(all_paths)[:3]) if len(all_paths) <= 3 else f"{list(all_paths)[0]}+...",
        symbol=", ".join(list(all_symbols)[:3]) if all_symbols else "",
        kind="merged_semantic_code_chunks",
        line_start=min(getattr(c, 'line_start', 1) if isinstance(c, CodeChunk) else c.get('line_start', 1) for c in chunks),
        line_end=max(getattr(c, 'line_end', -1) if isinstance(c, CodeChunk) else c.get('line_end', -1) for c in chunks),
        domain=["merged_code_chunks"],
        risk="medium",
        compatibility_notes=["merged from multiple semantic code chunks"],
    )
    
    return merged


def build_evidence_chunk_sequence(
    commands: list[dict[str, Any] | EvidenceChunk],
) -> list[EvidenceChunk]:
    """Build a sequence of evidence chunks from command data."""
    result = []
    for item in commands:
        if isinstance(item, dict):
            chunk = EvidenceChunk(
                chunk_id=f"evidence:{item.get('name', '')}:{item.get('requirement', '')}",
                name=item.get("name", ""),
                requirement=item.get("requirement", ""),
                kind="semantic_evidence_chunk",
                passed=bool(item.get("passed", False)),
                effective_passed=bool(item.get("effective_passed", False)),
                degraded=bool(item.get("degraded", False)),
                hard_failed=bool(item.get("hard_failed", False)),
                useful_artifact_paths=item.get("useful_artifact_paths", []),
            )
        else:
            chunk = item
        result.append(chunk)
    return result


def concat_evidence_chunks(chunks: list[EvidenceChunk | dict[str, Any]]) -> str:
    """Concatenate evidence chunks to form complete evidence summary (chunk + chunk = testo completo)."""
    sorted_chunks = sorted(
        [c if isinstance(c, EvidenceChunk) else EvidenceChunk(**c) for c in chunks],
        key=lambda c: (c.requirement or "", c.name or ""),
    )
    
    # Build concatenated evidence summary
    lines = ["# Heap Startup Semantic Evidence Chunks", ""]
    passed_count = 0
    failed_count = 0
    
    for chunk in sorted_chunks:
        status = "passed" if chunk.effective_passed else ("degraded" if chunk.degraded else ("failed" if chunk.hard_failed else "unknown"))
        lines.append(
            f"- `{chunk.requirement}` name=`{chunk.name}` passed=`{chunk.passed}` "
            f"effective=`{chunk.effective_passed}` degraded=`{chunk.degraded}` status=`{status}`"
        )
        if chunk.effective_passed:
            passed_count += 1
        else:
            failed_count += 1
    
    lines.append("")
    lines.append(f"## Summary")
    lines.append(f"- Total evidence chunks: `{len(sorted_chunks)}`")
    lines.append(f"- Passed: `{passed_count}`")
    lines.append(f"- Failed/Degraded: `{failed_count}`")
    
    return "\n".join(lines) + "\n"


def merge_evidence_chunks(chunks: list[EvidenceChunk | dict[str, Any]]) -> EvidenceChunk:
    """Merge multiple evidence chunks into a single unified evidence representation."""
    if not chunks:
        return EvidenceChunk()
    
    # Aggregate status
    all_passed = all(getattr(c, 'effective_passed', True) if isinstance(c, EvidenceChunk) else c.get('effective_passed', False) for c in chunks)
    any_degraded = any(getattr(c, 'degraded', False) if isinstance(c, EvidenceChunk) else c.get('degraded', False) for c in chunks)
    
    merged = EvidenceChunk(
        chunk_id=f"merged_evidence_chunks:{len(chunks)}_chunks",
        name="unified_evidence_summary",
        requirement="startup_semantic_evidence_chunks",
        kind="merged_semantic_evidence_chunks",
        passed=all_passed,
        effective_passed=all_passed and not any_degraded,
        degraded=any_degraded,
        hard_failed=not all_passed,
        useful_artifact_paths=[
            str(getattr(c, 'useful_artifact_paths', []) if isinstance(c, EvidenceChunk) else c.get('useful_artifact_paths', []))
            for c in chunks
        ],
    )
    
    return merged


def build_proposal_chunk_sequence(
    proposals: list[dict[str, Any] | ProposalChunk],
) -> list[ProposalChunk]:
    """Build a sequence of proposal chunks from dictionary data."""
    result = []
    for item in proposals:
        if isinstance(item, dict):
            chunk = ProposalChunk(
                chunk_id=item.get("chunk_id", ""),
                name=item.get("name", ""),
                kind=item.get("kind", "proposal_chunk"),
                block_id=str(item.get("block_id", "")),
                proposal_block_id=str(item.get("proposal_block_id", "")),
                previous_block_id=str(item.get("previous_block_id", "")),
                refines_block_id=str(item.get("refines_block_id", "")),
                resume_from_block_id=str(item.get("resume_from_block_id", "")),
                quality_passed=bool(item.get("quality_passed", False)),
                exit_decision=str(item.get("exit_decision", "")),
                pointer_action=str(item.get("pointer_action", "")),
                target_files=item.get("target_files", []),
                summary_short=str(item.get("summary_short", "")),
                content_preview=str(item.get("content_preview", "")),
            )
        else:
            chunk = item
        result.append(chunk)
    return result


def concat_proposal_chunks(chunks: list[ProposalChunk | dict[str, Any]]) -> str:
    """Concatenate proposal chunks to form complete proposal text (chunk + chunk = testo completo)."""
    sorted_chunks = sorted(
        [c if isinstance(c, ProposalChunk) else ProposalChunk(**c) for c in chunks],
        key=lambda c: (c.proposal_block_id or "", c.name or ""),
    )
    
    # Build concatenated proposal summary
    lines = ["# Heap Final Proposals", ""]
    
    for chunk in sorted_chunks:
        status = "accepted" if chunk.quality_passed else "rejected"
        lines.append(f"## Proposal: `{chunk.name or chunk.proposal_block_id}`")
        lines.append(f"- Status: `{status}`")
        lines.append(f"- Exit decision: `{chunk.exit_decision}`")
        lines.append(f"- Pointer action: `{chunk.pointer_action}`")
        
        if chunk.target_files:
            lines.append("- Target files:")
            for tf in chunk.target_files:
                lines.append(f"  - `{tf}`")
        
        if chunk.content_preview:
            lines.extend(["", "```text", chunk.content_preview, "```"])
        
        lines.append("")
    
    return "\n".join(lines) + "\n"


def merge_proposal_chunks(chunks: list[ProposalChunk | dict[str, Any]]) -> ProposalChunk:
    """Merge multiple proposal chunks into a single unified proposal representation."""
    if not chunks:
        return ProposalChunk()
    
    # Aggregate metadata
    all_block_ids = set(str(c.block_id or c.proposal_block_id) for c in chunks if getattr(c, 'block_id', None) or (isinstance(c, dict) and c.get('block_id')))
    
    merged = ProposalChunk(
        chunk_id=f"merged_proposal_chunks:{len(chunks)}_chunks",
        name="unified_proposal_summary",
        kind="merged_semantic_proposal_chunks",
        proposal_block_id=list(all_block_ids)[0] if all_block_ids else "",
        quality_passed=all(getattr(c, 'quality_passed', False) for c in chunks),
        exit_decision="PATCHABLE_TARGET" if any(getattr(c, 'exit_decision', '') == "PATCHABLE_TARGET" for c in chunks) else "BLOCKED",
        pointer_action="RESUME_FORWARD",
        target_files=[str(c.target_files[0]) if getattr(c, 'target_files', None) and c.target_files else "" for c in chunks if getattr(c, 'target_files', None)],
    )
    
    return merged


__all__ = [
    # From code_chunks module
    "CodeChunk",
    "build_code_chunk_sequence",
    "concat_code_chunks",
    "merge_code_chunks",
    # From evidence_chunks module
    "EvidenceChunk",
    "build_evidence_chunk_sequence",
    "concat_evidence_chunks",
    "merge_evidence_chunks",
    # From proposal_chunks module
    "ProposalChunk",
    "build_proposal_chunk_sequence",
    "concat_proposal_chunks",
    "merge_proposal_chunks",
]