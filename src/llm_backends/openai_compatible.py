"""Remote OpenAI-compatible chat-completions backend ("bring your own key").

Targets the `/v1/chat/completions` endpoint, which — unlike vLLM's legacy
`/v1/completions` used by `LocalVLLMBackend` — is what most hosted
OpenAI-compatible providers (OpenAI itself, Groq, Together, Fireworks,
OpenRouter, Mistral, Anyscale, etc.) actually implement.

The chat logprobs response shape differs from the completions shape:

    completions:  {"tokens": [...], "token_logprobs": [...], "top_logprobs": [{tok: lp}, ...]}
    chat:         {"content": [{"token": ..., "logprob": ..., "top_logprobs": [{"token":..,"logprob":..}, ...]}, ...]}

This module converts chat's shape into the same fields VLLMClient's
GenerationResult already uses (`tokens`, `token_logprobs`, `top_logprobs`),
so `src.vllm_adapter.generation_result_to_intrinsic_data()` and everything
downstream works unmodified regardless of which backend produced the text.

Many hosted providers omit logprobs entirely (or cap top_logprobs low). In
that case `token_logprobs`/`tokens`/`top_logprobs` stay `None` and Prong 4
gracefully falls back to neutral scores — exactly like the existing
"no vLLM" path.

API keys are never persisted beyond the lifetime of a single client
instance/request — see `src/llm_backends/factory.py`.
"""

import json
import time
import logging
from typing import Optional, List, AsyncIterator

import httpx

from src.llm_backends.base import LLMBackend
from src.vllm_client import GenerationResult

logger = logging.getLogger(__name__)


class OpenAICompatibleClient(LLMBackend):
    """Async client for a remote OpenAI-compatible `/v1/chat/completions` host.

    Usage::

        client = OpenAICompatibleClient(base_url="https://api.openai.com", api_key="sk-...")
        models = await client.list_models()
        result = await client.generate("What is AI?", model=models[0])
        await client.close()
    """

    def __init__(self, base_url: str, api_key: Optional[str] = None,
                 timeout: float = 120.0):
        if not base_url:
            raise ValueError("base_url is required for a remote backend")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
                headers=self._headers(),
            )
        return self._client

    async def health_check(self) -> bool:
        try:
            client = await self._get_client()
            resp = await client.get("/v1/models")
            return resp.status_code == 200
        except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError):
            return False

    async def list_models(self) -> List[str]:
        client = await self._get_client()
        resp = await client.get("/v1/models")
        resp.raise_for_status()
        data = resp.json()
        return [m["id"] for m in data.get("data", [])]

    def _build_request_body(
        self,
        prompt: str,
        model: str,
        max_tokens: int,
        temperature: float,
        top_p: float,
        repetition_penalty: float,
        frequency_penalty: float,
        logprobs: Optional[int],
        stop: Optional[List[str]],
        stream: bool,
    ) -> dict:
        """Build the request body for /v1/chat/completions."""
        body = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": stream,
        }
        if top_p != 1.0:
            body["top_p"] = top_p
        if frequency_penalty != 0.0:
            body["frequency_penalty"] = frequency_penalty
        if repetition_penalty != 1.0:
            # Not part of the OpenAI spec, but several OpenAI-compatible
            # hosts (e.g. vLLM/TGI-backed ones) accept it as an extra field.
            # Hosts that don't recognize it will simply ignore it.
            body["repetition_penalty"] = repetition_penalty
        if logprobs:
            body["logprobs"] = True
            body["top_logprobs"] = logprobs
        if stop:
            body["stop"] = stop
        return body

    @staticmethod
    def _parse_chat_logprobs(logprobs_obj: Optional[dict]):
        """Convert chat-completions logprobs shape into flat parallel lists.

        Returns (tokens, token_logprobs, top_logprobs) — each None if the
        provider didn't return logprobs at all.
        """
        content = (logprobs_obj or {}).get("content") or []
        if not content:
            return None, None, None

        tokens = [item.get("token", "") for item in content]
        token_logprobs = [item.get("logprob") for item in content]
        top_logprobs = []
        for item in content:
            entries = item.get("top_logprobs") or []
            top_logprobs.append({e.get("token"): e.get("logprob") for e in entries})
        return tokens, token_logprobs, top_logprobs

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
        """Generate text from a prompt (non-streaming) via chat completions."""
        client = await self._get_client()
        request_body = self._build_request_body(
            prompt=prompt, model=model, max_tokens=max_tokens,
            temperature=temperature, top_p=top_p,
            repetition_penalty=repetition_penalty,
            frequency_penalty=frequency_penalty,
            logprobs=logprobs, stop=stop, stream=False,
        )

        start = time.perf_counter()
        resp = await client.post("/v1/chat/completions", json=request_body)
        resp.raise_for_status()
        elapsed_ms = (time.perf_counter() - start) * 1000.0

        data = resp.json()
        choice = data["choices"][0]
        message = choice.get("message") or {}
        text = (message.get("content") or "").strip()

        tokens, token_logprobs, top_logprobs = self._parse_chat_logprobs(
            choice.get("logprobs")
        )
        if tokens is None:
            logger.info(
                "Remote host %s returned no logprobs for model %s — "
                "Prong 4 will use its neutral fallback.", self.base_url, model,
            )

        result = GenerationResult(
            text=text,
            model=model,
            finish_reason=choice.get("finish_reason", "unknown"),
            generation_time_ms=elapsed_ms,
            prompt=prompt,
            token_logprobs=token_logprobs,
            tokens=tokens,
            top_logprobs=top_logprobs,
        )

        logger.info(
            "Generated %d chars from %s (%s) in %.1fms",
            len(text), model, self.base_url, elapsed_ms,
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
        """Stream text generation token-by-token (SSE) via chat completions.

        Yields dicts with keys: token, reasoning_token, finish_reason,
        token_logprob, top_logprobs, done. `token` carries visible answer
        text (same contract as VLLMClient.generate_stream()). `reasoning_token`
        is additive: some hosted "reasoning" models (e.g. gpt-oss, DeepSeek-R1
        style) stream hidden chain-of-thought via a separate
        `delta.reasoning_content` field before any visible `content` appears.
        Callers that don't care about it can simply ignore the key (it's
        absent/None for models and hosts that don't use it).
        """
        client = await self._get_client()
        request_body = self._build_request_body(
            prompt=prompt, model=model, max_tokens=max_tokens,
            temperature=temperature, top_p=top_p,
            repetition_penalty=repetition_penalty,
            frequency_penalty=frequency_penalty,
            logprobs=logprobs, stop=stop, stream=True,
        )

        async with client.stream("POST", "/v1/chat/completions", json=request_body) as resp:
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
                delta = choice.get("delta") or {}
                text = delta.get("content") or ""
                reasoning_text = delta.get("reasoning_content") or ""
                finish_reason = choice.get("finish_reason")

                tokens, token_lps, top_lps = self._parse_chat_logprobs(
                    choice.get("logprobs")
                )

                chunk = {
                    "token": text,
                    "reasoning_token": reasoning_text or None,
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

