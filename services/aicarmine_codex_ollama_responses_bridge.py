"""Compatibility wrapper for the Codex Ollama Responses bridge."""

from codex_bridge import ollama_responses_bridge as _impl

globals().update(
    {name: value for name, value in vars(_impl).items() if not name.startswith("__")}
)
app = _impl.app
