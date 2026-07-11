"""LLM backend abstraction: local vLLM and remote OpenAI-compatible hosts.

Both backends expose the same async interface (see `base.LLMBackend`) and
return the shared `GenerationResult` dataclass from `src.vllm_client`, so
`src.vllm_adapter.generation_result_to_intrinsic_data()` and the rest of the
pipeline work unmodified regardless of which backend produced the text.
"""

from src.llm_backends.base import LLMBackend
from src.llm_backends.local_vllm import LocalVLLMBackend
from src.llm_backends.openai_compatible import OpenAICompatibleClient
from src.llm_backends.factory import BackendConfig, build_backend

__all__ = [
    "LLMBackend",
    "LocalVLLMBackend",
    "OpenAICompatibleClient",
    "BackendConfig",
    "build_backend",
]

