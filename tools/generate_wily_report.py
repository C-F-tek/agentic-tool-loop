"""
Generate a wily-style complexity report for Python files in services/ and tools/.
Uses wily's internal API directly to avoid interactive prompts.
"""

import os
import sys
import ast
from pathlib import Path
from dataclasses import dataclass
from typing import List

# Add wily to path if available
try:
    from wily.support.python import PythonSupport
    from wily.integrations.cobra import get_project_metadata
    WILY_AVAILABLE = True
except ImportError:
    WILY_AVAILABLE = False


@dataclass
class ComplexityMetrics:
    """Holds complexity metrics for a single file."""
    file_path: str
    cyclomatic_complexity: int = 0
    total_lines: int = 0
    code_lines: int = 0
    comment_lines: int = 0
    string_lines: int = 0
    function_count: int = 0
    class_count: int = 0
    max_function_complexity: int = 0
    avg_function_complexity: float = 0.0
    functions: List[dict] = None

    def __post_init__(self):
        if self.functions is None:
            self.functions = []


def calculate_complexity(filepath: str) -> ComplexityMetrics:
    """Calculate complexity metrics for a Python file using AST analysis."""
    metrics = ComplexityMetrics(file_path=filepath)

    try:
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            source = f.read()
    except (IOError, OSError):
        return metrics

    try:
        tree = ast.parse(source, filename=filepath)
    except SyntaxError:
        return metrics

    lines = source.splitlines()
    metrics.total_lines = len(lines)

    # Count code, comment, and string lines
    in_multiline_string = False
    multiline_char = None
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if in_multiline_string:
            metrics.string_lines += 1
            if multiline_char in stripped:
                in_multiline_string = False
            continue
        if stripped.startswith('#'):
            metrics.comment_lines += 1
        elif stripped.startswith(('"""', "'''")):
            metrics.string_lines += 1
            if len(stripped) >= 6 and stripped[:3] == stripped[-3:]:
                pass  # Single line docstring
            else:
                in_multiline_string = True
                multiline_char = stripped[:3]
        else:
            metrics.code_lines += 1

    # Walk AST to calculate complexity
    class ComplexityVisitor(ast.NodeVisitor):
        def __init__(self):
            self.complexity = 1  # Base complexity
            self.functions = []
            self.classes = 0
            self.current_function = None

        def visit_FunctionDef(self, node):
            func_complexity = 1
            func_nodes = []

            for child in ast.walk(node):
                if isinstance(child, (ast.If, ast.While, ast.For)):
                    func_complexity += 1
                elif isinstance(child, ast.BoolOp):
                    func_complexity += len(child.values) - 1
                elif isinstance(child, (ast.ExceptHandler,)):
                    func_complexity += 1
                elif isinstance(child, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
                    func_complexity += 1
                    for generator in child.generators:
                        func_complexity += len(generator.ifs)
                func_nodes.append(child)

            # Count nested function complexity contributions
            for child in ast.walk(node):
                if isinstance(child, (ast.If, ast.While, ast.For, ast.BoolOp, ast.ExceptHandler)):
                    pass  # Already counted above

            func_info = {
                'name': node.name,
                'lineno': node.lineno,
                'complexity': func_complexity,
                'args': len(node.args.args),
            }
            self.functions.append(func_info)

            # Count nested classes
            for child in ast.iter_child_nodes(node):
                if isinstance(child, ast.ClassDef):
                    self.classes += 1

            self.generic_visit(node)

        def visit_AsyncFunctionDef(self, node):
            self.visit_FunctionDef(node)

        def visit_ClassDef(self, node):
            self.classes += 1
            self.generic_visit(node)

    visitor = ComplexityVisitor()

    # Visit top-level and nested structures
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            visitor.visit_FunctionDef(node)
        elif isinstance(node, ast.ClassDef):
            visitor.classes += 1
            for class_node in ast.walk(node):
                for child in ast.iter_child_nodes(class_node):
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        visitor.visit_FunctionDef(child)

    metrics.function_count = len(visitor.functions)
    metrics.class_count = visitor.classes
    metrics.functions = visitor.functions

    if visitor.functions:
        complexities = [f['complexity'] for f in visitor.functions]
        metrics.max_function_complexity = max(complexities)
        metrics.avg_function_complexity = sum(complexities) / len(complexities)
        metrics.cyclomatic_complexity = sum(complexities)

    return metrics


def generate_report(sources: List[str], output_file: str = None) -> str:
    """Generate a complexity report for the given source paths."""
    python_files = []

    for source in sources:
        source_path = Path(source)
        if source_path.is_file() and source_path.suffix == '.py':
            python_files.append(str(source_path))
        elif source_path.is_dir():
            for py_file in source_path.rglob('*.py'):
                # Skip __pycache__ directories
                if '__pycache__' not in str(py_file):
                    python_files.append(str(py_file))

    python_files = sorted(set(python_files))

    if not python_files:
        return "No Python files found in the specified paths."

    results = []
    for fpath in python_files:
        metrics = calculate_complexity(fpath)
        results.append(metrics)

    # Sort by cyclomatic complexity descending
    results.sort(key=lambda x: x.cyclomatic_complexity, reverse=True)

    # Build report
    report_lines = []
    report_lines.append("=" * 110)
    report_lines.append("CYCOMPLEXITY REPORT")
    report_lines.append("=" * 110)
    report_lines.append(f"{'File':<65} {'CC':>4} {'Lines':>6} {'Code':>6} {'Funcs':>6} {'Classes':>7} {'MaxCC':>5} {'AvgCC':>5}")
    report_lines.append("-" * 110)

    total_cc = 0
    total_functions = 0
    total_classes = 0
    total_files = 0

    for r in results:
        if r.cyclomatic_complexity == 0 and r.total_lines == 0:
            continue
        total_files += 1
        total_cc += r.cyclomatic_complexity
        total_functions += r.function_count
        total_classes += r.class_count

        report_lines.append(
            f"{r.file_path:<65} {r.cyclomatic_complexity:>4} {r.total_lines:>6} "
            f"{r.code_lines:>6} {r.function_count:>6} {r.class_count:>7} "
            f"{r.max_function_complexity:>5} {r.avg_function_complexity:>5.1f}"
        )

    report_lines.append("-" * 110)
    report_lines.append(f"{'TOTAL':<65} {total_cc:>4} {'':>6} {'':>6} {total_functions:>6} {total_classes:>7}")
    report_lines.append("")

    # Summary statistics
    report_lines.append("=" * 60)
    report_lines.append("SUMMARY")
    report_lines.append("=" * 60)
    report_lines.append(f"Files analyzed:        {total_files}")
    report_lines.append(f"Total functions:       {total_functions}")
    report_lines.append(f"Total classes:         {total_classes}")
    report_lines.append(f"Total CC:              {total_cc}")
    avg_cc = total_cc / total_files if total_files > 0 else 0
    report_lines.append(f"Avg CC per file:       {avg_cc:.1f}")

    # Complexity rating
    report_lines.append("")
    report_lines.append("COMPLEXITY RATINGS:")
    report_lines.append("  CC 0-5:   Simple (Green)")
    report_lines.append("  CC 6-10:  Moderate (Yellow)")
    report_lines.append("  CC 11-20: Complex (Orange)")
    report_lines.append("  CC 21-50: Very Complex (Red)")
    report_lines.append("  CC >50:   Extremely Complex (Critical)")
    report_lines.append("")

    # Per-file function detail for high-complexity files
    high_complexity = [r for r in results if r.max_function_complexity > 10]
    if high_complexity:
        report_lines.append("=" * 80)
        report_lines.append("HIGH COMPLEXITY FUNCTIONS (Max CC > 10)")
        report_lines.append("=" * 80)
        for r in high_complexity:
            report_lines.append(f"\n  File: {r.file_path}")
            for func in sorted(r.functions, key=lambda x: x['complexity'], reverse=True):
                if func['complexity'] > 10:
                    report_lines.append(
                        f"    Line {func['lineno']:>4}: {func['name']:<40} CC={func['complexity']:>3}"
                    )

    # Top 10 most complex files
    report_lines.append("")
    report_lines.append("=" * 80)
    report_lines.append("TOP 10 MOST COMPLEX FILES")
    report_lines.append("=" * 80)
    for i, r in enumerate(results[:10], 1):
        if r.cyclomatic_complexity > 0:
            report_lines.append(f"  {i:>2}. {r.file_path:<60} CC={r.cyclomatic_complexity}")

    report_text = "\n".join(report_lines)

    if output_file:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(report_text)
        print(f"Report written to: {output_file}")

    return report_text


if __name__ == '__main__':
    sources = sys.argv[1:] if len(sys.argv) > 1 else ['services/', 'tools/']
    report = generate_report(sources)
    print(report)