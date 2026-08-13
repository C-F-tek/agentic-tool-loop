# Security by Design

## Overview

This document describes the security-by-design principles and implementations across the `agentic-tool-loop` project. The goal is to protect against common injection attacks including SQL injection, command injection, path traversal, and XSS.

## Security Architecture

### 1. Input Sanitization Layer

All user-supplied input must pass through the centralized sanitization module before use:

```python
from services.aicarmine_broker.security import (
    sanitize_sql_identifier,
    validate_sql_query,
    sanitize_command_arg,
    validate_command_args,
    sanitize_file_path,
    escape_html,
    sanitize_query_text,
)
```

### 2. SQL Injection Prevention

**Principles:**
- Always use parameterized queries (`?` placeholders)
- Sanitize SQL identifiers (table names, column names)
- Validate SQL queries before execution
- Never concatenate user input into SQL strings

**Implementation:**
```python
from .security import sanitize_sql_identifier

# Safe: Table name sanitized
safe_table = sanitize_sql_identifier("user_supplied_table")
conn.execute(f"SELECT * FROM {safe_table} WHERE id = ?", (user_id,))

# Safe: Query validated
if validate_sql_query(user_query, allowed_tables={"users"}):
    conn.execute(user_query)
```

**Vulnerable Patterns (AVOID):**
```python
# DANGEROUS - String concatenation
conn.execute(f"SELECT * FROM users WHERE name = '{user_name}'")

# DANGEROUS - f-string in query
query = f"SELECT * FROM {table_name} WHERE id = {user_id}"
```

### 3. Command Injection Prevention

**Principles:**
- Use `shell=False` for subprocess calls
- Sanitize command arguments
- Classify commands by risk level
- Require consent for dangerous operations

**Implementation:**
```python
from .security import sanitize_command_arg, classify_command_safety

# Safe: Arguments sanitized
safe_args = validate_command_args(["git", "status", "/path/to/repo"])
subprocess.run(safe_args, shell=False)

# Safe: Command classified
classification = classify_command_safety(user_command)
if classification["requires_consent"]:
    require_user_approval()
```

**Vulnerable Patterns (AVOID):**
```python
# DANGEROUS - Shell execution
os.system(f"git commit -m '{user_message}'")

# DANGEROUS - Unsanitized args
subprocess.run(f"git {user_action}", shell=True)
```

### 4. Path Traversal Prevention

**Principles:**
- Resolve and validate file paths
- Check paths are within allowed directories
- Reject null bytes and suspicious patterns

**Implementation:**
```python
from .security import sanitize_file_path

# Safe: Path validated within base directory
safe_path = sanitize_file_path(user_path, base_dir=project_root)

# Safe: Path checked
if validate_path_safe(user_path, base_dir=project_root):
    read_file(user_path)
```

**Vulnerable Patterns (AVOID):**
```python
# DANGEROUS - No path validation
file_path = os.path.join(base_dir, user_input)

# DANGEROUS - No resolution
path = Path(user_input)
```

### 5. XSS Prevention

**Principles:**
- Escape HTML entities before rendering
- Validate identifiers
- Sanitize HTML attributes

**Implementation:**
```python
from .security import escape_html

# Safe: HTML escaped
safe_output = escape_html(user_content)

# Safe: Identifier validated
safe_id = validate_identifier(user_id)
```

## Security Modules

### `services/aicarmine_broker/security/`

| Module | Purpose |
|--------|---------|
| `__init__.py` | Package exports for all security utilities |
| `sanitization.py` | Core sanitization functions |

### Key Functions

| Function | Protects Against | Usage |
|----------|-------------------|-------|
| `sanitize_sql_identifier()` | SQL injection via table/column names | Validate SQL identifiers |
| `validate_sql_query()` | SQL injection via query strings | Validate SELECT-only queries |
| `sanitize_command_arg()` | Command injection | Validate command arguments |
| `validate_command_args()` | Command injection | Validate entire command arrays |
| `classify_command_safety()` | Command injection risk assessment | Classify commands by risk |
| `sanitize_file_path()` | Path traversal | Validate file paths |
| `escape_html()` | XSS | Escape HTML entities |
| `sanitize_query_text()` | General input injection | Validate search/query text |

## Testing Security

Run security tests to verify protections:

```powershell
# Test SQL injection prevention
python -c "from services.aicarmine_broker.security import sanitize_sql_identifier; print(sanitize_sql_identifier('users'))"

# Test command injection prevention
python -c "from services.aicarmine_broker.security import sanitize_command_arg; print(sanitize_command_arg('git status'))"

# Test path traversal prevention
python -c "from services.aicarmine_broker.security import sanitize_file_path; from pathlib import Path; print(sanitize_file_path('../etc/passwd', base_dir=Path('/safe/dir')))"
```

## Security Checklist

For every new feature:

- [ ] All user input passes through sanitization functions
- [ ] SQL queries use parameterized placeholders (`?`)
- [ ] SQL identifiers are sanitized with `sanitize_sql_identifier()`
- [ ] Commands use `shell=False` and sanitized arguments
- [ ] File paths are validated with `sanitize_file_path()`
- [ ] HTML output uses `escape_html()` for user content
- [ ] Command risk classification checked before execution
- [ ] Dangerous operations require explicit user consent

## Incident Response

If an injection vulnerability is discovered:

1. **Symptom**: Observe the unexpected behavior
2. **Evidence**: Gather concrete MCP, source, Git, or runtime evidence
3. **Confirmed Cause**: Identify the specific injection point
4. **Minimal Fix**: Apply the smallest security patch
5. **Verification**: Test the fix with targeted checks
6. **Residual Risk**: Document any remaining concerns

## References

- OWASP Injection Prevention Cheat Sheet
- Python `sqlite3` Parameterized Queries Documentation
- Python `subprocess` Security Best Practices
- Path Traversal Prevention Guidelines