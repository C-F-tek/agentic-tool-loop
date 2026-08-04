"""
Bandit CI/CD Configuration Generator

This module generates a GitHub Actions workflow for automated security scanning
using Bandit (Python security linter).

Usage:
    python services/bandit_ci_config.py > .github/workflows/security.yml
"""
from __future__ import annotations

BANDIT_YML = """
name: Security Scan

on:
  push:
    branches: [ main, master ]
  pull_request:
    branches: [ main, master ]

jobs:
  security:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install Bandit
        run: pip install bandit bandit-json-output

      - name: Run Bandit
        run: |
          bandit -r services/ -f json -o security-report.json --recursive
          cat security-report.json

      - name: Upload Security Report
        uses: actions/upload-artifact@v4
        with:
          name: security-report
          path: security-report.json

      - name: Fail on Critical Findings
        run: |
          $report = Get-Content security-report.json | ConvertFrom-Json
          if ($report.results | Where-Object { $_.severity -eq "HIGH" -or $_.severity -eq "CRITICAL" }) {
            Write-Host "Critical or High severity findings detected!"
            exit 1
          }
"""


def generate_github_workflow() -> str:
    """Generate GitHub Actions workflow for Bandit security scanning."""
    return BANDIT_YML


if __name__ == "__main__":
    print(BANDIT_YML)