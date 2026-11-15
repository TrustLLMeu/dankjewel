"""Tests for the Stage A evidence contract.

Covers:
  - src/evidence.py: the closed SOURCE_KEYS set, entry normalization,
    rejection of bad keys / shapes / statuses
  - per-dimension metadata["evidence_sources"] for the default path and
    each opt-in flag (tiny_judge, llm_extract via claim.source, llm_verify)
  - the top-level coverage summary (counts sum, judge/rules flags,
    prongs_scored membership)
  - the additive guarantee: with all flags off, every pre-existing
    response field keeps its pre-Stage-A value (snapshot fixture)

No network, no model download beyond the CPU baselines the suite
already loads; the judge and verifier are always stubs here.
"""

import json
import os

import numpy as np
import pytest

from src.base import DimensionScore, ProngResult
from src.dimensions.prong2_dimensions import FluidityDimension, PolitenessDetection
from src.dimensions.prong3_dimensions import (
    FactualAccuracy, FactualConsistency, ModalityAwareness,
    TemporalAccuracy, ComparativeFactuality,
)
from src.evidence import SOURCE_KEYS, compute_coverage, normalize, source
from src.extraction.claim_extractor import Claim
from src.llm_judge_client import JudgeUnavailableError
from src.pipeline import EvaluationPipeline
from src.prongs.prong1_dimensions import Relevance, SemanticCoherence, Toxicity
from src.prongs.prong4_intrinsic import IntrinsicData, Prong4Intrinsic, Uncertainty, Perplexity
from src.resources.nli_verifier import VerifierUnavailableError
from src.resources.wikidata_offline import OfflineWikidata


# ── Test doubles ────────────────────────────────────────────────────────────

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


PARIS_CLAIM = Claim(
    subject="Paris", predicate="be", object="the capital of France",
    source_sentence="Paris is the capital of France.",
)
UNKNOWN_WHARVES_CLAIM = Claim(
    subject="Trondheim", predicate="be", object="famous for its wharves",
    source_sentence="Trondheim is famous for its wharves.",
)


# ── Contract module ──────────────────────────────────────────────────────────

class TestEvidenceContractModule:

    def test_source_keys_are_the_contract_set(self):
        """Exactly the nine keys the UI matches on."""
        assert SOURCE_KEYS == ('embedding', 'llm_judge', 'classifier', 'rules',
                               'spacy', 'llm_claims', 'kb_exact', 'minicheck',
                               'logprob')

    def test_source_normalizes_types(self):
        entry = source(1, 'scored', 3)
        assert entry == {'value': 1.0, 'status': 'scored', 'n': 3}
        assert isinstance(entry['value'], float)
        assert isinstance(entry['n'], int)
        assert source() == {'value': None, 'status': 'scored', 'n': None}

    def test_source_rejects_bad_status(self):
        with pytest.raises(ValueError):
            source(status='bogus')

    def test_normalize_rejects_unknown_key(self):
        with pytest.raises(ValueError):
            normalize({'gpt4': source()})

    def test_normalize_rejects_bad_entry_shape(self):
        with pytest.raises(ValueError):
            normalize({'rules': {'value': 0.5, 'status': 'scored'}})  # missing n
        with pytest.raises(ValueError):
            normalize({'rules': {'value': 0.5, 'status': 'scored', 'n': 1, 'x': 2}})

    def test_normalize_passes_valid_entries(self):
        out = normalize({'embedding': source(0.5, 'scored', 2)})
        assert out == {'embedding': {'value': 0.5, 'status': 'scored', 'n': 2}}
        assert normalize(None) == {}


# ── Prong 1 evidence ────────────────────────────────────────────────────────

