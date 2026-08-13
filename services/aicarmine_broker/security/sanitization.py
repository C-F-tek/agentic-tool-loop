"""
Security-by-Design: Input Sanitization Module

This module provides centralized sanitization functions for all input sources
across the application. It protects against:
- SQL injection
- Command injection  
- Path traversal
- HTML injection
- XSS attacks

All user-supplied input must pass through these functions before use.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# SQL Injection Prevention
# ---------------------------------------------------------------------------

def sanitize_sql_identifier(name: str) -> str:
    """Sanitize a SQL identifier (table name, column name).
    
    Only allows alphanumeric characters, underscores, and dots.
    Raises ValueError if invalid.
    """
    if not name:
        raise ValueError("SQL identifier must not be empty")
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_.]*$', name):
        raise ValueError(f"Invalid SQL identifier: {name!r}")
    return name


def sanitize_sql_table_name(table_name: str) -> str:
    """Sanitize a SQL table name."""
    return sanitize_sql_identifier(table_name)


def sanitize_sql_column_name(column_name: str) -> str:
    """Sanitize a SQL column name."""
    return sanitize_sql_identifier(column_name)


def validate_sql_query(sql: str, allowed_tables: set[str] | None = None) -> bool:
    """Validate that a SQL query is safe (read-only, no dangerous operations).
    
    Returns True if the query passes validation.
    """
    sql_stripped = sql.strip()
    
    # Must be SELECT only
    if not sql_stripped.upper().startswith("SELECT"):
        return False
    
    # No dangerous keywords
    dangerous_keywords = [
        "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", 
        "TRUNCATE", "GRANT", "REVOKE", "EXEC", "EXECUTE"
    ]
    for kw in dangerous_keywords:
        if re.search(r'\b' + kw + r'\b', sql_stripped, re.IGNORECASE):
            return False
    
    # No semicolons (prevents statement chaining)
    if ';' in sql_stripped:
        return False
    
    # No subqueries with dangerous operations
    if re.search(r'\bWHERE\s+\bEXISTS\b', sql_stripped, re.IGNORECASE):
        return False
    
    # Check allowed tables if specified
    if allowed_tables:
        table_pattern = r'\bFROM\s+(\w+)'
        matches = re.findall(table_pattern, sql_stripped, re.IGNORECASE)
        for table in matches:
            if table not in allowed_tables:
                return False
    
    return True


def escape_sql_like(value: str, like_pattern: str) -> str:
    r"""Escape special LIKE wildcard characters in a value for use in LIKE patterns.
    
    This prevents injection via LIKE patterns by escaping %, _, and \.
    """
    # Escape backslashes first, then wildcards
    value = value.replace('\\', '\\\\')
    value = value.replace('%', '\\%')
    value = value.replace('_', '\\_')
    value = value.replace('[', '\\[')
    value = value.replace(']', '\\]')
    return value


# ---------------------------------------------------------------------------
# Command Injection Prevention
# ---------------------------------------------------------------------------

def sanitize_command_arg(arg: str) -> str:
    """Sanitize a single command argument.
    
    Rejects arguments that contain shell metacharacters or suspicious patterns.
    """
    if not isinstance(arg, str):
        raise TypeError(f"Command argument must be string, got {type(arg)}")
    
    arg = arg.strip()
    
    if not arg:
        raise ValueError("Command argument must not be empty")
    
    # Reject shell metacharacters
    shell_metacharacters = r'[;&|`$(){}[\]<>!\n\r\t]'
    if re.search(shell_metacharacters, arg):
        raise ValueError(f"Command argument contains shell metacharacters: {arg!r}")
    
    # Reject null bytes
    if '\x00' in arg or '\x00\x00' in arg:
        raise ValueError(f"Command argument contains null bytes: {arg!r}")
    
    # Reject path traversal attempts
    if '../' in arg or '..\\' in arg:
        raise ValueError(f"Command argument contains path traversal: {arg!r}")
    
    return arg


def validate_command_args(args: list[str]) -> list[str]:
    """Validate and sanitize a list of command arguments.
    
    Returns sanitized args or raises ValueError.
    """
    sanitized = []
    for i, arg in enumerate(args):
        try:
            sanitized.append(sanitize_command_arg(arg))
        except (ValueError, TypeError) as exc:
            raise ValueError(f"Invalid argument at index {i}: {exc}") from exc
    return sanitized


def classify_command_safety(command: str) -> dict[str, Any]:
    """Classify a command for safety level.
    
    Returns dict with keys:
    - risk_level: 'safe', 'caution', 'dangerous'
    - description: human-readable explanation
    - requires_consent: bool
    """
    low = command.lower().strip()
    
    # Safe operations (read-only)
    safe_patterns = [
        r'^\s*git\s+status\b',
        r'^\s*git\s+diff\s+',
        r'^\s*git\s+log\b',
        r'^\s*git\s+show\b',
        r'^\s*git\s+branch\b',
        r'^\s*python\s+-m\s+py_compile\b',
        r'^\s*pytest\b',
        r'^\s*ruff\s+check\b',
        r'^\s*pyright\b',
        r'^\s*shellcheck\b',
        r'^\s*get-childitem\b',
        r'^\s*select-string\b',
        r'^\s*get-content\b',
    ]
    
    # Caution operations (write but reversible)
    caution_patterns = [
        r'\bset-content\b',
        r'\bout-file\b',
        r'\bnew-item\b',
        r'\bcopy-item\b',
        r'\bmove-item\b',
        r'\bgit\s+apply\b(?!\s+--check)',
    ]
    
    # Dangerous operations (destructive or irreversible)
    dangerous_patterns = [
        r'\bgit\s+reset\b',
        r'\bgit\s+clean\b',
        r'\bgit\s+push\b',
        r'\bgit\s+commit\b',
        r'\bgit\s+merge\b',
        r'\bgit\s+rebase\b',
        r'\bremove-item\b',
        r'\brm\s+',
        r'\bdel\s+',
        r'\brmdir\b',
        r'\bshutdown\b',
        r'\bformat\b',
    ]
    
    for pattern in safe_patterns:
        if re.search(pattern, low):
            return {
                "risk_level": "safe",
                "description": "Read-only or validation operation",
                "requires_consent": False,
            }
    
    for pattern in caution_patterns:
        if re.search(pattern, low):
            return {
                "risk_level": "caution",
                "description": "Write operation that may modify files",
                "requires_consent": True,
            }
    
    for pattern in dangerous_patterns:
        if re.search(pattern, low):
            return {
                "risk_level": "dangerous",
                "description": "Destructive or irreversible operation",
                "requires_consent": True,
            }
    
    return {
        "risk_level": "unknown",
        "description": "Unknown command - requires manual review",
        "requires_consent": True,
    }


# ---------------------------------------------------------------------------
# Path Traversal Prevention
# ---------------------------------------------------------------------------

def sanitize_file_path(path_str: str, base_dir: Path | None = None) -> Path:
    """Sanitize a file path to prevent directory traversal attacks.
    
    Returns an absolute Path within base_dir (if specified).
    Raises ValueError if path is unsafe.
    """
    if not isinstance(path_str, str):
        raise TypeError(f"File path must be string, got {type(path_str)}")
    
    path_str = path_str.strip()
    
    if not path_str:
        raise ValueError("File path must not be empty")
    
    # Create Path object
    target = Path(path_str)
    
    # Resolve to absolute path (handles .., ., etc.)
    resolved = target.resolve()
    
    # If base_dir specified, verify target is within it
    if base_dir:
        try:
            relative = resolved.relative_to(base_dir)
        except ValueError:
            raise ValueError(
                f"Path traversal detected: {path_str!r} resolves outside base directory {base_dir!r}"
            )
        
        # Check for null bytes in resolved path
        if '\x00' in str(resolved):
            raise ValueError(f"Path contains null bytes: {path_str!r}")
    
    return resolved


def validate_path_safe(path: Path, base_dir: Path | None = None) -> bool:
    """Check if a path is safe (within base_dir if specified).
    
    Returns True if safe, False otherwise.
    """
    try:
        sanitize_file_path(str(path), base_dir)
        return True
    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------------------------
# HTML Injection Prevention
# ---------------------------------------------------------------------------

def escape_html(text: str) -> str:
    """Escape special HTML characters to prevent XSS.
    
    Handles: < > & " ' /
    """
    if not isinstance(text, str):
        text = str(text)
    
    text = text.replace('&', '&')
    text = text.replace('<', '<')
    text = text.replace('>', '>')
    text = text.replace('"', '"')
    text = text.replace("'", '&#x27;')
    text = text.replace('/', '&#x2F;')
    
    return text


def sanitize_html_attribute(value: str) -> str:
    """Sanitize a value for use in HTML attributes.
    
    Strips quotes and backslashes.
    """
    if not isinstance(value, str):
        value = str(value)
    
    value = value.replace('"', '')
    value = value.replace("'", '')
    value = value.replace('\\', '')
    value = value.strip()
    
    return value


# ---------------------------------------------------------------------------
# General Input Validation
# ---------------------------------------------------------------------------

def validate_string_length(value: str, max_length: int = 10000, min_length: int = 0) -> str:
    """Validate string length and return sanitized string.
    
    Raises ValueError if length is out of bounds.
    """
    if not isinstance(value, str):
        raise TypeError(f"Expected string, got {type(value)}")
    
    value = value.strip()
    
    if len(value) > max_length:
        raise ValueError(f"String too long: {len(value)} > {max_length}")
    
    if len(value) < min_length and min_length > 0:
        raise ValueError(f"String too short: {len(value)} < {min_length}")
    
    return value


def validate_non_empty(value: str, field_name: str = "value") -> str:
    """Validate that a string is not empty after stripping.
    
    Returns stripped string or raises ValueError.
    """
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be string")
    
    stripped = value.strip()
    
    if not stripped:
        raise ValueError(f"{field_name} must not be empty")
    
    return stripped


def validate_identifier(name: str, prefix: str = "", suffix: str = "") -> str:
    """Validate a name/identifier follows safe naming conventions.
    
    Only allows alphanumeric, underscore, hyphen, and dot.
    """
    if not isinstance(name, str):
        raise TypeError(f"Identifier must be string, got {type(name)}")
    
    name = name.strip()
    
    if not name:
        raise ValueError("Identifier must not be empty")
    
    # Build full identifier with prefix/suffix
    full = prefix + name + suffix
    
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_.\-]*$', full):
        raise ValueError(f"Invalid identifier: {name!r}")
    
    return name


def sanitize_job_id(job_id: str) -> str:
    """Sanitize a job ID specifically.
    
    Job IDs should be UUID-like or alphanumeric identifiers.
    """
    job_id = validate_non_empty(job_id, "job_id")
    
    if not re.match(r'^[a-zA-Z0-9_-]+$', job_id):
        raise ValueError(f"Invalid job ID format: {job_id!r}")
    
    return job_id


def sanitize_tool_name(tool_name: str) -> str:
    """Sanitize a tool name.
    
    Tool names should follow the aicarmine_ prefix convention and alphanumeric pattern.
    """
    tool_name = validate_non_empty(tool_name, "tool_name")
    
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_.]*$', tool_name):
        raise ValueError(f"Invalid tool name: {tool_name!r}")
    
    return tool_name


def sanitize_query_text(query: str, max_length: int = 10000) -> str:
    """Sanitize search/query text input.
    
    Allows most printable characters but rejects null bytes and control chars.
    """
    query = validate_string_length(query, max_length=max_length)
    query = query.strip()
    
    # Reject null bytes
    if '\x00' in query:
        raise ValueError("Query contains null bytes")
    
    # Reject control characters (except space)
    for char in query:
        if char.isprintable() or char == ' ':
            continue
        raise ValueError(f"Query contains non-printable character: {repr(char)}")
    
    return query