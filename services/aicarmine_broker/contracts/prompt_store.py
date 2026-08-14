from __future__ import annotations

from typing import Protocol

from ..domain import EvidenceWindow


class PromptStore(Protocol):
    """Job-local prompt document/window storage port.

    Defines the interface for writing prompt documents and reading bounded
    text windows with tracking metadata for evidence reconstruction.
    """

    def write_document(self,  section: str, text: str) -> str:
        """Persist a complete prompt document and return its document id.

        Args:
            section: The document section identifier.
            text: The prompt document content to persist.
        Returns:
            The document ID for the persisted document.
        """
    def read_window(
        self,
        
        document_id: str,
        offset: int,
        max_chars: int,
    ) -> EvidenceWindow:
        """Return a real bounded text window with tracking metadata.

        Args:
            document_id: The ID of the document to read from.
            offset: The byte offset to start reading from.
            max_chars: The maximum number of characters to read.
        Returns:
            An EvidenceWindow containing the bounded text and tracking metadata.
        """
