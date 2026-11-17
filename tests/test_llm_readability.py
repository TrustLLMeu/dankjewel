"""Tests for the [READABILITY] LLM track (Prong 2 Fluency dual output).

Unit tests use httpx.MockTransport or an injected stub client — no
network and no running readability model needed. One live smoke test at
the bottom is skipped unless the 1.5B at 127.0.0.1:18093 is reachable
AND a key is available via DANKJEWEL_READABILITY_API_KEY (or the
DANKJEWEL_JUDGE_API_KEY fallback; the key is read from the
environment, never hardcoded).
"""

import json
import os

import httpx
import pytest

from src.dimensions.llm_fluidity import LLMFluidityDimension
from src.dimensions.prong2_dimensions import FluidityDimension
from src.llm_judge_client import (
    JudgeError,
    JudgeParseError,
    JudgeUnavailableError,
    LLMJudgeClient,
    READABILITY_DEFAULT_BASE_URL,
    READABILITY_DEFAULT_MODEL,
    ReadabilityParseError,
    get_shared_judge_client,
)
from src.prongs.prong2_rule_based import Prong2RuleBased
from src.pipeline import EvaluationPipeline

# The exact few-shot prompt verified live against the 1.5B on
# 2026-11-17 (easy -> 1.0, dense jargon -> 0.2, garbled -> 0.0; the
# 0.5B does NOT discriminate — every text got a single mid score).
# This test pins it: the prompt must not be rewritten without
# re-verifying discrimination.
VERIFIED_READABILITY_PROMPT = (
    "[READABILITY] Rate how readable the Text is for a general adult "
    "audience, considering coherence, structural flow, vocabulary "
    "complexity, and sentence structure. Scale: 1 = clear and easy for "
    "any adult, 0.7 = a plain news article, 0.5 = needs effort or some "
    "background knowledge, 0.2 = dense jargon most adults cannot parse, "
    "0 = garbled or incoherent. "
    'Reply with ONLY JSON: {"score": 0 to 1, "level": "A1"|"A2"|"B1"|"B2"|"C1"|"C2", '
    '"rationale": at most 40 words}.\n'
    "Examples:\n"
    "Text: The sun rises in the east every morning. Plants need light to "
    "grow. Farmers water their fields when the soil is dry. -> "
    '{"score": 1, "level": "A1", "rationale": "Common words, short '
    'sentences, logical order; understandable for any reader."}\n'
    "Text: Utilization of polysyllabic nomenclature frequently obfuscates "
    "pedagogical objectives, thereby attenuating comprehension amongst "
    "demographically heterogeneous cohorts. -> "
    '{"score": 0.1, "level": "C2", "rationale": "Dense jargon in one long '
    'sentence; only expert readers parse it easily."}'
)

TEXT = "The cat sits on the mat. The dog runs in the park."


def chat_completion_response(content):
    """OpenAI chat-completion response body with the given content."""
    return {"choices": [{"message": {"role": "assistant", "content": content}}]}


class StubReadabilityJudge:
    """Test double matching the [READABILITY] client surface."""

    readability_model_name = "stub-readability-1.5b"

    def __init__(self, score=0.8, level="B2", rationale="Stub rationale.",
                 exc=None):
        self.score = score
        self.level = level
        self.rationale = rationale
        self.exc = exc
        self.calls = 0

    def readability(self, text):
        self.calls += 1
        if self.exc is not None:
            raise self.exc
        return {"score": self.score, "level": self.level,
                "rationale": self.rationale}


