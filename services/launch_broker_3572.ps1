#!/usr/bin/env powershell
# Launch the vulkan tool broker on port 3572
# Usage: Run from ANY directory - uses hardcoded repo root

# Hardcoded repo root (adjust if needed)
$repoRoot = "C:\Users\sanit\progeetsbat\agentic-tool-loop"
Set-Location $repoRoot

# Add repo root to Python path to ensure services package is importable
$env:PYTHONPATH = "$repoRoot;$env:PYTHONPATH"

Write-Host "Launching vulkan tool broker on port 3572..." -ForegroundColor Green
Write-Host "Working directory: $repoRoot" -ForegroundColor Cyan

python -m uvicorn services.aicarmine_vulkan_tool_broker:app --host 127.0.0.1 --port 3572