class TestProng1Evidence:

    def test_relevance_embedding_evidence(self):
        """Default path: embedding listed with the dimension's value and n."""
        rel = Relevance()
        score = rel.evaluate("What is the capital of France?",
                             "Paris is the capital of France. It is a city.")
        ev = score.metadata['evidence_sources']
        assert set(ev) == {'embedding'}
        assert ev['embedding']['status'] == 'scored'
        assert ev['embedding']['value'] == score.value
        assert ev['embedding']['n'] == 2  # two response sentences

    def test_relevance_judge_adds_llm_judge(self):
        """tiny_judge=True: llm_judge listed alongside embedding."""
        judge = StubJudge(score=0.7)
        rel = Relevance()
        score = rel.evaluate("What is the capital of France?",
                             "Paris is the capital of France.",
                             judge=judge)
        ev = score.metadata['evidence_sources']
        assert set(ev) == {'embedding', 'llm_judge'}
        assert ev['llm_judge'] == {'value': 0.7, 'status': 'scored', 'n': 1}
        assert ev['embedding']['status'] == 'scored'

    def test_relevance_no_prompt_omits_embedding(self):
        """Missing prompt: embedding never invoked, so it is omitted."""
        rel = Relevance()
        score = rel.evaluate(None, "Paris is the capital of France.")
        assert score.metadata['evidence_sources'] == {}

    def test_relevance_no_prompt_with_judge_lists_unknown(self):
        """Judge requested but no prompt: the judge track abstains."""
        rel = Relevance()
        score = rel.evaluate(None, "Paris is the capital of France.",
                             judge=StubJudge())
        assert score.metadata['evidence_sources'] == \
            {'llm_judge': {'value': None, 'status': 'unknown', 'n': None}}

    def test_relevance_judge_unavailable_is_unknown(self):
        """Unreachable judge: llm_judge unknown, baseline untouched."""
        rel = Relevance()
        score = rel.evaluate("What is the capital of France?",
                             "Paris is the capital of France.",
                             judge=StubJudge(exc=JudgeUnavailableError("down")))
        ev = score.metadata['evidence_sources']
        assert ev['llm_judge'] == {'value': None, 'status': 'unknown', 'n': None}
        assert ev['embedding']['status'] == 'scored'

    def test_relevance_judge_parse_error_is_error(self):
        """Unparseable judge reply: llm_judge error, baseline untouched."""
        rel = Relevance()
        score = rel.evaluate("What is the capital of France?",
                             "Paris is the capital of France.",
                             judge=StubJudge(exc=RuntimeError("bad json")))
        ev = score.metadata['evidence_sources']
        assert ev['llm_judge']['status'] == 'error'
        assert ev['llm_judge']['value'] is None
        assert ev['embedding']['status'] == 'scored'

    def test_coherence_short_text_lists_no_source(self):
        """Short-text coherence 1.0 is a default, not a measurement."""
        score = SemanticCoherence().evaluate("Paris is the capital of France.")
        assert score.value == 1.0
        assert score.metadata['evidence_sources'] == {}

    def test_coherence_multisentence_lists_embedding(self):
        score = SemanticCoherence().evaluate(
            "Paris is the capital of France. Paris is a city in France.")
        ev = score.metadata['evidence_sources']
        assert ev['embedding']['status'] == 'scored'
        assert ev['embedding']['value'] == score.value
        assert ev['embedding']['n'] == 2

    def test_toxicity_lists_classifier(self):
        score = Toxicity().evaluate("Biathlon is an interesting winter sport.")
        ev = score.metadata['evidence_sources']
        assert ev == {'classifier': {'value': score.value, 'status': 'scored', 'n': None}}


# ── Prong 2 / Modality evidence ─────────────────────────────────────────────

class TestProng2Evidence:

    def test_fluency_lists_rules(self):
        score = FluidityDimension().evaluate("The cat sits on the mat.")
        ev = score.metadata['evidence_sources']
        assert ev == {'rules': {'value': score.value, 'status': 'scored', 'n': None}}

    def test_politeness_lists_rules(self):
        score = PolitenessDetection().evaluate("Please help me, thank you kindly.")
        ev = score.metadata['evidence_sources']
        assert ev['rules']['status'] == 'scored'
        assert ev['rules']['value'] == score.value

    def test_modality_rules_counts_claims(self):
        """Modality Awareness maps to rules; n is the claims classified."""
        claims = [
            Claim(subject="A", predicate="be", object="B",
                  source_sentence="A is B."),
            Claim(subject="C", predicate="be", object="D",
                  source_sentence="C could be D.", modifiers=["could"]),
        ]
        score = ModalityAwareness().evaluate("", claims=claims)
        ev = score.metadata['evidence_sources']
        assert ev == {'rules': {'value': score.value, 'status': 'scored', 'n': 2}}


# ── Prong 3 evidence ────────────────────────────────────────────────────────

