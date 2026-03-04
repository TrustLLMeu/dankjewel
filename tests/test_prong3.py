"""Tests for Prong 3 (Extraction-Based) evaluation.

Comprehensive tests for:
  - Claim extraction (ClaimExtractor)
  - Wikidata offline lookup and verification
  - All five dimensions with D7.5 examples
  - Full pipeline integration
"""

import pytest
from src.prongs.prong3_extraction import Prong3Extraction
from src.extraction.claim_extractor import ClaimExtractor, Claim
from src.resources.wikidata_offline import OfflineWikidata, VerificationResult
from src.dimensions.prong3_dimensions import (
    FactualAccuracy, FactualConsistency, TemporalAccuracy,
    ComparativeFactuality, ModalityAwareness
)


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def extractor():
    return ClaimExtractor()


@pytest.fixture(scope="module")
def wikidata():
    return OfflineWikidata()


@pytest.fixture(scope="module")
def prong():
    return Prong3Extraction()


# ── Claim Extraction Tests ──────────────────────────────────────────────────

class TestClaimExtraction:

    def test_simple_copula(self, extractor):
        """'Paris is the capital of France' → (Paris, be, the capital of France)."""
        result = extractor.extract("Paris is the capital of France.")
        assert len(result.claims) >= 1
        c = result.claims[0]
        assert c.subject.lower() == "paris"
        assert c.predicate == "be"
        assert "capital" in c.object.lower()
        assert "france" in c.object.lower()

    def test_superlative_detection(self, extractor):
        """'Mount Everest is the highest mountain in the world' → comparative_tag = 'superlative'."""
        result = extractor.extract("Mount Everest is the highest mountain in the world.")
        assert len(result.claims) >= 1
        sup_claims = [c for c in result.claims if c.comparative_tag == 'superlative']
        assert len(sup_claims) >= 1
        assert 'everest' in sup_claims[0].subject.lower()

    def test_temporal_anchor_extraction(self, extractor):
        """Dates are extracted as temporal anchors."""
        result = extractor.extract("Queen played their last concert at Knebworth in 1986.")
        temporal_claims = [c for c in result.claims if c.temporal_anchor]
        assert len(temporal_claims) >= 1
        assert '1986' in temporal_claims[0].temporal_anchor

    def test_hedging_modifiers(self, extractor):
        """Modal verbs are captured as modifiers."""
        result = extractor.extract("There could be an uprising this week.")
        hedged = [c for c in result.claims if c.modifiers]
        assert len(hedged) >= 1
        assert 'could' in hedged[0].modifiers

    def test_no_claims_from_empty(self, extractor):
        """Empty or trivial text yields no claims."""
        result = extractor.extract("")
        assert len(result.claims) == 0

    def test_multiple_sentences(self, extractor):
        """Multiple sentences yield multiple claims."""
        result = extractor.extract(
            "Paris is the capital of France. Berlin is the capital of Germany."
        )
        assert len(result.claims) >= 2

    def test_extraction_timing(self, extractor):
        """Extraction reports timing in milliseconds."""
        result = extractor.extract("The capital of France is Paris.")
        assert result.extraction_time_ms > 0
        assert result.extraction_time_ms < 5000  # Should be fast

    def test_inverted_copula(self, extractor):
        """'The capital of France is Paris' → flipped to (Paris, be, The capital of France)."""
        result = extractor.extract("The capital of France is Paris.")
        assert len(result.claims) >= 1
        c = result.claims[0]
        assert c.subject.lower() == "paris"
        assert "capital" in c.object.lower()
        assert "france" in c.object.lower()

    def test_claim_to_dict(self, extractor):
        """Claim.to_dict() serializes correctly."""
        result = extractor.extract("Paris is the capital of France.")
        d = result.claims[0].to_dict()
        assert 'subject' in d
        assert 'predicate' in d
        assert 'object' in d
        assert 'source_sentence' in d


# ── Wikidata Offline Tests ──────────────────────────────────────────────────

