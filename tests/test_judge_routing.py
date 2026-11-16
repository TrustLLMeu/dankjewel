"""Tests for the language-routed judge (0.5B English / 1.5B non-English).

Background (docs/MULTILINGUAL_JUDGE.md): the 210-item test shows the
0.5B judge fails the Icelandic pass check (rho 0.30) while the 1.5B
passes all seven languages (mean rho 0.973), so the product judge
routes by language via get_judge_for_lang.

No network: attribute-level routing checks, a MockTransport wire test,
and stub judges for the metadata and threading paths.
"""

import json

import httpx
import pytest

import src.llm_judge_client as judge_client_module
from src.llm_judge_client import (
    DEFAULT_BASE_URL, DEFAULT_MODEL, NONEN_DEFAULT_BASE_URL,
    NONEN_DEFAULT_MODEL, LLMJudgeClient, get_judge_for_lang,
    get_shared_judge_client, judge_route_for_lang,
)
from src.pipeline import EvaluationPipeline
from src.prongs.prong1_llm_as_judge import Prong1LLMAsJudge
from src.prongs.prong1_dimensions import Relevance

_JUDGE_ENV_VARS = (
    "DANKJEWEL_JUDGE_BASE_URL", "DANKJEWEL_JUDGE_MODEL",
    "DANKJEWEL_JUDGE_API_KEY", "DANKJEWEL_JUDGE_TIMEOUT_S",
    "DANKJEWEL_JUDGE_BASE_URL_NONEN", "DANKJEWEL_JUDGE_MODEL_NONEN",
)


class StubJudge:
    """Test double matching the LLMJudgeClient surface."""

    model_name = "stub-tiny-judge"

    def __init__(self, score=0.9, exc=None):
        self.score = score
        self.exc = exc
        self.calls = 0

    def judge(self, prompt, response, task="JUDGE"):
        self.calls += 1
        if self.exc is not None:
            raise self.exc
        return {"score": self.score, "rationale": "Stub rationale."}


@pytest.fixture
def clean_judge_env(monkeypatch):
    """Isolated judge env and fresh shared-client caches per test."""
    for var in _JUDGE_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(judge_client_module, "_shared_client", None)
    monkeypatch.setattr(judge_client_module, "_shared_nonen_client", None)


# ── get_judge_for_lang ───────────────────────────────────────────────────────

class TestGetJudgeForLang:

    def test_english_routes_to_default_client(self, clean_judge_env):
        client = get_judge_for_lang('en')
        assert client is get_shared_judge_client()
        assert client.model_name == DEFAULT_MODEL          # Qwen2.5-0.5B
        assert client.base_url == DEFAULT_BASE_URL         # :18092

    def test_non_english_routes_to_15b(self, clean_judge_env):
        for lang in ('nl', 'de', 'nb', 'is'):
            client = get_judge_for_lang(lang)
            assert client.model_name == NONEN_DEFAULT_MODEL   # Qwen2.5-1.5B
            assert client.base_url == NONEN_DEFAULT_BASE_URL  # :18093

    def test_non_english_client_is_cached(self, clean_judge_env):
        assert get_judge_for_lang('nl') is get_judge_for_lang('de')
        assert get_judge_for_lang('nl') is not get_shared_judge_client()

    def test_route_classification(self):
        assert judge_route_for_lang('en') == 'en'
        assert judge_route_for_lang('EN') == 'en'
        assert judge_route_for_lang(None) == 'en'
        for lang in ('nl', 'de', 'nb', 'sv'):
            assert judge_route_for_lang(lang) == 'non-en'

    def test_explicit_empty_nonen_url_falls_back(self, clean_judge_env, monkeypatch):
        monkeypatch.setenv("DANKJEWEL_JUDGE_BASE_URL_NONEN", "")
        client = get_judge_for_lang('nl')
        assert client is get_shared_judge_client()
        assert client.model_name == DEFAULT_MODEL

    def test_explicit_empty_nonen_model_falls_back(self, clean_judge_env, monkeypatch):
        monkeypatch.setenv("DANKJEWEL_JUDGE_MODEL_NONEN", "")
        assert get_judge_for_lang('de') is get_shared_judge_client()

    def test_custom_nonen_env_respected(self, clean_judge_env, monkeypatch):
        monkeypatch.setenv("DANKJEWEL_JUDGE_BASE_URL_NONEN", "http://judge-15b.example/v1")
        monkeypatch.setenv("DANKJEWEL_JUDGE_MODEL_NONEN", "custom/judge")
        client = get_judge_for_lang('is')
        assert client.base_url == "http://judge-15b.example/v1"
        assert client.model_name == "custom/judge"

    def test_nonen_client_shares_judge_api_key(self, clean_judge_env, monkeypatch):
        monkeypatch.setenv("DANKJEWEL_JUDGE_API_KEY", "shared-key")
        assert get_judge_for_lang('nl').api_key == "shared-key"

    def test_routed_judge_call_hits_nonen_server(self, clean_judge_env):
        """Wire-level: a routed judge call carries the 1.5B model to :18093."""
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen['url'] = str(request.url)
            seen['payload'] = json.loads(request.content)
            return httpx.Response(200, json={"choices": [
                {"message": {"content": '{"score": 0.9, "rationale": "ok"}'}}]})

        client = LLMJudgeClient(base_url=NONEN_DEFAULT_BASE_URL,
                                model=NONEN_DEFAULT_MODEL,
                                transport=httpx.MockTransport(handler))
        verdict = client.judge("Hva er hovedstaden i Norge?",
                               "Oslo er hovedstaden i Norge.")
        assert seen['url'].startswith(NONEN_DEFAULT_BASE_URL)
        assert seen['payload']['model'] == NONEN_DEFAULT_MODEL
        assert verdict['score'] == 0.9


