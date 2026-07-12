# Request processing functions from vulkan_bridge/app.py
# This file was extracted from vulkan_bridge.app

from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel

class HelperForAllRequest(BaseModel):
    # Implementation from original app.py
    pass

class VulkanHelperRequest(BaseModel):
    # Implementation from original app.py
    pass

def _public_agent_arguments(raw_payload: dict[str, Any]) -> dict[str, Any]:
    # Implementation from original app.py
    pass

def payload_to_dict(payload: Any) -> dict[str, Any]:
    # Implementation from original app.py
    pass

def _first_text(payload: dict[str, Any], *keys: str) -> str:
    # Implementation from original app.py
    pass

def _first_dict(payload: dict[str, Any], *keys: str) -> dict[str, Any]:
    # Implementation from original app.py
    pass

def _compact_text(value: Any, limit: int) -> str:
    # Implementation from original app.py
    pass

# Other request processing utilities...
