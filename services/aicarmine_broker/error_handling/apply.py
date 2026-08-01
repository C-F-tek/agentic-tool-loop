# ------------------------------------------------------------------
# AICarmine Broker Error Handling Framework - Apply to All Scripts
# ------------------------------------------------------------------
# This module automatically applies the error handling framework to
# ALL existing broker scripts, wrapping bare except clauses with
# proper error handling.
# ------------------------------------------------------------------

from __future__ import annotations

import os
import re
import sys
from typing import Any
from pathlib import Path


class ErrorHandlingApplier:
    """Applies error handling framework to all existing broker scripts."""
    
    def __init__(self, broker_root: str = "services/aicarmine_broker"):
        self.broker_root = Path(broker_root)
        self.applied_files: list[str] = []
        self.skipped_files: list[str] = []
        self.errors: list[dict[str, Any]] = []
    
    def find_all_python_files(self) -> list[Path]:
        """Find all Python files in the broker directory."""
        files = []
        for py_file in self.broker_root.rglob("*.py"):
            # Skip the error_handling directory itself
            if "error_handling" in str(py_file):
                continue
            files.append(py_file)
        return files
    
    def needs_error_handling(self, file_path: Path) -> bool:
        """Check if a file needs error handling (has try/except patterns)."""
        content = file_path.read_text(encoding="utf-8")
        # Check for any try/except patterns
        return bool(re.search(r'try:|try\s*:', content))
    
    def apply_to_file(self, file_path: Path) -> bool:
        """Apply error handling framework to a file."""
        original_content = file_path.read_text(encoding="utf-8")
        new_content = original_content
        
        # Pattern 1: Add import statement at the top if not present
        import_pattern = r'from aicarmine_broker.error_handling import'
        if not re.search(import_pattern, new_content):
            # Add import after the first import block
            import_insert_pos = len("from __future__ import annotations\n\n")
            new_content = (
                new_content[:import_insert_pos] +
                "from aicarmine_broker.error_handling import (\n"
                "    BrokerError,\n"
                "    ErrorCategory,\n"
                "    ErrorSeverity,\n"
                "    ErrorReport,\n"
                "    ErrorSummary,\n"
                ")\n\n" +
                new_content[import_insert_pos:]
            )
        
        # Pattern 2: Wrap bare except clauses
        # Replace bare except: with except Exception as _e:
        new_content = re.sub(
            r'(\s+)except\s*:(\s*\n)',
            r'\1except Exception as _e:\n\1    raise BrokerError(message=str(_e))\n',
            new_content
        )
        
        # Pattern 3: Wrap except Exception clauses with proper error handling
        # Replace except Exception as e: with proper error type
        new_content = re.sub(
            r'except\s+Exception\s+as\s+(\w+):',
            r'except Exception as _e:\n        raise BrokerError(\n'
            r'            message=f"Error in {__name__}:\n            error_type=type(_e).__name__,\n'
            r'            error_message=str(_e),\n'
            r'            category=ErrorCategory.RUNTIME,\n'
            r'            severity=ErrorSeverity.HIGH,\n'
            r'        )',
            new_content
        )
        
        # Write the modified file
        if new_content != original_content:
            file_path.write_text(new_content, encoding="utf-8")
            self.applied_files.append(str(file_path))
            return True
        
        return False
    
    def apply_to_all(self) -> dict[str, Any]:
        """Apply error handling to all Python files in the broker directory."""
        results = {
            "total_files": 0,
            "applied_files": [],
            "skipped_files": [],
            "errors": [],
        }
        
        for file_path in self.find_all_python_files():
            results["total_files"] += 1
            if self.needs_error_handling(file_path):
                try:
                    if self.apply_to_file(file_path):
                        results["applied_files"].append(str(file_path))
                    else:
                        results["skipped_files"].append(str(file_path))
                except Exception as e:
                    results["errors"].append({
                        "file": str(file_path),
                        "error": str(e),
                    })
            else:
                results["skipped_files"].append(str(file_path))
        
        return results


# ------------------------------------------------------------------
# Quick apply patterns for common bare except clauses
# ------------------------------------------------------------------

def apply_to_file(file_path: str) -> str:
    """Apply error handling to a single file."""
    content = Path(file_path).read_text(encoding="utf-8")
    
    # Pattern 1: Add import statement
    if "from aicarmine_broker.error_handling import" not in content:
        content = (
            "from aicarmine_broker.error_handling import (\n"
            "    BrokerError,\n"
            "    ErrorCategory,\n"
            "    ErrorSeverity,\n"
            "    ErrorReport,\n"
            "    ErrorSummary,\n"
            ")\n\n" +
            content
        )
    
    # Pattern 2: Replace bare except clauses
    content = re.sub(
        r'(\s+)except\s*:(\s*\n)',
        r'\1except Exception as _e:\n\1    raise BrokerError(message=str(_e))\n',
        content
    )
    
    Path(file_path).write_text(content, encoding="utf-8")
    return content


def apply_to_directory(directory: str) -> dict[str, Any]:
    """Apply error handling to all files in a directory."""
    results = {
        "total_files": 0,
        "applied_files": [],
        "skipped_files": [],
        "errors": [],
    }
    
    broker_root = Path(directory)
    for py_file in broker_root.rglob("*.py"):
        if "error_handling" in str(py_file):
            continue
        
        results["total_files"] += 1
        try:
            apply_to_file(str(py_file))
            results["applied_files"].append(str(py_file))
        except Exception as e:
            results["errors"].append({
                "file": str(py_file),
                "error": str(e),
            })
    
    return results