# ── Relevance judge_route metadata ───────────────────────────────────────────

class TestJudgeRouteMetadata:

    def test_english_route_in_metadata(self):
        score = Relevance().evaluate("What is 2+2?", "The sum is 4.",
                                     judge=StubJudge(), lang='en')
        assert score.metadata['judge_route'] == 'en'
        assert score.metadata['judge_model'] == 'stub-tiny-judge'
        assert score.metadata['judge_status'] == 'scored'

    def test_nonen_route_in_metadata(self):
        score = Relevance().evaluate("Wat is de hoofdstad van Frankrijk?",
                                     "Parijs is de hoofdstad van Frankrijk.",
                                     judge=StubJudge(), lang='nl')
        assert score.metadata['judge_route'] == 'non-en'
        assert score.metadata['judge_status'] == 'scored'

    def test_route_recorded_even_when_judge_unavailable(self):
        stub = StubJudge(exc=judge_client_module.JudgeUnavailableError("down"))
        score = Relevance().evaluate("Wat is de hoofdstad?", "Parijs.",
                                     judge=stub, lang='nl')
        assert score.metadata['judge_route'] == 'non-en'
        assert score.metadata['judge_status'] == 'unknown'
        assert score.status == 'scored'  # baseline untouched

    def test_no_prompt_route_still_recorded(self):
        score = Relevance().evaluate(None, "Parijs.",
                                     judge=StubJudge(), lang='nl')
        assert score.metadata['judge_route'] == 'non-en'
        assert score.metadata['judge_status'] == 'unknown'


# ── Prong 1 / pipeline threading ─────────────────────────────────────────────

class TestProng1Routing:

    def test_router_called_with_lang(self, monkeypatch):
        seen = {}

        def fake_route(lang):
            seen['lang'] = lang
            return StubJudge(score=0.8)

        monkeypatch.setattr('src.prongs.prong1_llm_as_judge.get_judge_for_lang',
                            fake_route)
        prong = Prong1LLMAsJudge()
        result = prong.evaluate("Amsterdam is de hoofdstad van Nederland.",
                                prompt="Wat is de hoofdstad van Nederland?",
                                tiny_judge=True, lang='nl')
        assert seen['lang'] == 'nl'
        rel = result.dimensions[0]
        assert rel.metadata['judge_model'] == 'stub-tiny-judge'
        assert rel.metadata['judge_route'] == 'non-en'
        assert rel.metadata['llm_value'] == 0.8

    def test_injected_judge_overrides_routing(self):
        """An explicitly injected client wins over the language router —
        the test/explicit-configuration override."""
        stub = StubJudge(score=0.7)
        prong = Prong1LLMAsJudge(judge=stub)
        result = prong.evaluate("Antwoord.", prompt="Vraag?",
                                tiny_judge=True, lang='nl')
        assert stub.calls == 1
        rel = result.dimensions[0]
        assert rel.metadata['judge_model'] == 'stub-tiny-judge'
        assert rel.metadata['judge_route'] == 'non-en'

    def test_flag_off_makes_no_calls(self):
        stub = StubJudge()
        prong = Prong1LLMAsJudge(judge=stub)
        result = prong.evaluate("Some answer.", prompt="Some question?",
                                tiny_judge=False, lang='nl')
        assert stub.calls == 0
        rel = result.dimensions[0]
        assert 'judge_model' not in rel.metadata
        assert 'judge_route' not in rel.metadata
        assert 'llm_value' not in rel.metadata


class TestPipelineLangThreading:

    def test_pipeline_routes_judge_by_language(self, monkeypatch):
        seen = {}

        def fake_route(lang):
            seen['lang'] = lang
            return StubJudge(score=0.75)

        monkeypatch.setattr('src.prongs.prong1_llm_as_judge.get_judge_for_lang',
                            fake_route)
        pipeline = EvaluationPipeline()
        result = pipeline.evaluate(
            text="Parijs is de hoofdstad van Frankrijk.",
            prompt="Wat is de hoofdstad van Frankrijk?",
            lang="nl", tiny_judge=True,
        )
        assert seen['lang'] == 'nl'
        rel = next(d for p in result['prong_results']
                   if 'Prong 1' in p['prong_name']
                   for d in p['dimensions'] if d['name'] == 'Relevance')
        assert rel['metadata']['judge_route'] == 'non-en'
        assert rel['metadata']['llm_value'] == 0.75
