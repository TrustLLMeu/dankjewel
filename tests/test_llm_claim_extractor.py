"""Tests for the LLM atomic-claim extraction track (Prong 3 dual output).

Unit tests use httpx.MockTransport, injected stub clients, or an
unreachable local port — no network and no running claims model needed.
One live smoke test at the bottom is skipped unless the claims model at
127.0.0.1:18093 is reachable AND a claims API key is available via
DANKJEWEL_CLAIMS_API_KEY (or the DANKJEWEL_JUDGE_API_KEY fallback; the
key is read from the environment, never hardcoded).
"""

import json
import os

import httpx
import pytest

from src.extraction.claim_extractor import Claim, ClaimExtractor, ExtractionResult
from src.extraction.llm_claim_extractor import (
    LLMClaimExtractor, _merge_claims, _split_paragraphs
)
from src.llm_judge_client import (
    CLAIMS_DEFAULT_BASE_URL,
    CLAIMS_DEFAULT_MODEL,
    ClaimsParseError,
    JudgeUnavailableError,
    LLMJudgeClient,
)
from src.prongs.prong3_extraction import Prong3Extraction
from src.pipeline import EvaluationPipeline

# The exact [CLAIMS] prompt verified live against the 1.5B model on
# 2026-11-14. This test pins it: the prompt must not be rewritten
# without re-verifying extraction quality.
VERIFIED_CLAIMS_PROMPT = (
    "[CLAIMS] Extract atomic, self-contained factual claims from the text. "
    "Rules: (1) resolve pronouns to explicit names; if a referent cannot be "
    "resolved, omit the claim. (2) Each claim is one verifiable statement "
    "with an explicit subject and no pronouns. (3) Skip opinions, "
    "speculation, and pure filler. (4) The output must be valid JSON: a "
    "JSON array of strings, elements separated by commas. Reply with ONLY "
    "a JSON array of strings. Example: Text: France won the 2018 World "
    "Cup. They beat the hosts in the final. -> "
    '["France won the 2018 FIFA World Cup.", "France beat the host nation '
    'in the 2018 World Cup final."] Text with no verifiable facts -> []'
)

PARAGRAPH = ("Oslo is the capital of Norway. It is located at the head "
             "of the Oslofjord.")


def chat_completion_response(content):
    """OpenAI chat-completion response body with the given content."""
    return {"choices": [{"message": {"role": "assistant", "content": content}}]}


class StubClaimsClient:
    """Test double matching the client surface claims() calls."""

    def __init__(self, claims=None, exc=None):
        self.claims_result = claims or []
        self.exc = exc
        self.paragraphs = []

    def claims(self, text):
        self.paragraphs.append(text)
        if self.exc is not None:
            raise self.exc
        return list(self.claims_result)


class StubLLMExtractor:
    """Test double matching the LLMClaimExtractor.extract() surface."""

    def __init__(self, result):
        self.result = result
        self.calls = 0

    def extract(self, text):
        self.calls += 1
        return self.result


def make_result(claims, num_sentences=1):
    return ExtractionResult(
        claims=claims, extraction_time_ms=1.0, num_sentences=num_sentences)


@pytest.fixture(scope="module")
def spacy_extractor():
    return ClaimExtractor()


# ── [CLAIMS] client (MockTransport — no network) ────────────────────────────

