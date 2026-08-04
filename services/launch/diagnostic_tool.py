#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
AI-Powered Diagnostic Tool for AICarmine Broker
================================================
This tool reads broker logs and event files, identifies common error patterns,
and suggests possible solutions.

Usage:
    python diagnostic_tool.py --help
    python diagnostic_tool.py --log-dir C:\Users\sanit\AI\logs
    python diagnostic_tool.py --port 3579
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

# ------------------------------------------------------------------
# Error patterns and their suggested solutions
# ------------------------------------------------------------------

ERROR_PATTERNS = [
    {
        "name": "port_already_in_use",
        "pattern": r"errno 10048|address already in use|port.*already in use",
        "severity": "high",
        "solution": "Port 3579 is already in use. Kill the existing process:\n  netstat -ano | findstr ':3579'\n  taskkill /PID <PID> /F\n  Or use a different port.",
        "fix_command": "Stop-Process -Id <PID> -Force",
    },
    {
        "name": "ollama_connection_failed",
        "pattern": r"ConnectionRefusedError|ConnectionResetError|Connection refused|ECONNREFUSED",
        "severity": "high",
        "solution": "Ollama is not running or not accessible on the expected port. Start Ollama:\n  ollama serve\n  ollama run mio-qwen-code3:latest",
        "fix_command": "ollama serve",
    },
    {
        "name": "model_not_found",
        "pattern": r"model.*not found|model.*missing|no model|invalid model",
        "severity": "high",
        "solution": "The model specified in AICARMINE_AGENTIC_PLANNER_MODEL or AICARMINE_VULKAN_BROKER_MODEL is not available in Ollama. Check available models:\n  ollama list\n  Pull the correct model:\n  ollama pull mio-qwen-code3:latest",
        "fix_command": "ollama pull mio-qwen-code3:latest",
    },
    {
        "name": "planner_stuck_no_step",
        "pattern": r"planner.*stuck|planner.*timeout|planner.*step.*0|planner.*not.*enter|planner.*not.*start",
        "severity": "high",
        "solution": "The planner is not entering the step phase. This is likely because:\n1. Ollama is not responding to chat requests\n2. The model is not loaded\n3. The prompt is too large\nCheck Ollama logs and ensure the model is loaded.",
        "fix_command": "ollama ps",
    },
    {
        "name": "syntax_error",
        "pattern": r"SyntaxError|Traceback.*SyntaxError",
        "severity": "high",
        "solution": "There is a syntax error in the Python code. Check the traceback for the file and line number. Common causes:\n1. Missing closing parenthesis\n2. Missing comma\n3. Incorrect indentation",
        "fix_command": "python -m py_compile services/aicarmine_broker/config/models.py",
    },
    {
        "name": "import_error",
        "pattern": r"ImportError|ModuleNotFoundError",
        "severity": "high",
        "solution": "A required Python module is not installed. Install dependencies:\n  pip install -r requirements.txt\nOr check the Python environment.",
        "fix_command": "pip install fastapi uvicorn pydantic",
    },
    {
        "name": "environment_variable_missing",
        "pattern": r"AICARMINE.*not.*set|env.*missing|environment.*variable",
        "severity": "medium",
        "solution": "Required environment variables are not set. Set them:\n  $env:AICARMINE_LAB_REPO = \"C:\\Users\\sanit\\AI\\lab-worktrees\\blender-audio-project-lab\"\n  $env:AICARMINE_VULKAN_WORKSPACE = \"C:\\Users\\sanit\\AI\\qwen-agent-workspace\\vulkan-broker\"\n  $env:AICARMINE_AGENT_JOB_ROOT = \"C:\\Users\\sanit\\AI\\qwen-agent-workspace\\vulkan-broker\\agent-jobs\"\n  $env:AICARMINE_AGENT_JOB_DB = \"C:\\Users\\sanit\\AI\\qwen-agent-workspace\\vulkan-broker\\agent-jobs\\agent_jobs.sqlite3\"\n  $env:AICARMINE_AGENTIC_PLANNER_MODEL = \"mio-qwen-code3:latest\"\n  $env:AICARMINE_AGENTIC_PLANNER_NUM_CTX = \"262144\"",
        "fix_command": ". $PROFILE",
    },
    {
        "name": "database_error",
        "pattern": r"sqlite3.*error|database.*locked|database.*corrupt|database.*open",
        "severity": "high",
        "solution": "The SQLite database is locked or corrupt. Check the database:\n  sqlite3 C:\\Users\\sanit\\AI\\qwen-agent-workspace\\vulkan-broker\\agent-jobs\\agent_jobs.sqlite3\n  .tables\n  If corrupt, restore from backup.",
        "fix_command": "sqlite3 agent_jobs.sqlite3",
    },
    {
        "name": "permission_error",
        "pattern": r"PermissionError|Permission denied|Access denied",
        "severity": "high",
        "solution": "Permission denied for a file or directory. Check file permissions:\n  Get-Item C:\\Users\\sanit\\AI\\qwen-agent-workspace\\vulkan-broker\\agent-jobs\\agent_jobs.sqlite3\n  Ensure the user has read/write access.",
        "fix_command": "icacls agent_jobs.sqlite3",
    },
    {
        "name": "timeout_error",
        "pattern": r"TimeoutError|timed out|timeout",
        "severity": "medium",
        "solution": "A timeout occurred. This could be due to:\n1. Ollama is slow or unresponsive\n2. The model is loading\n3. The network is slow\nIncrease the timeout or optimize the model.",
        "fix_command": "ollama ps",
    },
    {
        "name": "json_decode_error",
        "pattern": r"JSONDecodeError|json.*decode|invalid JSON",
        "severity": "medium",
        "solution": "JSON decoding failed. This could be due to:\n1. Malformed JSON in the response\n2. Incomplete JSON\n3. Non-JSON response\nCheck the Ollama response format.",
        "fix_command": "ollama show --format json",
    },
    {
        "name": "memory_error",
        "pattern": r"MemoryError|OOM|out of memory|CUDA.*error",
        "severity": "high",
        "solution": "Out of memory. This could be due to:\n1. The model is too large for available VRAM\n2. Multiple models are loaded\n3. Other processes are using GPU\nFree up memory or use a smaller model.",
        "fix_command": "ollama ps",
    },
    {
        "name": "tool_execution_error",
        "pattern": r"tool.*execution.*error|tool.*failed|tool.*not.*found|tool.*invalid",
        "severity": "medium",
        "solution": "Tool execution failed. Check the tool registry:\n  python -c \"from aicarmine_broker.tool_registry import capability_map; print(capability_map().keys())\"\nEnsure the tool is registered and available.",
        "fix_command": "python -c \"from aicarmine_broker.tool_registry import capability_map; print(capability_map().keys())\"",
    },
    {
        "name": "validator_rejection",
        "pattern": r"validator.*rejected|decision.*rejected|planner.*rejected",
        "severity": "medium",
        "solution": "The planner decision was rejected by the validator. This could be due to:\n1. The decision does not match the evidence\n2. The tool is not allowed\n3. The parameters are invalid\nCheck the validator logs and adjust the planner prompt.",
        "fix_command": "python -m uvicorn aicarmine_broker.app:app --host 127.0.0.1 --port 3579",
    },
    {
        "name": "evidence_builder_error",
        "pattern": r"evidence.*builder.*error|evidence.*not.*found|evidence.*empty",
        "severity": "medium",
        "solution": "The evidence builder failed to collect evidence. This could be due to:\n1. The repository is not accessible\n2. The path is invalid\n3. The tool is not available\nCheck the repository path and ensure it exists.",
        "fix_command": "ls C:\\Users\\sanit\\AI\\lab-worktrees\\blender-audio-project-lab",
    },
    {
        "name": "preplanner_error",
        "pattern": r"preplanner.*error|preplanner.*failed|preplanner.*not.*found",
        "severity": "medium",
        "solution": "The preplanner failed to generate a query plan. This could be due to:\n1. Ollama is not responding\n2. The model is not loaded\n3. The RAG index is empty\nCheck the RAG index and ensure it has entries.",
        "fix_command": "python -m uvicorn aicarmine_broker.app:app --host 127.0.0.1 --port 3579",
    },
    {
        "name": "orientation_lane_error",
        "pattern": r"orientation.*lane.*error|lane.*mode.*invalid|orientation.*invalid",
        "severity": "medium",
        "solution": "The orientation lane mode is invalid. Valid modes are:\n- legacy\n- shadow\n- active\nSet AICARMINE_ORIENTATION_LANE_MODE to one of these values.",
        "fix_command": "$env:AICARMINE_ORIENTATION_LANE_MODE = \"legacy\"",
    },
    {
        "name": "final_quality_error",
        "pattern": r"final.*quality.*error|final.*judge.*error|final.*answer.*error",
        "severity": "medium",
        "solution": "The final quality judge failed. This could be due to:\n1. The answer is too short\n2. The answer is incomplete\n3. The answer does not match the task\nCheck the answer format and adjust the planner prompt.",
        "fix_command": "python -m uvicorn aicarmine_broker.app:app --host 127.0.0.1 --port 3579",
    },
    {
        "name": "native_tools_error",
        "pattern": r"native.*tools.*error|native.*mode.*error|native.*tools.*not.*enabled",
        "severity": "medium",
        "solution": "Native tools are not enabled. Set:\n  $env:AICARMINE_AGENTIC_PLANNER_NATIVE_TOOLS = \"1\"\n  $env:AICARMINE_AGENTIC_PLANNER_REQUIRE_NATIVE_TOOLS = \"1\"\nNative tools allow the planner to use MCP tools directly.",
        "fix_command": "$env:AICARMINE_AGENTIC_PLANNER_NATIVE_TOOLS = \"1\"",
    },
    {
        "name": "agentic_loop_error",
        "pattern": r"agentic.*loop.*error|agentic.*loop.*stuck|agentic.*loop.*timeout",
        "severity": "high",
        "solution": "The agentic loop is stuck or timed out. This could be due to:\n1. The planner is not completing steps\n2. The validator is rejecting all decisions\n3. The evidence builder is not collecting evidence\nCheck the logs and adjust the planner prompt.",
        "fix_command": "python -m uvicorn aicarmine_broker.app:app --host 127.0.0.1 --port 3579",
    },
    {
        "name": "reranker_error",
        "pattern": r"reranker.*error|reranker.*failed|reranker.*not.*found|OVMS.*error",
        "severity": "medium",
        "solution": "The reranker (OVMS) is not available. Start the reranker:\n  python services/ovms-reranker-npu.ps1\nOr disable reranking:\n  $env:RAG_RERANKING_ENGINE = \"\"\nCheck the reranker logs.",
        "fix_command": "python services/ovms-reranker-npu.ps1",
    },
    {
        "name": "webui_error",
        "pattern": r"webui.*error|openwebui.*error|openwebui.*not.*found",
        "severity": "medium",
        "solution": "OpenWebUI is not available. Start OpenWebUI:\n  python services/openwebui.ps1\nOr use the standalone broker without OpenWebUI.",
        "fix_command": "python services/openwebui.ps1",
    },
    {
        "name": "vulkan_bridge_error",
        "pattern": r"vulkan.*bridge.*error|vulkan.*bridge.*not.*found|vulkan.*bridge.*failed",
        "severity": "medium",
        "solution": "The Vulkan bridge is not available. Start the bridge:\n  python services/vulkan_bridge/app.py\nOr use the standalone broker without the bridge.",
        "fix_command": "python services/vulkan_bridge/app.py",
    },
    {
        "name": "job_error",
        "pattern": r"job.*error|job.*failed|job.*not.*found|job.*stuck|job.*pending",
        "severity": "high",
        "solution": "The job is stuck or failed. Check the job:\n  curl http://127.0.0.1:3572/jobs\n  curl http://127.0.0.1:3572/jobs.json\nOr check the job events:\n  cat C:\\Users\\sanit\\AI\\qwen-agent-workspace\\vulkan-broker\\agent-jobs\\<job-id>\\events.ndjson",
        "fix_command": "curl http://127.0.0.1:3572/jobs",
    },
    {
        "name": "config_error",
        "pattern": r"config.*error|config.*invalid|config.*not.*found|config.*load.*error",
        "severity": "medium",
        "solution": "The configuration is invalid. Check the config:\n  python -c \"from aicarmine_broker.config import load_broker_config_from_env; print(load_broker_config_from_env())\"\nOr check the environment variables.",
        "fix_command": "python -c \"from aicarmine_broker.config import load_broker_config_from_env; print(load_broker_config_from_env())\"",
    },
    {
        "name": "planner_model_error",
        "pattern": r"planner.*model.*error|planner.*model.*not.*found|planner.*model.*invalid",
        "severity": "high",
        "solution": "The planner model is not available. Set the correct model:\n  $env:AICARMINE_AGENTIC_PLANNER_MODEL = \"mio-qwen-code3:latest\"\n  $env:AICARMINE_VULKAN_BROKER_MODEL = \"mio-qwen-code3:latest\"\nCheck available models:\n  ollama list",
        "fix_command": "ollama pull mio-qwen-code3:latest",
    },
    {
        "name": "ollama_task_model_error",
        "pattern": r"ollama.*task.*model.*error|ollama.*task.*model.*not.*found|ollama.*task.*model.*invalid",
        "severity": "high",
        "solution": "The Ollama task model is not available. Set the correct model:\n  $env:AICARMINE_VULKAN_BROKER_MODEL = \"mio-qwen-code3:latest\"\nCheck available models:\n  ollama list",
        "fix_command": "ollama pull mio-qwen-code3:latest",
    },
    {
        "name": "ctx_size_error",
        "pattern": r"ctx.*size.*error|ctx.*size.*invalid|num_ctx.*error|num_ctx.*invalid",
        "severity": "medium",
        "solution": "The context size is invalid. Set the correct context size:\n  $env:AICARMINE_AGENTIC_PLANNER_NUM_CTX = \"262144\"\nLarger context sizes require more VRAM.",
        "fix_command": "$env:AICARMINE_AGENTIC_PLANNER_NUM_CTX = \"262144\"",
    },
    {
        "name": "temperature_error",
        "pattern": r"temperature.*error|temperature.*invalid|planner.*temperature.*error",
        "severity": "low",
        "solution": "The temperature is invalid. Set the correct temperature:\n  $env:AICARMINE_AGENTIC_PLANNER_TEMPERATURE = \"0.3\"\nValid range is 0.0 to 1.0.",
        "fix_command": "$env:AICARMINE_AGENTIC_PLANNER_TEMPERATURE = \"0.3\"",
    },
    {
        "name": "top_k_error",
        "pattern": r"top_k.*error|top_k.*invalid|planner.*top_k.*error",
        "severity": "low",
        "solution": "The top_k is invalid. Set the correct top_k:\n  $env:AICARMINE_AGENTIC_PLANNER_TOP_K = \"20\"\nValid range is 1 to 100.",
        "fix_command": "$env:AICARMINE_AGENTIC_PLANNER_TOP_K = \"20\"",
    },
    {
        "name": "top_p_error",
        "pattern": r"top_p.*error|top_p.*invalid|planner.*top_p.*error",
        "severity": "low",
        "solution": "The top_p is invalid. Set the correct top_p:\n  $env:AICARMINE_AGENTIC_PLANNER_TOP_P = \"0.85\"\nValid range is 0.0 to 1.0.",
        "fix_command": "$env:AICARMINE_AGENTIC_PLANNER_TOP_P = \"0.85\"",
    },
    {
        "name": "presence_penalty_error",
        "pattern": r"presence_penalty.*error|presence_penalty.*invalid|planner.*presence_penalty.*error",
        "severity": "low",
        "solution": "The presence_penalty is invalid. Set the correct presence_penalty:\n  $env:AICARMINE_AGENTIC_PLANNER_PRESENCE_PENALTY = \"0.0\"\nValid range is -2.0 to 2.0.",
        "fix_command": "$env:AICARMINE_AGENTIC_PLANNER_PRESENCE_PENALTY = \"0.0\"",
    },
    {
        "name": "max_steps_error",
        "pattern": r"max_steps.*error|max_steps.*invalid|agent.*max_steps.*error",
        "severity": "medium",
        "solution": "The max_steps is invalid. Set the correct max_steps:\n  $env:AICARMINE_AGENT_DEFAULT_MAX_STEPS = \"40\"\n  $env:AICARMINE_AGENT_MAX_STEPS = \"100\"\nLarger values allow more steps but take longer.",
        "fix_command": "$env:AICARMINE_AGENT_DEFAULT_MAX_STEPS = \"40\"",
    },
    {
        "name": "timeout_config_error",
        "pattern": r"timeout.*config.*error|timeout.*config.*invalid|command_timeout.*error",
        "severity": "medium",
        "solution": "The timeout configuration is invalid. Set the correct timeout:\n  $env:AICARMINE_AGENTIC_PLANNER_STEP_TIMEOUT = \"60\"\n  $env:AICARMINE_AGENTIC_PLANNER_FORCED_DECISION_TIMEOUT = \"75\"\n  $env:AICARMINE_CODEX_COMMAND_TIMEOUT = \"600\"",
        "fix_command": "$env:AICARMINE_AGENTIC_PLANNER_STEP_TIMEOUT = \"60\"",
    },
    {
        "name": "compact_chars_error",
        "pattern": r"compact_chars.*error|compact_chars.*invalid|result_compact_chars.*error",
        "severity": "low",
        "solution": "The compact_chars is invalid. Set the correct value:\n  $env:AICARMINE_AGENTIC_RESULT_COMPACT_CHARS = \"25000\"\nLarger values allow more output but take longer.",
        "fix_command": "$env:AICARMINE_AGENTIC_RESULT_COMPACT_CHARS = \"25000\"",
    },
    {
        "name": "prompt_chars_error",
        "pattern": r"prompt_chars.*error|prompt_chars.*invalid|prompt_char_budget.*error",
        "severity": "medium",
        "solution": "The prompt_char_budget is invalid. Set the correct value:\n  $env:AICARMINE_AGENTIC_PLANNER_PROMPT_CHAR_BUDGET = \"48000\"\nLarger values allow more context but take longer.",
        "fix_command": "$env:AICARMINE_AGENTIC_PLANNER_PROMPT_CHAR_BUDGET = \"48000\"",
    },
    {
        "name": "history_prompt_error",
        "pattern": r"history_prompt.*error|history_prompt.*invalid|history_prompt_tail.*error",
        "severity": "low",
        "solution": "The history_prompt_tail is invalid. Set the correct value:\n  $env:AICARMINE_AGENTIC_PLANNER_HISTORY_PROMPT_TAIL = \"8\"\nLarger values allow more history but take longer.",
        "fix_command": "$env:AICARMINE_AGENTIC_PLANNER_HISTORY_PROMPT_TAIL = \"8\"",
    },
    {
        "name": "preview_chars_error",
        "pattern": r"preview_chars.*error|preview_chars.*invalid|prompt_preview_chars.*error",
        "severity": "low",
        "solution": "The preview_chars is invalid. Set the correct value:\n  $env:AICARMINE_AGENTIC_PLANNER_PROMPT_PREVIEW_CHARS = \"360\"\nLarger values allow more preview but take longer.",
        "fix_command": "$env:AICARMINE_AGENTIC_PLANNER_PROMPT_PREVIEW_CHARS = \"360\"",
    },
    {
        "name": "num_predict_error",
        "pattern": r"num_predict.*error|num_predict.*invalid|planner.*num_predict.*error",
        "severity": "low",
        "solution": "The num_predict is invalid. Set the correct value:\n  $env:AICARMINE_AGENTIC_PLANNER_NUM_PREDICT = \"-1\"\n-1 means unlimited.",
        "fix_command": "$env:AICARMINE_AGENTIC_PLANNER_NUM_PREDICT = \"-1\"",
    },
    {
        "name": "keep_alive_error",
        "pattern": r"keep_alive.*error|keep_alive.*invalid|ollama.*keep_alive.*error",
        "severity": "low",
        "solution": "The keep_alive is invalid. Set the correct value:\n  $env:AICARMINE_OLLAMA_KEEP_ALIVE = \"24h\"\nLarger values keep the model loaded longer.",
        "fix_command": "$env:AICARMINE_OLLAMA_KEEP_ALIVE = \"24h\"",
    },
    {
        "name": "public_summary_chars_error",
        "pattern": r"public_summary_chars.*error|public_summary_chars.*invalid|agent_public_summary_chars.*error",
        "severity": "low",
        "solution": "The public_summary_chars is invalid. Set the correct value:\n  $env:AICARMINE_AGENT_PUBLIC_SUMMARY_CHARS = \"4000\"\nLarger values allow more summary but take longer.",
        "fix_command": "$env:AICARMINE_AGENT_PUBLIC_SUMMARY_CHARS = \"4000\"",
    },
    {
        "name": "public_answer_chars_error",
        "pattern": r"public_answer_chars.*error|public_answer_chars.*invalid|agent_public_answer_chars.*error",
        "severity": "low",
        "solution": "The public_answer_chars is invalid. Set the correct value:\n  $env:AICARMINE_AGENT_PUBLIC_ANSWER_CHARS = \"0\"\n0 means unlimited.",
        "fix_command": "$env:AICARMINE_AGENT_PUBLIC_ANSWER_CHARS = \"0\"",
    },
    {
        "name": "public_result_inline_chars_error",
        "pattern": r"public_result_inline_chars.*error|public_result_inline_chars.*invalid|agent_public_result_inline_chars.*error",
        "severity": "low",
        "solution": "The public_result_inline_chars is invalid. Set the correct value:\n  $env:AICARMINE_AGENT_PUBLIC_RESULT_INLINE_CHARS = \"25000\"\nLarger values allow more inline output but take longer.",
        "fix_command": "$env:AICARMINE_AGENT_PUBLIC_RESULT_INLINE_CHARS = \"25000\"",
    },
    {
        "name": "job_max_inline_events_error",
        "pattern": r"job_max_inline_events.*error|job_max_inline_events.*invalid|agent_job_max_inline_events.*error",
        "severity": "low",
        "solution": "The job_max_inline_events is invalid. Set the correct value:\n  $env:AICARMINE_AGENT_JOB_MAX_INLINE_EVENTS = \"20\"\nLarger values allow more inline events but take longer.",
        "fix_command": "$env:AICARMINE_AGENT_JOB_MAX_INLINE_EVENTS = \"20\"",
    },
    {
        "name": "wait_poll_seconds_error",
        "pattern": r"wait_poll_seconds.*error|wait_poll_seconds.*invalid|agent_wait_poll_seconds.*error",
        "severity": "low",
        "solution": "The wait_poll_seconds is invalid. Set the correct value:\n  $env:AICARMINE_AGENT_WAIT_POLL_SECONDS = \"1.0\"\nLarger values poll less frequently but take longer.",
        "fix_command": "$env:AICARMINE_AGENT_WAIT_POLL_SECONDS = \"1.0\"",
    },
    {
        "name": "return_wait_seconds_error",
        "pattern": r"return_wait_seconds.*error|return_wait_seconds.*invalid|agent_return_wait_seconds.*error",
        "severity": "low",
        "solution": "The return_wait_seconds is invalid. Set the correct value:\n  $env:AICARMINE_AGENT_RETURN_WAIT_SECONDS = \"900\"\nLarger values wait longer before returning.",
        "fix_command": "$env:AICARMINE_AGENT_RETURN_WAIT_SECONDS = \"900\"",
    },
    {
        "name": "jobs_refresh_seconds_error",
        "pattern": r"jobs_refresh_seconds.*error|jobs_refresh_seconds.*invalid|broker_jobs_refresh_seconds.*error",
        "severity": "low",
        "solution": "The jobs_refresh_seconds is invalid. Set the correct value:\n  $env:AICARMINE_BROKER_JOBS_REFRESH_SECONDS = \"10\"\nLarger values refresh less frequently but take longer.",
        "fix_command": "$env:AICARMINE_BROKER_JOBS_REFRESH_SECONDS = \"10\"",
    },
    {
        "name": "max_tool_result_chars_error",
        "pattern": r"max_tool_result_chars.*error|max_tool_result_chars.*invalid|code_max_tool_result_chars.*error",
        "severity": "low",
        "solution": "The max_tool_result_chars is invalid. Set the correct value:\n  $env:AICARMINE_CODEX_MAX_TOOL_RESULT_CHARS = \"12000\"\nLarger values allow more output but take longer.",
        "fix_command": "$env:AICARMINE_CODEX_MAX_TOOL_RESULT_CHARS = \"12000\"",
    },
    {
        "name": "command_timeout_error",
        "pattern": r"command_timeout.*error|command_timeout.*invalid|code_command_timeout.*error",
        "severity": "low",
        "solution": "The command_timeout is invalid. Set the correct value:\n  $env:AICARMINE_CODEX_COMMAND_TIMEOUT = \"600\"\nLarger values allow more time but take longer.",
        "fix_command": "$env:AICARMINE_CODEX_COMMAND_TIMEOUT = \"600\"",
    },
    {
        "name": "vulkan_interpreter_num_predict_error",
        "pattern": r"vulkan_interpreter_num_predict.*error|vulkan_interpreter_num_predict.*invalid|vulkan_interpreter.*error",
        "severity": "low",
        "solution": "The vulkan_interpreter_num_predict is invalid. Set the correct value:\n  $env:AICARMINE_VULKAN_INTERPRETER_NUM_PREDICT = \"1024\"\nLarger values allow more output but take longer.",
        "fix_command": "$env:AICARMINE_VULKAN_INTERPRETER_NUM_PREDICT = \"1024\"",
    },
    {
        "name": "openapi_contract_error",
        "pattern": r"openapi_contract.*error|openapi_contract.*invalid|broker_openapi_contract.*error",
        "severity": "low",
        "solution": "The openapi_contract is invalid. Set the correct value:\n  $env:AICARMINE_BROKER_OPENAPI_CONTRACT = \"3572: public X from 3571 -> 11435 selects internal L -> 3572 dispatcher executes L -> 3572 deterministic field mapping wraps L result as public X -> 3572 returns wrapper.\"",
        "fix_command": "$env:AICARMINE_BROKER_OPENAPI_CONTRACT = \"3572: public X from 3571 -> 11435 selects internal L -> 3572 dispatcher executes L -> 3572 deterministic field mapping wraps L result as public X -> 3572 returns wrapper.\"",
    },
    {
        "name": "v6_marker_error",
        "pattern": r"v6_marker.*error|v6_marker.*invalid|broker_v6_marker.*error",
        "severity": "low",
        "solution": "The v6_marker is invalid. Set the correct value:\n  $env:AICARMINE_BROKER_V6_MARKER = \"public_x_v6_vulkan_select_dispatcher_execute_deterministic_wrap\"",
        "fix_command": "$env:AICARMINE_BROKER_V6_MARKER = \"public_x_v6_vulkan_select_dispatcher_execute_deterministic_wrap\"",
    },
    {
        "name": "orientation_lane_mode_error",
        "pattern": r"orientation_lane_mode.*error|orientation_lane_mode.*invalid|broker_orientation_lane_mode.*error",
        "severity": "medium",
        "solution": "The orientation_lane_mode is invalid. Set the correct value:\n  $env:AICARMINE_ORIENTATION_LANE_MODE = \"legacy\"\nValid modes are: legacy, shadow, active.",
        "fix_command": "$env:AICARMINE_ORIENTATION_LANE_MODE = \"legacy\"",
    },
    {
        "name": "service_name_error",
        "pattern": r"service_name.*error|service_name.*invalid|broker_service_name.*error",
        "severity": "low",
        "solution": "The service_name is invalid. Set the correct value:\n  $env:AICARMINE_BROKER_SERVICE_NAME = \"aicarmine-vulkan-tool-broker\"",
        "fix_command": "$env:AICARMINE_BROKER_SERVICE_NAME = \"aicarmine-vulkan-tool-broker\"",
    },
    {
        "name": "app_title_error",
        "pattern": r"app_title.*error|app_title.*invalid|broker_app_title.*error",
        "severity": "low",
        "solution": "The app_title is invalid. Set the correct value:\n  $env:AICARMINE_BROKER_APP_TITLE = \"AI-Carmine Vulkan Tool Broker\"",
        "fix_command": "$env:AICARMINE_BROKER_APP_TITLE = \"AI-Carmine Vulkan Tool Broker\"",
    },
    {
        "name": "app_version_error",
        "pattern": r"app_version.*error|app_version.*invalid|broker_app_version.*error",
        "severity": "low",
        "solution": "The app_version is invalid. Set the correct value:\n  $env:AICARMINE_BROKER_APP_VERSION = \"2.0.0\"",
        "fix_command": "$env:AICARMINE_BROKER_APP_VERSION = \"2.0.0\"",
    },
    {
        "name": "app_description_error",
        "pattern": r"app_description.*error|app_description.*invalid|broker_app_description.*error",
        "severity": "low",
        "solution": "The app_description is invalid. Set the correct value:\n  $env:AICARMINE_BROKER_APP_DESCRIPTION = \"Internal 3572 broker. Receives public tool X from 3571, asks 11435/Vulkan to select one internal tool L, executes L, then deterministically wraps the dispatcher result as public X.\"",
        "fix_command": "$env:AICARMINE_BROKER_APP_DESCRIPTION = \"Internal 3572 broker. Receives public tool X from 3571, asks 11435/Vulkan to select one internal tool L, executes L, then deterministically wraps the dispatcher result as public X.\"",
    },
    {
        "name": "vulkan_agent_path_error",
        "pattern": r"vulkan_agent_path.*error|vulkan_agent_path.*invalid|broker_vulkan_agent_path.*error",
        "severity": "low",
        "solution": "The vulkan_agent_path is invalid. Set the correct value:\n  $env:AICARMINE_BROKER_VULKAN_AGENT_PATH = \"/vulkan/agent\"",
        "fix_command": "$env:AICARMINE_BROKER_VULKAN_AGENT_PATH = \"/vulkan/agent\"",
    },
    {
        "name": "jobs_index_path_error",
        "pattern": r"jobs_index_path.*error|jobs_index_path.*invalid|broker_jobs_index_path.*error",
        "severity": "low",
        "solution": "The jobs_index_path is invalid. Set the correct value:\n  $env:AICARMINE_BROKER_JOBS_PATH = \"/jobs\"",
        "fix_command": "$env:AICARMINE_BROKER_JOBS_PATH = \"/jobs\"",
    },
    {
        "name": "jobs_json_path_error",
        "pattern": r"jobs_json_path.*error|jobs_json_path.*invalid|broker_jobs_json_path.*error",
        "severity": "low",
        "solution": "The jobs_json_path is invalid. Set the correct value:\n  $env:AICARMINE_BROKER_JOBS_JSON_PATH = \"/jobs.json\"",
        "fix_command": "$env:AICARMINE_BROKER_JOBS_JSON_PATH = \"/jobs.json\"",
    },
    {
        "name": "health_path_error",
        "pattern": r"health_path.*error|health_path.*invalid|broker_health_path.*error",
        "severity": "low",
        "solution": "The health_path is invalid. Set the correct value:\n  $env:AICARMINE_BROKER_HEALTH_PATH = \"/health\"",
        "fix_command": "$env:AICARMINE_BROKER_HEALTH_PATH = \"/health\"",
    },
    {
        "name": "agent_approval_mode_error",
        "pattern": r"agent_approval_mode.*error|agent_approval_mode.*invalid|broker_agent_approval_mode.*error",
        "severity": "medium",
        "solution": "The agent_approval_mode is invalid. Set the correct value:\n  $env:AICARMINE_AGENT_APPROVAL_MODE = \"safe_write_lab\"\nValid modes are: safe_write_lab, prompt, auto.",
        "fix_command": "$env:AICARMINE_AGENT_APPROVAL_MODE = \"safe_write_lab\"",
    },
    {
        "name": "lab_repo_error",
        "pattern": r"lab_repo.*error|lab_repo.*invalid|broker_lab_repo.*error",
        "severity": "medium",
        "solution": "The lab_repo is invalid. Set the correct value:\n  $env:AICARMINE_LAB_REPO = \"C:\\Users\\sanit\\AI\\lab-worktrees\\blender-audio-project-lab\"",
        "fix_command": "$env:AICARMINE_LAB_REPO = \"C:\\Users\\sanit\\AI\\lab-worktrees\\blender-audio-project-lab\"",
    },
    {
        "name": "real_repo_error",
        "pattern": r"real_repo.*error|real_repo.*invalid|broker_real_repo.*error",
        "severity": "medium",
        "solution": "The real_repo is invalid. Set the correct value:\n  $env:AICARMINE_REAL_REPO = \"C:\\Users\\sanit\\ProjectsDir\\blender-audio-project\"",
        "fix_command": "$env:AICARMINE_REAL_REPO = \"C:\\Users\\sanit\\ProjectsDir\\blender-audio-project\"",
    },
    {
        "name": "workspace_error",
        "pattern": r"workspace.*error|workspace.*invalid|broker_workspace.*error",
        "severity": "medium",
        "solution": "The workspace is invalid. Set the correct value:\n  $env:AICARMINE_VULKAN_WORKSPACE = \"C:\\Users\\sanit\\AI\\qwen-agent-workspace\\vulkan-broker\"",
        "fix_command": "$env:AICARMINE_VULKAN_WORKSPACE = \"C:\\Users\\sanit\\AI\\qwen-agent-workspace\\vulkan-broker\"",
    },
    {
        "name": "agent_job_root_error",
        "pattern": r"agent_job_root.*error|agent_job_root.*invalid|broker_agent_job_root.*error",
        "severity": "medium",
        "solution": "The agent_job_root is invalid. Set the correct value:\n  $env:AICARMINE_AGENT_JOB_ROOT = \"C:\\Users\\sanit\\AI\\qwen-agent-workspace\\vulkan-broker\\agent-jobs\"",
        "fix_command": "$env:AICARMINE_AGENT_JOB_ROOT = \"C:\\Users\\sanit\\AI\\qwen-agent-workspace\\vulkan-broker\\agent-jobs\"",
    },
    {
        "name": "agent_job_db_error",
        "pattern": r"agent_job_db.*error|agent_job_db.*invalid|broker_agent_job_db.*error",
        "severity": "medium",
        "solution": "The agent_job_db is invalid. Set the correct value:\n  $env:AICARMINE_AGENT_JOB_DB = \"C:\\Users\\sanit\\AI\\qwen-agent-workspace\\vulkan-broker\\agent-jobs\\agent_jobs.sqlite3\"",
        "fix_command": "$env:AICARMINE_AGENT_JOB_DB = \"C:\\Users\\sanit\\AI\\qwen-agent-workspace\\vulkan-broker\\agent-jobs\\agent_jobs.sqlite3\"",
    },
    {
        "name": "planner_memory_db_error",
        "pattern": r"planner_memory_db.*error|planner_memory_db.*invalid|broker_planner_memory_db.*error",
        "severity": "medium",
        "solution": "The planner_memory_db is invalid. Set the correct value:\n  $env:AICARMINE_PLANNER_MEMORY_DB = \"C:\\Users\\sanit\\AI\\lab-worktrees\\blender-audio-project-lab\\indexAI\\agent_memory\\agent_memory.sqlite\"",
        "fix_command": "$env:AICARMINE_PLANNER_MEMORY_DB = \"C:\\Users\\sanit\\AI\\lab-worktrees\\blender-audio-project-lab\\indexAI\\agent_memory\\agent_memory.sqlite\"",
    },
    {
        "name": "planner_memory_retention_days_error",
        "pattern": r"planner_memory_retention_days.*error|planner_memory_retention_days.*invalid|broker_planner_memory_retention_days.*error",
        "severity": "low",
        "solution": "The planner_memory_retention_days is invalid. Set the correct value:\n  $env:AICARMINE_PLANNER_MEMORY_RETENTION_DAYS = \"2\"\nLarger values retain memory longer.",
        "fix_command": "$env:AICARMINE_PLANNER_MEMORY_RETENTION_DAYS = \"2\"",
    },
    {
        "name": "planner_rag_db_error",
        "pattern": r"planner_rag_db.*error|planner_rag_db.*invalid|broker_planner_rag_db.*error",
        "severity": "medium",
        "solution": "The planner_rag_db is invalid. Set the correct value:\n  $env:AICARMINE_PLANNER_RAG_DB = \"C:\\Users\\sanit\\AI\\lab-worktrees\\blender-audio-project-lab\\output\\ai_runtime_memory\\rag\\rag.sqlite\"",
        "fix_command": "$env:AICARMINE_PLANNER_RAG_DB = \"C:\\Users\\sanit\\AI\\lab-worktrees\\blender-audio-project-lab\\output\\ai_runtime_memory\\rag\\rag.sqlite\"",
    },
    {
        "name": "planner_intrinsic_context_max_chars_error",
        "pattern": r"planner_intrinsic_context_max_chars.*error|planner_intrinsic_context_max_chars.*invalid|broker_planner_intrinsic_context_max_chars.*error",
        "severity": "low",
        "solution": "The planner_intrinsic_context_max_chars is invalid. Set the correct value:\n  $env:AICARMINE_PLANNER_INTRINSIC_CONTEXT_MAX_CHARS = \"10000\"\nLarger values allow more context but take longer.",
        "fix_command": "$env:AICARMINE_PLANNER_INTRINSIC_CONTEXT_MAX_CHARS = \"10000\"",
    },
    {
        "name": "planner_intrinsic_rag_top_k_error",
        "pattern": r"planner_intrinsic_rag_top_k.*error|planner_intrinsic_rag_top_k.*invalid|broker_planner_intrinsic_rag_top_k.*error",
        "severity": "low",
        "solution": "The planner_intrinsic_rag_top_k is invalid. Set the correct value:\n  $env:AICARMINE_PLANNER_INTRINSIC_RAG_TOP_K = \"6\"\nLarger values return more results but take longer.",
        "fix_command": "$env:AICARMINE_PLANNER_INTRINSIC_RAG_TOP_K = \"6\"",
    },
    {
        "name": "planner_intrinsic_rag_char_budget_error",
        "pattern": r"planner_intrinsic_rag_char_budget.*error|planner_intrinsic_rag_char_budget.*invalid|broker_planner_intrinsic_rag_char_budget.*error",
        "severity": "low",
        "solution": "The planner_intrinsic_rag_char_budget is invalid. Set the correct value:\n  $env:AICARMINE_PLANNER_INTRINSIC_RAG_CHAR_BUDGET = \"2000\"\nLarger values allow more budget but take longer.",
        "fix_command": "$env:AICARMINE_PLANNER_INTRINSIC_RAG_CHAR_BUDGET = \"2000\"",
    },
    {
        "name": "planner_rag_reranking_engine_error",
        "pattern": r"planner_rag_reranking_engine.*error|planner_rag_reranking_engine.*invalid|broker_planner_rag_reranking_engine.*error",
        "severity": "low",
        "solution": "The planner_rag_reranking_engine is invalid. Set the correct value:\n  $env:RAG_RERANKING_ENGINE = \"\"\nEmpty means no reranking.",
        "fix_command": "$env:RAG_RERANKING_ENGINE = \"\"",
    },
    {
        "name": "planner_rag_external_reranker_url_error",
        "pattern": r"planner_rag_external_reranker_url.*error|planner_rag_external_reranker_url.*invalid|broker_planner_rag_external_reranker_url.*error",
        "severity": "low",
        "solution": "The planner_rag_external_reranker_url is invalid. Set the correct value:\n  $env:RAG_EXTERNAL_RERANKER_URL = \"\"\nEmpty means no external reranker.",
        "fix_command": "$env:RAG_EXTERNAL_RERANKER_URL = \"\"",
    },
    {
        "name": "planner_rag_reranking_model_error",
        "pattern": r"planner_rag_reranking_model.*error|planner_rag_reranking_model.*invalid|broker_planner_rag_reranking_model.*error",
        "severity": "low",
        "solution": "The planner_rag_reranking_model is invalid. Set the correct value:\n  $env:RAG_RERANKING_MODEL = \"BAAI/bge-reranker-v2-m3\"",
        "fix_command": "$env:RAG_RERANKING_MODEL = \"BAAI/bge-reranker-v2-m3\"",
    },
    {
        "name": "planner_rag_rerank_timeout_seconds_error",
        "pattern": r"planner_rag_rerank_timeout_seconds.*error|planner_rag_rerank_timeout_seconds.*invalid|broker_planner_rag_rerank_timeout_seconds.*error",
        "severity": "low",
        "solution": "The planner_rag_rerank_timeout_seconds is invalid. Set the correct value:\n  $env:AICARMINE_PLANNER_RAG_RERANK_TIMEOUT_SECONDS = \"30.0\"\nLarger values allow more time but take longer.",
        "fix_command": "$env:AICARMINE_PLANNER_RAG_RERANK_TIMEOUT_SECONDS = \"30.0\"",
    },
    {
        "name": "planner_rag_embedding_batch_size_error",
        "pattern": r"planner_rag_embedding_batch_size.*error|planner_rag_embedding_batch_size.*invalid|broker_planner_rag_embedding_batch_size.*error",
        "severity": "low",
        "solution": "The planner_rag_embedding_batch_size is invalid. Set the correct value:\n  $env:RAG_EMBEDDING_BATCH_SIZE = \"4\"\nLarger values allow more batching but take longer.",
        "fix_command": "$env:RAG_EMBEDDING_BATCH_SIZE = \"4\"",
    },
    {
        "name": "agent_public_base_url_error",
        "pattern": r"agent_public_base_url.*error|agent_public_base_url.*invalid|broker_agent_public_base_url.*error",
        "severity": "low",
        "solution": "The agent_public_base_url is invalid. Set the correct value:\n  $env:AICARMINE_AGENT_PUBLIC_BASE_URL = \"http://127.0.0.1:3572\"",
        "fix_command": "$env:AICARMINE_AGENT_PUBLIC_BASE_URL = \"http://127.0.0.1:3572\"",
    },
    {
        "name": "prompt_compact_ratio_error",
        "pattern": r"prompt_compact_ratio.*error|prompt_compact_ratio.*invalid|broker_prompt_compact_ratio.*error",
        "severity": "low",
        "solution": "The prompt_compact_ratio is invalid. Set the correct value:\n  $env:AICARMINE_AGENTIC_PLANNER_PROMPT_COMPACT_RATIO = \"0.85\"\nValid range is 0.0 to 1.0.",
        "fix_command": "$env:AICARMINE_AGENTIC_PLANNER_PROMPT_COMPACT_RATIO = \"0.85\"",
    },
    {
        "name": "native_max_parallel_readonly_error",
        "pattern": r"native_max_parallel_readonly.*error|native_max_parallel_readonly.*invalid|broker_native_max_parallel_readonly.*error",
        "severity": "low",
        "solution": "The native_max_parallel_readonly is invalid. Set the correct value:\n  $env:AICARMINE_AGENTIC_PLANNER_NATIVE_MAX_PARALLEL_READONLY = \"8\"\nLarger values allow more parallelism but may cause contention.",
        "fix_command": "$env:AICARMINE_AGENTIC_PLANNER_NATIVE_MAX_PARALLEL_READONLY = \"8\"",
    },
    {
        "name": "agentic_fallback_oneshot_error",
        "pattern": r"agentic_fallback_oneshot.*error|agentic_fallback_oneshot.*invalid|broker_agentic_fallback_oneshot.*error",
        "severity": "low",
        "solution": "The agentic_fallback_oneshot is invalid. Set the correct value:\n  $env:AICARMINE_AGENTIC_FALLBACK_ONESHOT = \"0\"\n0 means disabled.",
        "fix_command": "$env:AICARMINE_AGENTIC_FALLBACK_ONESHOT = \"0\"",
    },
    {
        "name": "agentic_planner_enabled_error",
        "pattern": r"agentic_planner_enabled.*error|agentic_planner_enabled.*invalid|broker_agentic_planner_enabled.*error",
        "severity": "medium",
        "solution": "The agentic_planner_enabled is invalid. Set the correct value:\n  $env:AICARMINE_AGENTIC_PLANNER_ENABLED = \"1\"\n1 means enabled.",
        "fix_command": "$env:AICARMINE_AGENTIC_PLANNER_ENABLED = \"1\"",
    },
    {
        "name": "planner_incomprehensible_retries_error",
        "pattern": r"planner_incomprehensible_retries.*error|planner_incomprehensible_retries.*invalid|broker_planner_incomprehensible_retries.*error",
        "severity": "low",
        "solution": "The planner_incomprehensible_retries is invalid. Set the correct value:\n  $env:AICARMINE_AGENTIC_PLANNER_INCOMPREHENSIBLE_RETRIES = \"3\"\nLarger values allow more retries but take longer.",
        "fix_command": "$env:AICARMINE_AGENTIC_PLANNER_INCOMPREHENSIBLE_RETRIES = \"3\"",
    },
    {
        "name": "default_max_steps_error",
        "pattern": r"default_max_steps.*error|default_max_steps.*invalid|broker_default_max_steps.*error",
        "severity": "medium",
        "solution": "The default_max_steps is invalid. Set the correct value:\n  $env:AICARMINE_AGENT_DEFAULT_MAX_STEPS = \"40\"\nLarger values allow more steps but take longer.",
        "fix_command": "$env:AICARMINE_AGENT_DEFAULT_MAX_STEPS = \"40\"",
    },
    {
        "name": "max_steps_error",
        "pattern": r"max_steps.*error|max_steps.*invalid|broker_max_steps.*error",
        "severity": "medium",
        "solution": "The max_steps is invalid. Set the correct value:\n  $env:AICARMINE_AGENT_MAX_STEPS = \"100\"\nLarger values allow more steps but take longer.",
        "fix_command": "$env:AICARMINE_AGENT_MAX_STEPS = \"100\"",
    },
    {
        "name": "return_wait_seconds_error",
        "pattern": r"return_wait_seconds.*error|return_wait_seconds.*invalid|broker_return_wait_seconds.*error",
        "severity": "low",
        "solution": "The return_wait_seconds is invalid. Set the correct value:\n  $env:AICARMINE_AGENT_RETURN_WAIT_SECONDS = \"900\"\nLarger values wait longer before returning.",
        "fix_command": "$env:AICARMINE_AGENT_RETURN_WAIT_SECONDS = \"900\"",
    },
    {
        "name": "wait_poll_seconds_error",
        "pattern": r"wait_poll_seconds.*error|wait_poll_seconds.*invalid|broker_wait_poll_seconds.*error",
        "severity": "low",
        "solution": "The wait_poll_seconds is invalid. Set the correct value:\n  $env:AICARMINE_AGENT_WAIT_POLL_SECONDS = \"1.0\"\nLarger values poll less frequently but take longer.",
        "fix_command": "$env:AICARMINE_AGENT_WAIT_POLL_SECONDS = \"1.0\"",
    },
    {
        "name": "job_max_inline_events_error",
        "pattern": r"job_max_inline_events.*error|job_max_inline_events.*invalid|broker_job_max_inline_events.*error",
        "severity": "low",
        "solution": "The job_max_inline_events is invalid. Set the correct value:\n  $env:AICARMINE_AGENT_JOB_MAX_INLINE_EVENTS = \"20\"\nLarger values allow more inline events but take longer.",
        "fix_command": "$env:AICARMINE_AGENT_JOB_MAX_INLINE_EVENTS = \"20\"",
    },
    {
        "name": "public_summary_chars_error",
        "pattern": r"public_summary_chars.*error|public_summary_chars.*invalid|broker_public_summary_chars.*error",
        "severity": "low",
        "solution": "The public_summary_chars is invalid. Set the correct value:\n  $env:AICARMINE_AGENT_PUBLIC_SUMMARY_CHARS = \"4000\"\nLarger values allow more summary but take longer.",
        "fix_command": "$env:AICARMINE_AGENT_PUBLIC_SUMMARY_CHARS = \"4000\"",
    },
    {
        "name": "public_answer_chars_error",
        "pattern": r"public_answer_chars.*error|public_answer_chars.*invalid|broker_public_answer_chars.*error",
        "severity": "low",
        "solution": "The public_answer_chars is invalid. Set the correct value:\n  $env:AICARMINE_AGENT_PUBLIC_ANSWER_CHARS = \"0\"\n0 means unlimited.",
        "fix_command": "$env:AICARMINE_AGENT_PUBLIC_ANSWER_CHARS = \"0\"",
    },
    {
        "name": "public_result_inline_chars_error",
        "pattern": r"public_result_inline_chars.*error|public_result_inline_chars.*invalid|broker_public_result_inline_chars.*error",
        "severity": "low",
        "solution": "The public_result_inline_chars is invalid. Set the correct value:\n  $env:AICARMINE_AGENT_PUBLIC_RESULT_INLINE_CHARS = \"25000\"\nLarger values allow more inline output but take longer.",
        "fix_command": "$env:AICARMINE_AGENT_PUBLIC_RESULT_INLINE_CHARS = \"25000\"",
    },
    {
        "name": "jobs_refresh_seconds_error",
        "pattern": r"jobs_refresh_seconds.*error|jobs_refresh_seconds.*invalid|broker_jobs_refresh_seconds.*error",
        "severity": "low",
        "solution": "The jobs_refresh_seconds is invalid. Set the correct value:\n  $env:AICARMINE_BROKER_JOBS_REFRESH_SECONDS = \"10\"\nLarger values refresh less frequently but take longer.",
        "fix_command": "$env:AICARMINE_BROKER_JOBS_REFRESH_SECONDS = \"10\"",
    },
    {
        "name": "max_tool_result_chars_error",
        "pattern": r"max_tool_result_chars.*error|max_tool_result_chars.*invalid|broker_max_tool_result_chars.*error",
        "severity": "low",
        "solution": "The max_tool_result_chars is invalid. Set the correct value:\n  $env:AICARMINE_CODEX_MAX_TOOL_RESULT_CHARS = \"12000\"\nLarger values allow more output but take longer.",
        "fix_command": "$env:AICARMINE_CODEX_MAX_TOOL_RESULT_CHARS = \"12000\"",
    },
    {
        "name": "command_timeout_error",
        "pattern": r"command_timeout.*error|command_timeout.*invalid|broker_command_timeout.*error",
        "severity": "low",
        "solution": "The command_timeout is invalid. Set the correct value:\n  $env:AICARMINE_CODEX_COMMAND_TIMEOUT = \"600\"\nLarger values allow more time but take longer.",
        "fix_command": "$env:AICARMINE_CODEX_COMMAND_TIMEOUT = \"600\"",
    },
    {
        "name": "vulkan_interpreter_num_predict_error",
        "pattern": r"vulkan_interpreter_num_predict.*error|vulkan_interpreter_num_predict.*invalid|broker_vulkan_interpreter_num_predict.*error",
        "severity": "low",
        "solution": "The vulkan_interpreter_num_predict is invalid. Set the correct value:\n  $env:AICARMINE_VULKAN_INTERPRETER_NUM_PREDICT = \"1024\"\nLarger values allow more output but take longer.",
        "fix_command": "$env:AICARMINE_VULKAN_INTERPRETER_NUM_PREDICT = \"1024\"",
    },
    {
        "name": "openapi_contract_error",
        "pattern": r"openapi_contract.*error|openapi_contract.*invalid|broker_openapi_contract.*error",
        "severity": "low",
        "solution": "The openapi_contract is invalid. Set the correct value:\n  $env:AICARMINE_BROKER_OPENAPI_CONTRACT = \"3572: public X from 3571 -> 11435 selects internal L -> 3572 dispatcher executes L -> 3572 deterministic field mapping wraps L result as public X -> 3572 returns wrapper.\"",
        "fix_command": "$env:AICARMINE_BROKER_OPENAPI_CONTRACT = \"3572: public X from 3571 -> 11435 selects internal L -> 3572 dispatcher executes L -> 3572 deterministic field mapping wraps L result as public X -> 3572 returns wrapper.\"",
    },
    {
        "name": "v6_marker_error",
        "pattern": r"v6_marker.*error|v6_marker.*invalid|broker_v6_marker.*error",
        "severity": "low",
        "solution": "The v6_marker is invalid. Set the correct value:\n  $env:AICARMINE_BROKER_V6_MARKER = \"public_x_v6_vulkan_select_dispatcher_execute_deterministic_wrap\"",
        "fix_command": "$env:AICARMINE_BROKER_V6_MARKER = \"public_x_v6_vulkan_select_dispatcher_execute_deterministic_wrap\"",
    },
    {
        "name": "orientation_lane_mode_error",
        "pattern": r"orientation_lane_mode.*error|orientation_lane_mode.*invalid|broker_orientation_lane_mode.*error",
        "severity": "medium",
        "solution": "The orientation_lane_mode is invalid. Set the correct value:\n  $env:AICARMINE_ORIENTATION_LANE_MODE = \"legacy\"\nValid modes are: legacy, shadow, active.",
        "fix_command": "$env:AICARMINE_ORIENTATION_LANE_MODE = \"legacy\"",
    },
    {
        "name": "service_name_error",
        "pattern": r"service_name.*error|service_name.*invalid|broker_service_name.*error",
        "severity": "low",
        "solution": "The service_name is invalid. Set the correct value:\n  $env:AICARMINE_BROKER_SERVICE_NAME = \"aicarmine-vulkan-tool-broker\"",
        "fix_command": "$env:AICARMINE_BROKER_SERVICE_NAME = \"aicarmine-vulkan-tool-broker\"",
    },
    {
        "name": "app_title_error",
        "pattern": r"app_title.*error|app_title.*invalid|broker_app_title.*error",
        "severity": "low",
        "solution": "The app_title is invalid. Set the correct value:\n  $env:AICARMINE_BROKER_APP_TITLE = \"AI-Carmine Vulkan Tool Broker\"",
        "fix_command": "$env:AICARMINE_BROKER_APP_TITLE = \"AI-Carmine Vulkan Tool Broker\"",
    },
    {
        "name": "app_version_error",
        "pattern": r"app_version.*error|app_version.*invalid|broker_app_version.*error",
        "severity": "low",
        "solution": "The app_version is invalid. Set the correct value:\n  $env:AICARMINE_BROKER_APP_VERSION = \"2.0.0\"",
        "fix_command": "$env:AICARMINE_BROKER_APP_VERSION = \"2.0.0\"",
    },
    {
        "name": "app_description_error",
        "pattern": r"app_description.*error|app_description.*invalid|broker_app_description.*error",
        "severity": "low",
        "solution": "The app_description is invalid. Set the correct value:\n  $env:AICARMINE_BROKER_APP_DESCRIPTION = \"Internal 3572 broker. Receives public tool X from 3571, asks 11435/Vulkan to select one internal tool L, executes L, then deterministically wraps the dispatcher result as public X.\"",
        "fix_command": "$env:AICARMINE_BROKER_APP_DESCRIPTION = \"Internal 3572 broker. Receives public tool X from 3571, asks 11435/Vulkan to select one internal tool L, executes L, then deterministically wraps the dispatcher result as public X.\"",
    },
    {
        "name": "vulkan_agent_path_error",
        "pattern": r"vulkan_agent_path.*error|vulkan_agent_path.*invalid|broker_vulkan_agent_path.*error",
        "severity": "low",
        "solution": "The vulkan_agent_path is invalid. Set the correct value:\n  $env:AICARMINE_BROKER_VULKAN_AGENT_PATH = \"/vulkan/agent\"",
        "fix_command": "$env:AICARMINE_BROKER_VULKAN_AGENT_PATH = \"/vulkan/agent\"",
    },
    {
        "name": "jobs_index_path_error",
        "pattern": r"jobs_index_path.*error|jobs_index_path.*invalid|broker_jobs_index_path.*error",
        "severity": "low",
        "solution": "The jobs_index_path is invalid. Set the correct value:\n  $env:AICARMINE_BROKER_JOBS_PATH = \"/jobs\"",
        "fix_command": "$env:AICARMINE_BROKER_JOBS_PATH = \"/jobs\"",
    },
    {
        "name": "jobs_json_path_error",
        "pattern": r"jobs_json_path.*error|jobs_json_path.*invalid|broker_jobs_json_path.*error",
        "severity": "low",
        "solution": "The jobs_json_path is invalid. Set the correct value:\n  $env:AICARMINE_BROKER_JOBS_JSON_PATH = \"/jobs.json\"",
        "fix_command": "$env:AICARMINE_BROKER_JOBS_JSON_PATH = \"/jobs.json\"",
    },
    {
        "name": "health_path_error",
        "pattern": r"health_path.*error|health_path.*invalid|broker_health_path.*error",
        "severity": "low",
        "solution": "The health_path is invalid. Set the correct value:\n  $env:AICARMINE_BROKER_HEALTH_PATH = \"/health\"",
        "fix_command": "$env:AICARMINE_BROKER_HEALTH_PATH = \"/health\"",
    },
    {
        "name": "agent_approval_mode_error",
        "pattern": r"agent_approval_mode.*error|agent_approval_mode.*invalid|broker_agent_approval_mode.*error",
        "severity": "medium",
        "solution": "The agent_approval_mode is invalid. Set the correct value:\n  $env:AICARMINE_AGENT_APPROVAL_MODE = \"safe_write_lab\"\nValid modes are: safe_write_lab, prompt, auto.",
        "fix_command": "$env:AICARMINE_AGENT_APPROVAL_MODE = \"safe_write_lab\"",
    },
    {
        "name": "lab_repo_error",
        "pattern": r"lab_repo.*error|lab_repo.*invalid|broker_lab_repo.*error",
        "severity": "medium",
        "solution": "The lab_repo is invalid. Set the correct value:\n  $env:AICARMINE_LAB_REPO = \"C:\\Users\\sanit\\AI\\lab-worktrees\\blender-audio-project-lab\"",
        "fix_command": "$env:AICARMINE_LAB_REPO = \"C:\\Users\\sanit\\AI\\lab-worktrees\\blender-audio-project-lab\"",
    },
    {
        "name": "real_repo_error",
        "pattern": r"real_repo.*error|real_repo.*invalid|broker_real_repo.*error",
        "severity": "medium",
        "solution": "The real_repo is invalid. Set the correct value:\n  $env:AICARMINE_REAL_REPO = \"C:\\Users\\sanit\\ProjectsDir\\blender-audio-project\"",
        "fix_command": "$env:AICARMINE_REAL_REPO = \"C:\\Users\\sanit\\ProjectsDir\\blender-audio-project\"",
    },
    {
        "name": "workspace_error",
        "pattern": r"workspace.*error|workspace.*invalid|broker_workspace.*error",
        "severity": "medium",
        "solution": "The workspace is invalid. Set the correct value:\n  $env:AICARMINE_VULKAN_WORKSPACE = \"C:\\Users\\sanit\\AI\\qwen-agent-workspace\\vulkan-broker\"",
        "fix_command": "$env:AICARMINE_VULKAN_WORKSPACE = \"C:\\Users\\sanit\\AI\\qwen-agent-workspace\\vulkan-broker\"",
    },
    {
        "name": "agent_job_root_error",
        "pattern": r"agent_job_root.*error|agent_job_root.*invalid|broker_agent_job_root.*error",
        "severity": "medium",
        "solution": "The agent_job_root is invalid. Set the correct value:\n  $env:AICARMINE_AGENT_JOB_ROOT = \"C:\\Users\\sanit\\AI\\qwen-agent-workspace\\vulkan-broker\\agent-jobs\"",
        "fix_command": "$env:AICARMINE_AGENT_JOB_ROOT = \"C:\\Users\\sanit\\AI\\qwen-agent-workspace\\vulkan-broker\\agent-jobs\"",
    },
    {
        "name": "agent_job_db_error",
        "pattern": r"agent_job_db.*error|agent_job_db.*invalid|broker_agent_job_db.*error",
        "severity": "medium",
        "solution": "The agent_job_db is invalid. Set the correct value:\n  $env:AICARMINE_AGENT_JOB_DB = \"C:\\Users\\sanit\\AI\\qwen-agent-workspace\\vulkan-broker\\agent-jobs\\agent_jobs.sqlite3\"",
        "fix_command": "$env:AICARMINE_AGENT_JOB_DB = \"C:\\Users\\sanit\\AI\\qwen-agent-workspace\\vulkan-broker\\agent-jobs\\agent_jobs.sqlite3\"",
    },
    {
        "name": "planner_memory_db_error",
        "pattern": r"planner_memory_db.*error|planner_memory_db.*invalid|broker_planner_memory_db.*error",
        "severity": "medium",
        "solution": "The planner_memory_db is invalid. Set the correct value:\n  $env:AICARMINE_PLANNER_MEMORY_DB = \"C:\\Users\\sanit\\AI\\lab-worktrees\\blender-audio-project-lab\\indexAI\\agent_memory\\agent_memory.sqlite\"",
        "fix_command": "$env:AICARMINE_PLANNER_MEMORY_DB = \"C:\\Users\\sanit\\AI\\lab-worktrees\\blender-audio-project-lab\\indexAI\\agent_memory\\agent_memory.sqlite\"",
    },
    {
        "name": "planner_memory_retention_days_error",
        "pattern": r"planner_memory_retention_days.*error|planner_memory_retention_days.*invalid|broker_planner_memory_retention_days.*error",
        "severity": "low",
        "solution": "The planner_memory_retention_days is invalid. Set the correct value:\n  $env:AICARMINE_PLANNER_MEMORY_RETENTION_DAYS = \"2\"\nLarger values retain memory longer.",
        "fix_command": "$env:AICARMINE_PLANNER_MEMORY_RETENTION_DAYS = \"2\"",
    },
    {
        "name": "planner_rag_db_error",
        "pattern": r"planner_rag_db.*error|planner_rag_db.*invalid|broker_planner_rag_db.*error",
        "severity": "medium",
        "solution": "The planner_rag_db is invalid. Set the correct value:\n  $env:AICARMINE_PLANNER_RAG_DB = \"C:\\Users\\sanit\\AI\\lab-worktrees\\blender-audio-project-lab\\output\\ai_runtime_memory\\rag\\rag.sqlite\"",
        "fix_command": "$env:AICARMINE_PLANNER_RAG_DB = \"C:\\Users\\sanit\\AI\\lab-worktrees\\blender-audio-project-lab\\output\\ai_runtime_memory\\rag\\rag.sqlite\"",
    },
    {
        "name": "planner_intrinsic_context_max_chars_error",
        "pattern": r"planner_intrinsic_context_max_chars.*error|planner_intrinsic_context_max_chars.*invalid|broker_planner_intrinsic_context_max_chars.*error",
        "severity": "low",
        "solution": "The planner_intrinsic_context_max_chars is invalid. Set the correct value:\n  $env:AICARMINE_PLANNER_INTRINSIC_CONTEXT_MAX_CHARS = \"10000\"\nLarger values allow more context but take longer.",
        "fix_command": "$env:AICARMINE_PLANNER_INTRINSIC_CONTEXT_MAX_CHARS = \"10000\"",
    },
    {
        "name": "planner_intrinsic_rag_top_k_error",
        "pattern": r"planner_intrinsic_rag_top_k.*error|planner_intrinsic_rag_top_k.*invalid|broker_planner_intrinsic_rag_top_k.*error",
        "severity": "low",
        "solution": "The planner_intrinsic_rag_top_k is invalid. Set the correct value:\n  $env:AICARMINE_PLANNER_INTRINSIC_RAG_TOP_K = \"6\"\nLarger values return more results but take longer.",
        "fix_command": "$env:AICARMINE_PLANNER_INTRINSIC_RAG_TOP_K = \"6\"",
    },
    {
        "name": "planner_intrinsic_rag_char_budget_error",
        "pattern": r"planner_intrinsic_rag_char_budget.*error|planner_intrinsic_rag_char_budget.*invalid|broker_planner_intrinsic_rag_char_budget.*error",
        "severity": "low",
        "solution": "The planner_intrinsic_rag_char_budget is invalid. Set the correct value:\n  $env:AICARMINE_PLANNER_INTRINSIC_RAG_CHAR_BUDGET = \"2000\"\nLarger values allow more budget but take longer.",
        "fix_command": "$env:AICARMINE_PLANNER_INTRINSIC_RAG_CHAR_BUDGET = \"2000\"",
    },
    {
        "name": "planner_rag_reranking_engine_error",
        "pattern": r"planner_rag_reranking_engine.*error|planner_rag_reranking_engine.*invalid|broker_planner_rag_reranking_engine.*error",
        "severity": "low",
        "solution": "The planner_rag_reranking_engine is invalid. Set the correct value:\n  $env:RAG_RERANKING_ENGINE = \"\"\nEmpty means no reranking.",
        "fix_command": "$env:RAG_RERANKING_ENGINE = \"\"",
    },
    {
        "name": "planner_rag_external_reranker_url_error",
        "pattern": r"planner_rag_external_reranker_url.*error|planner_rag_external_reranker_url.*invalid|broker_planner_rag_external_reranker_url.*error",
        "severity": "low",
        "solution": "The planner_rag_external_reranker_url is invalid. Set the correct value:\n  $env:RAG_EXTERNAL_RERANKER_URL = \"\"\nEmpty means no external reranker.",
        "fix_command": "$env:RAG_EXTERNAL_RERANKER_URL = \"\"",
    },
    {
        "name": "planner_rag_reranking_model_error",
        "pattern": r"planner_rag_reranking_model.*error|planner_rag_reranking_model.*invalid|broker_planner_rag_reranking_model.*error",
        "severity": "low",
        "solution": "The planner_rag_reranking_model is invalid. Set the correct value:\n  $env:RAG_RERANKING_MODEL = \"BAAI/bge-reranker-v2-m3\"",
        "fix_command": "$env:RAG_RERANKING_MODEL = \"BAAI/bge-reranker-v2-m3\"",
    },
    {
        "name": "planner_rag_rerank_timeout_seconds_error",
        "pattern": r"planner_rag_rerank_timeout_seconds.*error|planner_rag_rerank_timeout_seconds.*invalid|broker_planner_rag_rerank_timeout_seconds.*error",
        "severity": "low",
        "solution": "The planner_rag_rerank_timeout_seconds is invalid. Set the correct value:\n  $env:AICARMINE_PLANNER_RAG_RERANK_TIMEOUT_SECONDS = \"30.0\"\nLarger values allow more time but take longer.",
        "fix_command": "$env:AICARMINE_PLANNER_RAG_RERANK_TIMEOUT_SECONDS = \"30.0\"",
    },
    {
        "name": "planner_rag_embedding_batch_size_error",
        "pattern": r"planner_rag_embedding_batch_size.*error|planner_rag_embedding_batch_size.*invalid|broker_planner_rag_embedding_batch_size.*error",
        "severity": "low",
        "solution": "The planner_rag_embedding_batch_size is invalid. Set the correct value:\n  $env:RAG_EMBEDDING_BATCH_SIZE = \"4\"\nLarger values allow more batching but take longer.",
        "fix_command": "$env:RAG_EMBEDDING_BATCH_SIZE = \"4\"",
    },
    {
        "name": "agent_public_base_url_error",
        "pattern": r"agent_public_base_url.*error|agent_public_base_url.*invalid|broker_agent_public_base_url.*error",
        "severity": "low",
        "solution": "The agent_public_base_url is invalid. Set the correct value:\n  $env:AICARMINE_AGENT_PUBLIC_BASE_URL = \"http://127.0.0.1:3572\"",
        "fix_command": "$env:AICARMINE_AGENT_PUBLIC_BASE_URL = \"http://127.0.0.1:3572\"",
    },
    {
        "name": "prompt_compact_ratio_error",
        "pattern": r"prompt_compact_ratio.*error|prompt_compact_ratio.*invalid|broker_prompt_compact_ratio.*error",
        "severity": "low",
        "solution": "The prompt_compact_ratio is invalid. Set the correct value:\n  $env:AICARMINE_AGENTIC_PLANNER_PROMPT_COMPACT_RATIO = \"0.85\"\nValid range is 0.0 to 1.0.",
        "fix_command": "$env:AICARMINE_AGENTIC_PLANNER_PROMPT_COMPACT_RATIO = \"0.85\"",
    },
    {
        "name": "native_max_parallel_readonly_error",
        "pattern": r"native_max_parallel_readonly.*error|native_max_parallel_readonly.*invalid|broker_native_max_parallel_readonly.*error",
        "severity": "low",
        "solution": "The native_max_parallel_readonly is invalid. Set the correct value:\n  $env:AICARMINE_AGENTIC_PLANNER_NATIVE_MAX_PARALLEL_READONLY = \"8\"\nLarger values allow more parallelism but may cause contention.",
        "fix_command": "$env:AICARMINE_AGENTIC_PLANNER_NATIVE_MAX_PARALLEL_READONLY = \"8\"",
    },
    {
        "name": "agentic_fallback_oneshot_error",
        "pattern": r"agentic_fallback_oneshot.*error|agentic_fallback_oneshot.*invalid|broker_agentic_fallback_oneshot.*error",
        "severity": "low",
        "solution": "The agentic_fallback_oneshot is invalid. Set the correct value:\n  $env:AICARMINE_AGENTIC_FALLBACK_ONESHOT = \"0\"\n0 means disabled.",
        "fix_command": "$env:AICARMINE_AGENTIC_FALLBACK_ONESHOT = \"0\"",
    },
    {
        "name": "agentic_planner_enabled_error",
        "pattern": r"agentic_planner_enabled.*error|agentic_planner_enabled.*invalid|broker_agentic_planner_enabled.*error",
        "severity": "medium",
        "solution": "The agentic_planner_enabled is invalid. Set the correct value:\n  $env:AICARMINE_AGENTIC_PLANNER_ENABLED = \"1\"\n1 means enabled.",
        "fix_command": "$env:AICARMINE_AGENTIC_PLANNER_ENABLED = \"1\"",
    },
    {
        "name": "planner_incomprehensible_retries_error",
        "pattern": r"planner_incomprehensible_retries.*error|planner_incomprehensible_retries.*invalid|broker_planner_incomprehensible_retries.*error",
        "severity": "low",
        "solution": "The planner_incomprehensible_retries is invalid. Set the correct value:\n  $env:AICARMINE_AGENTIC_PLANNER_INCOMPREHENSIBLE_RETRIES = \"3\"\nLarger values allow more retries but take longer.",
        "fix_command": "$env:AICARMINE_AGENTIC_PLANNER_INCOMPREHENSIBLE_RETRIES = \"3\"",
    },
]


