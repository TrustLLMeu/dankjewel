"""Factory for building an LLMBackend from a request-supplied configuration.

Design note on API keys: remote backends are constructed fresh per request
and never cached or logged. The server is a pure pass-through — the
frontend holds the user's key, sends it with each request, and nothing is
persisted server-side. This mirrors the "bring your own key" pattern used
by most LLM playground UIs.
"""

from typing import Optional

from pydantic import BaseModel, Field

from src.llm_backends.base import LLMBackend
from src.llm_backends.openai_compatible import OpenAICompatibleClient


class BackendConfig(BaseModel):
    """Which backend to use for a single generation/listing request."""
    backend_type: str = Field("local", description="'local' (vLLM) or 'remote' (OpenAI-compatible)")
    base_url: Optional[str] = Field(None, description="Base URL for a remote backend, e.g. https://api.openai.com")
    api_key: Optional[str] = Field(None, description="API key for a remote backend. Never stored server-side.")


def build_backend(config: BackendConfig, local_backend: LLMBackend) -> LLMBackend:
    """Return the backend to use for this request.

    Args:
        config: Backend selection from the incoming request.
        local_backend: The shared, server-managed local vLLM backend instance
            (created once at startup) — returned as-is when config selects
            "local". Never closed by the caller in that case.

    Returns:
        Either `local_backend` (local) or a freshly constructed
        `OpenAICompatibleClient` (remote) — callers MUST close the latter
        after use (it is not shared/cached).
    """
    if config.backend_type == "remote":
        if not config.base_url:
            raise ValueError("base_url is required when backend_type='remote'")
        return OpenAICompatibleClient(base_url=config.base_url, api_key=config.api_key)
    return local_backend


def is_remote(config: BackendConfig) -> bool:
    """Whether this config selects a remote (per-request, closeable) backend."""
    return config.backend_type == "remote"

