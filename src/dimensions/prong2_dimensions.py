"""Prong 2: Rule-Based Dimensions."""

import threading
import textstat
from nltk.sentiment import SentimentIntensityAnalyzer
from src.dimensions.base_dimension import ScorableDimension
from src.base import DimensionScore
from src.resources.lexicon_manager import lexicon_manager
from src.config import (
    FLESCH_COEFFICIENTS, FLESCH_PAN_GERMANIC,
    TEXTSTAT_LANG_MAP,
    FLESCH_FORMULA_NAMES, FLESCH_PAN_GERMANIC_NAME,
)

# textstat.set_lang() mutates global state.  Guard it so concurrent
# requests in a threaded executor cannot interleave languages.
_textstat_lock = threading.Lock()


class FluidityDimension(ScorableDimension):
    """Fluency evaluation using language-aware Flesch readability.

    Uses empirically validated coefficients for English (Flesch 1948),
    German (Amstad 1978), and Dutch (Douma 1960).  All other supported
    languages fall back to Pan-Germanic coefficients (Matricciani 2023).

    This is a heuristic baseline; LLMs are state-of-the-art for
    readability assessment and a fine-tuned model will replace this
    in a future iteration.
    """

    def __init__(self):
        super().__init__(name="Fluency")

    def evaluate(self, text: str, **kwargs) -> DimensionScore:
        """Evaluate fluency using the language-appropriate Flesch formula."""
        try:
            lang = kwargs.get('lang', 'en')
            base, asl_coeff, asw_coeff = FLESCH_COEFFICIENTS.get(
                lang, FLESCH_PAN_GERMANIC
            )
            formula = FLESCH_FORMULA_NAMES.get(lang, FLESCH_PAN_GERMANIC_NAME)
            ts_lang = TEXTSTAT_LANG_MAP.get(lang, 'en')

            with _textstat_lock:
                textstat.set_lang(ts_lang)
                words = textstat.lexicon_count(text, removepunct=True)
                sentences = textstat.sentence_count(text)
                syllables = textstat.syllable_count(text)

            if words == 0 or sentences == 0:
                return self.create_score(
                    value=0.0,
                    raw_value=0.0,
                    metadata={'formula': formula, 'lang': lang,
                              'note': 'degenerate text (no words or sentences)'}
                )

            asl = words / sentences          # average sentence length
            asw = syllables / words           # average syllables per word
            flesch_score = base - asl_coeff * asl - asw_coeff * asw

            # Clamp to 0–100, then normalise to 0–1
            flesch_score = max(0.0, min(100.0, flesch_score))
            normalized = self.normalize_score(flesch_score, 0, 100)

            return self.create_score(
                value=normalized,
                raw_value=flesch_score,
                metadata={
                    'formula': formula,
                    'lang': lang,
                    'words': words,
                    'sentences': sentences,
                    'syllables': syllables,
                }
            )
        except Exception as e:
            return self.create_score(value=0.0, metadata={'error': str(e)}, status='error')


class PolitenessDetection(ScorableDimension):
    """Politeness evaluation using lexical cues."""

    def __init__(self):
        super().__init__(name="Politeness")

    def evaluate(self, text: str, **kwargs) -> DimensionScore:
        """Evaluate politeness based on lexical cues."""
        try:
            lang = kwargs.get('lang', 'en')
            politeness_cues = lexicon_manager.get_keywords('politeness_cues', lang)
            rudeness_cues = lexicon_manager.get_keywords('rudeness_cues', lang)

            text_lower = text.lower()
            politeness_count = sum(1 for cue in politeness_cues if cue in text_lower)
            rudeness_count = sum(1 for cue in rudeness_cues if cue in text_lower)

            # Simple score: 0.5 baseline, +0.1 per politeness cue, -0.1 per rudeness cue
            score = 0.5 + (politeness_count * 0.1) - (rudeness_count * 0.1)
            score = max(0.0, min(1.0, score))

            return self.create_score(
                value=score,
                metadata={'politeness_cues': politeness_count, 'rudeness_cues': rudeness_count,
                          'lang': lang}
            )
        except Exception as e:
            return self.create_score(value=0.5, metadata={'error': str(e)}, status='error')


