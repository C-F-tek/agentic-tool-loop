"""Compatibility wrapper for the Vulkan bridge FastAPI app.

The implementation lives in :mod:`vulkan_bridge.app`.  This root module keeps
the historical import path used by uvicorn and launcher scripts:

    uvicorn aicarmine_vulkan_bridge_server:app
"""

from vulkan_bridge.app import app

__all__ = ["app"]
