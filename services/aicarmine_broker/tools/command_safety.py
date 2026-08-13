from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class CommandClassification:
    """Bounded classification result for a shell command."""
    command_class: str
    reason: str
    matched_pattern: str = ""
    consent_required: bool = False


_READONLY_PATTERNS = (
    r"^\s*git\s+status\b",
    r"^\s*git\s+diff\s+(--stat|--name-only|--name-status|--check)\b",
    r"^\s*git\s+branch\s+--show-current\b",
    r"^\s*git\s+grep\b",
    r"^\s*rg\b",
    r"^\s*fd\b",
    r"^\s*get-childitem\b",
    r"^\s*select-string\b",
    r"^\s*get-content\b",
    r"^\s*format-table\b",
    r"^\s*\(get-location\)",
)
_VALIDATION_PATTERNS = (
    r"^\s*python\s+-m\s+compileall\b",
    r"^\s*pytest\b",
    r"^\s*python\s+-m\s+pytest\b",
    r"^\s*ruff\s+check\b",
    r"^\s*pyright\b",
    r"^\s*shellcheck\b",
    r"^\s*git\s+apply\s+--check\b",
)
_WRITE_PATTERNS = (
    r"(?:^|[;&|]\s*)\s*git\s+apply\b(?!\s+--check\b)",
    r"\bset-content\b",
    r"\bout-file\b",
    r"\bnew-item\b",
    r"\bcopy-item\b",
    r"\bmove-item\b",
)
_DESTRUCTIVE_PATTERNS = (
    r"\bgit\s+reset\b",
    r"\bgit\s+clean\b",
    r"\bgit\s+push\b",
    r"\bgit\s+commit\b",
    r"\bgit\s+merge\b",
    r"\bgit\s+rebase\b",
    r"\bremove-item\b",
    r"(?:^|[;&|]\s*)\s*rm\b",
    r"\bdel\s+",
    r"\brmdir\b",
    r"^\s*format(?:\s|$)",
    r"\bshutdown\b",
)


def _matches(command: str, patterns: tuple[str, ...]) -> str:
    low = command.lower()
    for pattern in patterns:
        if re.search(pattern, low):
            return pattern
    return ""


def classify_command(command: str) -> CommandClassification:
    raw = str(command or "").strip()
    if not raw:
        return CommandClassification("unknown", "empty command", consent_required=True)
    for command_class, patterns, reason, consent in (
        ("destructive", _DESTRUCTIVE_PATTERNS, "destructive command requires explicit consent", True),
        ("write", _WRITE_PATTERNS, "write command requires explicit consent", True),
        ("validation", _VALIDATION_PATTERNS, "validation command allowed by policy", False),
        ("readonly", _READONLY_PATTERNS, "readonly command allowed by policy", False),
    ):
        matched = _matches(raw, patterns)
        if matched:
            return CommandClassification(command_class, reason, matched, consent)
    return CommandClassification("unknown", "unknown command requires explicit consent", consent_required=True)


def dangerous_command(command: str) -> bool:
    return classify_command(command).command_class == "destructive"
