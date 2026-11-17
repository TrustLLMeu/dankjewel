"""Tests for the Prong 3 five-way relation track (slice 6b).

Covers:
  - the MiniCheck verifier path in FactualAccuracy (0.8 / 0.2
    thresholds, partial band, doc formatting, atomic_text preference,
    negation inversion, verifier-unavailable fallback)
  - the always-on rule-based CONFLATED label in verify_triple
  - flags-off parity: llm_verify default == explicit False, no
    verifier model call, binary math unchanged
  - the /evaluate llm_verify API flag with a stubbed verifier
  - the expanded seed DB (new entities, counts, no duplicate qids)
  - the qualifier gate in OfflineWikidata (slice 6c): mutated claims
    carrying an embedded role / ordinal-series / temporal qualifier
    never CONFIRM via a weak match — they abstain (UNKNOWN), or DENY
    when the seed contradicts the qualifier (regression pins)

No network, no model download: the verifier is always a stub here.
"""

import json
import sqlite3

import pytest

from src.dimensions.prong3_dimensions import (
    FactualAccuracy, VERIFIER_CONFIRM_THRESHOLD, VERIFIER_DENY_THRESHOLD,
)
from src.extraction.claim_extractor import Claim
from src.resources.nli_verifier import NliVerifier, VerifierUnavailableError
from src.resources.wikidata_offline import (
    OfflineWikidata, VerificationResult, PROPERTY_TO_PHRASE,
)
from src.prongs.prong3_extraction import Prong3Extraction
from src.pipeline import EvaluationPipeline


# ── Test doubles ────────────────────────────────────────────────────────────

class StubVerifier:
    """NliVerifier double with a canned score and a call log."""

    def __init__(self, score=0.5):
        self.score_value = score
        self.calls = []

    def score(self, claim: str, context: str) -> float:
        self.calls.append((claim, context))
        return self.score_value


class UnavailableVerifier:
    """Always raises, like a MiniCheck model that failed to load."""

    def score(self, claim: str, context: str) -> float:
        raise VerifierUnavailableError("model load failed")


# The KB leaves this triple UNKNOWN but the subject resolves with
# facts — the canonical verifier-path test claim.
UNKNOWN_CLAIM = Claim(
    subject="Trondheim", predicate="be", object="famous for its wharves",
    source_sentence="Trondheim is famous for its wharves.",
)
CONFIRMED_CLAIM = Claim(
    subject="Paris", predicate="be", object="the capital of France",
    source_sentence="Paris is the capital of France.",
)
CONFLATED_CLAIM = Claim(
    subject="Trondheim", predicate="be", object="the capital of Hordaland",
    source_sentence="Trondheim is the capital of Hordaland.",
)


# ── Five-way verifier thresholds ─────────────────────────────────────────────

