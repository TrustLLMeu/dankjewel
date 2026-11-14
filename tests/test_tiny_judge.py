"""Tests for the shared tiny LLM judge and the dual-output Relevance track.

Unit tests use httpx.MockTransport or an injected stub — no network and
no running judge needed. One live smoke test at the bottom is skipped
unless the real judge at 127.0.0.1:18092 is reachable AND
DANKJEWEL_JUDGE_API_KEY is set (the key is read from the environment,
never hardcoded).
"""

import json
import os
import socket
import threading

import httpx
import pytest

from src.llm_judge_client import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    DEFAULT_TIMEOUT_S,
    JudgeParseError,
    JudgeUnavailableError,
    LLMJudgeClient,
    get_shared_judge_client,
)
from src.prongs.prong1_dimensions import Relevance
from src.prongs.prong1_llm_as_judge import Prong1LLMAsJudge
from src.pipeline import EvaluationPipeline

# The exact few-shot prompt verified live against the 0.5B judge on
# 2026-11-14 (relevant→1.0, irrelevant→0.0). This test pins it: the
# prompt must not be rewritten without re-verifying discrimination.
VERIFIED_SYSTEM_PROMPT = (
    "[JUDGE] Rate how relevant the Answer is to the Prompt. "
    "0 = irrelevant, 0.5 = partially relevant, 1 = directly answers. "
    'Reply with ONLY JSON: {"score": 0 to 1, "rationale": at most 40 words}.\n'
    "Examples:\n"
    'Prompt: What is 2+2? Answer: The sum is 4. -> '
    '{"score": 1, "rationale": "Directly answers the arithmetic question."}\n'
    'Prompt: What is 2+2? Answer: Apples grow on trees. -> '
    '{"score": 0, "rationale": "No connection to the arithmetic question."}'
)

PROMPT = "What is the capital of France?"
RESPONSE = "The capital of France is Paris."


def chat_completion_response(content):
    """OpenAI chat-completion response body with the given content."""
    return {"choices": [{"message": {"role": "assistant", "content": content}}]}


class StubJudge:
    """Test double matching the LLMJudgeClient surface (model_name + judge())."""

    model_name = "stub-tiny-judge"

    def __init__(self, score=0.9, rationale="Stub rationale.", exc=None):
        self.score = score
        self.rationale = rationale
        self.exc = exc
        self.calls = 0

    def judge(self, prompt, response, task="JUDGE"):
        self.calls += 1
        if self.exc is not None:
            raise self.exc
        return {"score": self.score, "rationale": self.rationale}


# ── Judge client (MockTransport — no network) ───────────────────────────────

