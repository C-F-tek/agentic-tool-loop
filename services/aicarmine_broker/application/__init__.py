"""Application services for the 3572 broker.

Exports are lazy so importing one application submodule does not load the full
tool dispatcher, repo tools or job store graph.
"""

__all__ = [
    "BaseTool",
    "DispatchRequest",
    "RegistryToolDispatcher",
    "build_default_dispatcher",
    "build_public_result_digest",
    "normalize_planner_decision",
]


def __getattr__(name: str):
    if name in {
        "BaseTool",
        "DispatchRequest",
        "RegistryToolDispatcher",
        "build_default_dispatcher",
    }:
        from .tool_surface import dispatcher

        return getattr(dispatcher, name)
    if name == "build_public_result_digest":
        from .public_payload.history_ledger import build_public_result_digest

        return build_public_result_digest
    if name == "normalize_planner_decision":
        from .planner.decision_normalizer import normalize_planner_decision

        return normalize_planner_decision
    raise AttributeError(name)