@pytest.fixture(autouse=True)
def _clean_readability_env(monkeypatch):
    """Pin the [READABILITY] env config away from the ambient machine.

    The judge env vars are cleared so constructor-level defaults are
    deterministic, and the shared client singleton is reset so no test
    sees another test's injection.
    """
    for var in ("DANKJEWEL_READABILITY_BASE_URL", "DANKJEWEL_READABILITY_MODEL",
                "DANKJEWEL_READABILITY_API_KEY", "DANKJEWEL_READABILITY_TIMEOUT_S",
                "DANKJEWEL_JUDGE_BASE_URL", "DANKJEWEL_JUDGE_MODEL",
                "DANKJEWEL_JUDGE_API_KEY", "DANKJEWEL_JUDGE_TIMEOUT_S"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr("src.llm_judge_client._shared_client", None)
    yield
    # monkeypatch restores env + the singleton automatically.


def _fluency(prong_result):
    return next(d for d in prong_result.dimensions if d.name == "Fluency")


# ── Judge client: wire + parser (MockTransport — no network) ─────────────────

class TestReadabilityClient:

    def test_parses_valid_json_and_request_shape(self):
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["request"] = request
            return httpx.Response(200, json=chat_completion_response(
                '{"score": 0.8, "level": "B2", '
                '"rationale": "Clear paragraphs, common words."}'))

        client = LLMJudgeClient(api_key="k-test",
                                transport=httpx.MockTransport(handler))
        verdict = client.readability(TEXT)
        assert verdict == {"score": 0.8, "level": "B2",
                           "rationale": "Clear paragraphs, common words."}

        req = seen["request"]
        assert str(req.url) == f"{READABILITY_DEFAULT_BASE_URL}/chat/completions"
        body = json.loads(req.content)
        assert body["messages"][0]["content"] == VERIFIED_READABILITY_PROMPT
        assert body["messages"][0]["content"].startswith("[READABILITY] ")
        assert body["messages"][1]["content"] == f"Text: {TEXT}"
        assert body["model"] == READABILITY_DEFAULT_MODEL
        assert body["temperature"] == 0.0
        assert body["max_tokens"] == 160
        assert req.headers["Authorization"] == "Bearer k-test"
        client.close()

    def test_no_authorization_header_without_key(self):
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["request"] = request
            return httpx.Response(200, json=chat_completion_response(
                '{"score": 0.5, "level": "B1", "rationale": "Ok."}'))

        client = LLMJudgeClient(transport=httpx.MockTransport(handler))
        assert client.readability(TEXT)["score"] == 0.5
        assert "Authorization" not in seen["request"].headers
        client.close()

    def test_key_precedence_readability_env_over_judge_env(self, monkeypatch):
        monkeypatch.setenv("DANKJEWEL_JUDGE_API_KEY", "judge-key")
        monkeypatch.setenv("DANKJEWEL_READABILITY_API_KEY", "readability-key")
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["request"] = request
            return httpx.Response(200, json=chat_completion_response(
                '{"score": 0.5, "level": "B1", "rationale": "Ok."}'))

        client = LLMJudgeClient(transport=httpx.MockTransport(handler))
        assert client.readability_api_key == "readability-key"
        assert client.readability(TEXT)["score"] == 0.5
        assert seen["request"].headers["Authorization"] == "Bearer readability-key"
        client.close()

    def test_key_falls_back_to_judge_env(self, monkeypatch):
        monkeypatch.setenv("DANKJEWEL_JUDGE_API_KEY", "judge-key")
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["request"] = request
            return httpx.Response(200, json=chat_completion_response(
                '{"score": 0.5, "level": "B1", "rationale": "Ok."}'))

        client = LLMJudgeClient(transport=httpx.MockTransport(handler))
        assert client.readability_api_key == "judge-key"
        assert client.readability(TEXT)["score"] == 0.5
        assert seen["request"].headers["Authorization"] == "Bearer judge-key"
        client.close()

    def test_env_overrides_base_url_model_timeout(self, monkeypatch):
        monkeypatch.setenv("DANKJEWEL_READABILITY_BASE_URL",
                           "http://127.0.0.1:19999/v1/")
        monkeypatch.setenv("DANKJEWEL_READABILITY_MODEL", "other-model")
        monkeypatch.setenv("DANKJEWEL_READABILITY_TIMEOUT_S", "5")
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["request"] = request
            return httpx.Response(200, json=chat_completion_response(
                '{"score": 0.5, "level": "B1", "rationale": "Ok."}'))

        client = LLMJudgeClient(transport=httpx.MockTransport(handler))
        assert client.readability_base_url == "http://127.0.0.1:19999/v1"
        assert client.readability_model_name == "other-model"
        assert client.readability_timeout == 5.0
        assert client.readability(TEXT)["score"] == 0.5
        assert str(seen["request"].url) == "http://127.0.0.1:19999/v1/chat/completions"
        client.close()

    def test_tolerates_markdown_fence_and_prose(self):
        for content in (
            '```json\n{"score": 0.2, "level": "C2", "rationale": "Jargon."}\n```',
            'Sure: {"score": 0.2, "level": "C2", "rationale": "Jargon."} thanks',
        ):
            client = LLMJudgeClient(
                transport=httpx.MockTransport(
                    lambda request: httpx.Response(
                        200, json=chat_completion_response(content))))
            assert client.readability(TEXT) == {
                "score": 0.2, "level": "C2", "rationale": "Jargon."}
            client.close()

    @pytest.mark.parametrize("content, why", [
        ("", "empty reply"),
        ("not json at all", "not JSON"),
        ('["not", "an", "object"]', "array, not object"),
        ('{"level": "B2", "rationale": "No score."}', "score missing"),
        ('{"score": 1.5, "level": "B2", "rationale": "Out of range."}', "score > 1"),
        ('{"score": -0.1, "level": "B2", "rationale": "Negative."}', "score < 0"),
        ('{"score": true, "level": "B2", "rationale": "Boolean."}', "bool score"),
        ('{"score": "0.8", "level": "B2", "rationale": "String score."}', "string score"),
        ('{"score": 0.8, "rationale": "Level missing."}', "level missing"),
        ('{"score": 0.8, "level": 3, "rationale": "Numeric level."}', "level not str"),
        ('{"score": 0.8, "level": "B2"}', "rationale missing"),
        ('{"score": 0.8, "level": "B2", "rationale": 42}', "rationale not str"),
    ])
    def test_unusable_reply_raises_readability_parse_error(self, content, why):
        client = LLMJudgeClient(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200, json=chat_completion_response(content))))
        with pytest.raises(ReadabilityParseError):
            client.readability(TEXT)
        client.close()

    def test_parse_error_is_a_judge_parse_error(self):
        assert issubclass(ReadabilityParseError, JudgeParseError)
        assert issubclass(ReadabilityParseError, JudgeError)

    def test_transport_error_raises_unavailable(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused", request=request)

        client = LLMJudgeClient(transport=httpx.MockTransport(handler))
        with pytest.raises(JudgeUnavailableError):
            client.readability(TEXT)
        client.close()

    def test_timeout_raises_unavailable(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("timed out", request=request)

        client = LLMJudgeClient(transport=httpx.MockTransport(handler))
        with pytest.raises(JudgeUnavailableError):
            client.readability(TEXT)
        client.close()

    def test_http_error_status_raises_unavailable(self):
        client = LLMJudgeClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(500, json={"error": "boom"})))
        with pytest.raises(JudgeUnavailableError):
            client.readability(TEXT)
        client.close()

    def test_shared_client_serves_readability(self, monkeypatch):
        """get_shared_judge_client() is the one instance for all tasks."""
        monkeypatch.setenv("DANKJEWEL_READABILITY_API_KEY", "shared-key")
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["request"] = request
            return httpx.Response(200, json=chat_completion_response(
                '{"score": 0.9, "level": "A2", "rationale": "Simple."}'))

        monkeypatch.setattr("src.llm_judge_client._shared_client",
                            LLMJudgeClient(transport=httpx.MockTransport(handler)))
        client = get_shared_judge_client()
        assert client.readability(TEXT)["score"] == 0.9
        assert seen["request"].headers["Authorization"] == "Bearer shared-key"