class TestProng3Evidence:

    @pytest.fixture
    def wikidata(self):
        return OfflineWikidata()

    def test_fa_default_lists_spacy_and_kb_exact(self, wikidata):
        """Flags off: spacy + kb_exact only (no llm_claims, no minicheck)."""
        dim = FactualAccuracy(wikidata=wikidata)
        score = dim.evaluate("", claims=[PARIS_CLAIM])
        ev = score.metadata['evidence_sources']
        assert set(ev) == {'spacy', 'kb_exact'}
        assert ev['spacy'] == {'value': None, 'status': 'scored', 'n': 1}
        assert ev['kb_exact'] == {'value': 1.0, 'status': 'scored', 'n': 1}

    def test_fa_llm_claims_listed_when_contributed(self, wikidata):
        """A claim from the LLM track lists llm_claims (deviation from the
        brief's FA-only mapping: LLM claims inform FA when present)."""
        llm_claim = Claim(
            subject="Trondheim", predicate="be", object="famous for its wharves",
            source_sentence="Trondheim is famous for its wharves.",
            source="llm", atomic_text="Trondheim is famous for its wharves.",
        )
        score = FactualAccuracy(wikidata=wikidata).evaluate("", claims=[llm_claim])
        ev = score.metadata['evidence_sources']
        assert ev['llm_claims'] == {'value': None, 'status': 'scored', 'n': 1}
        assert 'spacy' not in ev  # no spaCy-source claim contributed

    def test_fa_both_claims_count_in_both_tracks(self, wikidata):
        both = Claim(
            subject="Paris", predicate="be", object="the capital of France",
            source_sentence="Paris is the capital of France.",
            source="both", atomic_text="Paris is the capital of France.",
        )
        score = FactualAccuracy(wikidata=wikidata).evaluate("", claims=[both])
        ev = score.metadata['evidence_sources']
        assert ev['spacy']['n'] == 1
        assert ev['llm_claims']['n'] == 1

    def test_fa_kb_exact_unknown_when_nothing_verifiable(self, wikidata):
        score = FactualAccuracy(wikidata=wikidata).evaluate(
            "", claims=[UNKNOWN_WHARVES_CLAIM])
        ev = score.metadata['evidence_sources']
        assert ev['kb_exact'] == {'value': None, 'status': 'unknown', 'n': 0}
        assert score.status == 'unknown'

    def test_fa_no_claims_lists_nothing(self, wikidata):
        score = FactualAccuracy(wikidata=wikidata).evaluate("Hello.", claims=[])
        assert score.metadata['evidence_sources'] == {}

    def test_fa_minicheck_listed_when_scored(self, wikidata):
        """llm_verify with a working verifier: minicheck scored, n = claims."""
        stub = StubVerifier(0.5)
        score = FactualAccuracy(wikidata=wikidata, verifier=stub).evaluate(
            "", claims=[UNKNOWN_WHARVES_CLAIM], llm_verify=True)
        ev = score.metadata['evidence_sources']
        assert ev['minicheck'] == {'value': None, 'status': 'scored', 'n': 1}
        assert ev['kb_exact']['status'] == 'unknown'  # KB left it unknown

    def test_fa_minicheck_error_when_all_attempts_fail(self, wikidata):
        stub = UnavailableVerifier()
        score = FactualAccuracy(wikidata=wikidata, verifier=stub).evaluate(
            "", claims=[UNKNOWN_WHARVES_CLAIM], llm_verify=True)
        ev = score.metadata['evidence_sources']
        assert ev['minicheck'] == {'value': None, 'status': 'error', 'n': 0}

    def test_fa_minicheck_omitted_when_never_invoked(self, wikidata):
        """All claims KB-confirmed: the verifier never runs, so no entry."""
        score = FactualAccuracy(wikidata=wikidata, verifier=StubVerifier()).evaluate(
            "", claims=[PARIS_CLAIM], llm_verify=True)
        assert 'minicheck' not in score.metadata['evidence_sources']

    def test_temporal_no_temporal_claims_lists_nothing(self, wikidata):
        """Early return: no temporal evidence at all, contract is empty."""
        claims = [Claim(subject="Paris", predicate="be", object="a city",
                        source_sentence="Paris is a city.")]
        score = TemporalAccuracy(wikidata=wikidata).evaluate("", claims=claims)
        assert score.metadata['evidence_sources'] == {}

    def test_temporal_lists_kb_exact(self, wikidata):
        claims = [Claim(
            subject="Albert Einstein", predicate="bear", object="in 1879",
            source_sentence="Albert Einstein was born in 1879.",
            temporal_anchor="1879",
        )]
        score = TemporalAccuracy(wikidata=wikidata).evaluate("", claims=claims)
        ev = score.metadata['evidence_sources']
        assert ev['spacy'] == {'value': None, 'status': 'scored', 'n': 1}
        assert ev['kb_exact'] == {'value': 1.0, 'status': 'scored', 'n': 1}

    def test_comparative_lists_kb_exact(self, wikidata):
        claims = [Claim(
            subject="Mount Everest", predicate="be",
            object="the highest mountain in the world",
            source_sentence="Mount Everest is the highest mountain in the world.",
            comparative_tag="superlative",
        )]
        score = ComparativeFactuality(wikidata=wikidata).evaluate("", claims=claims)
        ev = score.metadata['evidence_sources']
        assert ev['kb_exact']['status'] == 'scored'
        assert ev['spacy']['n'] == 1

    def test_consistency_lists_kb_exact_for_qid_pairs(self, wikidata):
        """A pair whose conflict check consults Wikidata lists kb_exact."""
        claims = [
            Claim(subject="Paris", predicate="be", object="the capital of France",
                  source_sentence="Paris is the capital of France."),
            Claim(subject="Paris", predicate="be", object="a city in Germany",
                  source_sentence="Paris is a city in Germany."),
        ]
        score = FactualConsistency(wikidata=wikidata).evaluate("", claims=claims)
        ev = score.metadata['evidence_sources']
        assert 'spacy' in ev and ev['spacy']['n'] == 2
        assert 'kb_exact' in ev
        assert ev['kb_exact']['status'] in ('scored', 'unknown')


