"""
Security Audit: Injection Point Analysis

This module provides a comprehensive audit of all potential injection points
across the services directory, categorizing them by risk level and type.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class InjectionPoint:
    """Represents a potential injection vulnerability."""
    file_path: str
    line_number: int
    injection_type: str  # 'sql', 'command', 'path', 'xss', 'format'
    severity: str  # 'high', 'medium', 'low'
    description: str
    pattern: str
    safe: bool = False
    remediation: str = ""


# ---------------------------------------------------------------------------
# SQL Injection Points
# ---------------------------------------------------------------------------

SQL_INJECTION_PATTERNS = [
    # f-string formatted SQL queries (HIGH RISK)
    (
        r'conn\.execute\s*\(\s*f["\'].*WHERE.*\{',
        'f-string SQL WHERE clause',
        'high',
        'Use parameterized queries with ? placeholders instead of f-strings'
    ),
    (
        r'conn\.execute\s*\(\s*f["\'].*DELETE.*\{',
        'f-string SQL DELETE clause',
        'high',
        'Validate table names with sanitize_sql_identifier() and use ? placeholders'
    ),
    (
        r'conn\.execute\s*\(\s*f["\'].*INSERT.*\{',
        'f-string SQL INSERT clause',
        'high',
        'Use parameterized queries with ? placeholders'
    ),
    (
        r'conn\.execute\s*\(\s*f["\'].*UPDATE.*\{',
        'f-string SQL UPDATE clause',
        'high',
        'Use parameterized queries with ? placeholders'
    ),
    # String concatenation in SQL (HIGH RISK)
    (
        r'query\s*=\s*f["\'].*SELECT.*FROM.*\{',
        'String concatenation in SELECT query',
        'high',
        'Sanitize table/column names and use parameterized queries'
    ),
    # os.system() with user input (CRITICAL)
    (
        r'os\.system\s*\(',
        'os.system() call',
        'critical',
        'Replace with subprocess.run() using shell=False and sanitized arguments'
    ),
]

# ---------------------------------------------------------------------------
# Command Injection Points
# ---------------------------------------------------------------------------

COMMAND_INJECTION_PATTERNS = [
    # subprocess with shell=True (CRITICAL)
    (
        r'subprocess\.(run|Popen)\([^)]*shell\s*=\s*True',
        'subprocess with shell=True',
        'critical',
        'Always use shell=False and pass arguments as a list'
    ),
    # os.system() (CRITICAL)
    (
        r'os\.system\s*\(',
        'os.system() call',
        'critical',
        'Replace with subprocess.run() using shell=False'
    ),
    # os.popen() (CRITICAL)
    (
        r'os\.popen\s*\(',
        'os.popen() call',
        'critical',
        'Replace with subprocess.run() using shell=False'
    ),
    # eval()/exec() (CRITICAL)
    (
        r'\b(?:eval|exec)\s*\(',
        'eval()/exec() call',
        'critical',
        'Never use eval()/exec() with user-supplied input'
    ),
]

# ---------------------------------------------------------------------------
# Path Traversal Points
# ---------------------------------------------------------------------------

PATH_TRAVERSAL_PATTERNS = [
    # Unvalidated path joins
    (
        r'os\.path\.join\s*\([^)]*\)',
        'os.path.join() without validation',
        'medium',
        'Validate resolved path is within allowed base directory'
    ),
    # User input in file paths
    (
        r'Path\s*\([^)]*user',
        'Path created from user input',
        'medium',
        'Use sanitize_file_path() to validate paths'
    ),
]

# ---------------------------------------------------------------------------
# XSS/HTML Injection Points
# ---------------------------------------------------------------------------

XSS_PATTERNS = [
    # Unescaped HTML output
    (
        r'f["\'].*<html|f["\'].*<div|f["\'].*<script',
        'f-string HTML output without escaping',
        'medium',
        'Use escape_html() for all user-supplied content in HTML output'
    ),
    # format() in HTML context
    (
        r'\.format\s*\([^)]*\).*<html|\.format\s*\([^)]*\).*<div',
        '.format() in HTML context without escaping',
        'medium',
        'Use escape_html() for user-supplied content'
    ),
]

# ---------------------------------------------------------------------------
# Format String Vulnerabilities
# ---------------------------------------------------------------------------

FORMAT_PATTERNS = [
    # .format() with user input
    (
        r'\.format\s*\([^)]*user[^)]*\)',
        '.format() with user input',
        'low',
        'Consider using parameterized alternatives or validation'
    ),
    # % formatting with user input
    (
        r'%\s*\([^)]*user',
        '% formatting with user input',
        'low',
        'Consider using parameterized alternatives or validation'
    ),
]


def audit_sql_injection_points() -> list[InjectionPoint]:
    """Audit SQL injection points across the services directory."""
    points = []
    services_root = Path(__file__).parent.parent
    
    for py_file in services_root.rglob('*.py'):
        try:
            content = py_file.read_text(encoding='utf-8')
            lines = content.split('\n')
            
            for pattern, description, severity, remediation in SQL_INJECTION_PATTERNS:
                for i, line in enumerate(lines, 1):
                    if re.search(pattern, line):
                        points.append(InjectionPoint(
                            file_path=str(py_file.relative_to(services_root)),
                            line_number=i,
                            injection_type='sql',
                            severity=severity,
                            description=description,
                            pattern=line.strip(),
                            safe=False,
                            remediation=remediation
                        ))
        except (OSError, UnicodeDecodeError):
            continue
    
    return points


def audit_command_injection_points() -> list[InjectionPoint]:
    """Audit command injection points across the services directory."""
    points = []
    services_root = Path(__file__).parent.parent
    
    for py_file in services_root.rglob('*.py'):
        try:
            content = py_file.read_text(encoding='utf-8')
            lines = content.split('\n')
            
            for pattern, description, severity, remediation in COMMAND_INJECTION_PATTERNS:
                for i, line in enumerate(lines, 1):
                    if re.search(pattern, line):
                        points.append(InjectionPoint(
                            file_path=str(py_file.relative_to(services_root)),
                            line_number=i,
                            injection_type='command',
                            severity=severity,
                            description=description,
                            pattern=line.strip(),
                            safe=False,
                            remediation=remediation
                        ))
        except (OSError, UnicodeDecodeError):
            continue
    
    return points


def audit_path_traversal_points() -> list[InjectionPoint]:
    """Audit path traversal points across the services directory."""
    points = []
    services_root = Path(__file__).parent.parent
    
    for py_file in services_root.rglob('*.py'):
        try:
            content = py_file.read_text(encoding='utf-8')
            lines = content.split('\n')
            
            for pattern, description, severity, remediation in PATH_TRAVERSAL_PATTERNS:
                for i, line in enumerate(lines, 1):
                    if re.search(pattern, line):
                        points.append(InjectionPoint(
                            file_path=str(py_file.relative_to(services_root)),
                            line_number=i,
                            injection_type='path',
                            severity=severity,
                            description=description,
                            pattern=line.strip(),
                            safe=False,
                            remediation=remediation
                        ))
        except (OSError, UnicodeDecodeError):
            continue
    
    return points


def audit_xss_points() -> list[InjectionPoint]:
    """Audit XSS/HTML injection points across the services directory."""
    points = []
    services_root = Path(__file__).parent.parent
    
    for py_file in services_root.rglob('*.py'):
        try:
            content = py_file.read_text(encoding='utf-8')
            lines = content.split('\n')
            
            for pattern, description, severity, remediation in XSS_PATTERNS:
                for i, line in enumerate(lines, 1):
                    if re.search(pattern, line):
                        points.append(InjectionPoint(
                            file_path=str(py_file.relative_to(services_root)),
                            line_number=i,
                            injection_type='xss',
                            severity=severity,
                            description=description,
                            pattern=line.strip(),
                            safe=False,
                            remediation=remediation
                        ))
        except (OSError, UnicodeDecodeError):
            continue
    
    return points


def audit_format_vulnerabilities() -> list[InjectionPoint]:
    """Audit format string vulnerabilities across the services directory."""
    points = []
    services_root = Path(__file__).parent.parent
    
    for py_file in services_root.rglob('*.py'):
        try:
            content = py_file.read_text(encoding='utf-8')
            lines = content.split('\n')
            
            for pattern, description, severity, remediation in FORMAT_PATTERNS:
                for i, line in enumerate(lines, 1):
                    if re.search(pattern, line):
                        points.append(InjectionPoint(
                            file_path=str(py_file.relative_to(services_root)),
                            line_number=i,
                            injection_type='format',
                            severity=severity,
                            description=description,
                            pattern=line.strip(),
                            safe=False,
                            remediation=remediation
                        ))
        except (OSError, UnicodeDecodeError):
            continue
    
    return points


def generate_audit_report() -> dict[str, Any]:
    """Generate a comprehensive security audit report."""
    sql_points = audit_sql_injection_points()
    cmd_points = audit_command_injection_points()
    path_points = audit_path_traversal_points()
    xss_points = audit_xss_points()
    format_points = audit_format_vulnerabilities()
    
    all_points = sql_points + cmd_points + path_points + xss_points + format_points
    
    # Count by severity
    critical_count = sum(1 for p in all_points if p.severity == 'critical')
    high_count = sum(1 for p in all_points if p.severity == 'high')
    medium_count = sum(1 for p in all_points if p.severity == 'medium')
    low_count = sum(1 for p in all_points if p.severity == 'low')
    
    # Count by type
    sql_count = len(sql_points)
    cmd_count = len(cmd_points)
    path_count = len(path_points)
    xss_count = len(xss_points)
    format_count = len(format_points)
    
    return {
        'total_points': len(all_points),
        'critical': critical_count,
        'high': high_count,
        'medium': medium_count,
        'low': low_count,
        'by_type': {
            'sql_injection': sql_count,
            'command_injection': cmd_count,
            'path_traversal': path_count,
            'xss': xss_count,
            'format_vulnerability': format_count,
        },
        'points': [
            {
                'file': p.file_path,
                'line': p.line_number,
                'type': p.injection_type,
                'severity': p.severity,
                'description': p.description,
                'pattern': p.pattern[:200],
                'safe': p.safe,
                'remediation': p.remediation,
            }
            for p in all_points
        ],
    }


if __name__ == '__main__':
    import json
    report = generate_audit_report()
    print(json.dumps(report, indent=2, default=str))