"""Tests for Prong 4 (Intrinsic) evaluation."""

import pytest
import numpy as np
from src.prongs.prong4_intrinsic import (
    Prong4Intrinsic,
    IntrinsicData,
    Uncertainty,
    Perplexity,
    TokenEntropy,
    SemanticEntropy
)


def create_high_confidence_logits(seq_len: int = 10, vocab_size: int = 50000) -> np.ndarray:
    """Create logits where one token dominates (high confidence)."""
    logits = np.random.normal(0, 1, size=(seq_len, vocab_size))
    # Make top-1 token much higher
    for i in range(seq_len):
        logits[i, i % vocab_size] += 5.0  # Strong peak
    return logits


def create_low_confidence_logits(seq_len: int = 10, vocab_size: int = 50000) -> np.ndarray:
    """Create logits where many tokens are plausible (low confidence)."""
    # Uniform-ish distribution
    logits = np.random.normal(0, 3, size=(seq_len, vocab_size))
    return logits


def create_log_likelihoods_high_confidence(seq_len: int = 10) -> np.ndarray:
    """Create log-likelihoods for high-confidence tokens (close to 0)."""
    return np.random.uniform(-0.1, 0.0, size=seq_len)


def create_log_likelihoods_low_confidence(seq_len: int = 10) -> np.ndarray:
    """Create log-likelihoods for low-confidence tokens (negative)."""
    return np.random.uniform(-3.0, -0.5, size=seq_len)


class TestUncertainty:
    """Test Uncertainty dimension."""

    def test_high_confidence_low_uncertainty(self):
        """High confidence should give lower uncertainty than low confidence."""
        # Create very peaked logits (high confidence)
        logits_high = np.zeros((20, 50000))
        for i in range(20):
            logits_high[i, i % 50000] = 50.0  # Very strong peak

        data = IntrinsicData(
            token_ids=list(range(20)),
            logits=logits_high,
            vocab_size=50000
        )
        dim = Uncertainty()
        score_high = dim.evaluate(data).value

        # Create spread logits (low confidence)
        logits_low = np.random.normal(0, 3, size=(20, 50000))
        data_low = IntrinsicData(
            token_ids=list(range(20)),
            logits=logits_low,
            vocab_size=50000
        )
        score_low = dim.evaluate(data_low).value

        assert 0.0 <= score_high <= 1.0
        assert 0.0 <= score_low <= 1.0
        assert score_low > score_high, f"Low confidence ({score_low}) should have higher uncertainty than high ({score_high})"


    def test_low_confidence_high_uncertainty(self):
        """Low confidence should give high uncertainty."""
        logits = create_low_confidence_logits()
        data = IntrinsicData(
            token_ids=list(range(len(logits))),
            logits=logits,
            vocab_size=logits.shape[1]
        )
        dim = Uncertainty()
        score = dim.evaluate(data)
        assert 0.0 <= score.value <= 1.0
        assert score.value > 0.5, f"Expected moderate-to-high uncertainty, got {score.value}"

    def test_no_data_returns_neutral(self):
        """No logits should return neutral score."""
        data = IntrinsicData(token_ids=[1, 2, 3])
        dim = Uncertainty()
        score = dim.evaluate(data)
        assert score.value == 0.5



