"""Dataclass per informazioni entry point."""

from dataclasses import dataclass
from typing import Any


@dataclass
class EntryPointInfo:
    """Entry point dinamico letto dal codice sorgente."""
    
    path: str
    symbol_name: str
    line_number: int
    function_signature: str
    is_entry_point: bool