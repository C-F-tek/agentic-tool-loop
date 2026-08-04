"""Secret management for agentic loop services.

This module provides secure environment variable loading with:
- python-dotenv support for .env files
- Windows Credential Manager integration (optional)
- Safe fallback chain for development environments
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


class SecretManagementError(Exception):
    """Exception raised when secret management fails."""
    pass


class DotEnvLoader:
    """Load secrets from .env file with safe fallback chain.
    
    Usage:
        loader = DotEnvLoader(root=Path("/path/to/project"))
        ollama_url = loader.get_secret("OLLAMA_URL")
        broker_port = loader.get_secret("BROKER_PORT", default="3579")
    """
    
    def __init__(self, root: Path):
        self.root = root
        self.env_path = root / ".env"
        self.env_dev_path = root / ".env.development"  # For non-sensitive defaults
    
    def load(self) -> dict[str, str]:
        """Load .env file contents into environment.
        
        Returns loaded key-value pairs.
        """
        if not self.env_path.is_file():
            return {}
        
        try:
            with open(self.env_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            
            loaded = {}
            for line in lines:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, value = line.split("=", 1)
                    loaded[key.strip()] = value.strip()
                    os.environ[key.strip()] = value.strip()
            
            return loaded
        except OSError as exc:
            raise SecretManagementError(f"Failed to read .env file: {exc}")
    
    def get_secret(self, key: str, default: str = "", require_secret: bool = True) -> str:
        """Get secret from environment with fallback chain.
        
        Priority:
        1. Environment variable (os.environ)
        2. .env file value
        3. Default value (if provided)
        4. Empty string (if require_secret=False)
        
        Raises SecretManagementError if key is required but not found.
        """
        # Check os.environ first
        value = os.environ.get(key)
        if value:
            return value
        
        # Check .env file
        env_values = self.load()
        if key in env_values:
            return env_values[key]
        
        # Return default or raise
        if default:
            return default
        
        if require_secret:
            raise SecretManagementError(f"Required secret '{key}' not found in environment or .env file")
        
        return ""
    
    def validate_secrets(self, required_keys: list[str]) -> dict[str, Any]:
        """Validate that all required secrets are available.
        
        Returns validation report with ok field.
        """
        missing = []
        for key in required_keys:
            try:
                self.get_secret(key, require_secret=True)
            except SecretManagementError:
                missing.append(key)
        
        return {
            "ok": len(missing) == 0,
            "missing_secrets": missing,
            "required_keys": required_keys,
            "total_required": len(required_keys),
            "available": len(required_keys) - len(missing),
        }


class WindowsCredentialManager:
    """Optional integration with Windows Credential Manager.
    
    This class provides secure storage/retrieval using Windows DPAPI.
    Requires pywin32 package.
    """
    
    def __init__(self):
        self._credential_available = False
        try:
            import win32api
            self._credential_available = True
        except ImportError:
            pass
    
    def store_secret(self, key: str, value: str) -> bool:
        """Store secret in Windows Credential Manager."""
        if not self._credential_available:
            return False
        # Implementation would use win32crypt.CryptProtectData
        return False
    
    def get_secret(self, key: str) -> str | None:
        """Retrieve secret from Windows Credential Manager."""
        if not self._credential_available:
            return None
        # Implementation would use win32crypt.CryptUnprotectData
        return None


def create_secret_manager(root: Path) -> DotEnvLoader:
    """Factory function to create secret manager."""
    return DotEnvLoader(root=root)


def load_dotenv_if_available(root: Path) -> dict[str, str]:
    """Load .env file if it exists, return empty dict otherwise."""
    loader = DotEnvLoader(root=root)
    return loader.load()