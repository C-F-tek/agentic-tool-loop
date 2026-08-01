# ------------------------------------------------------------------
# AICarmine Broker Error Handling Framework - Migration
# ------------------------------------------------------------------
# This module provides automatic migration of existing broker scripts
# to use the error handling framework. It wraps all bare except clauses
# with proper error handling.
# ------------------------------------------------------------------

from __future__ import annotations

import os
import re
from typing import Any
from pathlib import Path


class ErrorHandlingMigrator:
    """Migrates existing broker scripts to use the error handling framework."""
    
    def __init__(self, broker_root: str = "services/aicarmine_broker"):
        self.broker_root = Path(broker_root)
        self.migrated_files: list[str] = []
        self.skipped_files: list[str] = []
    
    def find_python_files(self) -> list[Path]:
        """Find all Python files in the broker directory."""
        return list(self.broker_root.rglob("*.py"))
    
    def needs_migration(self, file_path: Path) -> bool:
        """Check if a file needs migration (has bare except clauses)."""
        content = file_path.read_text(encoding="utf-8")
        # Check for bare except clauses
        return bool(re.search(r'except\s*:', content))
    
    def migrate_file(self, file_path: Path) -> bool:
        """Migrate a file to use the error handling framework."""
        original_content = file_path.read_text(encoding="utf-8")
        new_content = original_content
        
        # Replace bare except clauses with proper error handling
        new_content = re.sub(
            r'(\s+)except\s*:(\s*\n\s+pass)',
            r'\1except Exception as _e:\n\1    from services.aicarmine_broker.error_handling import BrokerError\n\1    raise BrokerError(message=str(_e))',
            new_content
        )
        
        # Replace bare except with Exception as e clauses
        new_content = re.sub(
            r'except\s+Exception\s+as\s+_e:',
            r'except Exception as _e:\n        from services.aicarmine_broker.error_handling import BrokerError\n        raise BrokerError(message=str(_e))',
            new_content
        )
        
        # Write the migrated file
        if new_content != original_content:
            file_path.write_text(new_content, encoding="utf-8")
            self.migrated_files.append(str(file_path))
            return True
        
        return False
    
    def migrate_all(self) -> dict[str, Any]:
        """Migrate all Python files in the broker directory."""
        results = {
            "total_files": 0,
            "migrated_files": [],
            "skipped_files": [],
            "errors": [],
        }
        
        for file_path in self.find_python_files():
            results["total_files"] += 1
            if self.needs_migration(file_path):
                try:
                    if self.migrate_file(file_path):
                        results["migrated_files"].append(str(file_path))
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
# Migration patterns for common bare except clauses
# ------------------------------------------------------------------

def migrate_bare_except(file_path: str) -> str:
    """Migrate bare except clauses in a file."""
    content = Path(file_path).read_text(encoding="utf-8")
    
    # Pattern 1: bare except with pass
    content = re.sub(
        r'(\s+)except\s*:(\s*\n\s+pass)',
        r'\1except Exception as _e:\n\1    from services.aicarmine_broker.error_handling import BrokerError\n\1    raise BrokerError(message=str(_e))',
        content
    )
    
    # Pattern 2: bare except with logging
    content = re.sub(
        r'(\s+)except\s*:(\s*\n\s+logger\.\w+\(.*\))',
        r'\1except Exception as _e:\n\1    from services.aicarmine_broker.error_handling import BrokerError\n\1    logger.error("Error: %s", str(_e))\n\1    raise BrokerError(message=str(_e))',
        content
    )
    
    # Pattern 3: bare except with return
    content = re.sub(
        r'(\s+)except\s*:(\s*\n\s+return\s+.*\n)',
        r'\1except Exception as _e:\n\1    from services.aicarmine_broker.error_handling import BrokerError\n\1    raise BrokerError(message=str(_e))',
        content
    )
    
    Path(file_path).write_text(content, encoding="utf-8")
    return content


def migrate_sqlite_except(file_path: str) -> str:
    """Migrate SQLite except clauses."""
    content = Path(file_path).read_text(encoding="utf-8")
    
    # Pattern: except sqlite3.Error
    content = re.sub(
        r'except\s+sqlite3\.Error\s+as\s+(\w+):',
        r'except Exception as _e:\n    from services.aicarmine_broker.error_handling import DatabaseError\n    raise DatabaseError(message=str(_e))',
        content
    )
    
    Path(file_path).write_text(content, encoding="utf-8")
    return content


def migrate_json_except(file_path: str) -> str:
    """Migrate JSON except clauses."""
    content = Path(file_path).read_text(encoding="utf-8")
    
    # Pattern: except json.JSONDecodeError
    content = re.sub(
        r'except\s+json\.JSONDecodeError\s+as\s+(\w+):',
        r'except Exception as _e:\n    from services.aicarmine_broker.error_handling import BrokerError\n    raise BrokerError(message=str(_e))',
        content
    )
    
    Path(file_path).write_text(content, encoding="utf-8")
    return content