def analyze_log_content(content: str) -> list[dict[str, Any]]:
    """Analyze log content and return matching error patterns."""
    results = []
    for pattern in ERROR_PATTERNS:
        if re.search(pattern["pattern"], content):
            results.append({
                "name": pattern["name"],
                "severity": pattern["severity"],
                "solution": pattern["solution"],
                "fix_command": pattern["fix_command"],
            })
    return results


def main():
    """Main entry point for the diagnostic tool."""
    parser = argparse.ArgumentParser(description="AI-Powered Diagnostic Tool for AICarmine Broker")
    parser.add_argument("--log-dir", type=str, default=None, help="Directory containing log files")
    parser.add_argument("--port", type=int, default=3579, help="Port to check")
    parser.add_argument("--input", type=str, default=None, help="Input file to analyze")
    args = parser.parse_args()

    # Analyze input file if provided
    if args.input:
        with open(args.input, "r") as f:
            content = f.read()
        results = analyze_log_content(content)
        if results:
            print(f"Found {len(results)} error pattern(s):")
            for result in results:
                print(f"\n{'='*60}")
                print(f"Error: {result['name']}")
                print(f"Severity: {result['severity']}")
                print(f"Solution:\n{result['solution']}")
                print(f"Fix command: {result['fix_command']}")
        else:
            print("No error patterns found.")
        return

    # Check port if provided
    if args.port:
        import subprocess
        result = subprocess.run(['command', 'arg1', 'arg2'], check=True, capture_output=True, text=True)
        if result.stdout:
            print(f"Port {args.port} is in use:")
            print(result.stdout)
        else:
            print(f"Port {args.port} is free.")
        return

    # Analyze log directory if provided
    if args.log_dir:
        log_dir = Path(args.log_dir)
        if log_dir.exists():
            for log_file in log_dir.glob("*.log"):
                with open(log_file, "r") as f:
                    content = f.read()
                results = analyze_log_content(content)
                if results:
                    print(f"\n{'='*60}")
                    print(f"File: {log_file}")
                    print(f"Found {len(results)} error pattern(s):")
                    for result in results:
                        print(f"\n{'='*60}")
                        print(f"Error: {result['name']}")
                        print(f"Severity: {result['severity']}")
                        print(f"Solution:\n{result['solution']}")
                        print(f"Fix command: {result['fix_command']}")
        return

    # Print usage instructions
    print("AI-Powered Diagnostic Tool for AICarmine Broker")
    print("=" * 60)
    print("\nUsage:")
    print("  python diagnostic_tool.py --help")
    print("  python diagnostic_tool.py --log-dir C:\\Users\\sanit\\AI\\logs")
    print("  python diagnostic_tool.py --port 3579")
    print("  python diagnostic_tool.py --input C:\\Users\\sanit\\AI\\logs\\broker-3579-*.stderr.log")


if __name__ == "__main__":
    main()