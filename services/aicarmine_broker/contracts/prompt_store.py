from __future__ import annotations

from typing import Protocol

from aicarmine_broker.domain import EvidenceWindow


class PromptStore(Protocol):
    """Job-local prompt document/window storage port."""

    def write_document(self, *, section: str, text: str) -> str:
        """Persist a complete prompt document and return its document id."""

    def read_window(
        self,
        *,
        document_id: str,
        offset: int,
        max_chars: int,
    ) -> EvidenceWindow:
        """Return a real bounded text window with tracking metadata."""