class TestVerifierThresholds:

    @pytest.fixture
    def wikidata(self):
        return OfflineWikidata()

    @pytest.fixture(autouse=True)
    def _threshold_tests_ignore_coverage(self, monkeypatch):
        """These tests exercise the probability mapping; the relevance
        gate has its own tests (TestVerifierCoverageGate)."""
        import src.dimensions.prong3_dimensions as p3
        monkeypatch.setattr(p3, "VERIFIER_MIN_KB_COVERAGE", 0.0)

    def test_threshold_constants(self):
        """The five-way thresholds are 0.8 (confirm) and 0.2 (deny)."""
        assert VERIFIER_CONFIRM_THRESHOLD == 0.8
        assert VERIFIER_DENY_THRESHOLD == 0.2

    def test_high_score_confirmed(self, wikidata):
        """p >= 0.8 -> relation confirmed, score recorded in metadata."""
        dim = FactualAccuracy(wikidata=wikidata, verifier=StubVerifier(0.9))
        score = dim.evaluate("", claims=[UNKNOWN_CLAIM], llm_verify=True)
        detail = score.metadata['claim_details'][0]
        assert detail['relation'] == 'confirmed'
        assert detail['verifier_score'] == pytest.approx(0.9, abs=1e-4)
        assert score.metadata['relation_counts']['confirmed'] == 1

    def test_confirm_boundary_is_inclusive(self, wikidata):
        """p == 0.8 (exactly) confirms; p == 0.2 (exactly) denies."""
        dim = FactualAccuracy(wikidata=wikidata, verifier=StubVerifier(0.8))
        score = dim.evaluate("", claims=[UNKNOWN_CLAIM], llm_verify=True)
        assert score.metadata['claim_details'][0]['relation'] == 'confirmed'

        dim = FactualAccuracy(wikidata=wikidata, verifier=StubVerifier(0.2))
        score = dim.evaluate("", claims=[UNKNOWN_CLAIM], llm_verify=True)
        assert score.metadata['claim_details'][0]['relation'] == 'denied'

    def test_low_score_denied(self, wikidata):
        """p <= 0.2 -> relation denied."""
        dim = FactualAccuracy(wikidata=wikidata, verifier=StubVerifier(0.05))
        score = dim.evaluate("", claims=[UNKNOWN_CLAIM], llm_verify=True)
        assert score.metadata['claim_details'][0]['relation'] == 'denied'
        assert score.metadata['relation_counts']['denied'] == 1

    def test_partial_band(self, wikidata):
        """0.2 < p < 0.8 -> relation partially_supported."""
        for p in (0.21, 0.5, 0.79):
            dim = FactualAccuracy(wikidata=wikidata, verifier=StubVerifier(p))
            score = dim.evaluate("", claims=[UNKNOWN_CLAIM], llm_verify=True)
            assert score.metadata['claim_details'][0]['relation'] == \
                'partially_supported', f"p={p}"
            assert score.metadata['relation_counts']['partially_supported'] == 1

    def test_binary_math_unchanged_by_verifier_labels(self, wikidata):
        """Verifier relations never enter value/raw_value (dual output).

        A KB-unknown claim scored 'confirmed' by the verifier keeps the
        binary status unknown and the 0.5 placeholder — the binary track
        stays comparable with the flag off.
        """
        dim = FactualAccuracy(wikidata=wikidata, verifier=StubVerifier(0.9))
        score = dim.evaluate("", claims=[UNKNOWN_CLAIM], llm_verify=True)
        assert score.value == 0.5
        assert score.status == 'unknown'
        assert score.raw_value == {'confirmed': 0, 'denied': 0, 'unknown': 1}

    def test_verifier_runs_only_on_unknown_claims(self, wikidata):
        """Exact-match CONFIRMED/DENIED triples never reach the verifier."""
        stub = StubVerifier(0.9)
        dim = FactualAccuracy(wikidata=wikidata, verifier=stub)
        claims = [CONFIRMED_CLAIM, UNKNOWN_CLAIM]
        dim.evaluate("", claims=claims, llm_verify=True)
        # Only the UNKNOWN claim was scored against the KB facts.
        assert len(stub.calls) == 1
        assert stub.calls[0][0] == \
            "Trondheim be famous for its wharves"

    def test_atomic_text_preferred_over_constructed_triple(self, wikidata):
        """LLM claims score their decontextualized atomic_text, not the triple."""
        stub = StubVerifier(0.5)
        dim = FactualAccuracy(wikidata=wikidata, verifier=stub)
        claim = Claim(
            subject="Trondheim", predicate="be", object="famous for its wharves",
            source_sentence="It is famous for its wharves.",
            atomic_text="Trondheim is famous for its wharves.",
        )
        dim.evaluate("", claims=[claim], llm_verify=True)
        assert stub.calls[0][0] == "Trondheim is famous for its wharves."

    def test_doc_is_the_subjects_formatted_kb_facts(self, wikidata):
        """The grounding document is format_entity_facts(subject_qid)."""
        stub = StubVerifier(0.5)
        dim = FactualAccuracy(wikidata=wikidata, verifier=stub)
        dim.evaluate("", claims=[UNKNOWN_CLAIM], llm_verify=True)
        doc = stub.calls[0][1]
        assert doc == wikidata.format_entity_facts("Q25804")
        # One "subject <predicate phrase> <value>." line per claim row.
        rows = wikidata.get_claims("Q25804")
        assert len(doc.splitlines()) == len(rows)
        first = rows[0]
        assert doc.splitlines()[0] == (
            f"Trondheim {PROPERTY_TO_PHRASE.get(first['property'], first['property'])} "
            f"{first['value']}.")

    def test_no_facts_or_unresolved_subject_stays_unknown(self, wikidata):
        """Unresolved subject / no KB facts -> relation unknown, no call."""
        stub = StubVerifier(0.9)
        dim = FactualAccuracy(wikidata=wikidata, verifier=stub)
        claims = [
            Claim(subject="Xyzzy Nonexistent", predicate="be", object="a thing",
                  source_sentence="Xyzzy Nonexistent is a thing."),
        ]
        score = dim.evaluate("", claims=claims, llm_verify=True)
        assert stub.calls == []  # nothing to score against
        assert score.metadata['claim_details'][0]['relation'] == 'unknown'
        assert score.metadata['relation_counts']['unknown'] == 1

    def test_negated_constructed_triple_inverts_verifier_verdict(self, wikidata):
        """Negated spaCy triples invert the verifier verdict (no negation
        in the constructed text); atomic_text carries its own."""
        dim = FactualAccuracy(wikidata=wikidata, verifier=StubVerifier(0.9))
        negated = Claim(
            subject="Trondheim", predicate="be", object="famous for its wharves",
            source_sentence="Trondheim is not famous for its wharves.",
            negated=True,
        )
        score = dim.evaluate("", claims=[negated], llm_verify=True)
        # unnegated triple supported (0.9) -> negated claim denied
        assert score.metadata['claim_details'][0]['relation'] == 'denied'

        dim = FactualAccuracy(wikidata=wikidata, verifier=StubVerifier(0.1))
        negated = Claim(
            subject="Trondheim", predicate="be", object="famous for its wharves",
            source_sentence="Trondheim is not famous for its wharves.",
            negated=True, atomic_text="Trondheim is not famous for its wharves.",
        )
        score = dim.evaluate("", claims=[negated], llm_verify=True)
        # atomic_text is self-contained: p=0.1 denied, no double inversion
        assert score.metadata['claim_details'][0]['relation'] == 'denied'

    def test_verifier_unavailable_keeps_unknown(self, wikidata):
        """VerifierUnavailableError -> relation unknown, error in metadata,
        never a fabricated score."""
        dim = FactualAccuracy(wikidata=wikidata, verifier=UnavailableVerifier())
        score = dim.evaluate("", claims=[UNKNOWN_CLAIM], llm_verify=True)
        detail = score.metadata['claim_details'][0]
        assert detail['relation'] == 'unknown'
        assert 'verifier_score' not in detail
        assert len(score.metadata['verifier_errors']) == 1
        assert score.raw_value['unknown'] == 1  # binary math untouched

    def test_relation_counts_cover_every_claim(self, wikidata):
        """relation_counts sums to the claim count (skipped no-object
        claims count as unknown, like raw_value)."""
        dim = FactualAccuracy(wikidata=wikidata, verifier=StubVerifier(0.5))
        claims = [
            CONFIRMED_CLAIM,
            CONFLATED_CLAIM,
            UNKNOWN_CLAIM,
            Claim(subject="Paris", predicate="be", object="",
                  source_sentence="Paris is."),  # skipped: no object
        ]
        score = dim.evaluate("", claims=claims, llm_verify=True)
        counts = score.metadata['relation_counts']
        assert counts == {'confirmed': 1, 'denied': 0,
                          'partially_supported': 1, 'conflated': 1,
                          'unknown': 1}
        assert sum(counts.values()) == len(claims)
        # Binary math: only the triple-match CONFIRMED counts as verifiable.
        assert score.raw_value == {'confirmed': 1, 'denied': 0, 'unknown': 3}
        assert score.metadata['verifiable'] == 1