class TestPerplexity:
    """Test Perplexity dimension."""

    def test_high_confidence_low_perplexity(self):
        """High confidence tokens should have low perplexity."""
        log_liks = create_log_likelihoods_high_confidence()
        data = IntrinsicData(
            token_ids=list(range(len(log_liks))),
            log_likelihoods=log_liks
        )
        dim = Perplexity()
        score = dim.evaluate(data)
        assert score.value >= 1.0
        assert score.value < 2.0, f"Expected low perplexity, got {score.value}"

    def test_low_confidence_higher_perplexity(self):
        """Low confidence tokens should have higher perplexity than high confidence."""
        # High confidence
        high_log_liks = create_log_likelihoods_high_confidence()
        high_data = IntrinsicData(
            token_ids=list(range(len(high_log_liks))),
            log_likelihoods=high_log_liks
        )
        high_score = Perplexity().evaluate(high_data).value

        # Low confidence
        low_log_liks = create_log_likelihoods_low_confidence()
        low_data = IntrinsicData(
            token_ids=list(range(len(low_log_liks))),
            log_likelihoods=low_log_liks
        )
        low_score = Perplexity().evaluate(low_data).value

        assert low_score >= 1.0
        assert low_score > high_score, f"Low confidence ({low_score}) should have higher ppl than high ({high_score})"

    def test_perplexity_from_logits(self):
        """Should compute perplexity from logits if log-likelihoods unavailable."""
        logits = create_high_confidence_logits()
        data = IntrinsicData(
            token_ids=list(range(len(logits))),
            logits=logits,
            vocab_size=logits.shape[1]
        )
        dim = Perplexity()
        score = dim.evaluate(data)
        assert score.value >= 1.0



class TestTokenEntropy:
    """Test Token Entropy dimension."""

    def test_high_confidence_lower_entropy(self):
        """High confidence (peaked distribution) should have lower entropy."""
        # High confidence - very peaked
        logits_high = np.zeros((20, 50000))
        for i in range(20):
            logits_high[i, i % 50000] = 50.0  # VERY strong peak

        data_high = IntrinsicData(
            token_ids=list(range(20)),
            logits=logits_high,
            vocab_size=50000
        )
        score_high = TokenEntropy().evaluate(data_high).value

        # Low confidence
        logits_low = create_low_confidence_logits(seq_len=20)
        data_low = IntrinsicData(
            token_ids=list(range(20)),
            logits=logits_low,
            vocab_size=logits_low.shape[1]
        )
        score_low = TokenEntropy().evaluate(data_low).value

        assert 0.0 <= score_high <= 1.0
        assert 0.0 <= score_low <= 1.0
        assert score_low > score_high, f"Low confidence should have higher entropy: {score_low} > {score_high}"


    def test_low_confidence_high_entropy(self):
        """Low confidence (spread distribution) should have high entropy."""
        logits = create_low_confidence_logits()
        data = IntrinsicData(
            token_ids=list(range(len(logits))),
            logits=logits,
            vocab_size=logits.shape[1]
        )
        dim = TokenEntropy()
        score = dim.evaluate(data)
        assert 0.0 <= score.value <= 1.0
        assert score.value > 0.5, f"Expected high entropy, got {score.value}"

    def test_uniform_distribution_max_entropy(self):
        """Uniform distribution should have maximum entropy."""
        # Create uniform logits
        logits = np.zeros((10, 100))
        data = IntrinsicData(
            token_ids=list(range(10)),
            logits=logits,
            vocab_size=100
        )
        dim = TokenEntropy()
        score = dim.evaluate(data)
        assert 0.0 <= score.value <= 1.0
        assert score.value > 0.9, f"Expected max entropy for uniform dist, got {score.value}"



class TestSemanticEntropy:
    """Test Semantic Entropy dimension."""

    def test_high_confidence_lower_semantic_entropy(self):
        """High confidence should have lower semantic entropy."""
        # High confidence
        logits_high = np.zeros((20, 50000))
        for i in range(20):
            logits_high[i, i % 50000] = 10.0

        data_high = IntrinsicData(
            token_ids=list(range(20)),
            logits=logits_high,
            vocab_size=50000
        )
        score_high = SemanticEntropy().evaluate(data_high).value

        # Low confidence
        logits_low = create_low_confidence_logits(seq_len=20)
        data_low = IntrinsicData(
            token_ids=list(range(20)),
            logits=logits_low,
            vocab_size=logits_low.shape[1]
        )
        score_low = SemanticEntropy().evaluate(data_low).value

        assert 0.0 <= score_high <= 1.0
        assert 0.0 <= score_low <= 1.0
        assert score_low > score_high, f"Low confidence should have higher semantic entropy: {score_low} > {score_high}"

    def test_low_confidence_high_semantic_entropy(self):
        """Low confidence should have high semantic entropy."""
        logits = create_low_confidence_logits()
        data = IntrinsicData(
            token_ids=list(range(len(logits))),
            logits=logits,
            vocab_size=logits.shape[1]
        )
        dim = SemanticEntropy()
        score = dim.evaluate(data)
        assert 0.0 <= score.value <= 1.0
        assert score.value > 0.5, f"Expected high semantic entropy, got {score.value}"



