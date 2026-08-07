#!/usr/bin/env powershell
$ErrorActionPreference = "Stop"
Set-Location "C:\Users\sanit\agentic-tool-loop"
$env:PYTHONPATH = "C:\Users\sanit\agentic-tool-loop;C:\Users\sanit\agentic-tool-loop\services"

# Force all models to qwen2.5:7b as per user requirement
# This replaces the heavy model with qwen2.5:7b for planner and task execution
$env:AICARMINE_OLLAMA_TASK_MODEL = "qwen2.5:7b"
$env:AICARMINE_VULKAN_BROKER_MODEL = "qwen2.5:7b"
$env:AICARMINE_AGENT_PLANNER_MODEL = "qwen2.5:7b"
$env:AICARMINE_PLANNER_MODEL = "qwen2.5:7b"

python -m uvicorn services.aicarmine_vulkan_tool_broker:app --host 127.0.0.1 --port 3572