# ── Verifier relevance gate ─────────────────────────────────────────────────

class TestVerifierCoverageGate:
    """MiniCheck only scores claims the KB facts can actually ground.

    Its score is a *support* probability for a specific document; a
    document that names the subject but not the claimed property
    (population, a constitution, a term's origin) cannot confirm or
    deny the claim. Low lexical coverage therefore stays UNKNOWN with
    an explicit reason instead of becoming a fabricated denial.
    """

    def test_low_coverage_claim_stays_unknown_not_denied(self):
        wikidata = OfflineWikidata()
        stub = StubVerifier(0.01)
        dim = FactualAccuracy(wikidata=wikidata, verifier=stub)
        score = dim.evaluate("", claims=[UNKNOWN_CLAIM], llm_verify=True)
        detail = score.metadata['claim_details'][0]
        assert detail['relation'] == 'unknown'
        assert detail['reason'] == 'insufficient_kb_coverage'
        assert 'verifier_score' not in detail
        assert stub.calls == []  # the model is never consulted

    def test_kb_coverage_counts_content_words(self):
        from src.dimensions.prong3_dimensions import kb_coverage
        doc = "Oslo instance of city. Oslo capital of Norway."
        assert kb_coverage("Oslo is a city.", doc) == 1.0
        assert kb_coverage("Oslo has 700,000 inhabitants.", doc) < 0.75


# ── Rule-based conflation (always-on, no model) ──────────────────────────────

