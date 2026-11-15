"""Tests for Prong 2 (Rule-Based) evaluation."""

import pytest
from src.prongs.prong2_rule_based import Prong2RuleBased
from src.resources.lexicon_manager import lexicon_manager, REQUIRED_KEYS


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


def test_prong2_with_language():
    """Test Prong 2 evaluation with explicit lang='en' kwarg."""
    prong = Prong2RuleBased()

    text = "Please help me, thank you kindly."
    result = prong.evaluate(text, lang="en")

    assert result.prong_name == "Rule-Based (Prong 2)"
    assert result.error is None
    assert len(result.dimensions) > 0

    # Politeness should detect cues
    politeness = next(d for d in result.dimensions if d.name == "Politeness")
    assert politeness.value > 0.5
    assert politeness.metadata.get('lang') == 'en'


def test_prong2_lexicon_fallback():
    """Test that a nonexistent language falls back to English without error."""
    lexicon_manager.clear_cache()
    prong = Prong2RuleBased()

    text = "Please help me."
    result = prong.evaluate(text, lang="xx")

    assert result.error is None
    assert len(result.dimensions) > 0

    # Should still detect English politeness cues via fallback
    politeness = next(d for d in result.dimensions if d.name == "Politeness")
    assert politeness.value > 0.5


def test_prong2_dutch_lexicon():
    """Test Prong 2 evaluation with Dutch lexicon."""
    lexicon_manager.clear_cache()
    prong = Prong2RuleBased()

    text = "Alstublieft, dank u wel."
    result = prong.evaluate(text, lang="nl")

    assert result.error is None
    assert len(result.dimensions) > 0

    # Dutch politeness cues should be detected
    politeness = next(d for d in result.dimensions if d.name == "Politeness")
    assert politeness.metadata.get('lang') == 'nl'
    assert politeness.metadata.get('politeness_cues', 0) > 0


def test_lexicon_validation():
    """Test that the English lexicon has all required keys with valid data."""
    lexicon_manager.clear_cache()
    data = lexicon_manager.load_language("en")

    for key in REQUIRED_KEYS:
        assert key in data, f"Missing required key: {key}"
        assert isinstance(data[key], list), f"Key '{key}' should be a list"
        assert len(data[key]) > 0, f"Key '{key}' should not be empty"
        for item in data[key]:
            assert isinstance(item, str), f"Items in '{key}' should be strings"


def test_lexicon_all_languages():
    """Test that all supported language lexicons load and validate."""
    lexicon_manager.clear_cache()
    languages = ['en', 'da', 'nl', 'fo', 'de', 'is', 'nb', 'nn', 'sv']

    for lang in languages:
        data = lexicon_manager.load_language(lang)
        for key in REQUIRED_KEYS:
            assert key in data, f"Lang '{lang}': missing key '{key}'"
            assert isinstance(data[key], list), f"Lang '{lang}': key '{key}' not a list"


def test_fluency_formula_metadata():
    """Test that FluidityDimension returns the correct formula name per language."""
    from src.dimensions.prong2_dimensions import FluidityDimension

    dim = FluidityDimension()
    text = "The cat sits on the mat. The dog runs in the park."

    expected = {
        'en': 'Flesch Reading Ease',
        'de': 'Flesch-Amstad',
        'nl': 'Flesch-Douma',
        'sv': 'Flesch-Matricciani (Pan-Germanic)',
        'da': 'Flesch-Matricciani (Pan-Germanic)',
        'nb': 'Flesch-Matricciani (Pan-Germanic)',
        'nn': 'Flesch-Matricciani (Pan-Germanic)',
        'fo': 'Flesch-Matricciani (Pan-Germanic)',
        'is': 'Flesch-Matricciani (Pan-Germanic)',
    }

    for lang, formula_name in expected.items():
        score = dim.evaluate(text, lang=lang)
        assert score.metadata.get('formula') == formula_name, \
            f"lang={lang}: expected '{formula_name}', got '{score.metadata.get('formula')}'"
        assert score.metadata.get('lang') == lang


def test_fluency_german_vs_english():
    """Test that German and English Flesch coefficients produce different raw scores."""
    from src.dimensions.prong2_dimensions import FluidityDimension

    dim = FluidityDimension()
    # German text with multi-syllable compounds
    text = "Die Schmetterlingswanderung findet jährlich statt. Die Wissenschaftler beobachten das Naturphänomen."

    score_en = dim.evaluate(text, lang='en')
    score_de = dim.evaluate(text, lang='de')

    # Both should produce valid scores
    assert 0.0 <= score_en.value <= 1.0
    assert 0.0 <= score_de.value <= 1.0

    # The raw scores must differ because the coefficients differ
    assert score_en.raw_value != score_de.raw_value, \
        "German and English coefficients should produce different raw Flesch scores"

    # German coefficients have a lower ASW weight (58.5 vs 84.6), so for
    # polysyllabic German text, the German formula should be more lenient
    assert score_de.raw_value > score_en.raw_value, \
        "Flesch-Amstad should score higher than English Flesch for polysyllabic German text"


def test_fluency_metadata_fields():
    """Test that fluency scores include word/sentence/syllable counts in metadata."""
    from src.dimensions.prong2_dimensions import FluidityDimension

    dim = FluidityDimension()
    text = "The cat sits on the mat. The dog runs in the park."
    score = dim.evaluate(text, lang='en')

    assert 'words' in score.metadata
    assert 'sentences' in score.metadata
    assert 'syllables' in score.metadata
    assert score.metadata['words'] > 0
    assert score.metadata['sentences'] > 0
    assert score.metadata['syllables'] > 0


def test_lexical_diversity_worked_example():
    """The worked example in docs/EXTENSIBILITY.md stays wired in."""
    from src.dimensions.prong2_dimensions import LexicalDiversity

    dim = LexicalDiversity()
    score = dim.evaluate("The cat sat on the mat.")

    assert score.name == "Lexical Diversity"
    assert score.aggregate is False
    assert score.status == "scored"
    assert abs(score.value - 5 / 6) < 1e-6
    assert score.metadata["tokens"] == 6
    assert score.metadata["types"] == 5
    src = score.metadata["evidence_sources"]["rules"]
    assert src["status"] == "scored" and src["n"] == 6


def test_lexical_diversity_empty_text_is_unknown():
    """No tokens -> unknown, never a numeric score."""
    from src.dimensions.prong2_dimensions import LexicalDiversity

    score = LexicalDiversity().evaluate("")
    assert score.status == "unknown"
    assert score.metadata["evidence_sources"]["rules"]["status"] == "unknown"


def test_language_diversity_registered_in_prong2():
    """The new dimension is part of Prong 2's dimension registry."""
    prong = Prong2RuleBased()
    assert "Lexical Diversity" in prong.dimensions