class TestWikidataOffline:

    def test_lookup_paris(self, wikidata):
        """Paris resolves to Q90."""
        assert wikidata.lookup_entity("Paris") == "Q90"

    def test_lookup_case_insensitive(self, wikidata):
        """Lookup is case-insensitive."""
        assert wikidata.lookup_entity("paris") == "Q90"
        assert wikidata.lookup_entity("PARIS") == "Q90"

    def test_lookup_alias(self, wikidata):
        """Alias lookup: 'USA' → Q30."""
        assert wikidata.lookup_entity("USA") == "Q30"
        assert wikidata.lookup_entity("tromso") == "Q25437"

    def test_lookup_tromsoe_alias(self, wikidata):
        """'troms' alias finds Tromsø."""
        qid = wikidata.lookup_entity("troms")
        assert qid == "Q25437"

    def test_lookup_not_found(self, wikidata):
        """Unknown entity returns None."""
        assert wikidata.lookup_entity("Xyzzy Nonexistent City") is None

    def test_get_claims(self, wikidata):
        """Get claims for France (Q142)."""
        claims = wikidata.get_claims("Q142", "P36")
        assert len(claims) >= 1
        assert claims[0]['value'] == "Paris"

    def test_verify_paris_capital_confirmed(self, wikidata):
        """Paris is the capital of France → CONFIRMED."""
        detail = wikidata.verify_triple("Paris", "be", "the capital of France")
        assert detail.result == VerificationResult.CONFIRMED

    def test_verify_tromso_capital_denied(self, wikidata):
        """Tromsø is the capital of France → DENIED."""
        detail = wikidata.verify_triple("Tromsø", "be", "the capital of France")
        assert detail.result == VerificationResult.DENIED

    def test_verify_tromso_norway_confirmed(self, wikidata):
        """Tromsø is in Norway → CONFIRMED."""
        detail = wikidata.verify_triple("Tromsø", "be", "in Norway")
        assert detail.result == VerificationResult.CONFIRMED

    def test_verify_norwegian_city(self, wikidata):
        """Tromsø as a Norwegian city → CONFIRMED (demonym matching)."""
        detail = wikidata.verify_triple("Troms", "be", "a Norwegian city")
        assert detail.result == VerificationResult.CONFIRMED

    def test_verify_everest_superlative(self, wikidata):
        """Mount Everest is the highest mountain in the world → CONFIRMED."""
        detail = wikidata.verify_triple("Mount Everest", "be", "the highest mountain in the world")
        assert detail.result == VerificationResult.CONFIRMED

    def test_verify_tromso_stockholm_denied(self, wikidata):
        """Tromsø is in the Stockholm archipelago → DENIED (false claim)."""
        detail = wikidata.verify_triple("Troms", "be", "in the Stockholm archipelago")
        assert detail.result == VerificationResult.DENIED

    def test_verify_unknown_entity(self, wikidata):
        """Unknown entity returns UNKNOWN."""
        detail = wikidata.verify_triple("Xyzzy", "be", "something")
        assert detail.result == VerificationResult.UNKNOWN

    def test_verification_timing(self, wikidata):
        """Verification reports timing."""
        detail = wikidata.verify_triple("Paris", "be", "the capital of France")
        assert detail.verification_time_ms >= 0

    def test_check_object_conflict(self, wikidata):
        """Conflict detection for same subject + property."""
        # Tromsø (Q25437) country = Norway — "Norway" vs "Sweden" should conflict
        assert wikidata.check_object_conflict("Q25437", "P17", "Norway", "Sweden")


# ── Dimension Tests ─────────────────────────────────────────────────────────

class TestFactualAccuracy:

    def test_true_claim(self, wikidata):
        """Paris is the capital of France → accuracy 1.0."""
        dim = FactualAccuracy(wikidata=wikidata)
        claims = [Claim(
            subject="Paris", predicate="be", object="the capital of France",
            source_sentence="Paris is the capital of France."
        )]
        score = dim.evaluate("", claims=claims)
        assert score.value == 1.0
        assert score.raw_value['confirmed'] == 1

    def test_false_claim(self, wikidata):
        """Tromsø is the capital of France → accuracy 0.0."""
        dim = FactualAccuracy(wikidata=wikidata)
        claims = [Claim(
            subject="Tromsø", predicate="be", object="the capital of France",
            source_sentence="Tromsø is the capital of France."
        )]
        score = dim.evaluate("", claims=claims)
        assert score.value == 0.0
        assert score.raw_value['denied'] == 1

    def test_no_claims(self):
        """No claims → 0.5 fallback."""
        dim = FactualAccuracy(wikidata=OfflineWikidata())
        score = dim.evaluate("Hello world.", claims=[])
        assert score.value == 0.5

    def test_mixed_claims(self, wikidata):
        """Mix of true and false claims."""
        dim = FactualAccuracy(wikidata=wikidata)
        claims = [
            Claim(subject="Paris", predicate="be", object="the capital of France",
                  source_sentence="Paris is the capital of France."),
            Claim(subject="Berlin", predicate="be", object="the capital of France",
                  source_sentence="Berlin is the capital of France."),
        ]
        score = dim.evaluate("", claims=claims)
        assert score.value == 0.5  # 1 confirmed, 1 denied


