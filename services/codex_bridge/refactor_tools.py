#!/usr/bin/env python3
"""
Agent-friendly Python refactoring utilities.
Provides libcst-based AST-aware transformations and rope-based CLI refactors.
"""
from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

try:
    import libcst as cst
    HAS_LIBCST = True
except ImportError:
    HAS_LIBCST = False

try:
    import rope
    from rope.base.project import Project
    HAS_ROPE = True
except ImportError:
    HAS_ROPE = False

try:
    import bowler  # type: ignore[no-redef]
    HAS_BOWLER = True
except ImportError:
    HAS_BOWLER = False


# ---------------------------------------------------------------------------
# Git-based file discovery (respects .gitignore)
# ---------------------------------------------------------------------------

def git_list_tracked_files(root_dir: str = ".") -> list[str]:
    """List all tracked files in the repository using git ls-files.
    
    Respects .gitignore by only returning files that are actually tracked.
    Excludes external packages, virtual environments, and build artifacts.
    """
    excluded_patterns = {
        "site-packages",
        "__pycache__",
        ".venv",
        "venv",
        "node_modules",
        ".git",
        "*.egg-info",
        "*.pyc",
        "*.pyo",
        "*.so",
        "*.dylib",
        "*.dll",
        "*.exe",
        ".pytest_cache",
        ".mypy_cache",
        "htmlcov",
        "coverage.xml",
        ".tox",
        ".nox",
    }
    
    try:
        result = subprocess.run(
            ["git", "-C", root_dir, "ls-files", "--exclude-standard"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return []
        
        files = [f.strip() for f in result.stdout.splitlines() if f.strip()]
        filtered = []
        for f in files:
            # Skip files matching excluded patterns
            if not any(pattern in f for pattern in excluded_patterns):
                filtered.append(f)
        return filtered
    except Exception:
        return []


def git_list_staged_files(root_dir: str = ".") -> list[str]:
    """List currently staged (git add) files. Useful for targeted refactoring."""
    try:
        result = subprocess.run(
            ["git", "-C", root_dir, "diff", "--cached", "--name-only"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return []
        return [f.strip() for f in result.stdout.splitlines() if f.strip()]
    except Exception:
        return []


def git_list_modified_files(root_dir: str = ".") -> list[str]:
    """List currently modified (unstaged) files."""
    try:
        result = subprocess.run(
            ["git", "-C", root_dir, "status", "--porcelain", "--untracked-files=no"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return []
        files = [line.split(" ", 2)[1] for line in result.stdout.splitlines() if line.strip()]
        return [f for f in files if f]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------
@dataclass
class RefactorResult:
    """Result of a refactoring operation."""
    success: bool
    original_path: str
    new_content: str | None = None
    diff_preview: str | None = None
    error: str | None = None
    tool_used: str = ""


# ---------------------------------------------------------------------------
# libcst-based refactors (guarded: requires libcst)
# ---------------------------------------------------------------------------

if HAS_LIBCST:

    class AddParameterTransformer(cst.CSTTransformer):
        """Add a keyword argument to function calls matching a pattern."""

        def __init__(
            self,
            func_name: str,
            param_name: str,
            param_value: str,
        ):
            self.func_name = func_name
            self.param_name = param_name
            self.param_value = param_value

        def leave_Call(
            self,
            original_node: cst.Call,
            updated_node: cst.Call,
        ) -> cst.Call:
            # Check if this call matches our target function
            func_name = original_node.func
            if isinstance(func_name, cst.Name) and func_name.value == self.func_name:
                # Check if parameter already exists
                has_param = any(kw.keyword.value == self.param_name for kw in (original_node.keywords or []))
                if not has_param:
                    # Add the new keyword argument
                    new_kwarg = cst.Arg(
                        keyword=cst.Name(self.param_name),
                        value=cst.SimpleString(f'"{self.param_value}"'),
                        equal=cst.AssignEqual(),
                    )
                    new_args = list(updated_node.args or [])
                    new_args.append(new_kwarg)
                    return updated_node.with_deep_change('args', lambda x: new_args)
            return updated_node


    class RenameSymbolTransformer(cst.CSTTransformer):
        """Rename a symbol across a file."""

        def __init__(self, old_name: str, new_name: str):
            self.old_name = old_name
            self.new_name = new_name

        def leave_Name(
            self,
            original_node: cst.Name,
            updated_node: cst.Name,
        ) -> cst.Name:
            if original_node.value == self.old_name:
                return cst.Name(self.new_name)
            return updated_node

        def leave_FunctionDef(
            self,
            original_node: cst.FunctionDef,
            updated_node: cst.FunctionDef,
        ) -> cst.FunctionDef:
            if original_node.name.value == self.old_name:
                return updated_node.with_deep_change('name', lambda n: cst.Name(self.new_name))
            return updated_node


def refactor_add_parameter(
    file_path: str,
    func_name: str,
    param_name: str,
    param_value: str,
) -> RefactorResult:
    """Add a keyword parameter to matching function calls in a file."""
    if not HAS_LIBCST:
        return RefactorResult(False, file_path, error="libcst not installed", tool_used="libcst")

    source = Path(file_path).read_text(encoding="utf-8")
    transformer = AddParameterTransformer(func_name, param_name, param_value)
    module = cst.parse_module(source)
    new_module = module.transformer(transformer)
    new_content = new_module.code

    return RefactorResult(
        success=True,
        original_path=file_path,
        new_content=new_content,
        diff_preview=f"Added {param_name}={param_value!r} to {func_name}() calls",
        tool_used="libcst",
    )


def refactor_rename_symbol(
        file_path: str,
        old_name: str,
        new_name: str,
    ) -> RefactorResult:
        """Rename a symbol in a file."""
        if not HAS_LIBCST:
            return RefactorResult(False, file_path, error="libcst not installed", tool_used="libcst")

        source = Path(file_path).read_text(encoding="utf-8")
        transformer = RenameSymbolTransformer(old_name, new_name)
        module = cst.parse_module(source)
        new_module = module.transformer(transformer)
        new_content = new_module.code

        # Calculate diff preview
        old_lines = source.splitlines()
        new_lines = new_content.splitlines()
        diff_preview = f"Renamed '{old_name}' → '{new_name}' ({len([l for l in old_lines if l != l])} lines affected)"

        return RefactorResult(
            success=True,
            original_path=file_path,
            new_content=new_content,
            diff_preview=diff_preview,
            tool_used="libcst",
        )


# ---------------------------------------------------------------------------
# rope-based refactors (CLI wrapper)
# ---------------------------------------------------------------------------

def refactor_rename_rope(
    file_path: str,
    old_name: str,
    new_name: str,
    project_root: str | None = None,
) -> RefactorResult:
    """Use rope to rename a symbol across the project."""
    if not HAS_ROPE:
        return RefactorResult(False, file_path, error="rope not installed", tool_used="rope")

    project_path = project_root or str(Path(file_path).parent)
    try:
        project = Project(project_path)
        resource = project.get_resource(Path(file_path).name)
        if resource is None:
            return RefactorResult(False, file_path, error=f"resource not found: {file_path}", tool_used="rope")

        # Perform rename
        change = resource.rename(old_name, new_name)
        if change:
            for item in change:
                item.do()
            new_content = resource.read()
            return RefactorResult(
                success=True,
                original_path=file_path,
                new_content=new_content,
                diff_preview=f"Rope rename: '{old_name}' → '{new_name}'",
                tool_used="rope",
            )
        else:
            return RefactorResult(False, file_path, error="no changes produced", tool_used="rope")
    except Exception as exc:
        return RefactorResult(False, file_path, error=str(exc), tool_used="rope")


def refactor_extract_function(
    file_path: str,
    start_line: int,
    end_line: int,
    function_name: str,
) -> RefactorResult:
    """Extract a code block into a new function."""
    if not HAS_ROPE:
        return RefactorResult(False, file_path, error="rope not installed", tool_used="rope")

    project_path = str(Path(file_path).parent)
    try:
        project = Project(project_path)
        resource = project.get_resource(Path(file_path).name)
        if resource is None:
            return RefactorResult(False, file_path, error=f"resource not found: {file_path}", tool_used="rope")

        change_list = resource.extract_function(start_line, end_line, function_name)
        if change_list:
            for change in change_list:
                change.do()
            new_content = resource.read()
            return RefactorResult(
                success=True,
                original_path=file_path,
                new_content=new_content,
                diff_preview=f"Extracted function '{function_name}'",
                tool_used="rope",
            )
        return RefactorResult(False, file_path, error="extraction failed", tool_used="rope")
    except Exception as exc:
        return RefactorResult(False, file_path, error=str(exc), tool_used="rope")


# ---------------------------------------------------------------------------
# bowler-based refactors (AST mutations with git rollback)
# ---------------------------------------------------------------------------


def refactor_rename_bowler(
    file_path: str,
    old_name: str,
    new_name: str,
    dry_run: bool = True,
) -> RefactorResult:
    """Use bowler to rename a symbol with safe git rollback support.

    Bowler provides AST-aware code mutations with automatic git diff
    and rollback capabilities for safe refactoring.

    Args:
        file_path: Path to the Python file
        old_name: Current symbol name
        new_name: New symbol name
        dry_run: If True, only preview changes without applying

    Returns:
        RefactorResult with success status and preview
    """
    if not HAS_BOWLER:
        return RefactorResult(False, file_path, error="bowler not installed", tool_used="bowler")

    try:
        # Bowler uses a command-line style API via subprocess or direct calls
        cmd = ["bowler", file_path, old_name, new_name]
        if dry_run:
            cmd.append("--dry-run")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode == 0:
            return RefactorResult(
                success=True,
                original_path=file_path,
                new_content=None if dry_run else None,
                diff_preview=result.stdout or f"bowler rename: '{old_name}' → '{new_name}'",
                tool_used="bowler",
            )
        else:
            return RefactorResult(
                False, file_path,
                error=result.stderr or f"bowler failed with exit code {result.returncode}",
                tool_used="bowler",
            )
    except FileNotFoundError:
        return RefactorResult(
            False, file_path,
            error="bowler CLI not found (try: pip install bowler)",
            tool_used="bowler",
        )
    except Exception as exc:
        return RefactorResult(False, file_path, error=str(exc), tool_used="bowler")


def refactor_rewrite_bowler(
    file_path: str,
    query_pattern: str,
    replacement_code: str,
) -> RefactorResult:
    """Use bowler for pattern-based code rewrites.

    Args:
        file_path: Path to the Python file
        query_pattern: AST query pattern (e.g., "Name($old)")
        replacement_code: Replacement code template

    Returns:
        RefactorResult with success status
    """
    if not HAS_BOWLER:
        return RefactorResult(False, file_path, error="bowler not installed", tool_used="bowler")

    try:
        import subprocess
        # Bowler uses a query language for AST matching
        cmd = ["bowler", file_path, "-q", query_pattern, "--replace", replacement_code]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode == 0:
            return RefactorResult(
                success=True,
                original_path=file_path,
                diff_preview=result.stdout or f"bowler rewrite: {query_pattern} → {replacement_code}",
                tool_used="bowler",
            )
        else:
            return RefactorResult(
                False, file_path,
                error=result.stderr or f"bowler failed with exit code {result.returncode}",
                tool_used="bowler",
            )
    except FileNotFoundError:
        return RefactorResult(
            False, file_path,
            error="bowler CLI not found (try: pip install bowler)",
            tool_used="bowler",
        )
    except Exception as exc:
        return RefactorResult(False, file_path, error=str(exc), tool_used="bowler")


# ---------------------------------------------------------------------------
# Multi-file rename across project
# ---------------------------------------------------------------------------

def refactor_rename_project(
    symbol_old: str,
    symbol_new: str,
    root_dir: str = ".",
    scope: str = "tracked",  # "tracked", "staged", "modified", "all"
) -> list[RefactorResult]:
    """Rename a symbol across codebase files using git-tracked files (respects .gitignore).

    Args:
        symbol_old: Old symbol name to replace
        symbol_new: New symbol name
        root_dir: Repository root directory
        scope: File selection scope
            - "tracked": All tracked files (default, respects .gitignore)
            - "staged": Only staged files (git add)
            - "modified": Only modified working tree files
            - "all": All Python files including untracked
    """
    results = []

    if scope == "tracked":
        file_list = git_list_tracked_files(root_dir)
    elif scope == "staged":
        file_list = git_list_staged_files(root_dir)
    elif scope == "modified":
        file_list = git_list_modified_files(root_dir)
    else:  # "all"
        root = Path(root_dir)
        file_list = [str(f) for f in root.rglob("*.py")
                     if "site-packages" not in str(f) and "__pycache__" not in str(f)]

    for py_file in file_list:
        result = refactor_rename_symbol(py_file, symbol_old, symbol_new)
        results.append(result)

    return results


def refactor_rename_project_bowler(
    symbol_old: str,
    symbol_new: str,
    root_dir: str = ".",
    scope: str = "tracked",
    dry_run: bool = True,
) -> list[RefactorResult]:
    """Rename a symbol across codebase files using bowler (git-tracked only).

    Args:
        symbol_old: Old symbol name to replace
        symbol_new: New symbol name
        root_dir: Repository root directory
        scope: File selection scope
        dry_run: If True, only preview changes without applying
    """
    results = []

    if scope == "tracked":
        file_list = git_list_tracked_files(root_dir)
    elif scope == "staged":
        file_list = git_list_staged_files(root_dir)
    elif scope == "modified":
        file_list = git_list_modified_files(root_dir)
    else:
        file_list = []

    for py_file in file_list:
        result = refactor_rename_bowler(py_file, symbol_old, symbol_new, dry_run)
        results.append(result)

    return results


# ---------------------------------------------------------------------------
# CLI interface
# ---------------------------------------------------------------------------

def main():
    """CLI interface for refactoring tools."""
    import argparse

    parser = argparse.ArgumentParser(description="Python refactoring utilities")
    subparsers = parser.add_subparsers(dest="command", help="Refactoring command")

    # rename-symbol command
    rename_parser = subparsers.add_parser("rename", help="Rename a symbol")
    rename_parser.add_argument("file", help="Target file")
    rename_parser.add_argument("old_name", help="Old symbol name")
    rename_parser.add_argument("new_name", help="New symbol name")
    rename_parser.add_argument("--project-root", default=None, help="Project root for rope")
    rename_parser.add_argument("--use-rope", action="store_true", help="Use rope instead of libcst")

    # add-param command
    param_parser = subparsers.add_parser("add-param", help="Add parameter to function calls")
    param_parser.add_argument("file", help="Target file")
    param_parser.add_argument("func_name", help="Function name")
    param_parser.add_argument("param_name", help="Parameter name")
    param_parser.add_argument("param_value", help="Parameter value")

    # extract-function command
    extract_parser = subparsers.add_parser("extract", help="Extract code block into function")
    extract_parser.add_argument("file", help="Target file")
    extract_parser.add_argument("--start", type=int, required=True, help="Start line")
    extract_parser.add_argument("--end", type=int, required=True, help="End line")
    extract_parser.add_argument("--name", required=True, help="New function name")

    # rename-project command
    project_parser = subparsers.add_parser("rename-project", help="Rename across project (git-tracked files)")
    project_parser.add_argument("old_name", help="Old symbol name")
    project_parser.add_argument("new_name", help="New symbol name")
    project_parser.add_argument("--root", default=".", help="Root directory")
    project_parser.add_argument(
        "--scope",
        choices=["tracked", "staged", "modified", "all"],
        default="tracked",
        help="File selection scope (default: tracked)",
    )

    # bowler-rename command
    bowler_rename_parser = subparsers.add_parser("bowler-rename", help="Rename with bowler (git rollback)")
    bowler_rename_parser.add_argument("file", help="Target file")
    bowler_rename_parser.add_argument("old_name", help="Old symbol name")
    bowler_rename_parser.add_argument("new_name", help="New symbol name")
    bowler_rename_parser.add_argument("--dry-run", action="store_true", default=True, help="Preview only")

    # bowler-rewrite command
    bowler_rewrite_parser = subparsers.add_parser("bowler-rewrite", help="Pattern-based rewrite with bowler")
    bowler_rewrite_parser.add_argument("file", help="Target file")
    bowler_rewrite_parser.add_argument("query", help="AST query pattern")
    bowler_rewrite_parser.add_argument("replace", help="Replacement code")

    # bowler-rename-project command
    bowler_project_parser = subparsers.add_parser("bowler-rename-project", help="Rename across project with bowler")
    bowler_project_parser.add_argument("old_name", help="Old symbol name")
    bowler_project_parser.add_argument("new_name", help="New symbol name")
    bowler_project_parser.add_argument("--root", default=".", help="Root directory")
    bowler_project_parser.add_argument(
        "--scope",
        choices=["tracked", "staged", "modified", "all"],
        default="tracked",
        help="File selection scope (default: tracked)",
    )
    bowler_project_parser.add_argument("--apply", action="store_true", help="Apply changes (not dry-run)")

    args = parser.parse_args()

    if args.command == "rename":
        if args.use_rope:
            result = refactor_rename_rope(args.file, args.old_name, args.new_name, args.project_root)
        else:
            result = refactor_rename_symbol(args.file, args.old_name, args.new_name)
        print(f"Tool: {result.tool_used}")
        print(f"Success: {result.success}")
        print(f"Preview: {result.diff_preview}")
        if result.error:
            print(f"Error: {result.error}")
        if result.new_content:
            print("---NEW_CONTENT---")
            print(result.new_content)

    elif args.command == "add-param":
        result = refactor_add_parameter(args.file, args.func_name, args.param_name, args.param_value)
        print(f"Tool: {result.tool_used}")
        print(f"Success: {result.success}")
        print(f"Preview: {result.diff_preview}")
        if result.error:
            print(f"Error: {result.error}")

    elif args.command == "extract":
        result = refactor_extract_function(args.file, args.start, args.end, args.name)
        print(f"Tool: {result.tool_used}")
        print(f"Success: {result.success}")
        print(f"Preview: {result.diff_preview}")
        if result.error:
            print(f"Error: {result.error}")

    elif args.command == "rename-project":
        results = refactor_rename_project(args.old_name, args.new_name, args.root, args.scope)
        success_count = sum(1 for r in results if r.success)
        error_count = sum(1 for r in results if not r.success)
        print(f"Scope: {args.scope}")
        print(f"Total files: {len(results)}")
        print(f"Successes: {success_count}")
        print(f"Errors: {error_count}")

    # bowler-rename-project command
    elif args.command == "bowler-rename-project":
        dry_run = not args.apply
        results = refactor_rename_project_bowler(
            args.old_name,
            args.new_name,
            args.root,
            args.scope,
            dry_run=dry_run,
        )
        success_count = sum(1 for r in results if r.success)
        error_count = sum(1 for r in results if not r.success)
        print(f"Scope: {args.scope}")
        print(f"Dry-run: {dry_run}")
        print(f"Total files: {len(results)}")
        print(f"Successes: {success_count}")
        print(f"Errors: {error_count}")

    # bowler commands
    elif args.command == "bowler-rename":
        result = refactor_rename_bowler(args.file, args.old_name, args.new_name, args.dry_run)
        print(f"Tool: {result.tool_used}")
        print(f"Success: {result.success}")
        print(f"Preview: {result.diff_preview}")
        if result.error:
            print(f"Error: {result.error}")

    elif args.command == "bowler-rewrite":
        result = refactor_rewrite_bowler(args.file, args.query, args.replace)
        print(f"Tool: {result.tool_used}")
        print(f"Success: {result.success}")
        print(f"Preview: {result.diff_preview}")
        if result.error:
            print(f"Error: {result.error}")


if __name__ == "__main__":
    main()