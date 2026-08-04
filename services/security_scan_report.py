"""
Security Scan Report Generator
================================

This script scans the services directory for insecure HTTP patterns
and generates a detailed report.

Usage:
    python services/security_scan_report.py
"""

import json
import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

# ------------------------------------------------------------------
# Insecure patterns to detect
# ------------------------------------------------------------------
INSECURE_PATTERNS = {
    # ---- HTTP communication patterns ----
    "urllib_request": {
        "pattern": r"urllib\.request\.(urlopen|Request)",
        "severity": "HIGH",
        "description": "Uses urllib.request which lacks built-in validation and rate limiting",
        "recommendation": "Replace with httpx.Client for safe HTTP communication",
    },
    "subprocess_curl": {
        "pattern": r"subprocess\.run.*(?:curl|wget)",
        "severity": "CRITICAL",
        "description": "Uses subprocess to call curl/wget - command injection risk",
        "recommendation": "Replace with httpx.Client or requests library",
    },
    "subprocess_shell": {
        "pattern": r"subprocess\.run.*shell\s*=\s*True",
        "severity": "CRITICAL",
        "description": "Uses shell=True in subprocess - command injection risk",
        "recommendation": "Remove shell=True and pass command as list",
    },
    "raw_subprocess": {
        "pattern": r"subprocess\.run\s*\(",
        "severity": "MEDIUM",
        "description": "Uses subprocess.run without validation wrapper",
        "recommendation": "Use secure_subprocess wrapper with input validation",
    },
    "httpx_no_timeout": {
        "pattern": r"httpx\.Client\s*\([^)]*\)",
        "negate": r"timeout",
        "severity": "MEDIUM",
        "description": "httpx.Client created without timeout",
        "recommendation": "Always specify timeout for httpx.Client",
    },

    # ---- Prompt injection patterns ----
    "unsafe_prompt_concat": {
        "pattern": r'f["\'].*\{.*\}.*["\'].*(?:prompt|message|content|chat|generate)',
        "negate": r"sanitize|escape|validate|clean|strip|html\.escape|quote",
        "severity": "HIGH",
        "description": "F-string prompt concatenation without sanitization - potential prompt injection vector",
        "recommendation": "Use safe_prompt_template() with input validation",
    },
    "raw_user_input_in_prompt": {
        "pattern": r"(?:prompt|message|content)\s*=\s*(?:request\.|user\.|input\.|data\.)",
        "negate": r"validate|sanitize|clean|escape|strip",
        "severity": "HIGH",
        "description": "Raw user input assigned to prompt/message without validation",
        "recommendation": "Validate and sanitize all user inputs before use in prompts",
    },
    "sql_in_prompt": {
        "pattern": r"(?:SELECT\s+.*FROM|INSERT\s+INTO|UPDATE\s+.*SET|DELETE\s+FROM|DROP\s+TABLE|EXEC\s+sp_|UNION\s+SELECT)",
        "severity": "CRITICAL",
        "description": "SQL injection pattern detected in prompt/text",
        "recommendation": "Never embed raw user input in SQL queries. Use parameterized queries.",
    },
    "xss_in_prompt": {
        "pattern": r"<script[^>]*>|javascript\s*:|onerror\s*=|onload\s*=|<iframe|<object|<embed|<svg\s+on",
        "severity": "CRITICAL",
        "description": "XSS injection pattern detected in prompt/text",
        "recommendation": "Escape HTML entities in user input. Use content security policies.",
    },
    "command_in_prompt": {
        "pattern": r"(?:;|&&|\||\$\(|`|\\n\s*rm|\\n\s*sudo|\\n\s*exec)",
        "negate": r"validate|sanitize|escape|strip|comment|#|docstring|\"\"\"|'''",
        "severity": "CRITICAL",
        "description": "Command injection pattern in prompt/text",
        "recommendation": "Validate and sanitize all user inputs. Never pass raw input to shell.",
    },
    "llm_prompt_unvalidated": {
        "pattern": r"(?:generate|chat|completions|prompt)\s*\(",
        "negate": r"validate|sanitize|clean|escape|strip|security",
        "severity": "HIGH",
        "description": "LLM API call without input validation",
        "recommendation": "Add input validation before LLM API calls",
    },

    # ---- Injection chain patterns (relance/repeated calls) ----
    "chained_api_calls_no_validation": {
        "pattern": r"(?:for|while)\s+.*in.*:\s*\n\s*(?:http|request|call|api)",
        "negate": r"validate|sanitize|check",
        "severity": "HIGH",
        "description": "Loop with multiple API calls without input validation",
        "recommendation": "Validate input before each API call in loops",
    },
    "recursive_api_call": {
        "pattern": r"(?:def|async\s+def)\s+\w+.*\n\s+.*\(\w+\)\s*:",
        "negate": r"base_case|stop|limit|max_depth|depth\s*<",
        "severity": "HIGH",
        "description": "Recursive API call without depth limit - potential infinite loop",
        "recommendation": "Add maximum recursion depth and timeout",
    },
    "batch_request_no_limit": {
        "pattern": r"(?:batch|bulk|parallel)\s*(?:request|call|fetch)",
        "negate": r"limit|max|throttle|rate.?limit",
        "severity": "HIGH",
        "description": "Batch request without rate limiting",
        "recommendation": "Add rate limiting and batch size limits",
    },
    "prompt_chaining_injection": {
        "pattern": r"(?:output|response|result)\s*=\s*.*\n\s+.*prompt\s*=\s*(?:output|response|result)",
        "severity": "CRITICAL",
        "description": "Prompt chaining without sanitization - injection can propagate through chain",
        "recommendation": "Sanitize output before using as input to next prompt",
    },
    "unbounded_prompt_length": {
        "pattern": r"(?:prompt|message|content)\s*[:=]",
        "negate": r"max_length|max|truncate|limit|length\s*<",
        "severity": "MEDIUM",
        "description": "Prompt without length limit - potential resource exhaustion",
        "recommendation": "Add maximum prompt length and truncate oversized inputs",
    },
    "unsafe_model_output_usage": {
        "pattern": r"(?:model|llm|ai)\s*(?:output|response|result)\s*=\s*",
        "negate": r"validate|sanitize|clean|escape|strip|check",
        "severity": "HIGH",
        "description": "Model output used without validation - potential injection from model",
        "recommendation": "Validate and sanitize model outputs before use",
    },
}


