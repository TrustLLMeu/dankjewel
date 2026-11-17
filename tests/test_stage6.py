"""Stage 6: Top-k entropy, KB provenance, coverage split, prong metadata."""

import numpy as np

from src.base import DimensionScore, ProngResult
from src.evidence import compute_coverage
from src.pipeline import EvaluationPipeline
from src.prongs.prong4_intrinsic import (
    IntrinsicData, TokenEntropy, TopKEntropy,
)


def _topk(seq_len=8, k=20):
    """Peaked top-k logprobs; the top-5 head differs from the full top-20."""
    rows = []
    for _ in range(seq_len):
        row = np.full(k, -20.0)
        row[:5] = np.array([-0.1, -2.0, -2.1, -2.2, -2.3])
        rows.append(row)
    return np.array(rows)


def test_topk_entropy_is_distinct_from_token_entropy():
    data = IntrinsicData(token_ids=list(range(8)), top_k_logprobs=_topk(), top_k=20)
    token = TokenEntropy().evaluate(data)
    topk = TopKEntropy().evaluate(data)
    assert token.metadata['k'] == 20
    assert topk.metadata['k'] == 5
    assert token.value != topk.value


def test_topk_entropy_name_and_no_semantic_claim():
    data = IntrinsicData(token_ids=list(range(8)), top_k_logprobs=_topk(), top_k=20)
    score = TopKEntropy().evaluate(data)
    assert score.name == 'Top-k Entropy'
    assert 'semantic' not in str(score.metadata).lower()


def test_coverage_exposes_confirmed_and_denied():
    fa = DimensionScore(
        name='Factual Accuracy', value=0.5,
        metadata={'num_claims': 3, 'relation_counts': {
            'confirmed': 1, 'denied': 1, 'partially_supported': 1,
            'conflated': 0, 'unknown': 0}},
        status='scored',
    )
    result = ProngResult(prong_name='Extraction-Based (Prong 3)',
                         dimensions=[fa], processing_time=0.0)
    cov = compute_coverage([result], {}, prongs_total=1)
    assert cov['claims_verified'] == 2
    assert cov['claims_confirmed'] == 1
    assert cov['claims_denied'] == 1
    assert cov['claims_partial'] == 1


def test_prong3_timing_metadata_is_serialized():
    pipeline = EvaluationPipeline(enable_prongs=[3])
    result = pipeline.evaluate(text='Paris is the capital of France.')
    prong = result['prong_results'][0]
    assert prong['metadata']['num_claims'] >= 1
    assert 'extraction_time_ms' in prong['metadata']
    assert 'verification_time_ms' in prong['metadata']
    assert 'admitted_claims' in prong['metadata']['extraction']


def test_pipeline_reports_active_kb():
    pipeline = EvaluationPipeline(enable_prongs=[3])
    result = pipeline.evaluate(text='Paris is the capital of France.')
    kb = result['metadata']['kb']
    assert kb['db_path'].endswith('wikidata_seed.db')
    assert kb['entities'] == 144