# ── LLMFluidityDimension: dual output over the Flesch baseline ───────────────

class TestLLMFluidityDimension:

    def test_scored_dual_output(self):
        stub = StubReadabilityJudge()
        score = LLMFluidityDimension(client=stub).evaluate(TEXT, lang="en")
        baseline = FluidityDimension().evaluate(TEXT, lang="en")

        # The baseline half is exactly FluidityDimension's score.
        assert score.name == "Fluency"
        assert score.status == "scored"
        assert score.value == baseline.value
        assert score.raw_value == baseline.raw_value
        assert score.metadata["formula"] == baseline.metadata["formula"]
        assert score.metadata["lang"] == "en"
        assert score.metadata["words"] == baseline.metadata["words"]

        # Dual-output contract.
        assert score.metadata["baseline_value"] == baseline.value
        assert score.metadata["baseline_raw_value"] == baseline.raw_value
        assert score.metadata["llm_value"] == 0.8
        assert score.metadata["llm_level"] == "B2"
        assert score.metadata["llm_rationale"] == "Stub rationale."
        assert score.metadata["judge_status"] == "scored"
        assert score.metadata["judge_model"] == stub.readability_model_name
        assert score.metadata["baseline_processing_time_ms"] >= 0.0
        assert score.metadata["llm_processing_time_ms"] >= 0.0
        assert "judge_error" not in score.metadata

        # Evidence contract: rules (baseline) + llm_judge (LLM track).
        evidence = score.metadata["evidence_sources"]
        assert evidence["rules"] == {"value": baseline.value,
                                     "status": "scored", "n": None}
        assert evidence["llm_judge"] == {"value": 0.8, "status": "scored", "n": 1}

    def test_baseline_matches_old_single_track_values(self):
        """The dual dimension's value/raw_value/formula are byte-identical
        to today's single-track FluidityDimension on the same input."""
        stub = StubReadabilityJudge()
        dim = LLMFluidityDimension(client=stub)
        for text, lang in [
            (TEXT, "en"),
            ("Die Schmetterlingswanderung findet jährlich statt. "
             "Die Wissenschaftler beobachten das Naturphänomen.", "de"),
            ("Alstublieft, dank u wel. De kat zit op de mat.", "nl"),
        ]:
            dual = dim.evaluate(text, lang=lang)
            base = FluidityDimension().evaluate(text, lang=lang)
            assert dual.value == base.value
            assert dual.raw_value == base.raw_value
            assert dual.status == base.status
            assert dual.metadata["formula"] == base.metadata["formula"]
            assert dual.metadata["baseline_value"] == base.value

    def test_degenerate_text_abstains_without_a_call(self):
        stub = StubReadabilityJudge()
        score = LLMFluidityDimension(client=stub).evaluate("!!!", lang="en")
        base = FluidityDimension().evaluate("!!!", lang="en")
        assert score.status == base.status  # mirrors FluidityDimension today
        assert score.value == base.value
        assert score.metadata["judge_status"] == "unknown"
        assert score.metadata["llm_value"] is None
        assert score.metadata["llm_level"] is None
        assert score.metadata["llm_rationale"] is None
        assert score.metadata["llm_processing_time_ms"] is None
        assert "degenerate text" in score.metadata["judge_error"]
        assert stub.calls == 0
        assert score.metadata["evidence_sources"]["llm_judge"]["status"] == "unknown"

    def test_empty_text_abstains_without_a_call(self):
        stub = StubReadabilityJudge()
        score = LLMFluidityDimension(client=stub).evaluate("", lang="en")
        assert score.metadata["judge_status"] == "unknown"
        assert score.metadata["llm_value"] is None
        assert "empty text" in score.metadata["judge_error"]
        assert stub.calls == 0

    def test_non_english_abstains_english_only(self):
        stub = StubReadabilityJudge()
        score = LLMFluidityDimension(client=stub).evaluate(
            "Alstublieft, dank u wel.", lang="nl")
        base = FluidityDimension().evaluate("Alstublieft, dank u wel.", lang="nl")
        assert score.metadata["judge_status"] == "unknown"
        assert score.metadata["llm_value"] is None
        assert "English only" in score.metadata["judge_error"]
        assert stub.calls == 0
        # The Dutch Flesch baseline is untouched.
        assert score.value == base.value
        assert score.metadata["formula"] == "Flesch-Douma"
        assert score.metadata["lang"] == "nl"

    def test_unavailable_judge_keeps_baseline_and_marks_unknown(self):
        stub = StubReadabilityJudge(exc=JudgeUnavailableError(
            "cannot reach readability model at http://127.0.0.1:18093/v1"))
        score = LLMFluidityDimension(client=stub).evaluate(TEXT, lang="en")
        baseline = FluidityDimension().evaluate(TEXT, lang="en")
        assert score.status == "scored"  # never regresses to blank
        assert score.value == baseline.value
        assert score.metadata["baseline_value"] == baseline.value
        assert score.metadata["judge_status"] == "unknown"
        assert score.metadata["llm_value"] is None
        assert "cannot reach" in score.metadata["judge_error"]
        assert score.metadata["llm_processing_time_ms"] >= 0.0
        assert score.metadata["evidence_sources"]["llm_judge"] == {
            "value": None, "status": "unknown", "n": None}
        assert stub.calls == 1

    def test_parse_error_keeps_baseline_and_marks_error(self):
        stub = StubReadabilityJudge(exc=ReadabilityParseError(
            'readability reply is not a JSON object'))
        score = LLMFluidityDimension(client=stub).evaluate(TEXT, lang="en")
        baseline = FluidityDimension().evaluate(TEXT, lang="en")
        assert score.status == "scored"
        assert score.value == baseline.value
        assert score.metadata["judge_status"] == "error"
        assert score.metadata["llm_value"] is None
        assert score.metadata["judge_error"]
        assert score.metadata["evidence_sources"]["llm_judge"]["status"] == "error"

    def test_judge_kwarg_overrides_constructor_client(self):
        constructor_stub = StubReadabilityJudge(score=0.1)
        kwarg_stub = StubReadabilityJudge(score=0.9)
        score = LLMFluidityDimension(client=constructor_stub).evaluate(
            TEXT, judge=kwarg_stub, lang="en")
        assert score.metadata["llm_value"] == 0.9
        assert kwarg_stub.calls == 1
        assert constructor_stub.calls == 0

    def test_uses_shared_client_when_none_injected(self, monkeypatch):
        """client=None lazily resolves the process-wide shared judge."""
        stub = StubReadabilityJudge()
        monkeypatch.setattr("src.llm_judge_client._shared_client", stub)
        score = LLMFluidityDimension().evaluate(TEXT, lang="en")
        assert score.metadata["judge_status"] == "scored"
        assert score.metadata["llm_value"] == 0.8
        assert stub.calls == 1


