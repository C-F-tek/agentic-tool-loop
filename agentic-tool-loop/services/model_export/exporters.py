"""Model export function compatibility surface.

``model_export.cli`` still contains the original top-level argparse script.
Importing it eagerly would parse command-line arguments during normal imports,
so this module exposes lazy attributes for the old exporter function names.
"""

from __future__ import annotations

from importlib import import_module

__all__ = [
    "export_embeddings_model_ov",
    "export_image_generation_model",
    "export_rerank_model",
    "export_rerank_model_ov",
    "export_speech2text_model",
    "export_text2speech_model",
    "export_text_generation_model",
]


def __getattr__(name: str):
    if name not in __all__:
        raise AttributeError(name)
    cli = import_module("model_export.cli")
    return getattr(cli, name)