class TestClaimsClient:

    def test_request_shape_and_parse(self, monkeypatch):
        # Pin the claims env so ambient DANKJEWEL_* keys don't leak in.
        for var in ("DANKJEWEL_CLAIMS_API_KEY", "DANKJEWEL_CLAIMS_BASE_URL",
                    "DANKJEWEL_CLAIMS_MODEL", "DANKJEWEL_JUDGE_API_KEY"):
            monkeypatch.delenv(var, raising=False)
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["request"] = request
            return httpx.Response(200, json=chat_completion_response(
                '["Oslo is the capital of Norway."]'))

        client = LLMJudgeClient(api_key="k-claims", transport=httpx.MockTransport(handler))
        claims = client.claims(PARAGRAPH)
        assert claims == ["Oslo is the capital of Norway."]

        req = seen["request"]
        assert str(req.url) == f"{CLAIMS_DEFAULT_BASE_URL}/chat/completions"
        assert req.headers["Authorization"] == "Bearer k-claims"
        body = json.loads(req.content)
        assert body["model"] == CLAIMS_DEFAULT_MODEL
        assert body["messages"][0]["content"] == VERIFIED_CLAIMS_PROMPT
        assert body["messages"][0]["content"].startswith("[CLAIMS] ")
        assert body["messages"][1]["content"] == f"Text: {PARAGRAPH}"
        assert body["temperature"] == 0.0
        assert body["max_tokens"] == 300
        client.close()

    def test_env_configuration_and_key_fallback(self, monkeypatch):
        monkeypatch.delenv("DANKJEWEL_CLAIMS_API_KEY", raising=False)
        monkeypatch.setenv("DANKJEWEL_CLAIMS_BASE_URL", "http://claims.example:9/v1/")
        monkeypatch.setenv("DANKJEWEL_CLAIMS_MODEL", "Qwen/Qwen2.5-1.5B-Instruct")
        monkeypatch.setenv("DANKJEWEL_CLAIMS_TIMEOUT_S", "12.5")
        monkeypatch.setenv("DANKJEWEL_JUDGE_API_KEY", "judge-key")
        client = LLMJudgeClient()
        assert client.claims_base_url == "http://claims.example:9/v1"
        assert client.claims_model_name == "Qwen/Qwen2.5-1.5B-Instruct"
        assert client.claims_timeout == 12.5
        assert client.claims_api_key == "judge-key"  # falls back to judge key
        client.close()

    def test_claims_key_overrides_judge_key_fallback(self, monkeypatch):
        monkeypatch.setenv("DANKJEWEL_JUDGE_API_KEY", "judge-key")
        monkeypatch.setenv("DANKJEWEL_CLAIMS_API_KEY", "claims-key")
        client = LLMJudgeClient()
        assert client.claims_api_key == "claims-key"
        client.close()

    def test_defaults_when_env_unset(self, monkeypatch):
        for var in ("DANKJEWEL_CLAIMS_BASE_URL", "DANKJEWEL_CLAIMS_MODEL",
                    "DANKJEWEL_CLAIMS_API_KEY", "DANKJEWEL_CLAIMS_TIMEOUT_S",
                    "DANKJEWEL_JUDGE_API_KEY"):
            monkeypatch.delenv(var, raising=False)
        client = LLMJudgeClient()
        assert client.claims_base_url == CLAIMS_DEFAULT_BASE_URL
        assert client.claims_model_name == CLAIMS_DEFAULT_MODEL
        assert client.claims_api_key is None
        assert client.claims_timeout == 30.0
        client.close()

    def test_repairs_missing_comma_between_elements(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=chat_completion_response(
                '["Oslo is the capital of Norway." "Oslo is located at the '
                'head of the Oslofjord."]'))

        client = LLMJudgeClient(api_key=None, transport=httpx.MockTransport(handler))
        claims = client.claims(PARAGRAPH)
        assert claims == ["Oslo is the capital of Norway.",
                          "Oslo is located at the head of the Oslofjord."]
        client.close()

    def test_tolerates_markdown_fenced_array(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=chat_completion_response(
                '```json\n["France won the 2018 FIFA World Cup."]\n```'))

        client = LLMJudgeClient(api_key=None, transport=httpx.MockTransport(handler))
        assert client.claims("France won the 2018 World Cup.") == [
            "France won the 2018 FIFA World Cup."]
        client.close()

    def test_tolerates_prose_wrapped_array(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=chat_completion_response(
                'Here are the claims: ["Oslo is the capital of Norway." '
                '"Oslo is located at the head of the Oslofjord."]. '
                'Hope this helps.'))

        client = LLMJudgeClient(api_key=None, transport=httpx.MockTransport(handler))
        claims = client.claims(PARAGRAPH)
        assert claims == ["Oslo is the capital of Norway.",
                          "Oslo is located at the head of the Oslofjord."]
        client.close()

    def test_empty_array_is_valid(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=chat_completion_response('[]'))

        client = LLMJudgeClient(api_key=None, transport=httpx.MockTransport(handler))
        assert client.claims("Hello there.") == []
        client.close()

    def test_genuinely_broken_reply_raises_claims_parse_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=chat_completion_response(
                "I cannot extract claims from that text."))

        client = LLMJudgeClient(api_key=None, transport=httpx.MockTransport(handler))
        with pytest.raises(ClaimsParseError):
            client.claims(PARAGRAPH)
        client.close()

    def test_non_string_elements_raise_parse_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=chat_completion_response(
                '["Oslo is the capital of Norway.", 1]'))

        client = LLMJudgeClient(api_key=None, transport=httpx.MockTransport(handler))
        with pytest.raises(ClaimsParseError):
            client.claims(PARAGRAPH)
        client.close()

    def test_non_array_json_raises_parse_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=chat_completion_response(
                '{"claims": ["a"]}'))

        client = LLMJudgeClient(api_key=None, transport=httpx.MockTransport(handler))
        with pytest.raises(ClaimsParseError):
            client.claims(PARAGRAPH)
        client.close()

    def test_transport_error_raises_unavailable(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused", request=request)

        client = LLMJudgeClient(api_key=None, transport=httpx.MockTransport(handler))
        with pytest.raises(JudgeUnavailableError):
            client.claims(PARAGRAPH)
        client.close()

    def test_http_error_status_raises_unavailable(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"error": "boom"})

        client = LLMJudgeClient(api_key=None, transport=httpx.MockTransport(handler))
        with pytest.raises(JudgeUnavailableError, match="500"):
            client.claims(PARAGRAPH)
        client.close()

    def test_malformed_200_body_raises_parse_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"unexpected": "shape"})

        client = LLMJudgeClient(api_key=None, transport=httpx.MockTransport(handler))
        with pytest.raises(ClaimsParseError):
            client.claims(PARAGRAPH)
        client.close()


