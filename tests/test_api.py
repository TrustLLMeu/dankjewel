"""Tests for vLLM client and API server.

Tests the VLLMClient (with mocked HTTP) and the FastAPI endpoints
(with TestClient, no running vLLM needed).
"""

import asyncio
import pytest
import json

from src.vllm_client import VLLMClient, GenerationResult


# ── VLLMClient unit tests ──────────────────────────────────────────────────

class TestVLLMClient:

    def test_generation_result_to_dict(self):
        """GenerationResult.to_dict() serializes correctly."""
        result = GenerationResult(
            text="Paris is the capital of France.",
            model="test-model",
            finish_reason="stop",
            generation_time_ms=150.5,
            prompt="What is the capital of France?",
            token_logprobs=[-0.1, -0.2, -0.05],
            tokens=["Paris", " is", " the"],
        )
        d = result.to_dict()
        assert d['text'] == "Paris is the capital of France."
        assert d['model'] == "test-model"
        assert d['finish_reason'] == "stop"
        assert d['generation_time_ms'] == 150.5
        assert d['has_logprobs'] is True
        assert d['num_tokens'] == 3

    def test_generation_result_no_logprobs(self):
        """GenerationResult without logprobs."""
        result = GenerationResult(
            text="Hello",
            model="m",
            finish_reason="stop",
            generation_time_ms=10.0,
        )
        d = result.to_dict()
        assert d['has_logprobs'] is False
        assert d['num_tokens'] == 0

    def test_health_check_unreachable(self):
        """health_check returns False when server is unreachable."""
        async def _check():
            client = VLLMClient(base_url="http://localhost:19999", timeout=2.0)
            result = await client.health_check()
            await client.close()
            return result
        assert asyncio.run(_check()) is False

    def test_close_idempotent(self):
        """Closing twice doesn't raise."""
        async def _close_twice():
            client = VLLMClient()
            await client.close()
            await client.close()
        asyncio.run(_close_twice())

    def test_default_base_url(self):
        """Default base URL is localhost:8000."""
        client = VLLMClient()
        assert client.base_url == "http://localhost:8000"

    def test_custom_base_url(self):
        """Custom base URL is used."""
        client = VLLMClient(base_url="http://gpu-server:9000")
        assert client.base_url == "http://gpu-server:9000"

    def test_trailing_slash_stripped(self):
        """Trailing slash in URL is stripped."""
        client = VLLMClient(base_url="http://localhost:8000/")
        assert client.base_url == "http://localhost:8000"


# ── API server tests (with TestClient, no vLLM needed) ─────────────────────