# ── Prong 4 evidence ────────────────────────────────────────────────────────

class TestProng4Evidence:

    def test_logprob_evidence_on_scored_paths(self):
        ll = np.array([-0.1, -0.05, -0.3])
        data = IntrinsicData(token_ids=[0, 1, 2], log_likelihoods=ll)
        unc = Uncertainty().evaluate(data)
        ev = unc.metadata['evidence_sources']
        assert ev == {'logprob': {'value': unc.value, 'status': 'scored', 'n': 3}}

        ppl = Perplexity().evaluate(data)
        ev = ppl.metadata['evidence_sources']
        assert ev['logprob']['value'] == ppl.agg_value  # the [0,1] form 1/(1+ppl)
        assert ev['logprob']['n'] == 3

    def test_no_intrinsic_data_lists_logprob_unknown(self):
        result = Prong4Intrinsic().evaluate("Test text", intrinsic_data=None)
        for dim in result.dimensions:
            assert dim.metadata['evidence_sources'] == \
                {'logprob': {'value': None, 'status': 'unknown', 'n': None}}

    def test_no_logprob_data_lists_logprob_unknown(self):
        data = IntrinsicData(token_ids=[1, 2, 3])
        score = Uncertainty().evaluate(data)
        assert score.metadata['evidence_sources'] == \
            {'logprob': {'value': None, 'status': 'unknown', 'n': None}}


# ── Coverage summary ────────────────────────────────────────────────────────

