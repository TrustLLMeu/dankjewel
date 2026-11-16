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


def _stream_chunk(choice: dict) -> dict:
    """Normalize one streaming choice into the client's chunk shape.

    Accepts the legacy completions logprobs (parallel arrays) and the
    chat-shaped ``content`` list that llama.cpp returns, so the streaming
    path feeds Prong 4 the same way the non-streaming path does.
    """
    text = choice.get("text", "")
    finish_reason = choice.get("finish_reason")
    lp_data = choice.get("logprobs") or {}
    content = lp_data.get("content")
    if content:
        last = content[-1] or {}
        token_logprob = last.get("logprob")
        top_logprobs = {alt.get("token", ""): alt.get("logprob")
                        for alt in (last.get("top_logprobs") or [])}
    else:
        token_lps = lp_data.get("token_logprobs") or []
        top_lps = lp_data.get("top_logprobs") or []
        token_logprob = token_lps[-1] if token_lps else None
        top_logprobs = top_lps[-1] if top_lps else None
    return {
        "token": text,
        "finish_reason": finish_reason,
        "token_logprob": token_logprob,
        "top_logprobs": top_logprobs,
        "done": finish_reason is not None,
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
                 timeout: float = 120.0,
                 api_key: Optional[str] = None,
                 transport: Optional[httpx.AsyncBaseTransport] = None):
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.api_key = api_key
        self._transport = transport
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Lazy-init the async HTTP client.

        When an API key is configured it is sent as a Bearer token on
        every request — llama.cpp servers started with ``--api-key``
        reject ``/v1/*`` without it (their ``/health`` stays open).
        """
        if self._client is None or self._client.is_closed:
            headers = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
                headers=headers,
                transport=self._transport,
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
        """List available model ids on the generator endpoint.

        Accepts both the OpenAI/vLLM shape (``{"data": [{"id": ...}]}``)
        and the llama.cpp shape (``{"models": [{"name": ...}]}``).
        """
        client = await self._get_client()
        resp = await client.get("/v1/models")
        resp.raise_for_status()
        data = resp.json()
        entries = data.get("data") or data.get("models") or []
        models = []
        for entry in entries:
            model_id = entry.get("id") or entry.get("model") or entry.get("name")
            if model_id:
                models.append(model_id)
        return models

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
        # llama.cpp (and newer OpenAI-style servers) return a chat-shaped
        # ``content`` list of per-token dicts instead of the legacy
        # parallel arrays. Normalize it to the parallel-array form.
        content = lp_data.get("content")
        if content:
            tokens = [entry.get("token") for entry in content]
            token_logprobs = [entry.get("logprob") for entry in content]
            top_logprobs = [
                {alt.get("token", ""): alt.get("logprob")
                 for alt in (entry.get("top_logprobs") or [])}
                for entry in content
            ]

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
                yield _stream_chunk(choice)

    async def close(self):
        """Close the HTTP client connection."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

