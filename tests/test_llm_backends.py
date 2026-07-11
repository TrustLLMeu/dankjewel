"""Tests for the OpenAI-compatible remote backend and backend factory.

Uses monkeypatched httpx to avoid real network calls.
"""

import asyncio
import json

import httpx
import pytest

from src.llm_backends.factory import BackendConfig, build_backend, is_remote
from src.llm_backends.local_vllm import LocalVLLMBackend
from src.llm_backends.openai_compatible import OpenAICompatibleClient


# ── BackendConfig / factory ─────────────────────────────────────────────────

class TestBackendFactory:

    def test_local_returns_shared_instance(self):
        local = LocalVLLMBackend()
        cfg = BackendConfig(backend_type="local")
        backend = build_backend(cfg, local)
        assert backend is local

    def test_remote_returns_new_instance(self):
        local = LocalVLLMBackend()
        cfg = BackendConfig(backend_type="remote", base_url="https://api.openai.com", api_key="sk-test")
        backend = build_backend(cfg, local)
        assert backend is not local
        assert isinstance(backend, OpenAICompatibleClient)
        assert backend.base_url == "https://api.openai.com"
        assert backend.api_key == "sk-test"

    def test_remote_requires_base_url(self):
        local = LocalVLLMBackend()
        cfg = BackendConfig(backend_type="remote")
        with pytest.raises(ValueError):
            build_backend(cfg, local)

    def test_is_remote(self):
        assert is_remote(BackendConfig(backend_type="remote", base_url="https://x")) is True
        assert is_remote(BackendConfig(backend_type="local")) is False
        assert is_remote(BackendConfig()) is False  # default is local


# ── OpenAICompatibleClient ───────────────────────────────────────────────────

