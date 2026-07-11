"""Local vLLM backend — thin adapter of the existing VLLMClient to LLMBackend.

No behavior change from the original VLLMClient: still talks to a local
vLLM server's OpenAI-compatible `/v1/completions` endpoint, unauthenticated.
"""

from src.llm_backends.base import LLMBackend
from src.vllm_client import VLLMClient


class LocalVLLMBackend(VLLMClient, LLMBackend):
    """VLLMClient, formally conforming to the shared LLMBackend interface.

    All methods (`health_check`, `list_models`, `generate`, `generate_stream`,
    `close`) are already implemented by `VLLMClient` with matching signatures.
    """
    pass

