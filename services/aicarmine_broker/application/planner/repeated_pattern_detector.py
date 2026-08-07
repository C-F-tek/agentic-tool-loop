"""Detects repeated identical tool sequences in planner rejection cycles."""
from __future__ import annotations

from typing import Any


def _tool_sequence_key(sequence: list[str]) -> str:
    """Create a hashable key for a tool sequence."""
    return "|".join(sorted(sequence))


def _action_signature(action: dict[str, Any]) -> str:
    """Create a signature for an action decision."""
    tool = str(action.get("tool") or "").strip()
    action_type = str(action.get("action") or "").strip()
    return f"{action_type}:{tool}"


class RepeatedPatternDetector:
    """Core detection logic for repeated identical tool sequence patterns."""

    def __init__(self) -> None:
        self._rejection_history: list[dict[str, Any]] = []
        self._tool_sequences: list[list[str]] = []
        self._pattern_counts: dict[str, int] = {}
        self._last_sequence: list[str] | None = None
        self._consecutive_count: int = 0

    def track_decision(self, decision: dict[str, Any], tool_sequence: list[str]) -> dict[str, Any]:
        """Track a new decision with its associated tool sequence.
        
        Returns pattern info if a repeated pattern is detected.
        """
        sig = _action_signature(decision)
        seq_key = _tool_sequence_key(tool_sequence)
        
        self._rejection_history.append({
            "decision": decision,
            "tool_sequence": tool_sequence,
            "signature": sig,
        })
        
        self._tool_sequences.append(list(tool_sequence))
        
        # Check for repeated pattern
        self._pattern_counts[seq_key] = self._pattern_counts.get(seq_key, 0) + 1
        self._last_sequence = list(tool_sequence)
        
        count = self._pattern_counts[seq_key]
        
        # Determine if we should suggest alternatives
        should_suggest = count >= 2
        
        # Get alternative suggestions if needed
        alternatives = []
        if should_suggest:
            alternatives = self._generate_alternative_suggestions(tool_sequence)
        
        result = {
            "pattern_type": "identical_sequence" if count >= 2 else "single",
            "count": count,
            "sequence": tool_sequence,
            "signature": sig,
            "should_suggest_alternatives": should_suggest,
            "suggested_alternatives": alternatives,
        }
        
        return result

    def get_pattern_info(self) -> dict[str, Any]:
        """Return current pattern detection state."""
        most_common_seq = ""
        most_common_count = 0
        for seq_key, cnt in self._pattern_counts.items():
            if cnt > most_common_count:
                most_common_count = cnt
                most_common_seq = seq_key
        
        return {
            "consecutive_identical_count": self._consecutive_count,
            "total_rejections": len(self._rejection_history),
            "most_common_sequence": most_common_seq,
            "most_common_count": most_common_count,
            "pattern_counts": dict(self._pattern_counts),
            "last_sequence": self._last_sequence or [],
        }

    def should_suggest_alternatives(self) -> bool:
        """Check if we need to suggest different actions."""
        info = self.get_pattern_info()
        return info["most_common_count"] >= 2

    def get_alternative_suggestions(self) -> list[dict[str, Any]]:
        """Return suggested different actions based on current pattern."""
        if not self._last_sequence:
            return []
        
        return self._generate_alternative_suggestions(self._last_sequence)

    def _generate_alternative_suggestions(self, current_sequence: list[str]) -> list[dict[str, Any]]:
        """Generate alternative action suggestions that differ from current sequence."""
        # Define tool categories for diversification
        repo_tools = {"repo_list_files", "repo_read", "repo_search", "repo_semantic_search", 
                      "repo_propose_code_edit", "repo_apply_patch", "repo_command"}
        planning_tools = {"planner_scratchpad_write", "planner_scratchpad_read"}
        terminal_tools = {"terminal_run_command_wait"}
        
        # Find tools NOT in current sequence
        current_set = set(current_sequence)
        untried_categories = []
        
        if not repo_tools.issubset(current_set):
            untried_categories.append({
                "category": "repo_untried",
                "suggested_tools": [t for t in repo_tools if t not in current_set],
            })
        
        if not planning_tools.issubset(current_set):
            untried_categories.append({
                "category": "planning_primitives",
                "suggested_tools": [t for t in planning_tools if t not in current_set],
            })
        
        if not terminal_tools.issubset(current_set):
            untried_categories.append({
                "category": "terminal_commands",
                "suggested_tools": [t for t in terminal_tools if t not in current_set],
            })
        
        suggestions = []
        for cat in untried_categories:
            for tool in cat["suggested_tools"]:
                suggestions.append({
                    "tool": tool,
                    "reason": f"Different category from current sequence [{', '.join(current_sequence)}]; try {tool} instead.",
                    "category": cat["category"],
                })
        
        return suggestions

    def reset(self) -> None:
        """Reset detector state."""
        self._rejection_history = []
        self._tool_sequences = []
        self._pattern_counts = {}
        self._last_sequence = None
        self._consecutive_count = 0