"""Auth behaviour of the generator client.

llama.cpp servers started with ``--api-key`` reject ``/v1/*`` without a
Bearer token while leaving ``/health`` open, so the client must be able to
send a key and must not invent one.
"""

import asyncio

import httpx

from src.vllm_client import VLLMClient


def _client(handler, api_key=None):
    return VLLMClient("http://generator", api_key=api_key,
                      transport=httpx.MockTransport(handler))


def test_api_key_is_sent_as_bearer():
    seen = {}

    def handler(request):
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json={"status": "ok"})

    assert asyncio.run(_client(handler, api_key="secret").health_check()) is True
    assert seen["auth"] == "Bearer secret"


def test_no_key_means_no_authorization_header():
    seen = {}

    def handler(request):
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json={"data": []})

    assert asyncio.run(_client(handler).list_models()) == []
    assert seen["auth"] is None


def test_health_check_false_on_connection_error():
    def handler(request):
        raise httpx.ConnectError("refused", request=request)

    assert asyncio.run(_client(handler).health_check()) is False


def test_list_models_accepts_llamacpp_shape():
    def handler(request):
        return httpx.Response(200, json={"models": [
            {"name": "Qwen/Qwen3.8-27B", "model": "Qwen/Qwen3.8-27B"}]})

    assert asyncio.run(_client(handler).list_models()) == ["Qwen/Qwen3.8-27B"]


def test_generate_normalizes_chat_shaped_logprobs():
    """llama.cpp returns logprobs.content; the adapter expects parallel arrays."""
    def handler(request):
        return httpx.Response(200, json={"choices": [{
            "text": "Hello there",
            "finish_reason": "stop",
            "logprobs": {"content": [
                {"token": "Hello", "logprob": -0.1,
                 "top_logprobs": [{"token": "Hello", "logprob": -0.1}]},
                {"token": " there", "logprob": -0.2,
                 "top_logprobs": [{"token": " there", "logprob": -0.2}]},
            ]},
        }]})

    client = _client(handler, api_key="secret")
    result = asyncio.run(client.generate("hi", model="m", max_tokens=2))
    assert result.tokens == ["Hello", " there"]
    assert result.token_logprobs == [-0.1, -0.2]
    assert result.top_logprobs == [{"Hello": -0.1}, {" there": -0.2}]


def test_stream_chunk_normalizes_chat_shaped_logprobs():
    """llama.cpp streams chat-shaped logprobs; Prong 4 needs the token value."""
    from src.vllm_client import _stream_chunk

    chunk = _stream_chunk({
        "text": "Hello",
        "finish_reason": None,
        "logprobs": {"content": [{
            "token": "Hello", "logprob": -0.25,
            "top_logprobs": [{"token": "Hello", "logprob": -0.25},
                             {"token": "Hi", "logprob": -1.6}]}]},
    })
    assert chunk["token_logprob"] == -0.25
    assert chunk["top_logprobs"]["Hi"] == -1.6


def test_stream_chunk_accepts_legacy_arrays():
    from src.vllm_client import _stream_chunk

    chunk = _stream_chunk({
        "text": "Hello",
        "finish_reason": "stop",
        "logprobs": {"tokens": ["Hello"], "token_logprobs": [-0.3],
                     "top_logprobs": [{"Hello": -0.3}]},
    })
    assert chunk["token_logprob"] == -0.3
    assert chunk["done"] is True
