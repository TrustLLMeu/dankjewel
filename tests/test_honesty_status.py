"""Tests for the honesty core: unknown/error statuses never fake a score.

A missing measurement (no prompt, no verifiable claims, no logprobs) must
be reported as status="unknown" and excluded from prong/total averages —
never blended in as a middling-good 0.5 quality score. Failed computations
are status="error" and equally excluded. With nothing scored at all,
total_score is JSON null, never 0.5.
"""

import json

import pytest

from src.base import DimensionScore, ProngResult
from src.aggregation.aggregator import ScoreAggregator
from src.prongs.prong1_dimensions import Relevance
from src.prongs.prong4_intrinsic import Prong4Intrinsic
from src.dimensions.prong3_dimensions import FactualAccuracy
from src.extraction.claim_extractor import Claim
from src.resources.wikidata_offline import OfflineWikidata


def make_prong(prong_name, dims, error=None):
    """Build a ProngResult from (name, value, aggregate, status) tuples."""
    scores = [
        DimensionScore(name=name, value=value, aggregate=aggregate, status=status)
        for (name, value, aggregate, status) in dims
    ]
    return ProngResult(prong_name=prong_name, dimensions=scores,
                       processing_time=0.001, error=error)


# ── DimensionScore contract ─────────────────────────────────────────────────

class TestDimensionScoreStatus:

    def test_default_status_is_scored(self):
        score = DimensionScore(name='X', value=0.7)
        assert score.status == 'scored'

    def test_to_dict_includes_status(self):
        for status in ('scored', 'unknown', 'error'):
            score = DimensionScore(name='X', value=0.5, status=status)
            d = score.to_dict()
            assert d['status'] == status

    def test_invalid_status_rejected(self):
        with pytest.raises(ValueError):
            DimensionScore(name='X', value=0.5, status='bogus')

    def test_prong_result_json_carries_status(self):
        result = make_prong('P', [('X', 0.5, True, 'unknown')])
        parsed = json.loads(result.to_json())
        assert parsed['dimensions'][0]['status'] == 'unknown'


# ── Missing evidence at the dimension level ─────────────────────────────────

class TestMissingEvidenceDimensions:

    def test_relevance_missing_prompt_is_unknown(self):
        """a) No prompt → Relevance reports unknown (no fake-prompt path)."""
        rel = Relevance()
        score = rel.evaluate(None, "Biathlon combines skiing and shooting.")
        assert score.status == 'unknown'
        assert score.metadata.get('fallback') is None

    def test_relevance_blank_prompt_is_unknown(self):
        rel = Relevance()
        score = rel.evaluate("   ", "Biathlon combines skiing and shooting.")
        assert score.status == 'unknown'

    def test_prong3_no_claims_is_unknown(self):
        """b) No claims → Factual Accuracy reports unknown, value is placeholder."""
        dim = FactualAccuracy(wikidata=OfflineWikidata())
        score = dim.evaluate("Hello world.", claims=[])
        assert score.status == 'unknown'
        assert score.value == 0.5  # display-only

    def test_prong3_no_wikidata_is_unknown(self):
        dim = FactualAccuracy(wikidata=None)
        score = dim.evaluate("Paris is the capital of France.", claims=[
            Claim(subject="Paris", predicate="be",
                  object="the capital of France",
                  source_sentence="Paris is the capital of France."),
        ])
        assert score.status == 'unknown'

    def test_prong3_all_unknown_triples_is_unknown(self):
        """verifiable == 0 → unknown, not a quality 0.5."""
        dim = FactualAccuracy(wikidata=OfflineWikidata())
        score = dim.evaluate("", claims=[
            Claim(subject="Xyzzy Nonexistent", predicate="be", object="something",
                  source_sentence="Xyzzy Nonexistent is something."),
        ])
        assert score.status == 'unknown'
        assert score.raw_value['unknown'] == 1

    def test_prong4_no_intrinsic_data_dimensions_unknown(self):
        """c) intrinsic_data=None → all four dimensions unknown."""
        result = Prong4Intrinsic().evaluate("Test text", intrinsic_data=None)
        assert result.error is None
        assert len(result.dimensions) == 4
        for dim in result.dimensions:
            assert dim.status == 'unknown'


# ── Aggregation honesty ──────────────────────────────────────────────────────