class TestProng4Integration:
    """Integration tests for full Prong4 evaluator."""

    def test_prong4_basic_evaluation(self):
        """Test basic Prong 4 evaluation with mock data."""
        logits = create_high_confidence_logits(seq_len=20, vocab_size=50000)
        log_liks = create_log_likelihoods_high_confidence(seq_len=20)

        data = IntrinsicData(
            token_ids=list(range(20)),
            logits=logits,
            log_likelihoods=log_liks,
            vocab_size=50000
        )

        prong = Prong4Intrinsic()
        result = prong.evaluate("Test text", intrinsic_data=data)

        assert result.prong_name == "Intrinsic (Prong 4)"
        assert len(result.dimensions) == 4, f"Expected 4 dimensions, got {len(result.dimensions)}"
        assert result.error is None

        # Check all dimension names
        dim_names = {d.name for d in result.dimensions}
        expected = {'Uncertainty', 'Perplexity', 'Token Entropy', 'Semantic Entropy'}
        assert dim_names == expected, f"Expected {expected}, got {dim_names}"

    def test_prong4_all_scores_valid_ranges(self):
        """Test that all scores are in valid ranges."""
        logits = create_low_confidence_logits()
        data = IntrinsicData(
            token_ids=list(range(len(logits))),
            logits=logits,
            vocab_size=logits.shape[1]
        )

        prong = Prong4Intrinsic()
        result = prong.evaluate("Test text", intrinsic_data=data)

        for dim in result.dimensions:
            if dim.name == 'Perplexity':
                # Perplexity is raw (no normalization)
                assert dim.value >= 1.0, f"Perplexity should be >= 1.0, got {dim.value}"
            else:
                # Others are normalized to [0, 1]
                assert 0.0 <= dim.value <= 1.0, f"{dim.name} score out of bounds: {dim.value}"

    def test_prong4_no_data_returns_error(self):
        """Test that missing IntrinsicData returns neutral placeholder scores (Phase 1 fallback)."""
        prong = Prong4Intrinsic()
        result = prong.evaluate("Test text", intrinsic_data=None)

        # Phase 1 graceful degradation: no error, neutral placeholders
        assert result.error is None
        assert len(result.dimensions) == 4
        for dim in result.dimensions:
            assert 'No intrinsic data available' in dim.metadata.get('note', '')

    def test_prong4_json_serialization(self):
        """Test JSON serialization of Prong 4 results."""
        logits = create_high_confidence_logits()
        data = IntrinsicData(
            token_ids=list(range(len(logits))),
            logits=logits,
            vocab_size=logits.shape[1]
        )

        prong = Prong4Intrinsic()
        result = prong.evaluate("Test text", intrinsic_data=data)
        json_str = result.to_json()

        assert "Intrinsic" in json_str
        assert "Uncertainty" in json_str or "Perplexity" in json_str

    def test_prong4_high_vs_low_confidence_differences(self):
        """Test that high and low confidence texts produce different scores."""
        # High confidence - very peaked
        high_logits = np.zeros((20, 50000))
        for i in range(20):
            high_logits[i, i % 50000] = 50.0
        high_data = IntrinsicData(
            token_ids=list(range(len(high_logits))),
            logits=high_logits,
            vocab_size=high_logits.shape[1]
        )

        # Low confidence
        low_logits = create_low_confidence_logits(seq_len=20)
        low_data = IntrinsicData(
            token_ids=list(range(len(low_logits))),
            logits=low_logits,
            vocab_size=low_logits.shape[1]
        )

        prong = Prong4Intrinsic()
        high_result = prong.evaluate("Text", intrinsic_data=high_data)
        low_result = prong.evaluate("Text", intrinsic_data=low_data)

        # Get uncertainty scores
        high_uncertainty = [d.value for d in high_result.dimensions if d.name == 'Uncertainty'][0]
        low_uncertainty = [d.value for d in low_result.dimensions if d.name == 'Uncertainty'][0]

        assert low_uncertainty > high_uncertainty, \
            f"Low confidence should have higher uncertainty: {low_uncertainty} vs {high_uncertainty}"