class TestLLMJudgeClient:

    def test_parses_valid_json(self):
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["request"] = request
            return httpx.Response(200, json=chat_completion_response(
                '{"score": 1, "rationale": "Directly answers."}'))

        client = LLMJudgeClient(api_key="k-test", transport=httpx.MockTransport(handler))
        verdict = client.judge(PROMPT, RESPONSE)
        assert verdict == {"score": 1.0, "rationale": "Directly answers."}

        # Request shape: exact verified system prompt, user message, model.
        req = seen["request"]
        assert str(req.url) == f"{DEFAULT_BASE_URL}/chat/completions"
        body = json.loads(req.content)
        assert body["messages"][0]["content"] == VERIFIED_SYSTEM_PROMPT
        assert body["messages"][0]["content"].startswith("[JUDGE] ")
        assert body["messages"][1]["content"] == f"Prompt: {PROMPT}\nAnswer: {RESPONSE}"
        assert body["model"] == DEFAULT_MODEL
        assert req.headers["Authorization"] == "Bearer k-test"
        client.close()

    def test_no_authorization_header_without_key(self, monkeypatch):
        # api_key=None means "fall back to the environment" — pin the
        # env so this test doesn't depend on the ambient DANKJEWEL_JUDGE_API_KEY.
        monkeypatch.delenv("DANKJEWEL_JUDGE_API_KEY", raising=False)
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["request"] = request
            return httpx.Response(200, json=chat_completion_response(
                '{"score": 0.5, "rationale": "Partially relevant."}'))

        client = LLMJudgeClient(api_key=None, transport=httpx.MockTransport(handler))
        verdict = client.judge(PROMPT, RESPONSE)
        assert verdict["score"] == 0.5
        assert "Authorization" not in seen["request"].headers
        client.close()

    def test_tolerates_markdown_fenced_json(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=chat_completion_response(
                '```json\n{"score": 0, "rationale": "No connection."}\n```'))

        client = LLMJudgeClient(api_key=None, transport=httpx.MockTransport(handler))
        verdict = client.judge(PROMPT, RESPONSE)
        assert verdict == {"score": 0.0, "rationale": "No connection."}
        client.close()

    def test_unparseable_json_raises_parse_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=chat_completion_response(
                "I cannot answer that in JSON."))

        client = LLMJudgeClient(api_key=None, transport=httpx.MockTransport(handler))
        with pytest.raises(JudgeParseError):
            client.judge(PROMPT, RESPONSE)
        client.close()

    @pytest.mark.parametrize("bad_score", [1.5, -0.1, '"high"', "true", None])
    def test_score_out_of_range_or_wrong_type_raises_parse_error(self, bad_score):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=chat_completion_response(
                json.dumps({"score": bad_score, "rationale": "words"})))

        client = LLMJudgeClient(api_key=None, transport=httpx.MockTransport(handler))
        with pytest.raises(JudgeParseError):
            client.judge(PROMPT, RESPONSE)
        client.close()

    def test_missing_rationale_raises_parse_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=chat_completion_response(
                '{"score": 0.5}'))

        client = LLMJudgeClient(api_key=None, transport=httpx.MockTransport(handler))
        with pytest.raises(JudgeParseError):
            client.judge(PROMPT, RESPONSE)
        client.close()

    def test_boolean_score_rejected(self):
        # bool is an int subclass; True is not a valid 0..1 score.
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=chat_completion_response(
                '{"score": true, "rationale": "yes"}'))

        client = LLMJudgeClient(api_key=None, transport=httpx.MockTransport(handler))
        with pytest.raises(JudgeParseError):
            client.judge(PROMPT, RESPONSE)
        client.close()

    def test_transport_error_raises_unavailable(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused", request=request)

        client = LLMJudgeClient(api_key=None, transport=httpx.MockTransport(handler))
        with pytest.raises(JudgeUnavailableError):
            client.judge(PROMPT, RESPONSE)
        client.close()

    def test_timeout_exception_raises_unavailable(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("timed out", request=request)

        client = LLMJudgeClient(api_key=None, timeout=5.0,
                                transport=httpx.MockTransport(handler))
        with pytest.raises(JudgeUnavailableError, match="timed out"):
            client.judge(PROMPT, RESPONSE)
        client.close()

    def test_http_error_status_raises_unavailable(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"error": "boom"})

        client = LLMJudgeClient(api_key=None, transport=httpx.MockTransport(handler))
        with pytest.raises(JudgeUnavailableError, match="500"):
            client.judge(PROMPT, RESPONSE)
        client.close()

    def test_malformed_200_body_raises_parse_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"unexpected": "shape"})

        client = LLMJudgeClient(api_key=None, transport=httpx.MockTransport(handler))
        with pytest.raises(JudgeParseError):
            client.judge(PROMPT, RESPONSE)
        client.close()

    def test_unverified_task_rejected(self):
        client = LLMJudgeClient(api_key=None)
        with pytest.raises(ValueError):
            client.judge(PROMPT, RESPONSE, task="READABILITY")
        client.close()

    def test_env_configuration(self, monkeypatch):
        monkeypatch.setenv("DANKJEWEL_JUDGE_BASE_URL", "http://judge.example:9/v1/")
        monkeypatch.setenv("DANKJEWEL_JUDGE_MODEL", "Qwen/Qwen2.5-1.5B-Instruct")
        monkeypatch.setenv("DANKJEWEL_JUDGE_API_KEY", "env-key")
        monkeypatch.setenv("DANKJEWEL_JUDGE_TIMEOUT_S", "12.5")
        client = LLMJudgeClient()
        assert client.base_url == "http://judge.example:9/v1"  # trailing slash stripped
        assert client.model_name == "Qwen/Qwen2.5-1.5B-Instruct"
        assert client.api_key == "env-key"
        assert client.timeout == 12.5
        client.close()

    def test_invalid_timeout_env_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv("DANKJEWEL_JUDGE_TIMEOUT_S", "not-a-number")
        client = LLMJudgeClient()
        assert client.timeout == DEFAULT_TIMEOUT_S
        client.close()

    def test_shared_client_is_a_singleton(self, monkeypatch):
        monkeypatch.setattr("src.llm_judge_client._shared_client", None)
        first = get_shared_judge_client()
        second = get_shared_judge_client()
        assert first is second