# ── Prong 2 wiring: the llm_readability flag ─────────────────────────────────

class TestProng2ReadabilityFlag:

    def test_flag_off_identical_single_track_behavior(self):
        """Default off: no judge calls, no dual keys, same scores as a
        plain single-track prong run."""
        stub = StubReadabilityJudge()
        prong = Prong2RuleBased(judge=stub)
        plain = Prong2RuleBased()

        result = prong.evaluate(TEXT, lang="en")
        plain_result = plain.evaluate(TEXT, lang="en")

        assert stub.calls == 0
        assert result.error is None
        assert [d.name for d in result.dimensions] == \
            [d.name for d in plain_result.dimensions]
        assert [d.value for d in result.dimensions] == \
            [d.value for d in plain_result.dimensions]
        fluency = _fluency(result)
        for key in ("baseline_value", "baseline_raw_value", "llm_value",
                    "llm_level", "llm_rationale", "judge_status", "judge_model",
                    "baseline_processing_time_ms", "llm_processing_time_ms",
                    "judge_error"):
            assert key not in fluency.metadata
        assert "llm_judge" not in fluency.metadata["evidence_sources"]

    def test_flag_on_fluency_carries_dual_output(self):
        stub = StubReadabilityJudge()
        prong = Prong2RuleBased(judge=stub)

        on = prong.evaluate(TEXT, lang="en", llm_readability=True)
        off = prong.evaluate(TEXT, lang="en")

        assert stub.calls == 1
        assert on.error is None
        fluency = _fluency(on)
        assert fluency.value == _fluency(off).value
        assert fluency.metadata["judge_status"] == "scored"
        assert fluency.metadata["llm_value"] == 0.8
        assert fluency.metadata["baseline_value"] == fluency.value
        assert fluency.metadata["evidence_sources"]["llm_judge"]["status"] == "scored"
        # Every other dimension is untouched by the flag.
        other_on = [d for d in on.dimensions if d.name != "Fluency"]
        other_off = [d for d in off.dimensions if d.name != "Fluency"]
        assert [(d.name, d.value) for d in other_on] == \
            [(d.name, d.value) for d in other_off]

    def test_flag_on_unavailable_judge_stays_scored(self):
        stub = StubReadabilityJudge(exc=JudgeUnavailableError("dead server"))
        prong = Prong2RuleBased(judge=stub)
        result = prong.evaluate(TEXT, lang="en", llm_readability=True)
        assert result.error is None
        fluency = _fluency(result)
        assert fluency.status == "scored"
        assert fluency.metadata["judge_status"] == "unknown"
        assert fluency.metadata["llm_value"] is None
        assert fluency.metadata["baseline_value"] == fluency.value