class TestAggregatorHonesty:

    def test_unknown_relevance_excluded_from_prong_average(self):
        """a) Unknown Relevance never enters the prong 1 average."""
        unknown_rel = Relevance().evaluate(None, "Some response text.")
        result = ProngResult(
            prong_name='LLM-as-Judge (Prong 1)',
            dimensions=[
                unknown_rel,
                DimensionScore(name='Semantic Coherence', value=0.9),
                DimensionScore(name='Reliability', value=0.7),
            ],
            processing_time=0.001,
        )
        agg = ScoreAggregator().aggregate_prongs([result])
        # (0.9 + 0.7) / 2 — the unknown 0.5 placeholder does not count.
        assert agg['prong_scores']['LLM-as-Judge (Prong 1)'] == pytest.approx(0.8)
        # But it is still reported for display.
        assert agg['dimension_scores']['Relevance'] == [0.5]

    def test_prong4_placeholders_omitted_not_averaged(self):
        """c) Prong 4 without IntrinsicData is omitted from prong_scores."""
        result = Prong4Intrinsic().evaluate("Test text", intrinsic_data=None)
        agg = ScoreAggregator().aggregate_prongs([result])
        assert 'Intrinsic (Prong 4)' not in agg['prong_scores']
        assert len(agg['dimension_scores']) == 4  # still reported for display

    def test_all_unknown_total_score_is_none(self):
        """d) Nothing scored → total_score is None (JSON null), coverage none."""
        results = [
            make_prong('LLM-as-Judge (Prong 1)', [('Relevance', 0.5, True, 'unknown')]),
            make_prong('Intrinsic (Prong 4)', [('Uncertainty', 0.5, True, 'unknown')]),
        ]
        agg = ScoreAggregator().aggregate_prongs(results)
        assert agg['total_score'] is None
        assert agg['metadata']['coverage'] == 'none'
        # Serializes as JSON null, not 0.5.
        assert '"total_score": null' in json.dumps(agg)

    def test_error_status_excluded_too(self):
        results = [
            make_prong('LLM-as-Judge (Prong 1)', [('Toxicity', 0.0, True, 'error')]),
        ]
        agg = ScoreAggregator().aggregate_prongs(results)
        assert agg['prong_scores'] == {}
        assert agg['total_score'] is None

    def test_mixed_scored_and_unknown(self):
        """e) Only scored dimensions contribute; totals renormalize."""
        results = [
            make_prong('LLM-as-Judge (Prong 1)', [
                ('Relevance', 0.5, True, 'unknown'),
                ('Semantic Coherence', 0.8, True, 'scored'),
            ]),
            make_prong('Intrinsic (Prong 4)', [
                ('Uncertainty', 0.5, True, 'unknown'),
            ]),
        ]
        agg = ScoreAggregator().aggregate_prongs(results)
        # Only prong 1 scored, with its single scored dimension.
        assert agg['prong_scores'] == {'LLM-as-Judge (Prong 1)': pytest.approx(0.8)}
        # Total renormalizes over the prongs that scored: 0.8, not dragged
        # down (or padded) by the all-unknown prong 4.
        assert agg['total_score'] == pytest.approx(0.8)
        assert agg['metadata']['coverage'] == 'partial'

    def test_full_coverage_when_all_prongs_score(self):
        results = [
            make_prong('LLM-as-Judge (Prong 1)', [('Relevance', 1.0, True, 'scored')]),
            make_prong('Rule-Based (Prong 2)', [('Fluency', 1.0, True, 'scored')]),
            make_prong('Extraction-Based (Prong 3)', [('Factual Accuracy', 1.0, True, 'scored')]),
            make_prong('Intrinsic (Prong 4)', [('Uncertainty', 1.0, True, 'scored')]),
        ]
        agg = ScoreAggregator().aggregate_prongs(results)
        assert agg['total_score'] == pytest.approx(1.0)
        assert agg['metadata']['coverage'] == 'full'

    def test_descriptive_unknowns_do_not_affect_scores(self):
        """aggregate=False dimensions stay report-only whatever their status."""
        results = [
            make_prong('Intrinsic (Prong 4)', [
                ('Uncertainty', 0.6, True, 'scored'),
                ('Token Entropy', 0.5, False, 'unknown'),
            ]),
        ]
        agg = ScoreAggregator().aggregate_prongs(results)
        assert agg['prong_scores']['Intrinsic (Prong 4)'] == pytest.approx(0.6)
        assert 'Token Entropy' in agg['dimension_scores']


# ── Pipeline metadata ─────────────────────────────────────────────────────────

class TestPipelineMetadata:

    def test_evaluate_reports_prong1_backend(self):
        """Prong 1 results carry prong1_backend=embeddings (no LLM judge claim)."""
        from src.pipeline import EvaluationPipeline

        pipeline = EvaluationPipeline(enable_prongs=[1])
        result = pipeline.evaluate(
            text="Biathlon combines skiing and rifle shooting.",
            prompt="Explain biathlon.",
        )
        assert result['metadata']['prong1_backend'] == 'embeddings'

    def test_metadata_absent_without_prong1(self):
        from src.pipeline import EvaluationPipeline

        pipeline = EvaluationPipeline(enable_prongs=[2])
        result = pipeline.evaluate(text="The cat sits on the mat.")
        assert 'metadata' not in result
