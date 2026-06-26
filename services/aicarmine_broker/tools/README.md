# Tools Module — Repository Tool Implementations

> **Purpose**: Concrete implementations of repository operations: file reading, searching, patching, git operations, PowerShell execution, and validation.

---

## Files

| File | Purpose | Key Functions/Classes |
|------|---------|----------------------|
| `__init__.py` | Package init | — |
| `command_safety.py` | Command safety checks | Validates command safety before execution |
| `deterministic_common.py` | Deterministic common utilities | Shared deterministic helpers |
| `git_surface.py` | Git surface operations | Git operations wrapper |
| `powershell_runner.py` | PowerShell runner | Runs PowerShell commands |
| `repo_code_product.py` | Code product operations | Code product manipulation |
| `repo_command.py` | Repository commands | Generic repo commands |
| `repo_deterministic.py` | Deterministic repo operations | Deterministic operations |
| `repo_list_files.py` | File listing | Lists directory files |
| `repo_patch.py` | Patch application | Applies unified diffs |
| `repo_read.py` | File reading | Reads repository files |
| `repo_search.py` | Search operations | Searches repository files |
| `repo_semantic_search.py` | Semantic search | RAG-based semantic search |
| `repo_status.py` | Status reporting | Reports repo status |
| `repo_tree.py` | Tree operations | Directory tree traversal |
| `repo_validate.py` | Validation operations | Validates repository state |
| `terminal.py` | Terminal operations | Terminal I/O handling |

---

## Tool Categories

### File Operations
- `repo_read.py` — Read file contents with encoding detection
- `repo_list_files.py` — List directory files with filtering
- `repo_tree.py` — Directory tree traversal

### Search Operations
- `repo_search.py` — Regex search across files
- `repo_semantic_search.py` — RAG-based semantic search

### Patch & Code Operations
- `repo_patch.py` — Apply unified diff patches
- `repo_code_product.py` — Code product manipulation

### Git Operations
- `git_surface.py` — Git command wrapper
- `repo_status.py` — Repository status reporting

### Execution
- `powershell_runner.py` — PowerShell command execution
- `command_safety.py` — Command safety validation
- `terminal.py` — Terminal I/O handling

---

## Documentation Index

| Document | Location |
|----------|----------|
| [Complete Services Index](../../docs/SERVICES_INDEX.md) | Full file-by-file documentation |
| [Python Refactoring Guide](../../docs/PYTHON_REFACTORING_GUIDE.md) | Tool result dataclass pattern (§8.5) |

---

*Generated from analysis of the C:\Users\carmi\AI workspace.*