class TestOpenAICompatibleClient:

    def test_requires_base_url(self):
        with pytest.raises(ValueError):
            OpenAICompatibleClient(base_url="")

    def test_headers_include_bearer_token(self):
        client = OpenAICompatibleClient(base_url="https://api.openai.com", api_key="sk-abc123")
        headers = client._headers()
        assert headers["Authorization"] == "Bearer sk-abc123"

    def test_headers_omit_auth_without_key(self):
        client = OpenAICompatibleClient(base_url="https://api.openai.com")
        headers = client._headers()
        assert "Authorization" not in headers

    def test_trailing_slash_stripped(self):
        client = OpenAICompatibleClient(base_url="https://api.openai.com/", api_key="k")
        assert client.base_url == "https://api.openai.com"

    def test_parse_chat_logprobs_none(self):
        tokens, lps, top = OpenAICompatibleClient._parse_chat_logprobs(None)
        assert tokens is None and lps is None and top is None

    def test_parse_chat_logprobs_present(self):
        logprobs_obj = {
            "content": [
                {"token": "Paris", "logprob": -0.1,
                 "top_logprobs": [{"token": "Paris", "logprob": -0.1}, {"token": "London", "logprob": -2.3}]},
                {"token": " is", "logprob": -0.05, "top_logprobs": []},
            ]
        }
        tokens, lps, top = OpenAICompatibleClient._parse_chat_logprobs(logprobs_obj)
        assert tokens == ["Paris", " is"]
        assert lps == [-0.1, -0.05]
        assert top[0] == {"Paris": -0.1, "London": -2.3}
        assert top[1] == {}

    def test_build_request_body_chat_shape(self):
        client = OpenAICompatibleClient(base_url="https://api.openai.com", api_key="k")
        body = client._build_request_body(
            prompt="Hello", model="gpt-x", max_tokens=100, temperature=0.5,
            top_p=0.9, repetition_penalty=1.0, frequency_penalty=0.0,
            logprobs=5, stop=None, stream=False,
        )
        assert body["model"] == "gpt-x"
        assert body["messages"] == [{"role": "user", "content": "Hello"}]
        assert body["max_tokens"] == 100
        assert body["logprobs"] is True
        assert body["top_logprobs"] == 5
        assert "repetition_penalty" not in body  # default 1.0 omitted

    def test_generate_parses_chat_response(self, monkeypatch):
        """Mock httpx.AsyncClient.post to return a canned chat-completions response."""

        async def fake_post(self, url, json=None):
            payload = {
                "choices": [{
                    "message": {"content": "Paris is the capital of France."},
                    "finish_reason": "stop",
                    "logprobs": {
                        "content": [
                            {"token": "Paris", "logprob": -0.1, "top_logprobs": []},
                        ]
                    },
                }]
            }
            request = httpx.Request("POST", url)
            return httpx.Response(200, json=payload, request=request)

        monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

        async def _run():
            client = OpenAICompatibleClient(base_url="https://api.openai.com", api_key="k")
            result = await client.generate(prompt="What is the capital of France?", model="gpt-x")
            await client.close()
            return result

        result = asyncio.run(_run())
        assert result.text == "Paris is the capital of France."
        assert result.model == "gpt-x"
        assert result.finish_reason == "stop"
        assert result.tokens == ["Paris"]
        assert result.token_logprobs == [-0.1]

    def test_generate_handles_missing_logprobs(self, monkeypatch):
        """When a host omits logprobs, fields stay None (Prong 4 falls back gracefully)."""

        async def fake_post(self, url, json=None):
            payload = {
                "choices": [{
                    "message": {"content": "Hello there."},
                    "finish_reason": "stop",
                }]
            }
            request = httpx.Request("POST", url)
            return httpx.Response(200, json=payload, request=request)

        monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

        async def _run():
            client = OpenAICompatibleClient(base_url="https://api.groq.com/openai", api_key="k")
            result = await client.generate(prompt="Hi", model="llama-x")
            await client.close()
            return result

        result = asyncio.run(_run())
        assert result.text == "Hello there."
        assert result.tokens is None
        assert result.token_logprobs is None

    def test_list_models(self, monkeypatch):
        async def fake_get(self, url):
            payload = {"data": [{"id": "gpt-4o-mini"}, {"id": "gpt-4o"}]}
            request = httpx.Request("GET", url)
            return httpx.Response(200, json=payload, request=request)

        monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

        async def _run():
            client = OpenAICompatibleClient(base_url="https://api.openai.com", api_key="k")
            models = await client.list_models()
            await client.close()
            return models

        models = asyncio.run(_run())
        assert models == ["gpt-4o-mini", "gpt-4o"]

    def test_generate_stream_separates_reasoning_from_content(self, monkeypatch):
        """Reasoning models (gpt-oss, DeepSeek-R1 style) stream hidden
        chain-of-thought via `delta.reasoning_content`, separate from the
        visible `delta.content`. The client must expose both, keeping
        `token` strictly to visible content."""

        class FakeStreamCtx:
            def __init__(self, lines):
                self._lines = lines

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            def raise_for_status(self):
                pass

            async def aiter_lines(self):
                for line in self._lines:
                    yield line

        sse_lines = [
            'data: {"choices": [{"delta": {"reasoning_content": "Let me think. "}, "finish_reason": null}]}',
            'data: {"choices": [{"delta": {"content": "Oslo"}, "finish_reason": null}]}',
            'data: {"choices": [{"delta": {"content": "."}, "finish_reason": "stop"}]}',
            'data: [DONE]',
        ]

        def fake_stream(self, method, url, json=None):
            return FakeStreamCtx(sse_lines)

        monkeypatch.setattr(httpx.AsyncClient, "stream", fake_stream)

        async def _run():
            client = OpenAICompatibleClient(base_url="https://api.example.com", api_key="k")
            chunks = []
            async for chunk in client.generate_stream(prompt="hi", model="reasoning-model"):
                chunks.append(chunk)
                if chunk.get("done"):
                    break
            await client.close()
            return chunks

        chunks = asyncio.run(_run())
        reasoning_tokens = [c["reasoning_token"] for c in chunks if c.get("reasoning_token")]
        content_tokens = [c["token"] for c in chunks if c.get("token")]
        assert reasoning_tokens == ["Let me think. "]
        assert content_tokens == ["Oslo", "."]
        assert chunks[-1]["finish_reason"] == "stop"

    def test_health_check_unreachable(self):
        async def _check():
            client = OpenAICompatibleClient(base_url="http://localhost:19999", api_key="k", timeout=2.0)
            result = await client.health_check()
            await client.close()
            return result
        assert asyncio.run(_check()) is False

    def test_close_idempotent(self):
        async def _close_twice():
            client = OpenAICompatibleClient(base_url="https://api.openai.com", api_key="k")
            await client.close()
            await client.close()
        asyncio.run(_close_twice())