# ── Mapping / dedup / failure isolation (stub client — no network) ──────────

class TestLLMClaimExtractorMapping:

    def test_llm_track_marks_source_and_atomic_text(self, spacy_extractor):
        stub = StubClaimsClient(claims=["Oslo is the capital of Norway."])
        extractor = LLMClaimExtractor(client=stub, spacy_extractor=spacy_extractor,
                                      include_spacy=False)
        result = extractor.extract("Oslo is the capital of Norway.")
        assert stub.paragraphs == ["Oslo is the capital of Norway."]
        assert len(result.claims) == 1
        claim = result.claims[0]
        assert claim.source == "llm"
        assert claim.atomic_text == "Oslo is the capital of Norway."
        assert claim.subject == "Oslo"
        assert claim.predicate == "be"
        assert "capital" in claim.object.lower()
        assert result.metadata['llm_paragraphs'] == 1
        assert result.metadata['llm_claims'] == 1
        assert result.metadata['llm_errors'] == []

    def test_dual_track_dedup_marks_both(self, spacy_extractor):
        # The LLM echoes the same fact decontextualized; spaCy found the
        # same triple on the raw text -> one claim, source "both".
        stub = StubClaimsClient(claims=["Oslo is the capital of Norway."])
        extractor = LLMClaimExtractor(client=stub, spacy_extractor=spacy_extractor,
                                      include_spacy=True)
        result = extractor.extract("Oslo is the capital of Norway.")
        assert len(result.claims) == 1  # never double-counted
        claim = result.claims[0]
        assert claim.source == "both"
        assert claim.atomic_text == "Oslo is the capital of Norway."
        assert result.metadata['llm_claims'] == 1

    def test_dual_track_keeps_disjoint_claims(self, spacy_extractor):
        stub = StubClaimsClient(claims=["Berlin is the capital of Germany."])
        extractor = LLMClaimExtractor(client=stub, spacy_extractor=spacy_extractor,
                                      include_spacy=True)
        result = extractor.extract("Oslo is the capital of Norway.")
        sources = sorted(c.source for c in result.claims)
        assert sources == ["llm", "spacy"]
        llm_claim = next(c for c in result.claims if c.source == "llm")
        assert llm_claim.atomic_text == "Berlin is the capital of Germany."
        assert llm_claim.subject == "Berlin"

    def test_merge_collapses_llm_internal_duplicates(self):
        spacy_claim = Claim(subject="Oslo", predicate="be",
                            object="the capital of Norway", source_sentence="raw")
        llm_a = Claim(subject="Oslo", predicate="be",
                      object="the capital of Norway", source_sentence="atom",
                      source="llm", atomic_text="Oslo is the capital of Norway.")
        llm_b = Claim(subject="Oslo", predicate="be",
                      object="the capital of Norway", source_sentence="atom",
                      source="llm", atomic_text="Oslo is the capital of Norway.")
        merged = _merge_claims([spacy_claim], [llm_a, llm_b])
        assert len(merged) == 1
        assert merged[0].source == "both"
        assert merged[0].atomic_text == "Oslo is the capital of Norway."

    def test_split_paragraphs_blank_lines_only(self):
        assert _split_paragraphs("") == []
        assert _split_paragraphs("   \n\n  ") == []
        assert _split_paragraphs("one.\n\ntwo.") == ["one.", "two."]
        # single newlines stay in one paragraph (pronouns resolve)
        assert _split_paragraphs("one\ntwo") == ["one\ntwo"]

    def test_one_llm_call_per_paragraph(self, spacy_extractor):
        stub = StubClaimsClient(claims=["Berlin is the capital of Germany."])
        extractor = LLMClaimExtractor(client=stub, spacy_extractor=spacy_extractor,
                                      include_spacy=False)
        extractor.extract("Oslo is the capital of Norway.\n\nOslo has a university.")
        assert stub.paragraphs == ["Oslo is the capital of Norway.",
                                   "Oslo has a university."]
        assert extractor.extract("Hi").metadata['llm_paragraphs'] == 1

    def test_empty_text_yields_no_claims(self, spacy_extractor):
        stub = StubClaimsClient()
        extractor = LLMClaimExtractor(client=stub, spacy_extractor=spacy_extractor)
        result = extractor.extract("")
        assert result.claims == []
        assert stub.paragraphs == []
        assert result.metadata['llm_paragraphs'] == 0
        assert result.metadata['llm_claims'] == 0

    def test_claim_to_dict_includes_new_fields(self, spacy_extractor):
        stub = StubClaimsClient(claims=["Oslo is the capital of Norway."])
        extractor = LLMClaimExtractor(client=stub, spacy_extractor=spacy_extractor,
                                      include_spacy=True)
        result = extractor.extract("Oslo is the capital of Norway.")
        d = result.claims[0].to_dict()
        assert d['source'] == "both"
        assert d['atomic_text'] == "Oslo is the capital of Norway."
        assert 'metadata' in result.to_dict()