# ── Dual-output Relevance dimension (stub judge — no network) ────────────────

class TestRelevanceDualOutput:

    def relevance_meta(self, judge, prompt=PROMPT):
        rel = Relevance()
        return rel.evaluate(prompt, RESPONSE, judge=judge)

    def test_judge_scored_fills_dual_output_metadata(self):
        stub = StubJudge(score=0.9, rationale="Answers the question.")
        score = self.relevance_meta(stub)
        assert score.status == 'scored'
        meta = score.metadata
        assert meta['judge_status'] == 'scored'
        assert meta['llm_value'] == 0.9
        assert meta['rationale'] == "Answers the question."
        assert meta['judge_model'] == "stub-tiny-judge"
        assert meta['baseline_value'] == score.value  # baseline mirrors value
        assert meta['baseline_processing_time_ms'] >= 0.0
        assert meta['llm_processing_time_ms'] >= 0.0
        # Existing baseline metadata is preserved alongside the judge track.
        assert meta['model'] == "sentence-transformers/all-MiniLM-L6-v2"
        assert 'sentences' in meta and 'time' in meta

    def test_judge_unavailable_keeps_baseline_and_marks_unknown(self):
        rel = Relevance()
        baseline = rel.evaluate(PROMPT, RESPONSE)  # judge=None default
        stub = StubJudge(exc=JudgeUnavailableError("judge timed out after 30s"))
        score = self.relevance_meta(stub)
        # Baseline untouched: same value, same status, still aggregated.
        assert score.value == baseline.value
        assert score.status == 'scored'
        assert score.aggregate is True
        meta = score.metadata
        assert meta['judge_status'] == 'unknown'
        assert meta['llm_value'] is None
        assert meta['rationale'] is None
        assert 'judge_error' in meta
        assert meta['llm_processing_time_ms'] is not None

    def test_judge_parse_error_marks_judge_track_error(self):
        stub = StubJudge(exc=JudgeParseError("not a JSON object"))
        score = self.relevance_meta(stub)
        assert score.status == 'scored'  # baseline track unaffected
        assert score.metadata['judge_status'] == 'error'
        assert score.metadata['llm_value'] is None
        assert 'judge_error' in score.metadata

    def test_no_judge_leaves_metadata_unchanged(self):
        score = self.relevance_meta(None)
        meta = score.metadata
        for key in ('judge_status', 'llm_value', 'baseline_value', 'rationale'):
            assert key not in meta
        assert score.status == 'scored'

    def test_no_prompt_marks_judge_track_unknown(self):
        stub = StubJudge()
        score = self.relevance_meta(stub, prompt=None)
        assert score.status == 'unknown'
        meta = score.metadata
        assert meta['reason'] == 'no prompt provided'
        assert meta['judge_status'] == 'unknown'
        assert meta['llm_value'] is None
        assert stub.calls == 0  # nothing to judge without a prompt

    def test_server_down_baseline_only_no_exception(self):
        # Nothing listens on this local port (same convention as the
        # existing VLLMClient unreachable tests).
        judge = LLMJudgeClient(base_url="http://127.0.0.1:19999/v1", api_key="k", timeout=2.0)
        score = self.relevance_meta(judge)
        judge.close()
        assert score.status == 'scored'  # embedding baseline unaffected
        assert score.value > 0.0
        assert score.metadata['judge_status'] == 'unknown'
        assert score.metadata['llm_value'] is None


