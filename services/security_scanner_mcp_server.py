"""
Security Scanner MCP Server
============================

This MCP server provides tools to scan the codebase for insecure HTTP patterns
and provide recommendations for secure replacements.

Usage:
    python services/security_scanner_mcp_server.py

The server starts on http://127.0.0.1:8081 by default.
"""

import json
import re
import sys
import logging
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
import uvicorn

# ------------------------------------------------------------------
# Logging setup
# ------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("security_scanner_mcp")

# ------------------------------------------------------------------
# Insecure patterns to detect
# ------------------------------------------------------------------
INSECURE_PATTERNS = {
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
    "no_rate_limit": {
        "pattern": r"(?:FastAPI|app)\s*=",
        "negate": r"rate.?limit|rate_limit",
        "severity": "HIGH",
        "description": "FastAPI app without rate limiting",
        "recommendation": "Add rate limiting middleware",
    },
    "no_validation": {
        "pattern": r"(?:FastAPI|app)\s*=",
        "negate": r"validator|validate|pydantic",
        "severity": "HIGH",
        "description": "FastAPI app without input validation",
        "recommendation": "Add Pydantic validators for all endpoints",
    },
    "no_security_headers": {
        "pattern": r"response\.headers",
        "negate": r"X-Content-Type|X-Frame|X-XSS|Content-Security",
        "severity": "MEDIUM",
        "description": "Response without security headers",
        "recommendation": "Add security headers middleware",
    },
}

# ------------------------------------------------------------------
# Data classes for scan results
# ------------------------------------------------------------------
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

# ------------------------------------------------------------------
# FastAPI app
# ------------------------------------------------------------------
app = FastAPI(
    title="Security Scanner MCP Server",
    description="Scan codebase for insecure HTTP patterns and provide secure alternatives.",
    version="1.0.0",
)


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
                    
                    finding = SecurityFinding(
                        file_path=str(file_path.relative_to(Path("services"))),
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
        logger.warning(f"Skipping file {file_path}: {e}")
    
    return findings


def scan_directory(directory: Path, patterns: dict) -> ScanResult:
    """Scan a directory recursively for insecure patterns."""
    result = ScanResult(scan_directory=str(directory))
    
    py_files = list(directory.rglob("*.py"))
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


def generate_secure_replacement(pattern_name: str, original_code: str) -> str:
    """Generate a secure replacement for an insecure pattern."""
    replacements = {
        "urllib_request": """import httpx

def secure_http_call(url: str, data: dict, timeout: int = 30) -> dict:
    \"\"\"Safe HTTP call using httpx.\"\"\"
    with httpx.Client(timeout=timeout) as client:
        response = client.post(url, json=data)
        response.raise_for_status()
        return response.json() if response.content else {}
""",
        "subprocess_curl": """import httpx

def secure_api_call(url: str, data: dict, timeout: int = 30) -> dict:
    \"\"\"Replace subprocess curl with secure httpx call.\"\"\"
    headers = {"Content-Type": "application/json"}
    with httpx.Client(timeout=timeout) as client:
        response = client.post(url, json=data, headers=headers)
        response.raise_for_status()
        return response.json() if response.content else {}
""",
        "subprocess_shell": """# Replace:
# subprocess.run(cmd, shell=True)
# With:
subprocess.run(["command", "arg1", "arg2"], check=True, capture_output=True, text=True)
""",
        "raw_subprocess": """import subprocess
from typing import Optional

def secure_subprocess(cmd: list[str], input_data: Optional[str] = None, timeout: int = 30) -> subprocess.CompletedProcess:
    \"\"\"Safe subprocess wrapper with validation.\"\"\"
    # Validate command components
    dangerous = ["rm -rf", "sudo", "exec(", "system("]
    for d in dangerous:
        if d in str(input_data or ""):
            raise ValueError(f"Dangerous operation detected: {d}")
    
    result = subprocess.run(cmd, input=input_data, capture_output=True, text=True, timeout=timeout)
    result.check_returncode()
    return result
""",
        "httpx_no_timeout": """# Always specify timeout:
with httpx.Client(timeout=httpx.Timeout(30.0, connect=5.0)) as client:
    response = client.get(url)
""",
    }
    
    return replacements.get(pattern_name, "# No automatic replacement available")


# ------------------------------------------------------------------
# API Endpoints
# ------------------------------------------------------------------
@app.get("/scan")
async def scan_codebase(directory: str = "services"):
    """Scan the codebase for insecure HTTP patterns."""
    target = Path(directory)
    if not target.exists():
        raise HTTPException(status_code=404, detail=f"Directory not found: {directory}")
    
    logger.info(f"Scanning {directory}...")
    result = scan_directory(target, INSECURE_PATTERNS)
    
    return {
        "status": "complete",
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


@app.get("/findings/{finding_id}")
async def get_finding(finding_id: int):
    """Get details for a specific finding."""
    target = Path("services")
    result = scan_directory(target, INSECURE_PATTERNS)
    
    if 0 <= finding_id < len(result.findings):
        f = result.findings[finding_id]
        return {
            "id": finding_id,
            "file": f.file_path,
            "line": f.line_number,
            "severity": f.severity,
            "pattern": f.pattern_name,
            "description": f.description,
            "recommendation": f.recommendation,
            "code": f.line_content,
            "secure_replacement": generate_secure_replacement(f.pattern_name, f.line_content),
        }
    
    raise HTTPException(status_code=404, detail=f"Finding not found: {finding_id}")


@app.get("/summary")
async def get_scan_summary():
    """Get a summary of security posture."""
    target = Path("services")
    result = scan_directory(target, INSECURE_PATTERNS)
    
    return {
        "security_score": max(0, 100 - (result.critical_findings * 20 + result.high_findings * 10 + result.medium_findings * 5)),
        "total_findings": result.total_findings,
        "critical_issues": result.critical_findings,
        "high_issues": result.high_findings,
        "medium_issues": result.medium_findings,
        "recommendation": "Replace all urllib.request calls with httpx.Client and add input validation to all endpoints.",
    }


@app.post("/scan-pattern")
async def scan_specific_pattern(pattern_name: str):
    """Scan for a specific pattern."""
    if pattern_name not in INSECURE_PATTERNS:
        raise HTTPException(status_code=400, detail=f"Unknown pattern: {pattern_name}")
    
    target = Path("services")
    result = scan_directory(target, {pattern_name: INSECURE_PATTERNS[pattern_name]})
    
    return {
        "pattern": pattern_name,
        "findings": [
            {
                "file": f.file_path,
                "line": f.line_number,
                "code": f.line_content,
            }
            for f in result.findings
        ],
    }


if __name__ == "__main__":
    uvicorn.run(
        __file__,
        host="127.0.0.1",
        port=8081,
        reload=False,
        log_level="info",
    )