'''Backward-compatible shim.'''
from aicarmine_broker.domain.models import ToolResult, ValidationResult
__all__: list[str] = ['ToolResult', 'ValidationResult']