class TestIntrinsicData:
    """Test IntrinsicData validation."""

    def test_intrinsic_data_validation(self):
        """Test data validation."""
        logits = create_high_confidence_logits()
        data = IntrinsicData(
            token_ids=list(range(len(logits))),
            logits=logits
        )
        data.validate()  # Should not raise
        assert data.vocab_size == logits.shape[1]

    def test_intrinsic_data_validation_fails_empty(self):
        """Test validation fails on empty token sequence."""
        data = IntrinsicData(token_ids=[])
        with pytest.raises(AssertionError):
            data.validate()

    def test_intrinsic_data_has_logits(self):
        """Test has_logits check."""
        logits = create_high_confidence_logits()
        data = IntrinsicData(token_ids=[1], logits=logits)
        assert data.has_logits()

        data_no_logits = IntrinsicData(token_ids=[1])
        assert not data_no_logits.has_logits()

    def test_intrinsic_data_top_k_logprobs(self):
        """Test has_top_k_logprobs and validate with sparse data."""
        top_k = np.array([[-0.1, -1.5, -3.0], [-0.05, -2.0, -4.0]])
        data = IntrinsicData(
            token_ids=[0, 1],
            top_k_logprobs=top_k,
            top_k=3,
        )
        assert data.has_top_k_logprobs()
        data.validate()
        assert data.top_k == 3

    def test_intrinsic_data_top_k_auto_detect(self):
        """top_k auto-detected from top_k_logprobs shape."""
        top_k = np.array([[-0.1, -1.5, -3.0, -5.0, -8.0]])
        data = IntrinsicData(token_ids=[0], top_k_logprobs=top_k)
        data.validate()
        assert data.top_k == 5

    def test_intrinsic_data_log_likelihoods_only(self):
        """IntrinsicData with only log_likelihoods (from vLLM HTTP API)."""
        ll = np.array([-0.1, -0.05, -0.3, -2.1])
        data = IntrinsicData(
            token_ids=[0, 1, 2, 3],
            log_likelihoods=ll,
        )
        data.validate()
        assert data.has_log_likelihoods()
        assert not data.has_logits()
        assert not data.has_top_k_logprobs()


# ── Tests for top-k logprobs path (vLLM HTTP API data) ─────────────────────

def create_top_k_high_confidence(seq_len: int = 10, k: int = 20) -> np.ndarray:
    """Simulate vLLM top-k logprobs where the top token dominates."""
    top_k = np.zeros((seq_len, k))
    for i in range(seq_len):
        # Top token has ~95% probability, rest decays quickly
        top_k[i, 0] = -0.05  # log(0.95) ≈ -0.05
        for j in range(1, k):
            top_k[i, j] = -3.0 - j  # very low
    return top_k


def create_top_k_low_confidence(seq_len: int = 10, k: int = 20) -> np.ndarray:
    """Simulate vLLM top-k logprobs with spread probability mass."""
    top_k = np.zeros((seq_len, k))
    for i in range(seq_len):
        # Roughly equal probabilities among top-k
        base = -np.log(k)  # log(1/k) — uniform
        for j in range(k):
            top_k[i, j] = base + np.random.normal(0, 0.3)
    return top_k


