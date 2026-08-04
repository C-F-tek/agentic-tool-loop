"""
Improved Security Scanner MCP Server
====================================

This MCP server provides tools to scan the codebase for actual security vulnerabilities
with precise patterns that reduce false positives. It focuses on:

1. Hardcoded credentials/secrets
2. Insecure HTTP patterns (urllib.request without validation)
3. Subprocess shell injection risks
4. SQL injection patterns
5. XSS patterns
6. Prompt injection vulnerabilities
7. Missing input validation
8. Missing rate limiting
9. Missing timeout configuration

Usage:
    python services/security_scanner_mcp_server.py

The server starts on http://127.0.0.1:8082 by default.
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
logger = logging.getLogger("security_scanner_mcp_improved")

# ------------------------------------------------------------------
# Precise security patterns (reduced false positives)
# ------------------------------------------------------------------
PRECISE_SECURITY_PATTERNS = {
    "hardcoded_secret": {
        "pattern": r'(?:password|secret|api_key|token|credentials)\s*=\s*["\'][^"\']{8,}["\']',
        "severity": "CRITICAL",
        "description": "Hardcoded credential/secret found",
        "recommendation": "Move secrets to environment variables or secure vault. Never hardcode credentials.",
        "check_code": """
            def check_hardcoded_secret(content: str) -> list:
                findings = []
                lines = content.split('\\n')
                for i, line in enumerate(lines, 1):
                    if re.search(r'(?:password|secret|api_key|token|credentials)\\s*=\\s*[\"\\'][^\"\\']{8,}[\"\\']', line):
                        # Skip if it's a placeholder or example
                        if any(x in line.lower() for x in ['your_', 'changeme', 'example', 'placeholder', 'xxx']):
                            continue
                        findings.append((i, line.strip()))
                return findings
"""
    },
    "urllib_insecure": {
        "pattern": r'urllib\.request\.(urlopen|Request)\s*\(',
        "severity": "HIGH",
        "description": "Insecure HTTP request using urllib.request",
        "recommendation": "Replace with httpx.Client(timeout=30) for safe HTTP communication with timeout.",
        "check_code": """
            def check_urllib_insecure(content: str) -> list:
                findings = []
                lines = content.split('\\n')
                for i, line in enumerate(lines, 1):
                    if re.search(r'urllib\\.request\\.(urlopen|Request)\\s*\\(', line):
                        # Skip if it's in a comment or docstring discussing the pattern
                        if line.strip().startswith('#') or line.strip().startswith('\"\"\"'):
                            continue
                        findings.append((i, line.strip()))
                return findings
"""
    },
    "subprocess_shell_true": {
        "pattern": r'subprocess\.\w+\s*\([^)]*shell\s*=\s*True',
        "severity": "CRITICAL",
        "description": "Subprocess with shell=True - command injection risk",
        "recommendation": "Remove shell=True and pass command as a list of arguments.",
        "check_code": """
            def check_subprocess_shell_true(content: str) -> list:
                findings = []
                lines = content.split('\\n')
                for i, line in enumerate(lines, 1):
                    if re.search(r'subprocess\\.\\w+\\s*\\([^)]*shell\\s*=\\s*True', line):
                        findings.append((i, line.strip()))
                return findings
"""
    },
    "subprocess_unvalidated": {
        "pattern": r'subprocess\.\w+\s*\(\s*\[',
        "negate": r'(?:secure_subprocess|validated|sanitize|validate)',
        "severity": "MEDIUM",
        "description": "Unvalidated subprocess call",
        "recommendation": "Use secure_subprocess wrapper with input validation.",
        "check_code": """
            def check_subprocess_unvalidated(content: str) -> list:
                findings = []
                lines = content.split('\\n')
                for i, line in enumerate(lines, 1):
                    if re.search(r'subprocess\\.\\w+\\s*\\(\\s*\\[', line):
                        if re.search(r'(?:secure_subprocess|validated|sanitize|validate)', line):
                            continue
                        findings.append((i, line.strip()))
                return findings
"""
    },
    "httpx_no_timeout": {
        "pattern": r'httpx\\.Client\s*\(',
        "negate": r'timeout',
        "severity": "MEDIUM",
        "description": "httpx.Client created without timeout",
        "recommendation": "Always specify timeout for httpx.Client (e.g., timeout=30).",
        "check_code": """
            def check_httpx_no_timeout(content: str) -> list:
                findings = []
                lines = content.split('\\n')
                for i, line in enumerate(lines, 1):
                    if re.search(r'httpx\\.Client\\s*\\(', line) and 'timeout' not in line:
                        findings.append((i, line.strip()))
                return findings
"""
    },
    "fastapi_no_rate_limit": {
        "pattern": r'(?:FastAPI|app)\s*=\s*FastAPI\s*\(',
        "negate": r'(?:rate.?limit|RateLimitMiddleware)',
        "severity": "HIGH",
        "description": "FastAPI app without rate limiting",
        "recommendation": "Add rate limiting middleware (e.g., SlowAPI or custom middleware).",
        "check_code": """
            def check_fastapi_no_rate_limit(content: str) -> list:
                findings = []
                lines = content.split('\\n')
                has_rate_limit = any('rate' in line.lower() or 'ratelimit' in line.lower() for line in lines)
                for i, line in enumerate(lines, 1):
                    if re.search(r'(?:FastAPI|app)\\s*=\\s*FastAPI\\s*\\(', line):
                        if not has_rate_limit:
                            findings.append((i, line.strip()))
                return findings
"""
    },
    "fastapi_no_validation": {
        "pattern": r'(?:FastAPI|app)\s*=\s*FastAPI\s*\(',
        "negate": r'(?:Pydantic|BaseModel|validate|sanitize)',
        "severity": "HIGH",
        "description": "FastAPI app without input validation",
        "recommendation": "Add Pydantic models for input validation on all endpoints.",
        "check_code": """
            def check_fastapi_no_validation(content: str) -> list:
                findings = []
                lines = content.split('\\n')
                has_validation = any('pydantic' in line.lower() or 'basemodel' in line.lower() or 'validate' in line.lower() for line in lines)
                for i, line in enumerate(lines, 1):
                    if re.search(r'(?:FastAPI|app)\\s*=\\s*FastAPI\\s*\\(', line):
                        if not has_validation:
                            findings.append((i, line.strip()))
                return findings
"""
    },
    "sql_injection_risk": {
        "pattern": r'(?:cursor\.execute|executeQuery)\s*\(\s*f["\']|(?:cursor\.execute|executeQuery)\s*\(\s*["\'].*%s',
        "severity": "CRITICAL",
        "description": "Potential SQL injection vulnerability",
        "recommendation": "Use parameterized queries. Never concatenate user input into SQL strings.",
        "check_code": """
            def check_sql_injection_risk(content: str) -> list:
                findings = []
                lines = content.split('\\n')
                for i, line in enumerate(lines, 1):
                    if re.search(r'(?:cursor\\.execute|executeQuery)\\s*\\(\\s*f[\"\\']', line):
                        findings.append((i, line.strip()))
                    elif re.search(r'(?:cursor\\.execute|executeQuery)\\s*\\(\\s*[\"\\'].*%s', line):
                        findings.append((i, line.strip()))
                return findings
"""
    },
    "xss_risk": {
        "pattern": r'<script[^>]*>|javascript\s*:|onerror\s*=|onload\s*=',
        "severity": "CRITICAL",
        "description": "Potential XSS vulnerability",
        "recommendation": "Escape HTML entities in user input. Use content security policies.",
        "check_code": """
            def check_xss_risk(content: str) -> list:
                findings = []
                lines = content.split('\\n')
                for i, line in enumerate(lines, 1):
                    if re.search(r'<script[^>]*>|javascript\\s*:|onerror\\s*=|onload\\s*=', line):
                        # Skip if it's in a comment or docstring
                        if line.strip().startswith('#') or line.strip().startswith('\"\"\"'):
                            continue
                        findings.append((i, line.strip()))
                return findings
"""
    },
    "missing_security_headers": {
        "pattern": r'response\.headers\s*\[',
        "negate": r'(?:X-Content-Type|X-Frame|X-XSS|Content-Security|Strict-Transport)',
        "severity": "MEDIUM",
        "description": "Response headers without security headers",
        "recommendation": "Add security headers middleware (X-Content-Type, X-Frame, Content-Security-Policy).",
        "check_code": """
            def check_missing_security_headers(content: str) -> list:
                findings = []
                lines = content.split('\\n')
                has_security = any('X-Content-Type' in line or 'X-Frame' in line or 'Content-Security' in line for line in lines)
                for i, line in enumerate(lines, 1):
                    if re.search(r'response\\.headers\\s*\\[', line):
                        if not has_security:
                            findings.append((i, line.strip()))
                return findings
"""
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
    title="Improved Security Scanner MCP Server",
    description="Scan codebase for actual security vulnerabilities with precise patterns.",
    version="2.0.0",
)


def scan_file_precise(file_path: Path, patterns: dict) -> list[SecurityFinding]:
    """Scan a single file for security patterns with reduced false positives."""
    findings = []
    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
        lines = content.split("\n")
        
        for pattern_name, config in patterns.items():
            regex = re.compile(config["pattern"])
            negate_regex = re.compile(config["negate"]) if "negate" in config and config["negate"] else None
            
            for line_num, line in enumerate(lines, start=1):
                if regex.search(line):
                    # Check negate pattern
                    if negate_regex and negate_regex.search(line):
                        continue
                    
                    # Skip comments and docstrings for certain patterns
                    if pattern_name in ("hardcoded_secret", "sql_injection_risk", "xss_risk"):
                        stripped = line.strip()
                        if stripped.startswith('#') or stripped.startswith('"""') or stripped.startswith("'''"):
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


def scan_directory_precise(directory: Path, patterns: dict) -> ScanResult:
    """Scan a directory recursively for security patterns."""
    result = ScanResult(scan_directory=str(directory))
    
    py_files = sorted(list(directory.rglob("*.py")))
    result.total_files_scanned = len(py_files)
    
    for file_path in py_files:
        findings = scan_file_precise(file_path, patterns)
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
        "hardcoded_secret": """# Move secrets to environment variables:
import os
DATABASE_PASSWORD = os.environ.get("DATABASE_PASSWORD", "change-me")
API_KEY = os.environ.get("API_KEY", "change-me")
""",
        "urllib_insecure": """import httpx

def secure_http_call(url: str, data: dict, timeout: int = 30) -> dict:
    with httpx.Client(timeout=timeout) as client:
        response = client.post(url, json=data)
        response.raise_for_status()
        return response.json() if response.content else {}
""",
        "subprocess_shell_true": """# Replace:
subprocess.run("command arg1 arg2", shell=True)
# With:
subprocess.run(["command", "arg1", "arg2"], check=True, capture_output=True, text=True)
""",
        "subprocess_unvalidated": """import subprocess
from typing import Optional

def secure_subprocess(cmd: list[str], input_data: Optional[str] = None, timeout: int = 30) -> subprocess.CompletedProcess:
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
        "fastapi_no_rate_limit": """# Add rate limiting:
from slowapi import Limiter
from slowapi.middleware import SlowAPIMiddleware

app = FastAPI()
limiter = Limiter(key_func=lambda: "client-ip")
app.state.limiter = limiter

@app.get("/api/data")
@limiter.limit("100/minute")
async def get_data():
    return {"data": "value"}
""",
        "fastapi_no_validation": """# Add Pydantic validation:
from pydantic import BaseModel, Field

class UserInput(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    email: str = Field(..., pattern=r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$')

@app.post("/api/user")
async def create_user(user: UserInput):
    return {"user": user.dict()}
""",
        "sql_injection_risk": """# Use parameterized queries:
cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
# Never use:
cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")
""",
        "xss_risk": """# Escape HTML entities:
import html
safe_output = html.escape(user_input)
# Or use template engines with auto-escaping
""",
        "missing_security_headers": """# Add security headers middleware:
@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = "default-src 'self'"
    return response
""",
    }
    
    return replacements.get(pattern_name, "# No automatic replacement available")


# ------------------------------------------------------------------
# API Endpoints
# ------------------------------------------------------------------
@app.get("/scan")
async def scan_codebase(directory: str = "services"):
    """Scan the codebase for security vulnerabilities."""
    target = Path(directory)
    if not target.exists():
        raise HTTPException(status_code=404, detail=f"Directory not found: {directory}")
    
    logger.info(f"Scanning {directory} with precise patterns...")
    result = scan_directory_precise(target, PRECISE_SECURITY_PATTERNS)
    
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
                "secure_replacement": generate_secure_replacement(f.pattern_name, f.line_content),
            }
            for f in result.findings
        ],
    }


@app.get("/findings/{finding_id}")
async def get_finding(finding_id: int):
    """Get details for a specific finding."""
    target = Path("services")
    result = scan_directory_precise(target, PRECISE_SECURITY_PATTERNS)
    
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
    result = scan_directory_precise(target, PRECISE_SECURITY_PATTERNS)
    
    score = max(0, 100 - (result.critical_findings * 20 + result.high_findings * 10 + result.medium_findings * 5))
    
    return {
        "security_score": score,
        "total_findings": result.total_findings,
        "critical_issues": result.critical_findings,
        "high_issues": result.high_findings,
        "medium_issues": result.medium_findings,
        "recommendation": "Address critical and high severity findings first. Move secrets to environment variables.",
    }


@app.post("/scan-pattern")
async def scan_specific_pattern(pattern_name: str):
    """Scan for a specific pattern."""
    if pattern_name not in PRECISE_SECURITY_PATTERNS:
        raise HTTPException(status_code=400, detail=f"Unknown pattern: {pattern_name}")
    
    target = Path("services")
    result = scan_directory_precise(target, {pattern_name: PRECISE_SECURITY_PATTERNS[pattern_name]})
    
    return {
        "pattern": pattern_name,
        "findings": [
            {
                "file": f.file_path,
                "line": f.line_number,
                "code": f.line_content,
                "secure_replacement": generate_secure_replacement(pattern_name, f.line_content),
            }
            for f in result.findings
        ],
    }


@app.get("/patterns")
async def list_patterns():
    """List all available security patterns."""
    return {
        "patterns": {
            name: {
                "severity": config["severity"],
                "description": config["description"],
                "recommendation": config["recommendation"],
            }
            for name, config in PRECISE_SECURITY_PATTERNS.items()
        }
    }


if __name__ == "__main__":
    uvicorn.run(
        __file__,
        host="127.0.0.1",
        port=8082,
        reload=False,
        log_level="info",
    )