class EmotionalIntensity(ScorableDimension):
    """Emotional intensity evaluation using VADER and punctuation.

    Descriptive/style axis — high or low intensity isn't inherently
    "better" (context-dependent), so this is excluded from aggregation
    (aggregate=False) and reported for information only.
    """

    def __init__(self):
        super().__init__(name="Emotional Intensity")
        try:
            self.vader = SentimentIntensityAnalyzer()
        except:
            self.vader = None

    def evaluate(self, text: str, **kwargs) -> DimensionScore:
        """Evaluate emotional intensity."""
        try:
            if self.vader is None:
                return self.create_score(value=0.0, metadata={'error': 'VADER not available'}, aggregate=False, status='error')

            scores = self.vader.polarity_scores(text)
            # Use compound score as baseline
            intensity = abs(scores['compound'])

            # Boost with punctuation
            exclamation_count = text.count('!')
            question_count = text.count('?')
            intensity += (exclamation_count * 0.1) + (question_count * 0.05)

            intensity = max(0.0, min(1.0, intensity))

            return self.create_score(
                value=intensity,
                raw_value=scores,
                metadata={'exclamations': exclamation_count, 'questions': question_count},
                aggregate=False,
            )
        except Exception as e:
            return self.create_score(value=0.0, metadata={'error': str(e)}, aggregate=False, status='error')


class FormalityDimension(ScorableDimension):
    """Formality evaluation using formal/informal markers.

    Descriptive/style axis — neither formal nor informal register is
    inherently "better" (context-dependent), so this is excluded from
    aggregation (aggregate=False) and reported for information only.
    """

    def __init__(self):
        super().__init__(name="Formality")

    def evaluate(self, text: str, **kwargs) -> DimensionScore:
        """Evaluate formality based on markers."""
        try:
            lang = kwargs.get('lang', 'en')
            formal_markers = lexicon_manager.get_keywords('formal_markers', lang)
            informal_markers = lexicon_manager.get_keywords('informal_markers', lang)

            text_lower = text.lower()
            formal_count = sum(1 for marker in formal_markers if marker in text_lower)
            informal_count = sum(1 for marker in informal_markers if marker in text_lower)

            # Score from 0 (informal) to 1 (formal)
            score = 0.5 + (formal_count * 0.15) - (informal_count * 0.15)
            score = max(0.0, min(1.0, score))

            return self.create_score(
                value=score,
                metadata={'formal_markers': formal_count, 'informal_markers': informal_count,
                          'lang': lang},
                aggregate=False,
            )
        except Exception as e:
            return self.create_score(value=0.5, metadata={'error': str(e)}, aggregate=False, status='error')


class HedgingDetection(ScorableDimension):
    """Hedging detection using modal verbs and uncertainty cues.

    Descriptive/style axis — hedging is appropriate for uncertain topics
    and inappropriate for well-established facts, so there's no universal
    "better" direction. Excluded from aggregation (aggregate=False) and
    reported for information only.
    """

    def __init__(self):
        super().__init__(name="Hedging")

    def evaluate(self, text: str, **kwargs) -> DimensionScore:
        """Evaluate hedging (uncertainty) in the text."""
        try:
            lang = kwargs.get('lang', 'en')
            modal_verbs = lexicon_manager.get_keywords('modal_verbs', lang)
            uncertainty_cues = lexicon_manager.get_keywords('uncertainty_cues', lang)

            text_lower = text.lower()
            modal_count = sum(1 for verb in modal_verbs if verb in text_lower)
            uncertainty_count = sum(1 for cue in uncertainty_cues if cue in text_lower)

            # Higher score = more hedging (more uncertainty)
            hedging_score = (modal_count * 0.05) + (uncertainty_count * 0.1)
            hedging_score = max(0.0, min(1.0, hedging_score))

            return self.create_score(
                value=hedging_score,
                metadata={'modal_verbs': modal_count, 'uncertainty_cues': uncertainty_count,
                          'lang': lang},
                aggregate=False,
            )
        except Exception as e:
            return self.create_score(value=0.0, metadata={'error': str(e)}, aggregate=False, status='error')