# ── Pipeline flag threading ──────────────────────────────────────────────────

class TestPipelineReadabilityFlag:

    def test_pipeline_threads_flag_to_prong2(self):
        stub = StubReadabilityJudge()
        pipeline = EvaluationPipeline(enable_prongs=[2], judge=stub)

        on = pipeline.evaluate(TEXT, llm_readability=True)
        off = pipeline.evaluate(TEXT)

        # pipeline.evaluate returns to_dict() shapes: dict dimensions.
        def fluency_dim(evaluation):
            prong = evaluation["prong_results"][0]
            return next(d for d in prong["dimensions"] if d["name"] == "Fluency")

        fluency_on = fluency_dim(on)
        assert fluency_on["metadata"]["judge_status"] == "scored"
        assert fluency_on["metadata"]["llm_value"] == 0.8
        assert stub.calls == 1

        # Flag off: identical single-track output.
        fluency_off = fluency_dim(off)
        assert "llm_value" not in fluency_off["metadata"]
        assert fluency_off["value"] == fluency_on["value"]
        assert off["aggregated_scores"]["total_score"] == \
            on["aggregated_scores"]["total_score"]  # Flesch stays the value

        # The coverage summary sees the scored judge track.
        assert on["coverage"]["judge_scored"] is True
        assert on["coverage"]["rules_scored"] is True


