"""Thin async client for vLLM's OpenAI-compatible API.

Handles text generation (batch and streaming). Evaluation stays in the IE pipeline.
Captures logprobs on every generation for Prong 4 integration.

Tested with:
    vllm==0.16.0
    httpx==0.28.1
    Python 3.12
"""

import json
import time
import logging
from dataclasses import dataclass
from typing import Optional, List, AsyncIterator

import httpx

logger = logging.getLogger(__name__)


@dataclass
class GenerationResult:
    """Result from a single vLLM text generation call."""
    text: str
    model: str
    finish_reason: str
    generation_time_ms: float
    prompt: str = ""
    token_logprobs: Optional[List[float]] = None
    tokens: Optional[List[str]] = None
    top_logprobs: Optional[List[dict]] = None

    def to_dict(self) -> dict:
        return {
            'text': self.text,
            'model': self.model,
            'finish_reason': self.finish_reason,
            'generation_time_ms': self.generation_time_ms,
            'prompt': self.prompt,
            'has_logprobs': self.token_logprobs is not None,
            'num_tokens': len(self.tokens) if self.tokens else 0,
        }


class VLLMClient:
    """Async client for vLLM's OpenAI-compatible API.

    Connects to a running vLLM server (started separately via
    ``python -m vllm.entrypoints.openai.api_server``).

    Usage::

        client = VLLMClient("http://localhost:8000")
        models = await client.list_models()
        result = await client.generate("What is AI?", model=models[0])
        print(result.text)
        await client.close()
    """

    def __init__(self, base_url: str = "http://localhost:8000",
                 timeout: float = 120.0):
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Lazy-init the async HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
            )
        return self._client

    async def health_check(self) -> bool:
        """Check if the vLLM server is reachable."""
        try:
            client = await self._get_client()
            resp = await client.get("/health")
            return resp.status_code == 200
        except (httpx.ConnectError, httpx.TimeoutException):
            return False

    async def list_models(self) -> List[str]:
        """List available models on the vLLM server."""
        client = await self._get_client()
        resp = await client.get("/v1/models")
        resp.raise_for_status()
        data = resp.json()
        return [m["id"] for m in data.get("data", [])]

    def _build_request_body(
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
        stream: bool = False,
    ) -> dict:
        """Build the request body for /v1/completions."""
        body = {
            "model": model,
            "prompt": prompt,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": stream,
        }
        if top_p != 1.0:
            body["top_p"] = top_p
        if repetition_penalty != 1.0:
            body["repetition_penalty"] = repetition_penalty
        if frequency_penalty != 0.0:
            body["frequency_penalty"] = frequency_penalty
        if logprobs is not None:
            body["logprobs"] = logprobs
        if stop:
            body["stop"] = stop
        return body

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
        """Generate text from a prompt (non-streaming).

        Args:
            prompt: The input prompt.
            model: Model ID (from list_models()).
            max_tokens: Maximum tokens to generate.
            temperature: Sampling temperature (0.0 = greedy).
            top_p: Nucleus sampling threshold.
            repetition_penalty: Penalize repeated tokens (1.0 = off).
            frequency_penalty: Penalize frequent tokens (0.0 = off).
            logprobs: Number of top logprobs to return per token.
            stop: Optional list of stop sequences.

        Returns:
            GenerationResult with text, timing, and logprob data.
        """
        client = await self._get_client()
        request_body = self._build_request_body(
            prompt=prompt, model=model, max_tokens=max_tokens,
            temperature=temperature, top_p=top_p,
            repetition_penalty=repetition_penalty,
            frequency_penalty=frequency_penalty,
            logprobs=logprobs, stop=stop, stream=False,
        )

        start = time.perf_counter()
        resp = await client.post("/v1/completions", json=request_body)
        resp.raise_for_status()
        elapsed_ms = (time.perf_counter() - start) * 1000.0

        data = resp.json()
        choice = data["choices"][0]

        lp_data = choice.get("logprobs") or {}
        token_logprobs = lp_data.get("token_logprobs")
        tokens = lp_data.get("tokens")
        top_logprobs = lp_data.get("top_logprobs")

        result = GenerationResult(
            text=choice["text"].strip(),
            model=model,
            finish_reason=choice.get("finish_reason", "unknown"),
            generation_time_ms=elapsed_ms,
            prompt=prompt,
            token_logprobs=token_logprobs,
            tokens=tokens,
            top_logprobs=top_logprobs,
        )

        logger.info(
            "Generated %d tokens from %s in %.1fms",
            len(tokens) if tokens else 0, model, elapsed_ms,
        )
        return result

    async def generate_stream(
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
        """Stream text generation token-by-token (SSE).

        Yields dicts with keys: token, finish_reason, token_logprob, top_logprobs.
        Also accumulates logprob data for Prong 4.

        Usage::

            async for chunk in client.generate_stream(...):
                print(chunk["token"], end="", flush=True)
        """
        client = await self._get_client()
        request_body = self._build_request_body(
            prompt=prompt, model=model, max_tokens=max_tokens,
            temperature=temperature, top_p=top_p,
            repetition_penalty=repetition_penalty,
            frequency_penalty=frequency_penalty,
            logprobs=logprobs, stop=stop, stream=True,
        )

        async with client.stream("POST", "/v1/completions", json=request_body) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                payload = line[6:].strip()
                if payload == "[DONE]":
                    yield {"token": "", "finish_reason": "stop", "done": True}
                    return
                try:
                    data = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                choice = data.get("choices", [{}])[0]
                text = choice.get("text", "")
                finish_reason = choice.get("finish_reason")

                lp_data = choice.get("logprobs") or {}
                token_lps = lp_data.get("token_logprobs", [None])
                top_lps = lp_data.get("top_logprobs", [None])

                chunk = {
                    "token": text,
                    "finish_reason": finish_reason,
                    "token_logprob": token_lps[-1] if token_lps else None,
                    "top_logprobs": top_lps[-1] if top_lps else None,
                    "done": finish_reason is not None,
                }
                yield chunk

    async def close(self):
        """Close the HTTP client connection."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

