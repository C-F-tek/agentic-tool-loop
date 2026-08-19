"""IA-Carmine pointer memory for heap block navigation and anchoring."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PointerNode:
    """A node in the pointer graph representing a heap block or proposal chunk."""
    
    block_id: str = ""
    previous_block_id: str = ""
    next_block_id: str = ""
    refines_block_id: str = ""
    resume_from_block_id: str = ""
    
    # Pointer action and decision metadata
    pointer_action: str = ""
    exit_decision: str = ""
    quality_passed: bool = False
    
    # Role and classification
    role: str = ""
    block_type: str = ""
    
    # Target files and evidence
    target_files: list[str] = field(default_factory=list)
    proposal_block_id: str = ""
    
    def get_previous(self) -> str:
        """Return the previous block ID for backward navigation."""
        return self.previous_block_id or ""
    
    def get_next(self) -> str:
        """Return the next block ID for forward continuation."""
        return self.next_block_id or ""
    
    def get_refines(self) -> str:
        """Return the refines block ID for back-refinement."""
        return self.refines_block_id or ""
    
    def get_resume_from(self) -> str:
        """Return the resume from block ID for continuation after rewrite."""
        return self.resume_from_block_id or self.block_id or ""


@dataclass
class PointerGraph:
    """A directed graph of pointer nodes representing heap execution history."""
    
    nodes: dict[str, PointerNode] = field(default_factory=dict)
    latest_block_id: str = ""
    proposal_block_id: str = ""
    
    def add_node(self, node: PointerNode) -> None:
        """Add a node to the pointer graph."""
        if node.block_id:
            self.nodes[node.block_id] = node
            self.latest_block_id = node.block_id
    
    def get_node(self, block_id: str) -> PointerNode | None:
        """Retrieve a node by its block ID."""
        return self.nodes.get(block_id)
    
    def has_previous(self, block_id: str) -> bool:
        """Check if the block has a previous block in the graph."""
        node = self.get_node(block_id)
        if not node:
            return False
        prev_id = node.get_previous()
        return bool(prev_id and (prev_id in self.nodes or prev_id == "previous_block_id"))
    
    def get_previous_node(self, block_id: str) -> PointerNode | None:
        """Get the previous node in the graph."""
        node = self.get_node(block_id)
        if not node:
            return None
        prev_id = node.get_previous()
        if not prev_id:
            return None
        return self.get_node(prev_id)
    
    def has_next(self, block_id: str) -> bool:
        """Check if the block has a next block in the graph."""
        node = self.get_node(block_id)
        if not node:
            return False
        next_id = node.get_next()
        return bool(next_id and (next_id in self.nodes or next_id == "next_block_id"))
    
    def get_next_node(self, block_id: str) -> PointerNode | None:
        """Get the next node in the graph."""
        node = self.get_node(block_id)
        if not node:
            return None
        next_id = node.get_next()
        if not next_id:
            return None
        return self.get_node(next_id)
    
    def has_refines(self, block_id: str) -> bool:
        """Check if the block has a refines target."""
        node = self.get_node(block_id)
        if not node:
            return False
        refines_id = node.get_refines()
        return bool(refines_id and (refines_id in self.nodes or refines_id == "refines_block_id"))
    
    def get_refines_node(self, block_id: str) -> PointerNode | None:
        """Get the node that this block refines."""
        node = self.get_node(block_id)
        if not node:
            return None
        refines_id = node.get_refines()
        if not refines_id:
            return None
        return self.get_node(refines_id)
    
    def get_resume_anchor(self, block_id: str) -> str:
        """Get the resume anchor block ID for continuation after rewrite."""
        node = self.get_node(block_id)
        if not node:
            return ""
        return node.get_resume_from()


@dataclass
class ResumeContext:
    """Context for resuming heap execution after a rewrite or back-refinement."""
    
    resume_from_block_id: str = ""
    latest_block_id: str = ""
    proposal_block_id: str = ""
    
    # Pointer closure and quorum state
    closure_evidence_block_id: str = ""
    soft_lock_state: str = ""
    
    # Continuation flags
    continuation_required: bool = False
    product_blocked_reason: str = ""
    
    def get_resume_anchor(self) -> str:
        """Return the resume anchor block ID."""
        return self.resume_from_block_id or self.latest_block_id or self.proposal_block_id or ""
    
    def can_resume_forward(self) -> bool:
        """Check if forward continuation is possible from this context."""
        if not self.resume_from_block_id and not self.latest_block_id:
            return False
        if self.continuation_required and not self.product_blocked_reason:
            return True
        return bool(self.resume_from_block_id or self.latest_block_id)


@dataclass
class RevisionPointer:
    """Revision pointer context with anchor information for heap blocks."""
    
    # Block identifiers
    block_id: str = ""
    proposal_block_id: str = ""
    latest_block_id: str = ""
    
    # Pointer navigation fields
    previous_block_id: str = ""
    next_block_id: str = ""
    refines_block_id: str = ""
    resume_from_block_id: str = ""
    
    # Closure and quorum state
    closure_evidence_block_id: str = ""
    soft_lock_state: str = ""
    
    # Pointer action and decisions
    pointer_action: str = ""
    exit_decision: str = ""
    quality_passed: bool = False
    
    # Continuation flags
    continuation_required: bool = False
    product_blocked_reason: str = ""
    
    def get_anchor_block_id(self) -> str:
        """Return the primary anchor block ID for this revision."""
        return self.block_id or self.proposal_block_id or ""
    
    def get_resume_anchor(self) -> str:
        """Return the resume anchor block ID for continuation after rewrite."""
        return self.resume_from_block_id or self.latest_block_id or self.proposal_block_id or ""
    
    def has_backward_pointer(self) -> bool:
        """Check if this revision has a backward pointer (previous or refines)."""
        return bool(self.previous_block_id or self.refines_block_id)
    
    def has_forward_pointer(self) -> bool:
        """Check if this revision has a forward pointer (next or resume_from)."""
        return bool(self.next_block_id or self.resume_from_block_id)
    
    def get_pointer_action_type(self) -> str:
        """Return the type of pointer action for this revision."""
        action = self.pointer_action.upper() if self.pointer_action else ""
        if action in ("PROPOSE", "EVIDENCE"):
            return "STAY_FORWARD"
        elif action in ("REFINE", "AUDIT"):
            return "BACKTRACK_PROPAGATE"
        elif action == "RESUME_FORWARD":
            return "RESUME_FORWARD"
        return action or "UNKNOWN"


def get_previous_block_id(node: PointerNode | dict[str, Any]) -> str:
    """Extract previous block ID from a pointer node or dictionary."""
    if isinstance(node, dict):
        return str(node.get("previous_block_id") or "")
    return node.get_previous() if hasattr(node, 'get_previous') else ""


def get_next_block_id(node: PointerNode | dict[str, Any]) -> str:
    """Extract next block ID from a pointer node or dictionary."""
    if isinstance(node, dict):
        return str(node.get("next_block_id") or "")
    return node.get_next() if hasattr(node, 'get_next') else ""


def get_refines_block_id(node: PointerNode | dict[str, Any]) -> str:
    """Extract refines block ID from a pointer node or dictionary."""
    if isinstance(node, dict):
        return str(node.get("refines_block_id") or "")
    return node.get_refines() if hasattr(node, 'get_refines') else ""


def get_resume_from_block_id(node: PointerNode | dict[str, Any]) -> str:
    """Extract resume from block ID from a pointer node or dictionary."""
    if isinstance(node, dict):
        return str(node.get("resume_from_block_id") or "")
    return node.get_resume_from() if hasattr(node, 'get_resume_from') else ""


def has_previous(block_id: str, graph: PointerGraph) -> bool:
    """Check if a block has a previous block in the pointer graph."""
    return graph.has_previous(block_id)


def has_next(block_id: str, graph: PointerGraph) -> bool:
    """Check if a block has a next block in the pointer graph."""
    return graph.has_next(block_id)


def has_refines(block_id: str, graph: PointerGraph) -> bool:
    """Check if a block has a refines target in the pointer graph."""
    return graph.has_refines(block_id)


def resume_anchor(
    revision_context: dict[str, Any],
    latest_report: dict[str, Any] | None = None,
) -> str:
    """Extract the resume anchor block ID from revision context or latest report."""
    if latest_report:
        resume_from = str(latest_report.get("resume_from_block_id") or "")
        if resume_from:
            return resume_from
    
    # Fallback to revision context
    resume_from = str(revision_context.get("resume_from_block_id") or "")
    if resume_from:
        return resume_from
    
    latest_id = str(revision_context.get("latest_block_id") or "")
    proposal_id = str(revision_context.get("proposal_block_id") or "")
    
    return resume_from or latest_id or proposal_id or ""


def can_resume_forward(
    context: ResumeContext | dict[str, Any],
) -> bool:
    """Check if forward continuation is possible from the given context."""
    if isinstance(context, dict):
        resume_from = str(context.get("resume_from_block_id") or "")
        latest_id = str(context.get("latest_block_id") or "")
        continuation_required = bool(context.get("continuation_required"))
        product_blocked_reason = str(context.get("product_blocked_reason") or "")
        
        if not resume_from and not latest_id:
            return False
        if continuation_required and not product_blocked_reason:
            return True
        return bool(resume_from or latest_id)
    
    return context.can_resume_forward() if hasattr(context, 'can_resume_forward') else False


def build_resume_context(
    revision_context: dict[str, Any],
    latest_report: dict[str, Any] | None = None,
) -> ResumeContext:
    """Build a ResumeContext from revision context and latest report data."""
    resume_from_block_id = str(revision_context.get("resume_from_block_id") or "")
    if not resume_from_block_id and latest_report:
        resume_from_block_id = str(latest_report.get("resume_from_block_id") or "")
    
    latest_block_id = str(revision_context.get("latest_block_id") or "")
    if not latest_block_id and latest_report:
        latest_block_id = str(latest_report.get("latest_block_id") or "")
    
    proposal_block_id = str(revision_context.get("proposal_block_id") or "")
    
    closure_evidence_block_id = str(revision_context.get("closure_evidence_block_id") or "")
    if not closure_evidence_block_id and latest_report:
        closure_evidence_block_id = str(latest_report.get("closure_evidence_block_id") or "")
    
    soft_lock_state = str(revision_context.get("soft_lock_state") or "")
    continuation_required = bool(revision_context.get("continuation_required"))
    product_blocked_reason = str(revision_context.get("product_blocked_reason") or "")
    
    return ResumeContext(
        resume_from_block_id=resume_from_block_id,
        latest_block_id=latest_block_id,
        proposal_block_id=proposal_block_id,
        closure_evidence_block_id=closure_evidence_block_id,
        soft_lock_state=soft_lock_state,
        continuation_required=continuation_required,
        product_blocked_reason=product_blocked_reason,
    )


def build_revision_pointer(
    revision_context: dict[str, Any],
    latest_report: dict[str, Any] | None = None,
) -> RevisionPointer:
    """Build a RevisionPointer from revision context and optional latest report."""
    block_id = str(revision_context.get("block_id") or "")
    proposal_block_id = str(revision_context.get("proposal_block_id") or "")
    latest_block_id = str(revision_context.get("latest_block_id") or "")
    
    previous_block_id = str(revision_context.get("previous_block_id") or "")
    next_block_id = str(revision_context.get("next_block_id") or "")
    refines_block_id = str(revision_context.get("refines_block_id") or "")
    resume_from_block_id = str(revision_context.get("resume_from_block_id") or "")
    
    closure_evidence_block_id = str(revision_context.get("closure_evidence_block_id") or "")
    soft_lock_state = str(revision_context.get("soft_lock_state") or "")
    
    pointer_action = str(revision_context.get("pointer_action") or "")
    exit_decision = str(revision_context.get("exit_decision") or "")
    quality_passed = bool(revision_context.get("quality_passed")) if "quality_passed" in revision_context else False
    
    continuation_required = bool(revision_context.get("continuation_required"))
    product_blocked_reason = str(revision_context.get("product_blocked_reason") or "")
    
    # Fallback to latest report if available
    if latest_report:
        if not block_id:
            block_id = str(latest_report.get("block_id") or "")
        if not proposal_block_id:
            proposal_block_id = str(latest_report.get("proposal_block_id") or "")
        if not latest_block_id:
            latest_block_id = str(latest_report.get("latest_block_id") or "")
        if not previous_block_id:
            previous_block_id = str(latest_report.get("previous_block_id") or "")
        if not next_block_id:
            next_block_id = str(latest_report.get("next_block_id") or "")
        if not refines_block_id:
            refines_block_id = str(latest_report.get("refines_block_id") or "")
        if not resume_from_block_id:
            resume_from_block_id = str(latest_report.get("resume_from_block_id") or "")
        if not closure_evidence_block_id:
            closure_evidence_block_id = str(latest_report.get("closure_evidence_block_id") or "")
        if not soft_lock_state:
            soft_lock_state = str(latest_report.get("soft_lock_state") or "")
        if not pointer_action:
            pointer_action = str(latest_report.get("pointer_action") or "")
        if not exit_decision:
            exit_decision = str(latest_report.get("exit_decision") or "")
    
    return RevisionPointer(
        block_id=block_id,
        proposal_block_id=proposal_block_id,
        latest_block_id=latest_block_id,
        previous_block_id=previous_block_id,
        next_block_id=next_block_id,
        refines_block_id=refines_block_id,
        resume_from_block_id=resume_from_block_id,
        closure_evidence_block_id=closure_evidence_block_id,
        soft_lock_state=soft_lock_state,
        pointer_action=pointer_action,
        exit_decision=exit_decision,
        quality_passed=quality_passed,
        continuation_required=continuation_required,
        product_blocked_reason=product_blocked_reason,
    )


def extract_pointer_fields(revision_context: dict[str, Any]) -> dict[str, str]:
    """Extract pointer navigation fields from a revision context dictionary."""
    return {
        "previous_block_id": str(revision_context.get("previous_block_id") or ""),
        "next_block_id": str(revision_context.get("next_block_id") or ""),
        "refines_block_id": str(revision_context.get("refines_block_id") or ""),
        "resume_from_block_id": str(revision_context.get("resume_from_block_id") or ""),
        "proposal_block_id": str(revision_context.get("proposal_block_id") or ""),
        "latest_block_id": str(revision_context.get("latest_block_id") or ""),
    }


def build_pointer_contract(
    revision_pointer: RevisionPointer | dict[str, Any],
) -> dict[str, Any]:
    """Build a pointer contract dictionary from a RevisionPointer or context."""
    if isinstance(revision_pointer, dict):
        resume_from = str(revision_pointer.get("resume_from_block_id") or "")
        latest_id = str(revision_pointer.get("latest_block_id") or "")
        proposal_id = str(revision_pointer.get("proposal_block_id") or "")
        
        return {
            "product_contract": True,
            "decision_recovery": True,
            "navigation_role": "provider_evidence_chain",
            "closure_owner": bool(resume_from or latest_id),
            "primary_closer": bool(proposal_id),
            "sidecar_evidence": False,
            "can_continue_to_next": bool(latest_id or resume_from),
            "can_backrefine": bool(revision_pointer.get("previous_block_id") or revision_pointer.get("refines_block_id")),
            "requires_review": True,
        }
    
    return {
        "product_contract": True,
        "decision_recovery": True,
        "navigation_role": "provider_evidence_chain",
        "closure_owner": bool(revision_pointer.resume_from_block_id or revision_pointer.latest_block_id),
        "primary_closer": bool(revision_pointer.proposal_block_id),
        "sidecar_evidence": False,
        "can_continue_to_next": bool(revision_pointer.latest_block_id or revision_pointer.resume_from_block_id),
        "can_backrefine": bool(revision_pointer.previous_block_id or revision_pointer.refines_block_id),
        "requires_review": True,
    }


__all__ = [
    # From graph module
    "PointerGraph",
    "PointerNode",
    "get_previous_block_id",
    "get_next_block_id",
    "get_refines_block_id",
    "get_resume_from_block_id",
    "has_previous",
    "has_next",
    "has_refines",
    # From resume module
    "ResumeContext",
    "resume_anchor",
    "can_resume_forward",
    "build_resume_context",
    # From revision_context module
    "RevisionPointer",
    "build_revision_pointer",
    "extract_pointer_fields",
    "build_pointer_contract",
]