@dataclass
class SecurityFinding:
    """A single security finding."""
    file_path: str
    line_number: int
    line_content: str
    pattern_name: str
    severity: str
    description: str
    recommendation: str
    match_text: str


@dataclass
class ScanResult:
    """Complete scan result."""
    total_files_scanned: int = 0
    total_findings: int = 0
    critical_findings: int = 0
    high_findings: int = 0
    medium_findings: int = 0
    low_findings: int = 0
    findings: list[SecurityFinding] = field(default_factory=list)
    scan_directory: str = ""


def scan_file(file_path: Path, patterns: dict) -> list[SecurityFinding]:
    """Scan a single file for insecure patterns."""
    findings = []
    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
        lines = content.split("\n")
        
        for pattern_name, config in patterns.items():
            regex = re.compile(config["pattern"])
            for line_num, line in enumerate(lines, start=1):
                if regex.search(line):
                    # Check negate pattern
                    if "negate" in config and config["negate"]:
                        negate_regex = re.compile(config["negate"])
                        if negate_regex.search(line):
                            continue
                    
                    # Compute relative path from working directory
                    try:
                        rel_path = str(file_path.relative_to(Path("services")))
                    except ValueError:
                        # Fallback: use parent directory name
                        rel_path = str(file_path.parent.name) + "/" + file_path.name
                    
                    finding = SecurityFinding(
                        file_path=rel_path,
                        line_number=line_num,
                        line_content=line.strip(),
                        pattern_name=pattern_name,
                        severity=config["severity"],
                        description=config["description"],
                        recommendation=config["recommendation"],
                        match_text=line.strip(),
                    )
                    findings.append(finding)
    except (OSError, UnicodeDecodeError) as e:
        print(f"Skipping file {file_path}: {e}")
    
    return findings


def scan_directory(directory: Path, patterns: dict) -> ScanResult:
    """Scan a directory recursively for insecure patterns."""
    result = ScanResult(scan_directory=str(directory))
    
    py_files = sorted(list(directory.rglob("*.py")))
    result.total_files_scanned = len(py_files)
    
    for file_path in py_files:
        findings = scan_file(file_path, patterns)
        if findings:
            result.findings.extend(findings)
            result.total_findings += len(findings)
            for f in findings:
                if f.severity == "CRITICAL":
                    result.critical_findings += 1
                elif f.severity == "HIGH":
                    result.high_findings += 1
                elif f.severity == "MEDIUM":
                    result.medium_findings += 1
                else:
                    result.low_findings += 1
    
    return result