class TestLLMClaimExtractorFailureIsolation:

    def test_unavailable_client_zero_llm_claims_spacy_intact(self, spacy_extractor):
        stub = StubClaimsClient(exc=JudgeUnavailableError(
            "cannot reach claims model at http://127.0.0.1:19999/v1: refused"))
        extractor = LLMClaimExtractor(client=stub, spacy_extractor=spacy_extractor,
                                      include_spacy=True)
        result = extractor.extract("Oslo is the capital of Norway.")  # must not raise
        assert result.claims  # spaCy track intact
        assert all(c.source == "spacy" for c in result.claims)
        assert result.metadata['llm_claims'] == 0
        assert result.metadata['llm_paragraphs'] == 1
        assert len(result.metadata['llm_errors']) == 1
        assert 'llm' in result.metadata['llm_errors'][0] or \
            'claims' in result.metadata['llm_errors'][0]

    def test_parse_error_is_isolated_per_paragraph(self, spacy_extractor):
        stub = StubClaimsClient(exc=ClaimsParseError("not a JSON array"))
        extractor = LLMClaimExtractor(client=stub, spacy_extractor=spacy_extractor,
                                      include_spacy=True)
        result = extractor.extract("Oslo is the capital of Norway.\n\nBerlin is cold.")
        assert result.metadata['llm_paragraphs'] == 2
        assert len(result.metadata['llm_errors']) == 2
        assert all(c.source == "spacy" for c in result.claims)

    def test_error_strings_are_short(self, spacy_extractor):
        stub = StubClaimsClient(exc=JudgeUnavailableError("x" * 500))
        extractor = LLMClaimExtractor(client=stub, spacy_extractor=spacy_extractor,
                                      include_spacy=True)
        result = extractor.extract("Oslo is the capital of Norway.")
        assert all(len(e) <= 120 for e in result.metadata['llm_errors'])

    def test_dead_claims_server_end_to_end(self, spacy_extractor, monkeypatch):
        # Nothing listens on this local port (same convention as the
        # existing unreachable-server tests).
        monkeypatch.delenv("DANKJEWEL_CLAIMS_API_KEY", raising=False)
        monkeypatch.setenv("DANKJEWEL_CLAIMS_BASE_URL", "http://127.0.0.1:19999/v1")
        monkeypatch.setenv("DANKJEWEL_CLAIMS_TIMEOUT_S", "2")
        client = LLMJudgeClient()
        extractor = LLMClaimExtractor(client=client, spacy_extractor=spacy_extractor)
        try:
            result = extractor.extract("Oslo is the capital of Norway.")
        finally:
            client.close()
        assert result.claims
        assert all(c.source == "spacy" for c in result.claims)
        assert result.metadata['llm_claims'] == 0
        assert result.metadata['llm_errors']


