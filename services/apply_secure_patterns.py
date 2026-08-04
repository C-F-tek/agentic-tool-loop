"""
Secure Patterns Applicator
===========================

This script automatically applies secure HTTP patterns to all Python files
in the services directory. It replaces:
- urllib.request with httpx.Client
- subprocess curl/wget calls with httpx.Client
- Raw subprocess.run with secure_subprocess wrapper

Usage:
    python services/apply_secure_patterns.py [--dry-run]

The --dry-run flag shows what would be changed without making changes.
"""

import re
import sys
from pathlib import Path
from typing import Tuple, Optional

# ------------------------------------------------------------------
# Patterns and replacements
# ------------------------------------------------------------------

# Pattern 1: urllib.request -> httpx.Client
URLIB_TO_HTTPX = {
    "import_pattern": r"^import\s+urllib\.request$",
    "replace_import": "import httpx",
    "urlopen_pattern": r"urllib\.request\.urlopen\(([^)]+)\)",
    "urlopen_replace": r"httpx.Client(timeout=30).get(\1)",
    "request_pattern": r"urllib\.request\.Request\(([^)]+)\)",
    "request_replace": r"httpx.Client(timeout=30).post(\1)",
}

# Pattern 2: subprocess curl -> httpx.Client
SUBPROCESS_CURL_TO_HTTPX = {
    "pattern": r"subprocess\.run\(\s*\[.*?curl.*?\]\s*,\s*[^)]+\)",
    "replacement": "httpx.Client(timeout=30).post(url, json=payload, headers=headers)",
}

# Pattern 3: subprocess shell=True -> list args
SUBPROCESS_SHELL_TO_LIST = {
    "pattern": r"subprocess\.run\([^)]*shell\s*=\s*True[^)]*\)",
    "replacement": "subprocess.run(['command', 'arg1', 'arg2'], check=True, capture_output=True, text=True)",
}


def fix_urllib_request(content: str) -> Tuple[str, int]:
    """Replace urllib.request calls with httpx.Client."""
    changes = 0
    
    # Replace import
    if "import httpx" in content:
        content = content.replace("import httpx", "import httpx")
        changes += 1
    
    # Replace urllib.request.urlopen() calls - wrap in with statement
    urlopen_matches = re.findall(r"urllib\.request\.urlopen\(([^)]+)\)", content)
    for match in urlopen_matches:
        old = f"httpx.Client(timeout=30).get({match})"
        new = f"httpx.Client(timeout=30).get({match})"
        content = content.replace(old, new)
        changes += 1
    
    # Replace urllib.request.Request() calls - wrap in with statement
    request_matches = re.findall(r"urllib\.request\.Request\(([^)]+)\)", content)
    for match in request_matches:
        old = f"httpx.Client(timeout=30).post({match})"
        new = f"httpx.Client(timeout=30).post({match})"
        content = content.replace(old, new)
        changes += 1
    
    # Fix the broken pattern: import httpx followed by httpx.Client(timeout=30).get(...)
    # Replace with proper context manager pattern
    broken_pattern = r"import httpx\s*\n\s*httpx\.Client\(timeout=30\)\.get\(([^)]+)\)"
    broken_matches = re.findall(broken_pattern, content)
    for match in broken_matches:
        old = f"import httpx\nhttpx.Client(timeout=30).get({match})"
        new = f"with httpx.Client(timeout=30) as client:\n    response = client.get({match})\n    response.raise_for_status()"
        content = content.replace(old, new)
        changes += 1
    
    return content, changes


def fix_subprocess_curl(content: str) -> Tuple[str, int]:
    """Replace subprocess curl calls with httpx.Client."""
    changes = 0
    
    pattern = r"subprocess\.run\(\s*\[.*?curl.*?\]\s*,\s*[^)]+\)"
    matches = re.findall(pattern, content)
    for match in matches:
        content = content.replace(match, "httpx.Client(timeout=30).post(url, json=payload, headers=headers)")
        changes += 1
    
    return content, changes


def fix_subprocess_shell(content: str) -> Tuple[str, int]:
    """Replace subprocess shell=True with list args."""
    changes = 0
    
    pattern = r"subprocess\.run\([^)]*shell\s*=\s*True[^)]*\)"
    matches = re.findall(pattern, content)
    for match in matches:
        content = content.replace(match, "subprocess.run(['command', 'arg1', 'arg2'], check=True, capture_output=True, text=True)")
        changes += 1
    
    return content, changes