class TestConflationRule:

    @pytest.fixture
    def wikidata(self):
        return OfflineWikidata()

    def test_conflated_capital_claim(self, wikidata):
        """'Trondheim is the capital of Hordaland' -> CONFLATED, not UNKNOWN.

        Hordaland is the capital-of (P1376) value of a DIFFERENT subject
        (Bergen) while Trondheim's own capital-of value differs — the
        claim places the subject in another entity's known slot.
        """
        detail = wikidata.verify_triple(
            "Trondheim", "be", "the capital of Hordaland")
        assert detail.result == VerificationResult.CONFLATED
        assert detail.property_id == 'P1376'
        # The recorded wikidata_value is the subject's OWN value.
        own_values = [c['value'] for c in wikidata.get_claims("Q25804", "P1376")]
        assert detail.wikidata_value in own_values

    def test_conflated_location_claim(self, wikidata):
        """'Oslo is the capital of Vestland' -> CONFLATED (Vestland is
        Bergen's capital-of value; Oslo's own is Norway)."""
        detail = wikidata.verify_triple("Oslo", "be", "the capital of Vestland")
        assert detail.result == VerificationResult.CONFLATED

    def test_own_value_still_confirmed(self, wikidata):
        """'Bergen is the capital of Hordaland' stays CONFIRMED (own value)."""
        detail = wikidata.verify_triple("Bergen", "be", "the capital of Hordaland")
        assert detail.result == VerificationResult.CONFIRMED

    def test_unresolvable_object_stays_unknown(self, wikidata):
        """An object that resolves to no KB entity cannot be conflated."""
        detail = wikidata.verify_triple("Oslo", "be", "the capital of Narnia")
        assert detail.result == VerificationResult.UNKNOWN

    def test_confirmed_denied_unchanged_by_rule(self, wikidata):
        """Exact-match results are untouched, including the reverse-path
        denial of a claim about another entity's capital slot."""
        assert wikidata.verify_triple(
            "Oslo", "be", "the capital of Norway").result \
            == VerificationResult.CONFIRMED
        assert wikidata.verify_triple(
            "Oslo", "be", "the capital of Sweden").result \
            == VerificationResult.DENIED

    def test_conflated_never_inverts_for_negation(self, wikidata):
        """CONFLATED is a descriptive relation: negation leaves it as-is."""
        from src.dimensions.prong3_dimensions import _invert_result
        assert _invert_result(VerificationResult.CONFLATED) \
            == VerificationResult.CONFLATED
        assert _invert_result(VerificationResult.PARTIALLY_SUPPORTED) \
            == VerificationResult.PARTIALLY_SUPPORTED
        assert _invert_result(VerificationResult.CONFIRMED) \
            == VerificationResult.DENIED

    def test_conflated_counts_only_in_five_way(self, wikidata):
        """A conflated claim enriches relation_counts but keeps the binary
        unknown bucket (value math unchanged)."""
        stub = StubVerifier(0.5)
        dim = FactualAccuracy(wikidata=wikidata, verifier=stub)
        score = dim.evaluate("", claims=[CONFLATED_CLAIM], llm_verify=True)
        assert stub.calls == []  # CONFLATED never reaches the verifier
        assert score.metadata['relation_counts']['conflated'] == 1
        assert score.raw_value == {'confirmed': 0, 'denied': 0, 'unknown': 1}
        assert score.status == 'unknown'

    def test_conflated_always_on_without_flag(self, wikidata):
        """The rule-based label fires with llm_verify=False too (no model)."""
        stub = StubVerifier(0.5)
        dim = FactualAccuracy(wikidata=wikidata, verifier=stub)
        score = dim.evaluate("", claims=[CONFLATED_CLAIM], llm_verify=False)
        assert score.metadata['relation_counts']['conflated'] == 1
        assert stub.calls == []
        assert 'verifier_errors' not in score.metadata


# ── Flags-off parity ────────────────────────────────────────────────────────

PARITY_TEXT = ("Paris is the capital of France. "
               "Trondheim is the capital of Hordaland.")


def _strip_timing(dim_score_dict):
    """Remove per-run timing fields so two runs are comparable."""
    import copy
    d = copy.deepcopy(dim_score_dict)
    meta = d['metadata']
    meta.pop('verification_time_ms', None)
    meta.pop('evaluation_time_ms', None)
    for cd in meta.get('claim_details', []):
        cd['verification'].pop('verification_time_ms', None)
    return d


class TestFlagsOffParity:

    @pytest.fixture(autouse=True)
    def _ignore_coverage(self, monkeypatch):
        import src.dimensions.prong3_dimensions as p3
        monkeypatch.setattr(p3, "VERIFIER_MIN_KB_COVERAGE", 0.0)

    def test_flag_off_never_loads_or_calls_verifier(self):
        """Default and explicit-False never touch the verifier."""
        stub = StubVerifier(0.9)
        prong = Prong3Extraction(verifier=stub)
        prong.evaluate(PARITY_TEXT)             # flag absent
        prong.evaluate(PARITY_TEXT, llm_verify=False)
        assert stub.calls == []

    def test_default_equals_explicit_false(self):
        """llm_verify absent == llm_verify=False, byte-identical output."""
        prong = Prong3Extraction(verifier=StubVerifier(0.9))
        a = prong.evaluate(PARITY_TEXT).to_dict()
        b = prong.evaluate(PARITY_TEXT, llm_verify=False).to_dict()
        a['dimensions'] = [_strip_timing(d) for d in a['dimensions']]
        b['dimensions'] = [_strip_timing(d) for d in b['dimensions']]
        a.pop('processing_time')
        b.pop('processing_time')
        for result in (a, b):
            result.get('metadata', {}).pop('extraction_time_ms', None)
            result.get('metadata', {}).pop('verification_time_ms', None)
        assert a == b

    def test_flag_on_keeps_binary_math_identical(self):
        """value/raw_value/status identical with the flag on and off."""
        prong = Prong3Extraction(verifier=StubVerifier(0.9))
        off = prong.evaluate(PARITY_TEXT, llm_verify=False)
        on = prong.evaluate(PARITY_TEXT, llm_verify=True)

        def fac(result):
            return next(d for d in result.dimensions if d.name == "Factual Accuracy")

        fac_off, fac_on = fac(off), fac(on)
        assert fac_off.value == fac_on.value
        assert fac_off.raw_value == fac_on.raw_value
        assert fac_off.status == fac_on.status
        # The five-way track is where the verifier shows up.
        assert fac_on.metadata['relation_counts']['confirmed'] >= \
            fac_off.metadata['relation_counts']['confirmed']

    def test_pipeline_flag_reaches_prong3(self):
        """pipeline.evaluate(llm_verify=...) routes into Prong 3."""
        stub = StubVerifier(0.9)
        pipeline = EvaluationPipeline(enable_prongs=[3])
        pipeline.prongs['Prong 3'] = Prong3Extraction(verifier=stub)

        pipeline.evaluate(text=UNKNOWN_CLAIM.source_sentence)
        assert stub.calls == []
        pipeline.evaluate(text=UNKNOWN_CLAIM.source_sentence, llm_verify=True)
        assert len(stub.calls) >= 1