class TestFactualConsistency:

    def test_contradictory_claims(self, wikidata):
        """Tromsø in Norway + Tromsø in Stockholm → contradiction."""
        dim = FactualConsistency(wikidata=wikidata)
        claims = [
            Claim(subject="Troms", predicate="be", object="a Norwegian city",
                  source_sentence="Tromsø is a Norwegian city."),
            Claim(subject="Troms", predicate="be", object="in the Stockholm archipelago",
                  source_sentence="Tromsø is in the Stockholm archipelago."),
        ]
        score = dim.evaluate("", claims=claims)
        assert score.value < 1.0  # Should detect contradiction

    def test_consistent_claims(self, wikidata):
        """Two true claims about same entity → consistent."""
        dim = FactualConsistency(wikidata=wikidata)
        claims = [
            Claim(subject="Paris", predicate="be", object="the capital of France",
                  source_sentence="Paris is the capital of France."),
            Claim(subject="Paris", predicate="be", object="in France",
                  source_sentence="Paris is in France."),
        ]
        score = dim.evaluate("", claims=claims)
        assert score.value == 1.0

    def test_single_claim(self, wikidata):
        """Single claim → no contradiction possible."""
        dim = FactualConsistency(wikidata=wikidata)
        claims = [Claim(subject="Paris", predicate="be", object="the capital of France",
                        source_sentence="Paris is the capital of France.")]
        score = dim.evaluate("", claims=claims)
        assert score.value == 1.0


class TestTemporalAccuracy:

    def test_correct_date(self, wikidata):
        """Einstein born 1879 → confirmed."""
        dim = TemporalAccuracy(wikidata=wikidata)
        claims = [Claim(
            subject="Albert Einstein", predicate="bear", object="in 1879",
            source_sentence="Albert Einstein was born in 1879.",
            temporal_anchor="1879"
        )]
        score = dim.evaluate("", claims=claims)
        assert score.value == 1.0

    def test_wrong_date(self, wikidata):
        """Einstein born 1900 → denied."""
        dim = TemporalAccuracy(wikidata=wikidata)
        claims = [Claim(
            subject="Albert Einstein", predicate="bear", object="in 1900",
            source_sentence="Albert Einstein was born in 1900.",
            temporal_anchor="1900"
        )]
        score = dim.evaluate("", claims=claims)
        assert score.value == 0.0

    def test_no_temporal_claims(self, wikidata):
        """No temporal claims → 0.5 fallback."""
        dim = TemporalAccuracy(wikidata=wikidata)
        claims = [Claim(subject="Paris", predicate="be", object="a city",
                        source_sentence="Paris is a city.")]
        score = dim.evaluate("", claims=claims)
        assert score.value == 0.5


class TestComparativeFactuality:

    def test_true_superlative(self, wikidata):
        """Mount Everest is the highest mountain in the world → confirmed."""
        dim = ComparativeFactuality(wikidata=wikidata)
        claims = [Claim(
            subject="Mount Everest", predicate="be",
            object="the highest mountain in the world",
            source_sentence="Mount Everest is the highest mountain in the world.",
            comparative_tag="superlative"
        )]
        score = dim.evaluate("", claims=claims)
        assert score.value == 1.0

    def test_no_comparative_claims(self, wikidata):
        """No comparative claims → 0.5 fallback."""
        dim = ComparativeFactuality(wikidata=wikidata)
        claims = [Claim(subject="Paris", predicate="be", object="a city",
                        source_sentence="Paris is a city.")]
        score = dim.evaluate("", claims=claims)
        assert score.value == 0.5


