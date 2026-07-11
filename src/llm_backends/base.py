"""Abstract interface shared by local (vLLM) and remote (OpenAI-compatible) backends."""

from abc import ABC, abstractmethod
from typing import AsyncIterator, List, Optional

from src.vllm_client import GenerationResult


class LLMBackend(ABC):
    """Common async interface for any OpenAI-compatible text-generation backend.

    Implementations: `LocalVLLMBackend` (wraps `VLLMClient`, talks to a local
    vLLM server's `/v1/completions`) and `OpenAICompatibleClient` (talks to
    `/v1/chat/completions` on a remote, user-supplied, API-key-authenticated
    host such as OpenAI, Groq, Together, Fireworks, OpenRouter, etc.).
    """

    @abstractmethod
    async def health_check(self) -> bool:
        """Return True if the backend is reachable."""

    @abstractmethod
    async def list_models(self) -> List[str]:
        """Return the list of model IDs available on this backend."""

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        model: str,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        top_p: float = 1.0,
        repetition_penalty: float = 1.0,
        frequency_penalty: float = 0.0,
        logprobs: Optional[int] = 5,
        stop: Optional[List[str]] = None,
    ) -> GenerationResult:
        """Generate text from a prompt (non-streaming)."""

    @abstractmethod
    def generate_stream(
        self,
        prompt: str,
        model: str,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        top_p: float = 1.0,
        repetition_penalty: float = 1.0,
        frequency_penalty: float = 0.0,
        logprobs: Optional[int] = 5,
        stop: Optional[List[str]] = None,
    ) -> AsyncIterator[dict]:
        """Stream generation chunks: {token, finish_reason, token_logprob, top_logprobs, done}."""

    @abstractmethod
    async def close(self):
        """Release any held connections/resources."""