# ── API: /evaluate llm_verify flag ───────────────────────────────────────────

API_TEXT = "Trondheim is famous for its wharves."


class TestEvaluateLLMVerifyAPI:

    @pytest.fixture(autouse=True)
    def _ignore_coverage(self, monkeypatch):
        import src.dimensions.prong3_dimensions as p3
        monkeypatch.setattr(p3, "VERIFIER_MIN_KB_COVERAGE", 0.0)

    @pytest.fixture
    def client(self, monkeypatch):
        """TestClient whose /evaluate uses a stubbed verifier."""
        from fastapi.testclient import TestClient
        from src.api import app
        self.stub = StubVerifier(0.9)
        pipeline = EvaluationPipeline(enable_prongs=[3])
        pipeline.prongs['Prong 3'] = Prong3Extraction(verifier=self.stub)
        monkeypatch.setattr("src.api.evaluator", pipeline)
        return TestClient(app)

    @staticmethod
    def factual_dim(data):
        prong3 = next(p for p in data['prong_results']
                      if p['prong_name'].startswith('Extraction'))
        return next(d for d in prong3['dimensions']
                    if d['name'] == 'Factual Accuracy')

    @classmethod
    def factual_meta(cls, data):
        return cls.factual_dim(data)['metadata']

    def test_default_unchanged(self, client):
        resp = client.post("/evaluate", json={"text": API_TEXT})
        assert resp.status_code == 200
        meta = self.factual_meta(resp.json())
        assert self.stub.calls == []  # flag absent -> no verifier
        assert all(cd['relation'] == 'unknown' for cd in meta['claim_details'])
        assert meta['relation_counts']['partially_supported'] == 0

    def test_llm_verify_false_explicit(self, client):
        resp = client.post("/evaluate", json={"text": API_TEXT,
                                              "llm_verify": False})
        assert resp.status_code == 200
        assert self.stub.calls == []

    def test_llm_verify_true_relations_and_parity(self, client):
        baseline = client.post("/evaluate", json={"text": API_TEXT}).json()
        resp = client.post("/evaluate", json={"text": API_TEXT,
                                              "llm_verify": True})
        assert resp.status_code == 200
        meta = self.factual_meta(resp.json())
        assert len(self.stub.calls) >= 1
        assert all(cd['relation'] == 'confirmed'
                   for cd in meta['claim_details'] if cd['verifier_score'])
        assert meta['relation_counts']['confirmed'] >= 1
        # Binary track comparable: same value/status as the flag-off call.
        base_dim = self.factual_dim(baseline)
        assert self.factual_dim(resp.json())['value'] == base_dim['value']
        assert self.factual_dim(resp.json())['status'] == base_dim['status']
        assert meta['verifier_errors'] == []


# ── Expanded seed DB ─────────────────────────────────────────────────────────

# The committed seed DB after the slice-6b Nordic expansion and the
# civic-domain expansion (see scripts/extend_wikidata_db.py --entities;
# still a seed, not Wikidata).
EXPECTED_SEED_ENTITIES = 144
EXPECTED_SEED_CLAIMS = 788


