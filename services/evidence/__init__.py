# services/evidence - Evidence collection and transport pipeline
#
# This package contains modules for evidence collection from job artifacts
# and transport to OpenWebUI public surface.

from .evidence_pipeline import (
    EvidenceCollector,
    EvidenceTransport,
    get_evidence_collector,
    get_evidence_transport,
)

__all__ = [
    "EvidenceCollector",
    "EvidenceTransport",
    "get_evidence_collector",
    "get_evidence_transport",
]