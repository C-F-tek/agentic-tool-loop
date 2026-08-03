"""Small value-cleaning helpers for application payloads."""
from __future__ import annotations

from typing import Any


def drop_empty_dict_values(value: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in value.items() if v not in (None, "", [], {})}