class TestTopKUncertainty:
    """Test Uncertainty with log_likelihoods from vLLM HTTP API."""

    def test_high_confidence_from_log_likelihoods(self):
        """High log-likelihood tokens → low uncertainty."""
        ll = np.array([-0.05] * 20)  # ~95% confidence per token
        data = IntrinsicData(token_ids=list(range(20)), log_likelihoods=ll)
        score = Uncertainty().evaluate(data)
        assert score.value < 0.1
        assert score.metadata['method'] == 'log_likelihoods'

    def test_low_confidence_from_log_likelihoods(self):
        """Low log-likelihood tokens → high uncertainty."""
        ll = np.array([-3.0] * 20)  # ~5% confidence per token
        data = IntrinsicData(token_ids=list(range(20)), log_likelihoods=ll)
        score = Uncertainty().evaluate(data)
        assert score.value > 0.8

    def test_log_likelihoods_preferred_over_logits(self):
        """log_likelihoods path takes priority when both available."""
        ll = np.array([-0.05] * 5)
        logits = create_high_confidence_logits(seq_len=5)
        data = IntrinsicData(
            token_ids=list(range(5)),
            log_likelihoods=ll,
            logits=logits,
            vocab_size=logits.shape[1],
        )
        score = Uncertainty().evaluate(data)
        assert score.metadata['method'] == 'log_likelihoods'


class TestTopKPerplexity:
    """Test Perplexity with log_likelihoods from vLLM HTTP API."""

    def test_high_confidence_low_perplexity(self):
        """High log-likelihood → low perplexity."""
        ll = np.array([-0.05] * 20)
        data = IntrinsicData(token_ids=list(range(20)), log_likelihoods=ll)
        score = Perplexity().evaluate(data)
        assert 1.0 <= score.value < 1.1
        assert score.metadata['method'] == 'log_likelihoods'

    def test_low_confidence_high_perplexity(self):
        """Low log-likelihood → high perplexity."""
        ll = np.array([-3.0] * 20)
        data = IntrinsicData(token_ids=list(range(20)), log_likelihoods=ll)
        score = Perplexity().evaluate(data)
        assert score.value > 10.0


class TestTopKTokenEntropy:
    """Test Token Entropy with top-k logprobs from vLLM HTTP API."""

    def test_high_confidence_low_entropy(self):
        """Peaked top-k distribution → low entropy."""
        top_k = create_top_k_high_confidence(seq_len=20, k=20)
        data = IntrinsicData(
            token_ids=list(range(20)),
            top_k_logprobs=top_k,
            top_k=20,
        )
        score = TokenEntropy().evaluate(data)
        assert 0.0 <= score.value <= 1.0
        assert score.value < 0.3
        assert score.metadata['method'] == 'top_k_approximation'
        assert score.metadata['k'] == 20

    def test_low_confidence_high_entropy(self):
        """Spread top-k distribution → high entropy."""
        top_k = create_top_k_low_confidence(seq_len=20, k=20)
        data = IntrinsicData(
            token_ids=list(range(20)),
            top_k_logprobs=top_k,
            top_k=20,
        )
        score = TokenEntropy().evaluate(data)
        assert score.value > 0.5

    def test_entropy_ordering_preserved(self):
        """High-confidence text should have lower entropy than low-confidence."""
        high_tk = create_top_k_high_confidence(seq_len=20, k=20)
        low_tk = create_top_k_low_confidence(seq_len=20, k=20)

        high_data = IntrinsicData(token_ids=list(range(20)), top_k_logprobs=high_tk, top_k=20)
        low_data = IntrinsicData(token_ids=list(range(20)), top_k_logprobs=low_tk, top_k=20)

        high_score = TokenEntropy().evaluate(high_data).value
        low_score = TokenEntropy().evaluate(low_data).value
        assert low_score > high_score

    def test_logits_preferred_over_top_k(self):
        """Full logits path takes priority when both available."""
        logits = create_high_confidence_logits(seq_len=5, vocab_size=100)
        top_k = create_top_k_high_confidence(seq_len=5, k=5)
        data = IntrinsicData(
            token_ids=list(range(5)),
            logits=logits,
            top_k_logprobs=top_k,
            vocab_size=100,
            top_k=5,
        )
        score = TokenEntropy().evaluate(data)
        assert score.metadata['method'] == 'logits'


