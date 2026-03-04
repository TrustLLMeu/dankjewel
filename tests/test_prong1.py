"""Tests for Prong 1 (LLM-as-Judge) evaluation."""

import pytest
from src.prongs.prong1_llm_as_judge import Prong1LLMAsJudge
from src.prongs.prong1_dimensions import Relevance, SemanticCoherence, Reliability, Toxicity
from src.models.embeddings import Embeddings
from src.models.toxicity_model import ToxicityModel


class TestRelevance:
    """Test the Relevance dimension."""

    def test_high_relevance(self):
        """Test high relevance between prompt and response."""
        rel = Relevance()
        prompt = "Explain biathlon."
        response = "Biathlon combines cross-country skiing and rifle shooting in a winter sport."
        score = rel.evaluate(prompt, response)
        assert score.value >= 0.70, f"Expected high relevance, got {score.value}"
        assert 0.0 <= score.value <= 1.0, "Score out of bounds"

    def test_low_relevance(self):
        """Test low relevance between prompt and response."""
        rel = Relevance()
        prompt = "Explain biathlon."
        response = "The stock market crashed yesterday and pizza is delicious."
        score = rel.evaluate(prompt, response)
        assert score.value <= 0.75, f"Expected low relevance, got {score.value}"
        assert 0.0 <= score.value <= 1.0, "Score out of bounds"

    def test_fallback_no_prompt(self):
        """Test fallback when no prompt is provided."""
        rel = Relevance()
        response = "Biathlon combines skiing and shooting."
        score = rel.evaluate(None, response)
        assert 0.0 <= score.value <= 1.0, "Score out of bounds"
        assert score.metadata.get('fallback') == True, "Expected fallback mode"


class TestSemanticCoherence:
    """Test the Semantic Coherence dimension."""

    def test_coherent_text(self):
        """Test coherent multi-sentence text."""
        coh = SemanticCoherence()
        response = "Biathlon combines cross-country skiing and rifle shooting. It is a winter sport. Athletes must excel at both disciplines."
        score = coh.evaluate(response)
        assert score.value >= 0.60, f"Expected high coherence, got {score.value}"
        assert 0.0 <= score.value <= 1.0, "Score out of bounds"

    def test_incoherent_text(self):
        """Test incoherent text with unrelated sentences."""
        coh = SemanticCoherence()
        response = "Biathlon combines skiing and shooting. The pizza is delicious. Cars are fast."
        score = coh.evaluate(response)
        # Incoherent text should have lower coherence
        assert 0.0 <= score.value <= 1.0, "Score out of bounds"

    def test_short_text(self):
        """Test short single-sentence text (should score high by default)."""
        coh = SemanticCoherence()
        response = "Biathlon is a winter sport."
        score = coh.evaluate(response)
        assert score.value >= 0.9, f"Expected high coherence for short text, got {score.value}"


class TestReliability:
    """Test the Reliability dimension."""

    def test_single_response_consistent(self):
        """Test single response with internal consistency."""
        rel = Reliability()
        responses = ["Biathlon combines skiing and shooting. Both disciplines are important. Athletes train extensively."]
        score = rel.evaluate(responses)
        assert 0.0 <= score.value <= 1.0, "Score out of bounds"

    def test_multiple_consistent_responses(self):
        """Test multiple very similar responses (high reliability)."""
        rel = Reliability()
        responses = [
            "Biathlon combines cross-country skiing and rifle shooting.",
            "Biathlon is a sport combining skiing and shooting."
        ]
        score = rel.evaluate(responses)
        assert score.value >= 0.60, f"Expected high reliability for consistent responses, got {score.value}"

    def test_multiple_diverse_responses(self):
        """Test multiple very different responses (low reliability)."""
        rel = Reliability()
        responses = [
            "Biathlon combines skiing and shooting.",
            "The sky is blue and the grass is green."
        ]
        score = rel.evaluate(responses)
        # Diverse responses should have lower reliability
        assert 0.0 <= score.value <= 1.0, "Score out of bounds"


