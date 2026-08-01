# ------------------------------------------------------------------
# Diagnose OVMS Reranker Silent Failure
# ------------------------------------------------------------------
# This script diagnoses why OVMS.exe opens but then fails silently
# ------------------------------------------------------------------

import os
import sys
import subprocess
import json
from pathlib import Path
from typing import Dict, Any


def get_env_vars() -> Dict[str, str]:
    """Get critical environment variables."""
    env_vars = {}
    for name in ["OVMS_ROOT", "OVMS_EXE", "OVMS_SETUP", "OVMS_RERANK_MODELS", "OPENVINO_PROVIDER_DEVICE"]:
        # Use os.environ directly (no scope parameter)
        value = os.environ.get(name, "")
        env_vars[name] = value
    return env_vars


def check_ovms_exe() -> Dict[str, Any]:
    """Check if OVMS.exe exists and is accessible."""
    env_vars = get_env_vars()
    ovms_exe = env_vars.get("OVMS_EXE", "")
    
    result = {
        "exists": False,
        "path": ovms_exe,
        "size": 0,
        "error": "",
    }
    
    if not ovms_exe:
        result["error"] = "OVMS_EXE not set"
        return result
    
    try:
        path = Path(ovms_exe)
        result["exists"] = path.exists()
        if path.exists():
            result["size"] = path.stat().st_size
    except Exception as e:
        result["error"] = str(e)
    
    return result


def check_ovms_config() -> Dict[str, Any]:
    """Check OVMS config file."""
    env_vars = get_env_vars()
    models = env_vars.get("OVMS_RERANK_MODELS", "")
    config_path = Path(models) / "config.json" if models else ""
    
    result = {
        "exists": False,
        "path": str(config_path),
        "content": None,
        "error": "",
    }
    
    if not config_path or not config_path.exists():
        result["error"] = f"Config not found: {config_path}"
        return result
    
    try:
        result["exists"] = True
        result["content"] = json.loads(config_path.read_text())
    except Exception as e:
        result["error"] = str(e)
    
    return result


def run_ovms_diagnostic() -> Dict[str, Any]:
    """Run OVMS diagnostic."""
    env_vars = get_env_vars()
    ovms_exe = env_vars.get("OVMS_EXE", "")
    models = env_vars.get("OVMS_RERANK_MODELS", "")
    
    if not ovms_exe or not models:
        return {"error": "OVMS_EXE or OVMS_RERANK_MODELS not set"}
    
    config_path = Path(models) / "config.json"
    if not config_path.exists():
        return {"error": f"Config not found: {config_path}"}
    
    try:
        # Try to run OVMS with --help to see if it works
        result = subprocess.run(
            [ovms_exe, "--help"],
            capture_output=True,
            text=True,
            timeout=10
        )
        return {
            "exit_code": result.returncode,
            "stdout": result.stdout[:500],
            "stderr": result.stderr[:500],
        }
    except subprocess.TimeoutExpired:
        return {"error": "Timeout while running OVMS --help"}
    except Exception as e:
        return {"error": str(e)}


def diagnose():
    """Run all diagnostics."""
    print("=" * 60)
    print("OVMS RERANKER DIAGNOSTIC REPORT")
    print("=" * 60)
    
    print("\n1. ENVIRONMENT VARIABLES:")
    env_vars = get_env_vars()
    for k, v in env_vars.items():
        print(f"   {k}: {v}")
    
    print("\n2. OVMS.EXE STATUS:")
    ovms_exe = check_ovms_exe()
    print(f"   Path: {ovms_exe.get('path')}")
    print(f"   Exists: {ovms_exe.get('exists')}")
    print(f"   Size: {ovms_exe.get('size')}")
    print(f"   Error: {ovms_exe.get('error')}")
    
    print("\n3. OVMS CONFIG STATUS:")
    config = check_ovms_config()
    print(f"   Path: {config.get('path')}")
    print(f"   Exists: {config.get('exists')}")
    print(f"   Error: {config.get('error')}")
    
    print("\n4. OVMS DIAGNOSTIC:")
    diagnostic = run_ovms_diagnostic()
    print(f"   Exit code: {diagnostic.get('exit_code')}")
    print(f"   Stdout: {diagnostic.get('stdout', '')[:200]}")
    print(f"   Stderr: {diagnostic.get('stderr', '')[:200]}")
    print(f"   Error: {diagnostic.get('error', '')[:200]}")
    
    print("\n5. RECOMMENDATIONS:")
    if not ovms_exe.get('exists'):
        print("   - OVMS.exe not found. Check OVMS_EXE environment variable.")
    if not config.get('exists'):
        print("   - OVMS config not found. Check OVMS_RERANK_MODELS environment variable.")
    if diagnostic.get('error'):
        print(f"   - Diagnostic error: {diagnostic['error']}")
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    diagnose()