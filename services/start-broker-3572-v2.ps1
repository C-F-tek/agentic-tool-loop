#!/usr/bin/env powershell
$ErrorActionPreference = "Stop"
Set-Location "C:\Users\sanit\progeetsbat\agentic-tool-loop\services"
$env:PYTHONPATH = "C:\Users\sanit\progeetsbat\agentic-tool-loop"
python -m uvicorn services.aicarmine_vulkan_tool_broker:app --host 127.0.0.1 --port 3572