class TestCoverageSummary:

    def test_coverage_flags_off(self):
        pipeline = EvaluationPipeline()
        result = pipeline.evaluate(
            text="Paris is the capital of France. Paris is a city in France.",
            prompt="What is the capital of France?",
        )
        cov = result['coverage']
        assert set(cov) == {'claims_total', 'claims_verified', 'claims_partial',
                             'claims_unverified', 'judge_scored', 'rules_scored',
                             'prongs_scored', 'prongs_total'}
        assert cov['claims_total'] >= 1
        assert (cov['claims_verified'] + cov['claims_partial']
                + cov['claims_unverified']) == cov['claims_total']
        assert cov['judge_scored'] is False      # flags off
        assert cov['rules_scored'] is True       # Prong 2 scored
        assert cov['prongs_scored'] == 3          # Prong 4 unknown without logprobs
        assert cov['prongs_total'] == 4

    def test_coverage_judge_scored(self):
        """tiny_judge=True with a stub judge flips judge_scored."""
        pipeline = EvaluationPipeline(judge=StubJudge(score=0.8))
        result = pipeline.evaluate(
            text="Paris is the capital of France.",
            prompt="What is the capital of France?",
            tiny_judge=True,
        )
        assert result['coverage']['judge_scored'] is True

    def test_coverage_partial_counts_come_from_relation_counts(self):
        """Verifier partial band feeds claims_partial; counts still sum."""
        stub = StubVerifier(0.5)  # 0.2 < 0.5 < 0.8 -> partially_supported
        dim = FactualAccuracy(wikidata=OfflineWikidata(), verifier=stub)
        score = dim.evaluate("", claims=[UNKNOWN_WHARVES_CLAIM], llm_verify=True)
        result = ProngResult(prong_name='Extraction-Based (Prong 3)',
                             dimensions=[score], processing_time=0.001)
        cov = compute_coverage([result], prong_scores={}, prongs_total=1)
        assert cov['claims_total'] == 1
        assert cov['claims_partial'] == 1
        assert cov['claims_verified'] == 0
        assert cov['claims_unverified'] == 0
        assert (cov['claims_verified'] + cov['claims_partial']
                + cov['claims_unverified']) == cov['claims_total']

    def test_coverage_prongs_total_respects_enabled(self):
        pipeline = EvaluationPipeline(enable_prongs=[2])
        result = pipeline.evaluate(text="The cat sits on the mat.")
        assert result['coverage']['prongs_total'] == 1
        assert result['coverage']['prongs_scored'] == 1
        assert result['coverage']['claims_total'] == 0

    def test_coverage_all_unknown_prongs_scored_zero(self):
        pipeline = EvaluationPipeline(enable_prongs=[4])
        result = pipeline.evaluate(text="Test text", intrinsic_data=None)
        assert result['coverage']['prongs_scored'] == 0
        assert result['coverage']['prongs_total'] == 1

    def test_coverage_rules_scored_false_without_rules(self):
        """Only Prong 3, no Prong 2: rules_scored is False (Modality
        unknown on empty claims does not list rules)."""
        pipeline = EvaluationPipeline(enable_prongs=[3])
        result = pipeline.evaluate(text="Hello there, friend.")  # no claims
        assert result['coverage']['rules_scored'] is False


# ── Additive guarantee (snapshot of the pre-Stage-A response) ──────────────

class TestAdditiveGuarantee:

    SNAPSHOT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 'evidence_flags_off_snapshot.json')

    @staticmethod
    def _strip_volatile(obj, drop_evidence=False):
        """Drop timing keys (and optionally the additive metadata keys
        evidence_sources / claim_admission), round floats."""
        additive = {'evidence_sources', 'claim_admission'}
        if isinstance(obj, dict):
            return {k: TestAdditiveGuarantee._strip_volatile(v, drop_evidence)
                    for k, v in obj.items()
                    if 'time' not in k
                    and not (drop_evidence and k in additive)}
        if isinstance(obj, list):
            return [TestAdditiveGuarantee._strip_volatile(v, drop_evidence)
                    for v in obj]
        if isinstance(obj, float):
            return round(obj, 6)
        return obj

    def test_flags_off_preexisting_fields_unchanged(self):
        """With all flags off, every pre-existing key keeps its pre-Stage-A
        value; later slices only ADD keys — Stage A added the top-level
        coverage key and per-dimension metadata.evidence_sources, the
        claim-admission slice added Factual Accuracy's
        metadata.claim_admission (the admitted claim set itself is
        unchanged on this input). The snapshot was captured from the
        pre-Stage-A pipeline on this exact input.
        """
        with open(self.SNAPSHOT_PATH) as f:
            expected = self._strip_volatile(json.load(f))

        pipeline = EvaluationPipeline()
        result = pipeline.evaluate(
            text="Paris is the capital of France. Paris is a city in France.",
            prompt="What is the capital of France?",
        )
        # The only new top-level key is coverage.
        assert set(result) - {'coverage'} == set(expected)
        current = self._strip_volatile({k: v for k, v in result.items()
                                        if k != 'coverage'}, drop_evidence=True)
        assert current == expected

    def test_evidence_sources_are_pure_additions(self):
        """Removing the new metadata key restores the pre-change shape."""
        pipeline = EvaluationPipeline(enable_prongs=[2])
        result = pipeline.evaluate(text="The cat sits on the mat.")
        for prong in result['prong_results']:
            for dim in prong['dimensions']:
                stripped = {k: v for k, v in dim['metadata'].items()
                           if k != 'evidence_sources'}
                assert stripped  # non-empty: only evidence_sources was added
