"""Configuration package for the Data RAG Agent."""

import configparser
from pathlib import Path
from typing import Any


def load_settings(config_path: str | None = None) -> dict[str, Any]:
    """Load settings from INI configuration file."""
    if config_path is None:
        config_path = str(Path(__file__).parent / "settings.ini")

    path = Path(config_path)
    if not path.exists():
        return {}

    cp = configparser.ConfigParser()
    cp.read(path)

    result = {}
    for section in cp.sections():
        result[section] = dict(cp[section])

    return result