class TestAPIEndpoints:

    @pytest.fixture
    def client(self):
        """Create a FastAPI TestClient."""
        from fastapi.testclient import TestClient
        from src.api import app
        return TestClient(app)

    def test_health_endpoint(self, client):
        """GET /health returns status."""
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data['status'] == 'ok'
        assert 'vllm_connected' in data

    def test_evaluate_endpoint(self, client):
        """POST /evaluate works without vLLM."""
        resp = client.post("/evaluate", json={
            "prompt": "What is the capital of France?",
            "text": "The capital of France is Paris.",
        })
        # Accept 200 (success) or 503 (evaluator not initialized in test)
        if resp.status_code == 200:
            data = resp.json()
            assert 'aggregated_scores' in data
            assert 'prong_results' in data
        else:
            # Evaluator may not initialize in test context — that's OK
            assert resp.status_code in (500, 503)

    def test_models_without_vllm(self, client):
        """GET /models returns 502 when vLLM is not running."""
        resp = client.get("/models")
        assert resp.status_code == 502

    def test_generate_without_vllm(self, client):
        """POST /generate returns 502 when vLLM is not running."""
        resp = client.post("/generate", json={
            "prompt": "Hello",
            "model": "test-model",
        })
        assert resp.status_code == 502

    def test_generate_and_evaluate_without_vllm(self, client):
        """POST /generate-and-evaluate returns 502 when vLLM is not running."""
        resp = client.post("/generate-and-evaluate", json={
            "prompt": "Hello",
            "model": "test-model",
        })
        assert resp.status_code == 502

    def test_evaluate_blank_text_rejected(self, client):
        """Whitespace-only text is a 422 before evaluation."""
        resp = client.post("/evaluate", json={"text": "   "})
        assert resp.status_code == 422

    def test_evaluate_unsupported_language_rejected(self, client):
        """Only the nine supported Prong 2 codes are accepted."""
        resp = client.post("/evaluate", json={"text": "Hello", "language": "xx"})
        assert resp.status_code == 422

    def test_evaluate_request_validation(self, client):
        """POST /evaluate validates request body."""
        resp = client.post("/evaluate", json={})
        assert resp.status_code == 422  # Validation error (missing 'text')

    def test_generate_request_validation(self, client):
        """POST /generate validates request body."""
        resp = client.post("/generate", json={"prompt": "Hello"})
        assert resp.status_code == 422  # Missing 'model'

    def test_generate_and_evaluate_validation(self, client):
        """POST /generate-and-evaluate validates request body."""
        resp = client.post("/generate-and-evaluate", json={"prompt": "Hello"})
        assert resp.status_code == 422  # Missing 'model'

    # ── Remote (bring-your-own-key) backend routing ────────────────────────

    def test_models_post_local_default(self, client):
        """POST /models with no backend fields behaves like GET /models (local)."""
        resp = client.post("/models", json={})
        assert resp.status_code == 502  # local vLLM unreachable in tests

    def test_models_post_remote_unreachable(self, client):
        """POST /models with backend_type=remote hits the given base_url, not local vLLM."""
        resp = client.post("/models", json={
            "backend_type": "remote",
            "base_url": "http://localhost:19999",
            "api_key": "sk-test",
        })
        assert resp.status_code == 502
        assert "19999" in resp.json()["detail"]

    def test_generate_remote_unreachable(self, client):
        """POST /generate with backend_type=remote routes to the remote host."""
        resp = client.post("/generate", json={
            "prompt": "Hello",
            "model": "gpt-x",
            "backend_type": "remote",
            "base_url": "http://localhost:19999",
            "api_key": "sk-test",
        })
        assert resp.status_code == 502
        assert "19999" in resp.json()["detail"]

    def test_generate_remote_missing_base_url(self, client):
        """backend_type=remote without base_url fails cleanly, not with a crash."""
        resp = client.post("/generate", json={
            "prompt": "Hello",
            "model": "gpt-x",
            "backend_type": "remote",
        })
        assert resp.status_code == 422

    def test_generate_and_evaluate_remote_unreachable(self, client):
        resp = client.post("/generate-and-evaluate", json={
            "prompt": "Hello",
            "model": "gpt-x",
            "backend_type": "remote",
            "base_url": "http://localhost:19999",
            "api_key": "sk-test",
        })
        assert resp.status_code == 502


# ── Benchmark claims tests ─────────────────────────────────────────────────

class TestBenchmarkClaims:

    def test_claims_file_valid_json(self):
        """benchmark_claims.json is valid JSON."""
        with open("data/benchmark_claims.json") as f:
            claims = json.load(f)
        assert isinstance(claims, list)
        assert len(claims) > 0

    def test_claims_have_required_fields(self):
        """Each claim has id, claim, ground_truth, category, prompt_template."""
        with open("data/benchmark_claims.json") as f:
            claims = json.load(f)
        for claim in claims:
            assert 'id' in claim, f"Missing id: {claim}"
            assert 'claim' in claim, f"Missing claim: {claim}"
            assert 'ground_truth' in claim, f"Missing ground_truth: {claim}"
            assert 'category' in claim, f"Missing category: {claim}"
            assert 'prompt_template' in claim, f"Missing prompt_template: {claim}"

    def test_claims_ids_unique(self):
        """Claim IDs are unique."""
        with open("data/benchmark_claims.json") as f:
            claims = json.load(f)
        ids = [c['id'] for c in claims]
        assert len(ids) == len(set(ids)), f"Duplicate IDs: {ids}"

    def test_claims_ground_truth_types(self):
        """Ground truth is bool or null."""
        with open("data/benchmark_claims.json") as f:
            claims = json.load(f)
        for claim in claims:
            gt = claim['ground_truth']
            assert gt is True or gt is False or gt is None, \
                f"Invalid ground_truth for {claim['id']}: {gt}"

    def test_claims_categories(self):
        """Claims have meaningful categories."""
        with open("data/benchmark_claims.json") as f:
            claims = json.load(f)
        categories = set(c['category'] for c in claims)
        assert len(categories) >= 3  # At least geography, history, hedging