class TestSeedDBExpansion:

    @pytest.fixture
    def db(self):
        return OfflineWikidata()

    def test_counts(self):
        """Entity/claim counts match the committed expanded seed DB."""
        conn = sqlite3.connect("data/wikidata_seed.db")
        try:
            entities = conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
            claims = conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0]
        finally:
            conn.close()
        assert entities == EXPECTED_SEED_ENTITIES
        assert claims == EXPECTED_SEED_CLAIMS

    def test_new_entities_present(self, db):
        """The hand-picked Nordic/TrustLLM entities resolve."""
        expected = {
            "Bergen": "Q26793",
            "Trondheim": "Q25804",
            "Iceland": "Q189",
            "Reykjavík": "Q1764",
            "SINTEF": "Q3041255",
            "European Union": "Q458",
        }
        for name, qid in expected.items():
            assert db.lookup_entity(name) == qid, name

    def test_ntnu_resolves_to_the_university(self, db):
        """NTNU (and its full name) resolve to the university, and the
        'NTNU' Wikipedia disambiguation namesake was not kept."""
        assert db.lookup_entity("NTNU") == "Q314536"
        assert db.lookup_entity(
            "Norwegian University of Science and Technology") == "Q314536"
        conn = sqlite3.connect("data/wikidata_seed.db")
        try:
            row = conn.execute(
                "SELECT label FROM entities WHERE qid = 'Q6955486'").fetchone()
        finally:
            conn.close()
        assert row is None  # the disambiguation page is not an entity

    def test_no_duplicate_qids(self):
        """Every qid appears once in entities and claims have no orphans."""
        conn = sqlite3.connect("data/wikidata_seed.db")
        try:
            dupes = conn.execute(
                "SELECT qid, COUNT(*) c FROM entities GROUP BY qid HAVING c > 1"
            ).fetchall()
            orphan_claims = conn.execute(
                "SELECT COUNT(*) FROM claims WHERE qid NOT IN (SELECT qid FROM entities)"
            ).fetchone()[0]
            orphan_aliases = conn.execute(
                "SELECT COUNT(*) FROM aliases WHERE qid NOT IN (SELECT qid FROM entities)"
            ).fetchone()[0]
        finally:
            conn.close()
        assert dupes == []
        assert orphan_claims == 0
        assert orphan_aliases == 0

    def test_benchmark_entities_still_resolvable(self, db):
        """Pre-existing benchmark-claim entities survived the expansion."""
        for name in ("Paris", "France", "Tromsø", "Mount Everest", "Berlin",
                     "Germany", "Norway", "Oslo", "Albert Einstein",
                     "Marie Curie", "William Shakespeare", "London", "Nile",
                     "South America", "Knebworth", "Queen", "World War II"):
            assert db.lookup_entity(name) is not None, name

    def test_new_entities_have_claims(self, db):
        """New main entities carry claims (usable by verification)."""
        for name in ("Bergen", "Trondheim", "Iceland", "Reykjavík",
                     "SINTEF", "European Union"):
            qid = db.lookup_entity(name)
            assert db.get_claims(qid), name

    def test_civic_entities_present(self, db):
        """The civic-domain expansion resolves the tested political names."""
        expected = {
            "The United States Constitution": "Q11698",
            "The U.S. Constitution": "Q11698",
            "The United Kingdom": "Q145",
            "Nixon": "Q9588",
            "The President": "Q11696",
            "only Congress": "Q11268",
            "The Silent Majority": "Q2555361",
            "lobbying": "Q187117",
            "The U.S. Senate": "Q66096",
            "United States Electoral College": "Q47586",
        }
        for name, qid in expected.items():
            assert db.lookup_entity(name) == qid, name

    def test_civic_role_claim_verifies(self, db):
        """'The President is Commander-in-Chief' verifies through P279."""
        detail = db.verify_triple(
            "The President", "be",
            "the Commander in Chief of the armed forces")
        assert detail.result == VerificationResult.CONFIRMED
        assert detail.property_id == 'P279'

    def test_reverse_phrase_map(self):
        """PROPERTY_TO_PHRASE is the deterministic reverse of
        PREDICATE_TO_PROPERTY (first phrase wins)."""
        from src.resources.wikidata_offline import PREDICATE_TO_PROPERTY
        for phrase, pid in PREDICATE_TO_PROPERTY.items():
            if pid not in PROPERTY_TO_PHRASE:
                continue  # only the first phrase per pid is kept
            assert PROPERTY_TO_PHRASE[pid] in PREDICATE_TO_PROPERTY
        assert PROPERTY_TO_PHRASE['P36'] == 'capital'
        assert PROPERTY_TO_PHRASE['P1376'] == 'capital of'
        assert PROPERTY_TO_PHRASE['P17'] == 'country'

    def test_format_entity_facts(self, db):
        """Facts doc: one line per claim row; None for unknown/qid-less."""
        doc = db.format_entity_facts("Q20")  # Norway
        assert doc is not None
        lines = doc.splitlines()
        assert len(lines) == len(db.get_claims("Q20"))
        assert all(line.startswith("Norway ") and line.endswith(".")
                   for line in lines)
        assert db.format_entity_facts("Q999999") is None


# ── Qualifier gate (slice 6c regression pins) ──────────────────────────────
#
# FEVER 2.0 REFUTES claims often mutate one precise detail of an
# otherwise-true sentence ("the THIRD James Bond film", "directed by X",
# "founded before 1990"). The weak/generic match paths would confirm the
# still-true generic part; _apply_qualifier_gate must intercept and
# abstain (UNKNOWN) — or DENY on an explicit contradiction. Each UNKNOWN
# pin has a paired control proving the weak match WOULD confirm without
# the qualifier, so the pin is non-vacuous.