class TestModalityAwareness:

    def test_hedged_claim(self):
        """Claim with 'could' modifier → hedged."""
        dim = ModalityAwareness()
        claims = [Claim(
            subject="an uprising", predicate="exist", object="",
            source_sentence="There could be an uprising.",
            modifiers=["could"]
        )]
        score = dim.evaluate("", claims=claims)
        assert score.value == 1.0

    def test_asserted_claim(self):
        """Claim without modifiers → asserted."""
        dim = ModalityAwareness()
        claims = [Claim(
            subject="Paris", predicate="be", object="the capital of France",
            source_sentence="Paris is the capital of France."
        )]
        score = dim.evaluate("", claims=claims)
        assert score.value == 0.0

    def test_mixed_modality(self):
        """Mix of hedged and asserted claims."""
        dim = ModalityAwareness()
        claims = [
            Claim(subject="A", predicate="be", object="B",
                  source_sentence="A is B.", modifiers=[]),
            Claim(subject="C", predicate="be", object="D",
                  source_sentence="C could be D.", modifiers=["could"]),
        ]
        score = dim.evaluate("", claims=claims)
        assert score.value == 0.5


# ── Integration Tests ───────────────────────────────────────────────────────

class TestProng3Integration:

    def test_basic_evaluation(self, prong):
        """Basic evaluation produces 5 dimensions."""
        result = prong.evaluate("Tromsø is in Norway.")
        assert result.prong_name == "Extraction-Based (Prong 3)"
        assert len(result.dimensions) == 5
        assert result.error is None

    def test_d75_tromso_capital_false(self, prong):
        """D7.5 example: 'Tromsø is the capital of France' should score low on accuracy."""
        result = prong.evaluate("Tromsø is the capital of France.")
        accuracy = next(d for d in result.dimensions if d.name == "Factual Accuracy")
        assert accuracy.value == 0.0

    def test_d75_paris_capital_true(self, prong):
        """D7.5 example: 'Paris is the capital of France' should score high."""
        result = prong.evaluate("Paris is the capital of France.")
        accuracy = next(d for d in result.dimensions if d.name == "Factual Accuracy")
        assert accuracy.value == 1.0

    def test_d75_everest_superlative(self, prong):
        """D7.5: 'Mount Everest is the highest mountain in the world' → comparative confirmed."""
        result = prong.evaluate("Mount Everest is the highest mountain in the world.")
        comp = next(d for d in result.dimensions if d.name == "Comparative Factuality")
        assert comp.value == 1.0

    def test_d75_tromso_contradiction(self, prong):
        """D7.5: 'Tromsø is Norwegian. Tromsø is in Stockholm archipelago' → inconsistent.

        The Stockholm archipelago claim is false (Tromsø is in Norway).
        """
        result = prong.evaluate(
            "Tromsø is a Norwegian city. Tromsø is in the Stockholm archipelago."
        )
        consistency = next(d for d in result.dimensions if d.name == "Factual Consistency")
        assert consistency.value < 1.0

    def test_d75_tromso_stockholm_denied(self, prong):
        """The claim that Tromsø is in the Stockholm archipelago is false."""
        result = prong.evaluate("Tromsø is in the Stockholm archipelago.")
        accuracy = next(d for d in result.dimensions if d.name == "Factual Accuracy")
        assert accuracy.value == 0.0

    def test_d75_hedging(self, prong):
        """D7.5: 'There could be an uprising' → hedged."""
        result = prong.evaluate("There could be an uprising this week.")
        modality = next(d for d in result.dimensions if d.name == "Modality Awareness")
        assert modality.value > 0.0  # At least some hedging detected

    def test_inverted_paris_capital(self, prong):
        """'The capital of France is Paris, located in north-central France.'

        The inverted copula should be flipped so Paris becomes the subject,
        allowing Wikidata to confirm the claim (not return unknown).
        """
        result = prong.evaluate(
            "The capital of France is Paris, located in north-central France."
        )
        accuracy = next(d for d in result.dimensions if d.name == "Factual Accuracy")
        assert accuracy.value == 1.0
        assert accuracy.raw_value['confirmed'] >= 1
        assert accuracy.raw_value['unknown'] == 0

    def test_json_serialization(self, prong):
        """Results serialize to valid JSON."""
        result = prong.evaluate("Paris is the capital of France.")
        json_str = result.to_json()
        import json
        parsed = json.loads(json_str)
        assert 'Extraction-Based' in parsed['prong_name']
        assert len(parsed['dimensions']) == 5

    def test_all_scores_in_range(self, prong):
        """All dimension scores are in valid range."""
        result = prong.evaluate("The capital of France is Paris, located in north-central France.")
        for d in result.dimensions:
            assert 0.0 <= d.value <= 1.0, f"{d.name} out of range: {d.value}"

    def test_processing_time_tracked(self, prong):
        """Processing time is tracked."""
        result = prong.evaluate("Paris is the capital of France.")
        assert result.processing_time > 0
        assert result.processing_time < 30  # Should complete in under 30s