class _SilentServer:
    """Local TCP server that accepts connections but never replies."""

    def __init__(self):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(1)
        self.port = self._sock.getsockname()[1]
        self._conns = []
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self):
        while True:
            try:
                conn, _ = self._sock.accept()
            except OSError:
                return
            self._conns.append(conn)  # hold open, never respond

    def close(self):
        self._sock.close()


class TestJudgeTimeoutBudget:
    """A judge call that exceeds its timeout must not block evaluate."""

    def test_timed_out_call_surfaced_as_unknown(self):
        server = _SilentServer()
        try:
            judge = LLMJudgeClient(
                base_url=f"http://127.0.0.1:{server.port}/v1",
                api_key=None, timeout=0.25)
            rel = Relevance()
            score = rel.evaluate(PROMPT, RESPONSE, judge=judge)
            judge.close()
        finally:
            server.close()
        assert score.status == 'scored'
        meta = score.metadata
        assert meta['judge_status'] == 'unknown'
        assert meta['llm_value'] is None
        # The call was cut off at the timeout, not allowed to hang.
        assert meta['llm_processing_time_ms'] is not None
        assert meta['llm_processing_time_ms'] < 5_000  # ms — generous upper bound


# ── Wiring: prong evaluator / pipeline (stub judge — no network) ────────────

class TestTinyJudgeWiring:

    def test_prong1_tiny_judge_off_makes_no_judge_call(self):
        stub = StubJudge()
        prong = Prong1LLMAsJudge(judge=stub)
        result = prong.evaluate(RESPONSE, prompt=PROMPT, tiny_judge=False)
        assert stub.calls == 0
        relevance = result.dimensions[0]
        assert 'judge_status' not in relevance.metadata

    def test_prong1_tiny_judge_on_runs_judge_once(self):
        stub = StubJudge(score=1.0, rationale="Direct.")
        prong = Prong1LLMAsJudge(judge=stub)
        result = prong.evaluate(RESPONSE, prompt=PROMPT, tiny_judge=True)
        assert stub.calls == 1
        relevance = result.dimensions[0]
        assert relevance.metadata['judge_status'] == 'scored'
        assert relevance.metadata['llm_value'] == 1.0

    def test_pipeline_tiny_judge_flag_reaches_relevance(self):
        stub = StubJudge(score=0.25, rationale="Off-topic.")
        pipeline = EvaluationPipeline(enable_prongs=[1], judge=stub)

        off = pipeline.evaluate(text=RESPONSE, prompt=PROMPT, tiny_judge=False)
        assert stub.calls == 0
        off_rel = off['prong_results'][0]['dimensions'][0]
        assert 'judge_status' not in off_rel['metadata']

        on = pipeline.evaluate(text=RESPONSE, prompt=PROMPT, tiny_judge=True)
        assert stub.calls == 1
        on_rel = on['prong_results'][0]['dimensions'][0]
        assert on_rel['metadata']['judge_status'] == 'scored'
        assert on_rel['metadata']['llm_value'] == 0.25
        # Baseline is what value/aggregation carry — identical with and
        # without the judge, and prong1_backend stays honest.
        assert on_rel['value'] == off_rel['value']
        scores = lambda r: {k: v for k, v in r['aggregated_scores'].items() if k != 'metadata'}
        assert scores(on) == scores(off)  # metadata only differs in timing
        assert on['metadata']['prong1_backend'] == 'embeddings'


# ── API: /evaluate tiny_judge flag (TestClient, stubbed judge) ──────────────