def generate_report(result: ScanResult) -> str:
    """Generate a text report from scan results."""
    report = []
    report.append("=" * 70)
    report.append("SECURITY SCAN REPORT")
    report.append("=" * 70)
    report.append("")
    report.append(f"Scan Directory: {result.scan_directory}")
    report.append(f"Total Files Scanned: {result.total_files_scanned}")
    report.append(f"Total Findings: {result.total_findings}")
    report.append(f"  Critical: {result.critical_findings}")
    report.append(f"  High: {result.high_findings}")
    report.append(f"  Medium: {result.medium_findings}")
    report.append(f"  Low: {result.low_findings}")
    report.append("")
    report.append("-" * 70)
    report.append("FINDINGS DETAIL")
    report.append("-" * 70)
    
    for i, f in enumerate(result.findings, 1):
        report.append(f"\n[{i}] Finding: {f.pattern_name}")
        report.append(f"    File: {f.file_path}")
        report.append(f"    Line: {f.line_number}")
        report.append(f"    Severity: {f.severity}")
        report.append(f"    Description: {f.description}")
        report.append(f"    Code: {f.line_content}")
        report.append(f"    Recommendation: {f.recommendation}")
        report.append("-" * 70)
    
    report.append("")
    report.append("=" * 70)
    report.append("SECURE REPLACEMENT PATTERNS")
    report.append("=" * 70)
    report.append("")
    
    report.append("""
# Pattern 1: Replace urllib.request with httpx
# BEFORE:
import httpx
with httpx.Client(timeout=30).get(url) as response:
    data = json.loads(response.read())

# AFTER:
import httpx
with httpx.Client(timeout=30) as client:
    response = client.get(url)
    response.raise_for_status()
    data = response.json()

# Pattern 2: Replace subprocess curl with httpx
# BEFORE:
httpx.Client(timeout=30).post(url, json=payload, headers=headers)

# AFTER:
import httpx
with httpx.Client(timeout=30) as client:
    response = client.post(url, json=payload, headers=headers)
    response.raise_for_status()

# Pattern 3: Secure subprocess wrapper
def secure_subprocess(cmd: list[str], timeout: int = 30) -> subprocess.CompletedProcess:
    dangerous = ["rm -rf", "sudo", "exec(", "system("]
    for d in dangerous:
        if d in str(cmd):
            raise ValueError(f"Dangerous operation detected: {d}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=True)
    return result
""")
    
    report.append("")
    report.append("=" * 70)
    report.append("INTEGRATION RECOMMENDATIONS")
    report.append("=" * 70)
    report.append("")
    report.append("""
1. Replace all urllib.request calls with httpx.Client
2. Add input validation to all FastAPI endpoints using Pydantic
3. Add rate limiting middleware to all FastAPI apps
4. Add security headers middleware to all FastAPI apps
5. Use secure_subprocess wrapper for all subprocess calls
6. Always specify timeout for httpx.Client
7. Review all subprocess.run calls for shell injection risks
8. Add security scanning to CI/CD pipeline
""")
    
    report.append("")
    report.append("=" * 70)
    report.append("END OF REPORT")
    report.append("=" * 70)
    
    return "\n".join(report)


def main():
    """Run the security scan and generate report."""
    # Use absolute path
    services_dir = Path(__file__).parent
    
    print(f"Scanning {services_dir}...")
    result = scan_directory(services_dir, INSECURE_PATTERNS)
    
    report = generate_report(result)
    
    # Print report
    print(report)
    
    # Save report to file
    report_path = services_dir / "security_scan_report.txt"
    report_path.write_text(report, encoding="utf-8")
    print(f"\nReport saved to: {report_path}")
    
    # Save JSON findings
    json_data = {
        "scan_directory": result.scan_directory,
        "total_files_scanned": result.total_files_scanned,
        "total_findings": result.total_findings,
        "critical": result.critical_findings,
        "high": result.high_findings,
        "medium": result.medium_findings,
        "low": result.low_findings,
        "findings": [
            {
                "file": f.file_path,
                "line": f.line_number,
                "severity": f.severity,
                "pattern": f.pattern_name,
                "description": f.description,
                "recommendation": f.recommendation,
                "code": f.line_content,
            }
            for f in result.findings
        ],
    }
    
    json_path = services_dir / "security_scan_findings.json"
    json_path.write_text(json.dumps(json_data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"JSON findings saved to: {json_path}")


if __name__ == "__main__":
    main()