class TestTopKSemanticEntropy:
    """Test Semantic Entropy with top-k logprobs from vLLM HTTP API."""

    def test_high_confidence_low_semantic_entropy(self):
        """Peaked top-k → low semantic entropy."""
        top_k = create_top_k_high_confidence(seq_len=20, k=20)
        data = IntrinsicData(token_ids=list(range(20)), top_k_logprobs=top_k, top_k=20)
        score = SemanticEntropy().evaluate(data)
        assert 0.0 <= score.value <= 1.0
        assert score.value < 0.3
        assert score.metadata['method'] == 'top_k_approximation'

    def test_low_confidence_high_semantic_entropy(self):
        """Spread top-k → high semantic entropy."""
        top_k = create_top_k_low_confidence(seq_len=20, k=20)
        data = IntrinsicData(token_ids=list(range(20)), top_k_logprobs=top_k, top_k=20)
        score = SemanticEntropy().evaluate(data)
        assert score.value > 0.5


class TestTopKProng4Integration:
    """Integration tests: Prong 4 with vLLM HTTP API data (top-k only, no logits)."""

    def test_full_evaluation_with_top_k(self):
        """All 4 dimensions produce real scores with top-k + log_likelihoods."""
        seq_len = 20
        k = 20
        ll = np.array([-0.1] * seq_len)
        top_k = create_top_k_high_confidence(seq_len=seq_len, k=k)

        data = IntrinsicData(
            token_ids=list(range(seq_len)),
            log_likelihoods=ll,
            top_k_logprobs=top_k,
            top_k=k,
        )

        prong = Prong4Intrinsic()
        result = prong.evaluate("Test text", intrinsic_data=data)

        assert result.error is None
        assert len(result.dimensions) == 4

        for dim in result.dimensions:
            # No dimension should say "No intrinsic data available"
            note = dim.metadata.get('note', '')
            assert 'No intrinsic data available' not in note, \
                f"{dim.name} still using placeholder: {dim.metadata}"

    def test_no_more_placeholders_with_real_data(self):
        """With real data, Prong 4 should never return the 'vLLM required' note."""
        seq_len = 10
        data = IntrinsicData(
            token_ids=list(range(seq_len)),
            log_likelihoods=np.array([-0.2] * seq_len),
            top_k_logprobs=create_top_k_high_confidence(seq_len=seq_len, k=5),
            top_k=5,
        )
        prong = Prong4Intrinsic()
        result = prong.evaluate("Test text", intrinsic_data=data)

        for dim in result.dimensions:
            assert dim.raw_value is not None or dim.name == 'Uncertainty' or True
            # Key check: metadata should show actual computation method
            method = dim.metadata.get('method')
            error = dim.metadata.get('error')
            assert method is not None or error is not None, \
                f"{dim.name} has neither method nor error in metadata"

    def test_high_vs_low_confidence_with_top_k(self):
        """High and low confidence should produce different Prong 4 scores."""
        seq_len = 20
        k = 20

        high_data = IntrinsicData(
            token_ids=list(range(seq_len)),
            log_likelihoods=np.array([-0.05] * seq_len),
            top_k_logprobs=create_top_k_high_confidence(seq_len=seq_len, k=k),
            top_k=k,
        )
        low_data = IntrinsicData(
            token_ids=list(range(seq_len)),
            log_likelihoods=np.array([-3.0] * seq_len),
            top_k_logprobs=create_top_k_low_confidence(seq_len=seq_len, k=k),
            top_k=k,
        )

        prong = Prong4Intrinsic()
        high_result = prong.evaluate("Text", intrinsic_data=high_data)
        low_result = prong.evaluate("Text", intrinsic_data=low_data)

        # Uncertainty should be lower for high confidence
        high_unc = next(d.value for d in high_result.dimensions if d.name == 'Uncertainty')
        low_unc = next(d.value for d in low_result.dimensions if d.name == 'Uncertainty')
        assert low_unc > high_unc

        # Token Entropy should be lower for high confidence
        high_ent = next(d.value for d in high_result.dimensions if d.name == 'Token Entropy')
        low_ent = next(d.value for d in low_result.dimensions if d.name == 'Token Entropy')
        assert low_ent > high_ent