class TestEvaluateTinyJudgeAPI:

    @pytest.fixture
    def client(self, monkeypatch):
        """TestClient whose /evaluate uses a pipeline with a stub judge."""
        from fastapi.testclient import TestClient
        from src.api import app
        stub = StubJudge(score=0.8, rationale="Mostly answers it.")
        monkeypatch.setattr(
            "src.api.evaluator", EvaluationPipeline(enable_prongs=[1], judge=stub))
        return TestClient(app)

    @staticmethod
    def relevance_meta(data):
        prong1 = next(p for p in data['prong_results'] if p['prong_name'].startswith('LLM-as-Judge'))
        return next(d for d in prong1['dimensions'] if d['name'] == 'Relevance')['metadata']

    def test_evaluate_default_unchanged(self, client):
        resp = client.post("/evaluate", json={"prompt": PROMPT, "text": RESPONSE})
        assert resp.status_code == 200
        data = resp.json()
        meta = self.relevance_meta(data)
        # Flag absent → exactly the previous behavior: no judge keys.
        for key in ('judge_status', 'llm_value', 'baseline_value', 'rationale'):
            assert key not in meta
        assert data['metadata']['prong1_backend'] == 'embeddings'

    def test_evaluate_tiny_judge_true_both_tracks(self, client):
        baseline = client.post("/evaluate", json={"prompt": PROMPT, "text": RESPONSE}).json()
        resp = client.post("/evaluate", json={
            "prompt": PROMPT, "text": RESPONSE, "tiny_judge": True})
        assert resp.status_code == 200
        data = resp.json()
        meta = self.relevance_meta(data)
        assert meta['judge_status'] == 'scored'
        assert meta['llm_value'] == 0.8
        assert meta['rationale'] == "Mostly answers it."
        assert meta['judge_model'] == "stub-tiny-judge"
        assert 'baseline_value' in meta and 'baseline_processing_time_ms' in meta
        assert 'llm_processing_time_ms' in meta
        # Baseline / aggregation identical to the default-off request
        # (aggregated metadata only differs in timing).
        def scores_only(result):
            return {k: v for k, v in result['aggregated_scores'].items() if k != 'metadata'}
        assert scores_only(data) == scores_only(baseline)

    def test_evaluate_tiny_judge_false_explicit(self, client):
        resp = client.post("/evaluate", json={
            "prompt": PROMPT, "text": RESPONSE, "tiny_judge": False})
        assert resp.status_code == 200
        assert 'judge_status' not in self.relevance_meta(resp.json())


# ── Live smoke (skipped unless the real judge is up + key is set) ────────────

LIVE_JUDGE_HOST = "http://127.0.0.1:18092"


def _live_judge_reachable() -> bool:
    try:
        httpx.get(f"{LIVE_JUDGE_HOST}/v1/models", timeout=2.0)
        return True
    except httpx.HTTPError:
        return False


live_judge_ready = _live_judge_reachable() and bool(os.environ.get("DANKJEWEL_JUDGE_API_KEY"))


@pytest.mark.skipif(not live_judge_ready, reason=(
    "live tiny judge at 127.0.0.1:18092 unreachable or DANKJEWEL_JUDGE_API_KEY unset"))
def test_live_tiny_judge_smoke():
    """Live smoke: the 0.5B judge discriminates relevant vs irrelevant answers.

    Expect ~1.0 for the relevant answer and ~0.0 for the irrelevant
    one. Uses fresh content, not the few-shot exemplars: at the
    client's temperature 0, a user message that repeats an exemplar
    verbatim makes the 0.5B model echo that exemplar's continuation
    instead of judging (measured live 2026-11-14). Also runs one
    dual-output pass through the Relevance dimension.
    """
    client = LLMJudgeClient()  # full env config: base URL, model, key, timeout
    try:
        relevant = client.judge("What is the capital of France?",
                                "The capital of France is Paris.")
        irrelevant = client.judge("What is the capital of France?",
                                  "Apples grow on trees.")
        assert 0.0 <= relevant["score"] <= 1.0
        assert 0.0 <= irrelevant["score"] <= 1.0
        assert relevant["score"] > 0.5, f"expected ~1.0, got {relevant['score']}"
        assert irrelevant["score"] < 0.5, f"expected ~0.0, got {irrelevant['score']}"
        assert relevant["rationale"] and irrelevant["rationale"]

        rel = Relevance()
        score = rel.evaluate(
            "Explain biathlon.",
            "Biathlon combines cross-country skiing and rifle shooting in a winter sport.",
            judge=client,
        )
    finally:
        client.close()
    print(f"\nlive relevant verdict:   {relevant}")
    print(f"live irrelevant verdict: {irrelevant}")
    meta = score.metadata
    print(f"live dual-output metadata: {meta}")
    assert meta['judge_status'] == 'scored'
    assert meta['llm_value'] is not None and 0.0 <= meta['llm_value'] <= 1.0
    assert meta['baseline_value'] == score.value
    assert meta['judge_model'] == DEFAULT_MODEL