class TestToxicity:
    """Test the Toxicity dimension."""

    def test_toxic_text(self):
        """Test clearly toxic text."""
        tox = Toxicity()
        response = "You are such a moron!"
        score = tox.evaluate(response)
        assert score.value >= 0.70, f"Expected high toxicity, got {score.value}"
        assert 0.0 <= score.value <= 1.0, "Score out of bounds"

    def test_non_toxic_text(self):
        """Test non-toxic text."""
        tox = Toxicity()
        response = "Biathlon is an interesting winter sport."
        score = tox.evaluate(response)
        assert score.value <= 0.30, f"Expected low toxicity, got {score.value}"
        assert 0.0 <= score.value <= 1.0, "Score out of bounds"


class TestProng1Integration:
    """Integration tests for full Prong1 evaluator."""

    def test_prong1_basic_evaluation(self):
        """Test basic Prong 1 evaluation."""
        prong = Prong1LLMAsJudge()
        prompt = "Explain biathlon."
        response = "Biathlon combines cross-country skiing and rifle shooting in a winter sport."
        result = prong.evaluate(response, prompt=prompt)

        assert result.prong_name == "LLM-as-Judge (Prong 1)"
        assert len(result.dimensions) == 4, f"Expected 4 dimensions, got {len(result.dimensions)}"
        assert result.error is None

        # Check all scores are in [0,1]
        for dim in result.dimensions:
            assert 0.0 <= dim.value <= 1.0, f"Dimension {dim.name} score out of bounds: {dim.value}"

    def test_prong1_with_multiple_responses(self):
        """Test Prong 1 with multiple responses for reliability."""
        prong = Prong1LLMAsJudge()
        prompt = "Explain biathlon."
        responses = [
            "Biathlon combines skiing and shooting.",
            "Biathlon is a winter sport with skiing and shooting."
        ]
        result = prong.evaluate(responses[0], prompt=prompt, responses=responses)

        assert result.prong_name == "LLM-as-Judge (Prong 1)"
        assert result.error is None

        # Find reliability dimension
        rel_dim = [d for d in result.dimensions if d.name == "Reliability"][0]
        assert rel_dim.value >= 0.50, f"Expected reasonable reliability, got {rel_dim.value}"

    def test_prong1_to_json(self):
        """Test JSON serialization of Prong 1 results."""
        prong = Prong1LLMAsJudge()
        response = "Biathlon combines skiing and shooting."
        result = prong.evaluate(response)

        json_str = result.to_json()
        assert "LLM-as-Judge" in json_str
        assert "dimensions" in json_str
        assert "Relevance" in json_str or "Toxicity" in json_str


class TestModelWrappers:
    """Test the model wrapper classes directly."""

    def test_embeddings_initialization(self):
        """Test embeddings model initialization."""
        emb = Embeddings()
        assert emb.model_name == "sentence-transformers/all-MiniLM-L6-v2"

    def test_embeddings_single(self):
        """Test embedding a single text."""
        emb = Embeddings()
        emb_vec = emb.embed_texts(["Hello world"])
        assert emb_vec.shape == (1, 384), f"Expected shape (1, 384), got {emb_vec.shape}"

    def test_embeddings_batch(self):
        """Test embedding multiple texts."""
        emb = Embeddings()
        texts = ["Hello world", "Goodbye world", "Another test"]
        emb_vecs = emb.embed_texts(texts)
        assert emb_vecs.shape == (3, 384), f"Expected shape (3, 384), got {emb_vecs.shape}"

    def test_cosine_similarity(self):
        """Test cosine similarity calculation."""
        import numpy as np
        emb = Embeddings()
        a = np.array([1.0, 0.0])
        b = np.array([1.0, 0.0])
        sim = emb.cosine_sim(a, b)
        assert abs(sim - 1.0) < 0.01, f"Expected ~1.0 similarity, got {sim}"

    def test_toxicity_model_initialization(self):
        """Test toxicity model initialization."""
        tox = ToxicityModel()
        assert tox.model_name == "unitary/toxic-bert"

    def test_toxicity_scoring(self):
        """Test toxicity scoring."""
        tox = ToxicityModel()
        result = tox.score("You are a moron!")
        assert 'probability' in result
        assert 'raw_logits' in result
        assert 0.0 <= result['probability'] <= 1.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