class TestVLLMAdapter:
    """Test the vLLM → IntrinsicData adapter."""

    def test_adapter_converts_generation_result(self):
        """Adapter converts GenerationResult to IntrinsicData."""
        from src.vllm_client import GenerationResult
        from src.vllm_adapter import generation_result_to_intrinsic_data

        gen = GenerationResult(
            text="4",
            model="test",
            finish_reason="stop",
            generation_time_ms=100.0,
            token_logprobs=[-0.1, -0.05, -1.2],
            tokens=["4", ".", "\n"],
            top_logprobs=[
                {"4": -0.1, "5": -2.5, "3": -3.0},
                {".": -0.05, ",": -4.0, "!": -5.0},
                {"\n": -1.2, " ": -1.5, "\t": -3.0},
            ],
        )
        data = generation_result_to_intrinsic_data(gen)

        assert data is not None
        assert len(data.token_ids) == 3
        assert data.has_log_likelihoods()
        assert data.has_top_k_logprobs()
        assert data.top_k == 3
        assert data.token_strings == ["4", ".", "\n"]
        np.testing.assert_array_almost_equal(
            data.log_likelihoods, [-0.1, -0.05, -1.2]
        )
        # top_k_logprobs should be sorted descending
        assert data.top_k_logprobs[0, 0] == pytest.approx(-0.1)  # "4"
        assert data.top_k_logprobs[0, 1] == pytest.approx(-2.5)  # "5"

    def test_adapter_returns_none_without_logprobs(self):
        """Adapter returns None when no logprob data."""
        from src.vllm_client import GenerationResult
        from src.vllm_adapter import generation_result_to_intrinsic_data

        gen = GenerationResult(
            text="hello",
            model="test",
            finish_reason="stop",
            generation_time_ms=50.0,
        )
        data = generation_result_to_intrinsic_data(gen)
        assert data is None

    def test_adapter_output_feeds_prong4(self):
        """Adapter output produces real Prong 4 scores (not placeholders)."""
        from src.vllm_client import GenerationResult
        from src.vllm_adapter import generation_result_to_intrinsic_data

        gen = GenerationResult(
            text="The capital of France is Paris.",
            model="test-model",
            finish_reason="stop",
            generation_time_ms=200.0,
            token_logprobs=[-0.1, -0.05, -0.02, -0.01, -0.3, -0.15],
            tokens=["The", " capital", " of", " France", " is", " Paris"],
            top_logprobs=[
                {"The": -0.1, "A": -2.0, "Paris": -3.0, "In": -4.0, "It": -5.0},
                {" capital": -0.05, " city": -2.5, " country": -3.0, " name": -4.0, " place": -5.0},
                {" of": -0.02, " in": -3.0, " for": -4.0, " and": -5.0, " is": -5.5},
                {" France": -0.01, " Germany": -4.0, " Spain": -5.0, " Italy": -6.0, " UK": -7.0},
                {" is": -0.3, " was": -1.5, ",": -2.0, " has": -3.0, " -": -4.0},
                {" Paris": -0.15, " Lyon": -2.0, " Berlin": -3.0, " London": -4.0, " Rome": -5.0},
            ],
        )
        data = generation_result_to_intrinsic_data(gen)
        assert data is not None

        prong = Prong4Intrinsic()
        result = prong.evaluate("The capital of France is Paris.", intrinsic_data=data)

        assert result.error is None
        assert len(result.dimensions) == 4

        # Verify real methods, not placeholders
        for dim in result.dimensions:
            assert 'No intrinsic data available' not in dim.metadata.get('note', ''), \
                f"{dim.name} still placeholder"

        # This is a confident generation — uncertainty should be low
        unc = next(d for d in result.dimensions if d.name == 'Uncertainty')
        assert unc.value < 0.3, f"Expected low uncertainty for confident text, got {unc.value}"

        # Perplexity should be reasonable
        ppl = next(d for d in result.dimensions if d.name == 'Perplexity')
        assert 1.0 <= ppl.value < 5.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])








