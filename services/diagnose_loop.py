# ------------------------------------------------------------------
# Diagnose Agentic Loop Issues
# ------------------------------------------------------------------
# This script diagnoses issues with the agentic loop, particularly:
# - Preplanner working but Reranker not starting
# - Initial loop phase failures
# ------------------------------------------------------------------

import os
import sys
import subprocess
import json
from pathlib import Path
from typing import Dict, List, Any


def check_ports() -> Dict[str, Any]:
    """Check which ports are in use."""
    result = subprocess.run(
        ["netstat", "-ano", "-p", "tcp"],
        capture_output=True,
        text=True
    )
    return result.stdout


def check_processes() -> Dict[str, Any]:
    """Check running processes."""
    result = subprocess.run(
        ["Get-Process", "-Name", "python", "ollama", "uvicorn"],
        capture_output=True,
        text=True,
        shell=True
    )
    return result.stdout


def check_env_vars() -> Dict[str, Any]:
    """Check critical environment variables."""
    env_vars = {
        "AICARMINE_AGENTIC_PLANNER_MODEL": os.environ.get("AICARMINE_AGENTIC_PLANNER_MODEL", ""),
        "AICARMINE_VULKAN_BROKER_MODEL": os.environ.get("AICARMINE_VULKAN_BROKER_MODEL", ""),
        "RAG_RERANKING_ENGINE": os.environ.get("RAG_RERANKING_ENGINE", ""),
        "AICARMINE_LAB_REPO": os.environ.get("AICARMINE_LAB_REPO", ""),
    }
    return env_vars


def check_ollama_status() -> Dict[str, Any]:
    """Check Ollama status."""
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True
        )
        return {
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    except Exception as e:
        return {"error": str(e)}


def check_reranker_status() -> Dict[str, Any]:
    """Check Reranker (OVMS) status."""
    try:
        import urllib.request
        url = "http://127.0.0.1:3550/v2/models/BAAI/bge-reranker-v2-m3/ready"
        with urllib.request.urlopen(url, timeout=5) as response:
            return {"status": "healthy", "response": response.read().decode()}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


def check_broker_status() -> Dict[str, Any]:
    """Check broker status."""
    try:
        import urllib.request
        url = "http://127.0.0.1:3579/health"
        with urllib.request.urlopen(url, timeout=5) as response:
            return {"status": "healthy", "response": response.read().decode()}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


def diagnose():
    """Run all diagnostics."""
    print("=" * 60)
    print("AGENTIC LOOP DIAGNOSTIC REPORT")
    print("=" * 60)
    
    print("\n1. ENVIRONMENT VARIABLES:")
    env_vars = check_env_vars()
    for k, v in env_vars.items():
        print(f"   {k}: {v}")
    
    print("\n2. OLLAMA STATUS:")
    ollama_status = check_ollama_status()
    print(f"   Exit code: {ollama_status.get('exit_code')}")
    print(f"   Output: {ollama_status.get('stdout', '')[:200]}")
    
    print("\n3. RERANKER STATUS:")
    reranker_status = check_reranker_status()
    print(f"   Status: {reranker_status.get('status')}")
    print(f"   Error: {reranker_status.get('error', '')[:200]}")
    
    print("\n4. BROKER STATUS:")
    broker_status = check_broker_status()
    print(f"   Status: {broker_status.get('status')}")
    print(f"   Error: {broker_status.get('error', '')[:200]}")
    
    print("\n5. PORTS IN USE:")
    ports = check_ports()
    for line in ports.split('\n'):
        if any(port in line for port in ['3550', '3572', '3579', '11434', '11435']):
            print(f"   {line}")
    
    print("\n6. RECOMMENDATIONS:")
    if reranker_status.get('status') == 'unhealthy':
        print("   - Reranker is not running. Start it with:")
        print("     python services/ovms-reranker-npu.ps1")
        print("   - Or disable reranking:")
        print("     $env:RAG_RERANKING_ENGINE = ''")
    
    if ollama_status.get('exit_code') != 0:
        print("   - Ollama is not running. Start it with:")
        print("     ollama serve")
        print("     ollama run mio-qwen-code3:latest")
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    diagnose()