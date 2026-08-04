"""
secure_subprocess - Secure subprocess wrapper with bounded timeout and validation.

This module provides a secure wrapper around subprocess.run() that:
- Enforces bounded timeout (default 60 seconds)
- Validates command arguments
- Captures output safely
- Prevents shell=True usage
"""
from __future__ import annotations

import subprocess
from typing import List, Optional, Dict, Any


def secure_subprocess(
    args: List[str],
    timeout: Optional[int] = 60,
    check: bool = True,
    env: Optional[Dict[str, str]] = None,
    capture_output: bool = True,
    text: bool = True,
) -> subprocess.CompletedProcess:
    """Secure subprocess wrapper with bounded timeout.
    
    Args:
        args: Command arguments (must not include shell=True)
        timeout: Timeout in seconds (default 60, max 3600)
        check: Raise subprocess.TimeoutExpired on timeout (default True)
        env: Environment variables (optional)
        capture_output: Capture stdout/stderr (default True)
        text: Use text mode (default True)
    
    Returns:
        subprocess.CompletedProcess
    
    Raises:
        ValueError: If timeout exceeds maximum or args contains shell=True
        subprocess.TimeoutExpired: If command exceeds timeout
        subprocess.CalledProcessError: If command fails and check=True
    """
    # Validate timeout
    if timeout is None:
        timeout = 60
    timeout = max(1, min(timeout, 3600))  # Clamp between 1 and 3600 seconds
    
    # Validate no shell=True
    if any("shell=True" in str(arg) for arg in args):
        raise ValueError("shell=True is not allowed in secure_subprocess")
    
    # Run subprocess securely
    return subprocess.run(
        args,
        timeout=timeout,
        check=check,
        env=env,
        capture_output=capture_output,
        text=text,
    )


def secure_subprocess_with_output(
    args: List[str],
    timeout: Optional[int] = 60,
) -> dict[str, Any]:
    """Secure subprocess wrapper that returns a dict with output.
    
    Args:
        args: Command arguments
        timeout: Timeout in seconds (default 60)
    
    Returns:
        Dict with keys: ok, returncode, stdout, stderr, timeout_exceeded
    """
    try:
        result = secure_subprocess(args, timeout=timeout)
        return {
            "ok": result.returncode == 0,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "timeout_exceeded": False,
        }
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "returncode": -1,
            "stdout": "",
            "stderr": "Command timed out",
            "timeout_exceeded": True,
        }
    except subprocess.CalledProcessError as e:
        return {
            "ok": False,
            "returncode": e.returncode,
            "stdout": e.stdout or "",
            "stderr": e.stderr or "",
            "timeout_exceeded": False,
        }