# ── Wiring: prong evaluator / pipeline (stubbed extractor — no network) ─────

WIRING_TEXT = "Paris is the capital of France."


def stub_llm_extractor():
    """LLMClaimExtractor double returning both tracks for WIRING_TEXT."""
    claims = [
        Claim(subject="Paris", predicate="be", object="the capital of France",
              source_sentence=WIRING_TEXT, source="spacy"),
        Claim(subject="Paris", predicate="be", object="in France",
              source_sentence=WIRING_TEXT, source="llm",
              atomic_text="Paris is located in France."),
    ]
    return StubLLMExtractor(make_result(claims))


class TestProngWiring:

    def test_llm_extract_off_uses_spacy_only(self):
        prong = Prong3Extraction()
        result = prong.evaluate(WIRING_TEXT, llm_extract=False)
        assert result.error is None
        fac = next(d for d in result.dimensions if d.name == "Factual Accuracy")
        assert fac.metadata['num_claims'] >= 1
        assert all(cd['claim']['source'] == 'spacy'
                   for cd in fac.metadata['claim_details'])

    def test_llm_extract_on_returns_both_tracks(self):
        prong = Prong3Extraction(llm_extractor=stub_llm_extractor())
        result = prong.evaluate(WIRING_TEXT, llm_extract=True)
        assert result.error is None
        fac = next(d for d in result.dimensions if d.name == "Factual Accuracy")
        details = fac.metadata['claim_details']
        sources = sorted(cd['claim']['source'] for cd in details)
        assert sources == ["llm", "spacy"]
        llm_cd = next(cd for cd in details if cd['claim']['source'] == 'llm')
        assert llm_cd['claim']['atomic_text'] == "Paris is located in France."

    def test_llm_extract_on_dead_server_spacy_only_no_error(self, monkeypatch):
        monkeypatch.setattr("src.llm_judge_client._shared_client", None)
        monkeypatch.delenv("DANKJEWEL_CLAIMS_API_KEY", raising=False)
        monkeypatch.setenv("DANKJEWEL_CLAIMS_BASE_URL", "http://127.0.0.1:19999/v1")
        monkeypatch.setenv("DANKJEWEL_CLAIMS_TIMEOUT_S", "1.5")
        prong = Prong3Extraction()
        result = prong.evaluate(WIRING_TEXT, llm_extract=True)
        assert result.error is None  # LLM failure never raises into Prong 3
        fac = next(d for d in result.dimensions if d.name == "Factual Accuracy")
        assert fac.metadata['num_claims'] >= 1
        assert all(cd['claim']['source'] == 'spacy'
                   for cd in fac.metadata['claim_details'])

    def test_pipeline_flag_reaches_prong3(self):
        stub = stub_llm_extractor()
        pipeline = EvaluationPipeline(enable_prongs=[3])
        pipeline.prongs['Prong 3'] = Prong3Extraction(llm_extractor=stub)

        off = pipeline.evaluate(text=WIRING_TEXT)
        assert stub.calls == 0

        on = pipeline.evaluate(text=WIRING_TEXT, llm_extract=True)
        assert stub.calls == 1
        fac = next(d for d in on['prong_results'][0]['dimensions']
                   if d['name'] == "Factual Accuracy")
        sources = sorted(cd['claim']['source'] for cd in fac['metadata']['claim_details'])
        assert sources == ["llm", "spacy"]

    def test_pipeline_flag_off_identical_to_default(self):
        pipeline = EvaluationPipeline(enable_prongs=[3])
        a = pipeline.evaluate(text=WIRING_TEXT)
        b = pipeline.evaluate(text=WIRING_TEXT, llm_extract=False)

        def claim_ids(result):
            fac = next(d for d in result['prong_results'][0]['dimensions']
                       if d['name'] == "Factual Accuracy")
            # Compare claim identity, not per-run verification timing.
            return [(cd['claim']['subject'], cd['claim']['predicate'],
                     cd['claim']['object'], cd['claim']['source'],
                     cd['claim']['atomic_text'])
                    for cd in fac['metadata']['claim_details']]

        assert claim_ids(a) == claim_ids(b)
        assert all(cid[3] == 'spacy' for cid in claim_ids(a))


# ── API: /evaluate llm_extract flag (TestClient, stubbed extractor) ────────

