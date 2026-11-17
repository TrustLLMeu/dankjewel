"""Stage 1/2: assumption-scored dimensions abstain; language is explicit."""

import pytest
from pydantic import ValidationError

from src.api import EvaluateRequest
from src.pipeline import EvaluationPipeline


def test_empty_text_has_no_total():
    pipeline = EvaluationPipeline(enable_prongs=[1, 2, 3, 4])
    result = pipeline.evaluate(text="", prompt="test")
    assert result["prong_results"] == []
    assert result["aggregated_scores"]["total_score"] is None
    assert result["metadata"]["empty_text"] is True
    assert result["coverage"]["prongs_scored"] == 0


def test_short_text_coherence_and_reliability_abstain():
    pipeline = EvaluationPipeline(enable_prongs=[1])
    result = pipeline.evaluate(text="Paris is the capital of France.", prompt="test")
    dims = {d["name"]: d for d in result["prong_results"][0]["dimensions"]}
    assert dims["Semantic Coherence"]["status"] == "unknown"
    assert dims["Reliability"]["status"] == "unknown"
    # Relevance is still a real embedding measurement for a non-blank answer.
    assert dims["Relevance"]["status"] == "scored"


def test_flat_earth_does_not_get_a_perfect_factual_prong():
    pipeline = EvaluationPipeline(enable_prongs=[3])
    result = pipeline.evaluate(text="The Earth is flat.", prompt="Is the Earth flat?")
    dims = {d["name"]: d for d in result["prong_results"][0]["dimensions"]}
    assert dims["Factual Accuracy"]["status"] == "unknown"
    assert dims["Factual Consistency"]["status"] == "unknown"
    assert "Extraction-Based (Prong 3)" not in result["aggregated_scores"]["prong_scores"]


def test_denied_single_claim_scores_zero_not_half():
    pipeline = EvaluationPipeline(enable_prongs=[3])
    result = pipeline.evaluate(text="Paris is the capital of Germany.", prompt="test")
    assert result["aggregated_scores"]["prong_scores"]["Extraction-Based (Prong 3)"] == 0.0
    dims = {d["name"]: d for d in result["prong_results"][0]["dimensions"]}
    assert dims["Factual Accuracy"]["value"] == 0.0
    assert dims["Factual Consistency"]["status"] == "unknown"


def test_language_is_recorded_and_reaches_lexicons():
    pipeline = EvaluationPipeline(enable_prongs=[2])
    result = pipeline.evaluate(text="De kat zit op de mat.", prompt="test", lang="nl")
    assert result["metadata"]["language"] == "nl"
    dims = {d["name"]: d for d in result["prong_results"][0]["dimensions"]}
    assert dims["Fluency"]["metadata"]["lang"] == "nl"


def test_unsupported_language_is_rejected():
    with pytest.raises(ValidationError):
        EvaluateRequest(text="Hello", language="xx")


def test_blank_text_is_rejected_by_the_request_model():
    with pytest.raises(ValidationError):
        EvaluateRequest(text="   ")