# ── Live smoke (skipped unless the 1.5B is up + key is set) ──────────────────

LIVE_READABILITY_HOST = "http://127.0.0.1:18093"


def _live_readability_reachable() -> bool:
    try:
        httpx.get(f"{LIVE_READABILITY_HOST}/v1/models", timeout=2.0)
        return True
    except httpx.HTTPError:
        return False


def _live_readability_key() -> str:
    return (os.environ.get("DANKJEWEL_READABILITY_API_KEY")
            or os.environ.get("DANKJEWEL_JUDGE_API_KEY") or "")


# Captured at import time: the autouse env-cleaning fixture deletes the
# DANKJEWEL_* variables before the live test body runs, so the key must
# be read before any fixture touches the environment.
LIVE_READABILITY_KEY = _live_readability_key()
live_readability_ready = (_live_readability_reachable()
                          and bool(LIVE_READABILITY_KEY))


@pytest.mark.skipif(not live_readability_ready, reason=(
    "live 1.5B at 127.0.0.1:18093 unreachable or no "
    "DANKJEWEL_READABILITY_API_KEY/DANKJEWEL_JUDGE_API_KEY"))
def test_live_readability_smoke():
    """Live smoke: the 1.5B discriminates easy vs hard text and the
    dual-output dimension records both tracks.

    Uses fresh content, not the few-shot exemplars: at temperature 0 a
    user message that repeats an exemplar verbatim echoes that
    exemplar's score (same measured caveat as [JUDGE]).
    """
    client = LLMJudgeClient(api_key=LIVE_READABILITY_KEY)
    try:
        easy = client.readability(
            "Wash your hands before you eat. Cover your mouth when you cough.")
        hard = client.readability(
            "The hegemonic instrumentalization of epistemological paradigms "
            "obfuscates pedagogical praxis, thereby vitiating discursive "
            "legitimation amongst non-specialist interlocutors.")
        for verdict in (easy, hard):
            assert 0.0 <= verdict["score"] <= 1.0
            assert verdict["level"] and verdict["rationale"]
        assert easy["score"] > hard["score"], (
            f"expected easy > hard, got {easy['score']} vs {hard['score']}")

        score = LLMFluidityDimension(client=client).evaluate(
            "Wash your hands before you eat. Cover your mouth when you cough.",
            lang="en")
    finally:
        client.close()
    print(f"\nlive easy verdict: {easy}")
    print(f"live hard verdict: {hard}")
    meta = score.metadata
    print("live dual-output metadata: "
          f"{ {k: meta.get(k) for k in ('baseline_value', 'llm_value', 'llm_level', 'judge_status', 'judge_model')} }")
    assert meta['judge_status'] == 'scored'
    assert meta['llm_value'] is not None and 0.0 <= meta['llm_value'] <= 1.0
    assert meta['baseline_value'] == score.value
    assert meta['judge_model'] == READABILITY_DEFAULT_MODEL