def _build_gate_fixture_db(db_path, entities, claims):
    """Create a minimal seed-schema SQLite DB for qualifier-gate tests.

    Mirrors scripts/build_wikidata_db.py's schema so OfflineWikidata
    can read it. Args:
      entities: [(qid, label), ...]
      claims:   [(qid, property, value, value_qid), ...]
    """
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS entities (
            qid TEXT PRIMARY KEY,
            label TEXT NOT NULL,
            label_lower TEXT NOT NULL,
            description TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS aliases (
            qid TEXT NOT NULL,
            alias_lower TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS claims (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            qid TEXT NOT NULL,
            property TEXT NOT NULL,
            value TEXT NOT NULL,
            value_qid TEXT DEFAULT NULL
        );
    """)
    for qid, label in entities:
        conn.execute(
            "INSERT INTO entities (qid, label, label_lower, description) "
            "VALUES (?, ?, ?, 'fixture')",
            (qid, label, label.lower()),
        )
    for qid, prop, value, value_qid in claims:
        conn.execute(
            "INSERT INTO claims (qid, property, value, value_qid) "
            "VALUES (?, ?, ?, ?)",
            (qid, prop, value, value_qid),
        )
    conn.commit()
    conn.close()


class TestQualifierGate:
    """Pins the gate against the shipped seed DB (no fixtures).

    The pruned 122-entity seed carries no director/film/series data,
    so these cover the "property absent → abstain" half of the gate:
    the qualifier is unverifiable, so the whole claim must not CONFIRM
    through the still-true generic part.
    """

    @pytest.fixture
    def wikidata(self):
        return OfflineWikidata()

    def test_unqualified_location_claim_still_confirms(self, wikidata):
        """Control: without a qualifier the weak location match confirms."""
        detail = wikidata.verify_triple("Stockholm", "be", "a city in Sweden")
        assert detail.result == VerificationResult.CONFIRMED

    def test_role_qualifier_without_director_data_abstains(self, wikidata):
        """'directed by X' on an entity with no director data → UNKNOWN.

        A mutated claim ("Stockholm ... directed by Ingmar Bergman") must
        not CONFIRM via the still-true 'in Sweden' location match. The
        seed has no P57 rows, so the gate abstains rather than deny.
        """
        detail = wikidata.verify_triple(
            "Stockholm", "be", "a city in Sweden directed by Ingmar Bergman")
        assert detail.result == VerificationResult.UNKNOWN
        assert detail.subject_qid == "Q1754"  # subject resolved; gate decided

    def test_temporal_qualifier_before_year_abstains(self, wikidata):
        """'founded before 1990' → UNKNOWN: point dates, no arithmetic."""
        detail = wikidata.verify_triple(
            "Oslo", "be", "a city in Norway founded before 1990")
        assert detail.result == VerificationResult.UNKNOWN

    def test_temporal_qualifier_between_years_abstains(self, wikidata):
        """'between 1900 and 1990' → UNKNOWN: ranged dates unverifiable."""
        detail = wikidata.verify_triple(
            "Oslo", "be", "a city in Norway founded between 1900 and 1990")
        assert detail.result == VerificationResult.UNKNOWN

    def test_ordinal_series_claim_abstains_on_real_seed(self, wikidata):
        """Ordinal + series noun → UNKNOWN even when the generic part matches.

        Paired: the same object WITHOUT the ordinal confirms via the
        P31 'city' weak match, so the ordinal is what flips the verdict.
        """
        control = wikidata.verify_triple(
            "Trondheim", "be", "a city in Norway featured in a film")
        assert control.result == VerificationResult.CONFIRMED

        mutated = wikidata.verify_triple(
            "Trondheim", "be", "the third city in Norway featured in a film")
        assert mutated.result == VerificationResult.UNKNOWN

    def test_true_superlative_with_ordinal_word_still_confirms(self, wikidata):
        """Gate scoping pin: ordinals only abstain for series positions.

        'the second highest mountain' has an ordinal but no series noun
        (film/album/...), so the gate must NOT abstain — the true
        superlative claim confirms via the P2044 superlative path.
        """
        detail = wikidata.verify_triple(
            "K2", "be", "the second highest mountain in the world")
        assert detail.result == VerificationResult.CONFIRMED

    def test_gate_unknown_propagates_to_dimension_status(self, wikidata):
        """A gated claim stays status=unknown in the honesty core.

        The qualifier-gated triple counts as UNKNOWN in FactualAccuracy
        (never confirmed), so the dimension reports missing evidence
        rather than a scored quality value.
        """
        claim = Claim(
            subject="Stockholm", predicate="be",
            object="a city in Sweden directed by Ingmar Bergman",
            source_sentence="Stockholm is a city in Sweden directed by "
                            "Ingmar Bergman.",
        )
        score = FactualAccuracy(wikidata=wikidata).evaluate("", claims=[claim])
        assert score.status == 'unknown'
        assert score.raw_value == {'confirmed': 0, 'denied': 0, 'unknown': 1}


class TestQualifierGateFixtureDb:
    """Pins the gate branches the pruned seed cannot express.

    The seed carries no director/film data, so these use a fixture DB
    with the seed schema: a film entity (P31=film) and — for the
    contradicted case — a director claim (P57).
    """

    @pytest.fixture
    def db(self, tmp_path):
        path = tmp_path / "gate_fixture.db"
        _build_gate_fixture_db(
            path,
            entities=[("Q900001", "Goldfinger"), ("Q900002", "Pulp Fiction")],
            claims=[
                ("Q900001", "P31", "film", None),
                ("Q900002", "P31", "film", None),
                ("Q900002", "P57", "Quentin Tarantino", "Q900003"),
            ],
        )
        return OfflineWikidata(db_path=str(path))

    def test_ordinal_series_position_abstains(self, db):
        """'the third James Bond film' → UNKNOWN: no series-ordinal data.

        Paired control: 'a film' confirms via the P31 type-noun match,
        proving the ordinal+series-noun qualifier is what abstains.
        """
        control = db.verify_triple("Goldfinger", "be", "a film")
        assert control.result == VerificationResult.CONFIRMED

        mutated = db.verify_triple(
            "Goldfinger", "be", "the third James Bond film")
        assert mutated.result == VerificationResult.UNKNOWN

    def test_role_qualifier_absent_director_data_abstains(self, db):
        """'directed by X' with no P57 data for the entity → UNKNOWN.

        The claim must not CONFIRM via the still-true 'film' type match.
        """
        detail = db.verify_triple(
            "Goldfinger", "be", "a film directed by Guy Hamilton")
        assert detail.result == VerificationResult.UNKNOWN

    def test_role_qualifier_contradicted_director_denies(self, db):
        """'directed by X' where P57 data differs → DENIED (by design).

        The gate's documented split: DENY on an explicit contradiction
        with data we actually have (P57=Tarantino vs Scorsese), abstain
        (UNKNOWN) without data. Either way it must never CONFIRM.
        """
        detail = db.verify_triple(
            "Pulp Fiction", "be", "a film directed by Martin Scorsese")
        assert detail.result == VerificationResult.DENIED
        assert detail.result is not VerificationResult.CONFIRMED

    def test_role_qualifier_matching_director_confirms(self, db):
        """Positive control: a true 'directed by' claim still confirms."""
        detail = db.verify_triple(
            "Pulp Fiction", "be", "a film directed by Quentin Tarantino")
        assert detail.result == VerificationResult.CONFIRMED


# ── Seed-DB label-only pruning (slice 6c) ────────────────────────────────────

def _load_extend_script():
    """Import scripts/extend_wikidata_db.py as a module (not a package)."""
    import importlib.util
    import os
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    spec = importlib.util.spec_from_file_location(
        "extend_wikidata_db",
        os.path.join(root, "scripts", "extend_wikidata_db.py"),
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestPruneLabelOnly:
    """--prune-label-only keeps only location/identity-cited label-only rows.

    The 227 label-only values the slice 6b fetch pulled in were pruned to
    the 29 rows a P17/P131/P30/P36/P1376/P361 claim cites; this pins the
    flag's rule so the shipped 122-entity seed stays reproducible.
    """

    @pytest.fixture
    def extend(self):
        return _load_extend_script()

    @pytest.fixture
    def seed_db(self, tmp_path):
        path = str(tmp_path / "seed.db")
        _build_gate_fixture_db(
            path,
            entities=[("Q100", "Existing Entity"), ("Q400", "Old Label Only")],
            claims=[("Q100", "P17", "Norway", "Q20")],
        )
        return path

    @staticmethod
    def _new_entity_data(label_map):
        """One fetched entity: Q200 with a P17 claim citing Q20."""
        return {
            "Q200": {
                "label": "New Place",
                "aliases": [],
                "claims": {
                    "P17": [{
                        "rank": "normal",
                        "mainsnak": {
                            "snaktype": "value",
                            "datavalue": {
                                "type": "wikibase-entityid",
                                "value": {"id": "Q20"},
                            },
                        },
                    }],
                },
            },
        }

    def test_uncited_label_only_pruned_cited_kept(self, extend, seed_db):
        """Run-added label-only rows survive only when a whitelisted claim
        cites them; pre-existing rows (even uncited label-only ones) are
        never touched."""
        label_map = {
            "Q200": "New Place",
            "Q20": "Norway",       # cited by Q200's P17 → keep
            "Q300": "Random Ref",  # cited by nothing → prune
        }
        stats = extend.augment_database(
            seed_db, self._new_entity_data(label_map), label_map,
            prune_label_only=True,
        )

        conn = sqlite3.connect(seed_db)
        qids = {r[0] for r in conn.execute("SELECT qid FROM entities")}
        conn.close()
        assert qids == {"Q100", "Q400", "Q200", "Q20"}
        assert stats["label_only_kept"] == 1
        assert stats["label_only_pruned"] == 1

    def test_flag_off_keeps_all_label_only(self, extend, seed_db):
        """Default behaviour is unchanged: no pruning, stats stay None."""
        label_map = {
            "Q200": "New Place",
            "Q20": "Norway",
            "Q300": "Random Ref",
        }
        stats = extend.augment_database(
            seed_db, self._new_entity_data(label_map), label_map,
        )

        conn = sqlite3.connect(seed_db)
        qids = {r[0] for r in conn.execute("SELECT qid FROM entities")}
        conn.close()
        assert qids == {"Q100", "Q400", "Q200", "Q20", "Q300"}
        assert stats["label_only_pruned"] is None
        assert stats["label_only_kept"] is None
