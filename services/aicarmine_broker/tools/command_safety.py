from __future__ import annotations

import re


def dangerous_command(command: str) -> bool:
    low = command.lower()
    patterns = [
        r"\bgit\s+reset\b",
        r"\bgit\s+clean\b",
        r"\bgit\s+push\b",
        r"\bgit\s+commit\b",
        r"\bgit\s+merge\b",
        r"\bgit\s+rebase\b",
        r"\bremove-item\b",
        r"\brm\s+-",
        r"\bdel\s+",
        r"\brmdir\b",
        r"\bformat\b",
        r"\bshutdown\b",
    ]
    return any(re.search(pattern, low) for pattern in patterns)