class TestEvaluateLLMExtractAPI:

    @pytest.fixture
    def client(self, monkeypatch):
        """TestClient whose /evaluate uses a pipeline with a stubbed LLM extractor."""
        from fastapi.testclient import TestClient
        from src.api import app
        stub = stub_llm_extractor()
        pipeline = EvaluationPipeline(enable_prongs=[3])
        pipeline.prongs['Prong 3'] = Prong3Extraction(llm_extractor=stub)
        monkeypatch.setattr("src.api.evaluator", pipeline)
        return TestClient(app)

    @staticmethod
    def factual_meta(data):
        prong3 = next(p for p in data['prong_results']
                      if p['prong_name'].startswith('Extraction'))
        return next(d for d in prong3['dimensions']
                    if d['name'] == 'Factual Accuracy')['metadata']

    def test_evaluate_default_unchanged(self, client):
        resp = client.post("/evaluate", json={"text": WIRING_TEXT})
        assert resp.status_code == 200
        meta = self.factual_meta(resp.json())
        # Flag absent -> exactly the previous behavior: spaCy-only claims.
        assert all(cd['claim']['source'] == 'spacy'
                   for cd in meta['claim_details'])
        assert 'llm' not in [cd['claim']['source'] for cd in meta['claim_details']]

    def test_evaluate_llm_extract_false_explicit(self, client):
        resp = client.post("/evaluate", json={
            "text": WIRING_TEXT, "llm_extract": False})
        assert resp.status_code == 200
        meta = self.factual_meta(resp.json())
        assert all(cd['claim']['source'] == 'spacy'
                   for cd in meta['claim_details'])

    def test_evaluate_llm_extract_true_both_tracks(self, client):
        baseline = client.post("/evaluate", json={"text": WIRING_TEXT}).json()
        resp = client.post("/evaluate", json={
            "text": WIRING_TEXT, "llm_extract": True})
        assert resp.status_code == 200
        meta = self.factual_meta(resp.json())
        sources = sorted(cd['claim']['source'] for cd in meta['claim_details'])
        assert sources == ["llm", "spacy"]
        llm_cd = next(cd for cd in meta['claim_details']
                      if cd['claim']['source'] == 'llm')
        assert llm_cd['claim']['atomic_text'] == "Paris is located in France."
        # Default-off request stayed spaCy-only in the same session.
        base_meta = self.factual_meta(baseline)
        assert all(cd['claim']['source'] == 'spacy'
                   for cd in base_meta['claim_details'])


# ── Live smoke (skipped unless the claims model is up + key is set) ─────────

LIVE_CLAIMS_HOST = "http://127.0.0.1:18093"


def _live_claims_reachable() -> bool:
    try:
        httpx.get(f"{LIVE_CLAIMS_HOST}/v1/models", timeout=2.0)
        return True
    except httpx.HTTPError:
        return False


live_claims_ready = _live_claims_reachable() and bool(
    os.environ.get("DANKJEWEL_CLAIMS_API_KEY")
    or os.environ.get("DANKJEWEL_JUDGE_API_KEY"))


@pytest.mark.skipif(not live_claims_ready, reason=(
    "live claims model at 127.0.0.1:18093 unreachable or no claims API key set "
    "(DANKJEWEL_CLAIMS_API_KEY / DANKJEWEL_JUDGE_API_KEY)"))
def test_live_llm_claim_extraction_smoke():
    """Live smoke: a paragraph with a pronoun yields decontextualized llm claims.

    Verified 1.5B behavior (2026-11-14): "Oslo is the capital of Norway.
    It is located at the head of the Oslofjord." -> two atomic claims with
    "It" resolved to "Oslo". Uses the full dual-track extractor so the
    spaCy track and merge/dedup run exactly as in production.
    """
    extractor = LLMClaimExtractor()
    result = extractor.extract(PARAGRAPH)
    meta = result.metadata
    print(f"\nlive extraction metadata: {meta}")
    assert meta['llm_paragraphs'] == 1
    assert meta['llm_errors'] == []
    llm_claims = [c for c in result.claims if c.source in ("llm", "both")]
    assert llm_claims, "expected at least one llm-track claim"
    assert meta['llm_claims'] == len(llm_claims)
    # Decontextualized: subject is Oslo, not the pronoun; the atomic text
    # names the referent and contains no unresolved pronoun.
    assert any(c.subject.lower() == "oslo" for c in llm_claims)
    assert all("oslo" in (c.atomic_text or "").lower() for c in llm_claims)
