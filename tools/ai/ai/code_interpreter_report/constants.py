"""Constants for static code interpreter reports."""

from __future__ import annotations

import ast
import re

REPORT_KIND = "code_interpreter_report"
DEFAULT_OUTPUT = "output/analysis/code_interpreter_report.json"
DEFAULT_MARKDOWN = "output/analysis/code_interpreter_report.md"
DEFAULT_EXCLUDED_DIRS = {
    ".git",
    ".hg",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "output",
    "renders",
    "venv",
}
RISK_CALLS = {
    "eval": "dynamic_code_execution",
    "exec": "dynamic_code_execution",
    "compile": "dynamic_code_compilation",
    "open": "file_io",
    "subprocess.run": "subprocess_execution",
    "subprocess.Popen": "subprocess_execution",
    "os.system": "shell_execution",
    "shutil.rmtree": "destructive_file_operation",
}
TODO_PATTERN = re.compile(r"\b(TODO|FIXME|HACK|XXX)\b", re.IGNORECASE)
BRANCH_NODES = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.ExceptHandler, ast.BoolOp, ast.IfExp, ast.Match)
