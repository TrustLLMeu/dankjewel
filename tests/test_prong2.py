"""Tests for Prong 2 (Rule-Based) evaluation."""

import pytest
from src.prongs.prong2_rule_based import Prong2RuleBased


def test_prong2_basic_evaluation():
    """Test basic Prong 2 evaluation."""
    prong = Prong2RuleBased()

    text = "The cat sits on the mat."
    result = prong.evaluate(text)

    assert result.prong_name == "Rule-Based (Prong 2)"
    assert len(result.dimensions) > 0
    assert result.error is None

    for dimension in result.dimensions:
        assert 0.0 <= dimension.value <= 1.0


def test_prong2_fluency_dimension():
    """Test Fluency dimension."""
    prong = Prong2RuleBased()
    fluency_dim = prong.dimensions['Fluency']

    simple_text = "The cat is here."
    score = fluency_dim.evaluate(simple_text)

    assert score.name == 'Fluency'
    assert 0.0 <= score.value <= 1.0


def test_prong2_politeness_dimension():
    """Test Politeness dimension."""
    prong = Prong2RuleBased()
    politeness_dim = prong.dimensions['Politeness']

    polite_text = "Please help me."
    score = politeness_dim.evaluate(polite_text)

    assert score.name == 'Politeness'
    assert score.value > 0.5  # Should be polite


def test_prong2_to_json():
    """Test JSON output from Prong 2."""
    prong = Prong2RuleBased()
    result = prong.evaluate("The quick brown fox.")

    json_str = result.to_json()
    assert 'Rule-Based' in json_str
    assert 'dimensions' in json_str