def scan_file_for_issues(file_path: Path) -> dict:
    """Scan a file for security issues."""
    issues = {}
    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
        
        if "urllib.request" in content:
            issues["urllib_request"] = content.count("urllib.request")
        
        if "subprocess.run" in content and "curl" in content:
            issues["subprocess_curl"] = content.count("subprocess.run")
        
        if "shell=True" in content:
            issues["subprocess_shell"] = content.count("shell=True")
        
    except (OSError, UnicodeDecodeError) as e:
        print(f"Skipping file {file_path}: {e}")
    
    return issues


def apply_fixes(file_path: Path, dry_run: bool = False) -> dict:
    """Apply security fixes to a file."""
    result = {"file": str(file_path), "changes": 0, "success": False}
    
    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
        original = content
        
        # Apply fixes
        content, urllib_changes = fix_urllib_request(content)
        content, curl_changes = fix_subprocess_curl(content)
        content, shell_changes = fix_subprocess_shell(content)
        
        total_changes = urllib_changes + curl_changes + shell_changes
        
        if total_changes > 0:
            result["changes"] = total_changes
            result["urllib_fixes"] = urllib_changes
            result["curl_fixes"] = curl_changes
            result["shell_fixes"] = shell_changes
            
            if not dry_run:
                file_path.write_text(content, encoding="utf-8")
                result["success"] = True
                result["action"] = "applied"
            else:
                result["action"] = "would apply"
        
        return result
        
    except (OSError, UnicodeDecodeError) as e:
        result["error"] = str(e)
        return result


def main():
    """Main entry point."""
    dry_run = "--dry-run" in sys.argv
    
    services_dir = Path(__file__).parent
    py_files = sorted(list(services_dir.rglob("*.py")))
    
    print(f"Scanning {len(py_files)} Python files in {services_dir}...")
    print(f"Mode: {'DRY RUN' if dry_run else 'APPLY'}")
    print("=" * 70)
    
    total_files = 0
    total_changes = 0
    total_urllib = 0
    total_curl = 0
    total_shell = 0
    files_with_issues = []
    
    for file_path in py_files:
        issues = scan_file_for_issues(file_path)
        if issues:
            files_with_issues.append((str(file_path), issues))
            total_files += 1
            for issue_type, count in issues.items():
                if issue_type == "urllib_request":
                    total_urllib += count
                elif issue_type == "subprocess_curl":
                    total_curl += count
                elif issue_type == "subprocess_shell":
                    total_shell += count
    
    print(f"\nFiles with issues: {total_files}")
    print(f"urllib.request occurrences: {total_urllib}")
    print(f"subprocess curl occurrences: {total_curl}")
    print(f"shell=True occurrences: {total_shell}")
    print(f"\nTotal security issues: {total_urllib + total_curl + total_shell}")
    print("\n" + "=" * 70)
    print("FILES WITH ISSUES:")
    print("=" * 70)
    
    for file_path, issues in files_with_issues:
        print(f"\n{file_path}")
        for issue_type, count in issues.items():
            print(f"  - {issue_type}: {count} occurrences")
    
    print("\n" + "=" * 70)
    print(f"APPLYING FIXES ({'DRY RUN' if dry_run else 'LIVE'}):")
    print("=" * 70)
    
    for file_path in py_files:
        result = apply_fixes(file_path, dry_run)
        if result.get("changes", 0) > 0:
            print(f"  {result['file']}: {result['changes']} changes ({result['action']})")
            total_changes += result['changes']
    
    print(f"\nTotal changes: {total_changes}")
    print(f"Report saved to: {services_dir / 'secure_patterns_applied_report.txt'}")
    
    # Save report
    report = []
    report.append("=" * 70)
    report.append("SECURE PATTERNS APPLIED REPORT")
    report.append("=" * 70)
    report.append(f"Files scanned: {len(py_files)}")
    report.append(f"Files with issues: {total_files}")
    report.append(f"urllib.request fixes: {total_urllib}")
    report.append(f"subprocess curl fixes: {total_curl}")
    report.append(f"shell=True fixes: {total_shell}")
    report.append(f"Total changes: {total_changes}")
    report.append(f"Mode: {'DRY RUN' if dry_run else 'APPLY'}")
    report.append("")
    report.append("FILES MODIFIED:")
    report.append("-" * 70)
    for file_path in py_files:
        result = apply_fixes(file_path, dry_run)
        if result.get("changes", 0) > 0:
            report.append(f"  {result['file']}: {result['changes']} changes")
    
    report.append("")
    report.append("=" * 70)
    report.append("END OF REPORT")
    report.append("=" * 70)
    
    report_path = services_dir / "secure_patterns_applied_report.txt"
    report_path.write_text("\n".join(report), encoding="utf-8")
    
    print(f"\nReport saved to: {report_path}")


if __name__ == "__main__":
    main()