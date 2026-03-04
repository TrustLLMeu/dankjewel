"""Prong 2: Rule-Based Dimensions."""

import textstat
from nltk.sentiment import SentimentIntensityAnalyzer
from src.dimensions.base_dimension import ScorableDimension
from src.base import DimensionScore


class FluidityDimension(ScorableDimension):
    """Fluency evaluation using Flesch Reading Ease."""

    def __init__(self):
        super().__init__(name="Fluency")

    def evaluate(self, text: str) -> DimensionScore:
        """Evaluate fluency using Flesch Reading Ease score."""
        try:
            flesch_score = textstat.flesch_reading_ease(text)
            # Flesch score: 90-100 = very easy, 0-30 = very difficult
            # Normalize to 0-1 where higher is more fluent
            normalized = self.normalize_score(flesch_score, 0, 100)
            return self.create_score(
                value=normalized,
                raw_value=flesch_score,
                metadata={'metric': 'Flesch Reading Ease'}
            )
        except Exception as e:
            return self.create_score(value=0.0, metadata={'error': str(e)})


class PolitenessDetection(ScorableDimension):
    """Politeness evaluation using lexical cues."""

    def __init__(self):
        super().__init__(name="Politeness")
        self.politeness_cues = {'please', 'thank', 'kindly', 'appreciate', 'welcome'}
        self.rudeness_cues = {'pronto', 'hurry', 'rush'}

    def evaluate(self, text: str) -> DimensionScore:
        """Evaluate politeness based on lexical cues."""
        try:
            text_lower = text.lower()
            politeness_count = sum(1 for cue in self.politeness_cues if cue in text_lower)
            rudeness_count = sum(1 for cue in self.rudeness_cues if cue in text_lower)

            # Simple score: 0.5 baseline, +0.1 per politeness cue, -0.1 per rudeness cue
            score = 0.5 + (politeness_count * 0.1) - (rudeness_count * 0.1)
            score = max(0.0, min(1.0, score))

            return self.create_score(
                value=score,
                metadata={'politeness_cues': politeness_count, 'rudeness_cues': rudeness_count}
            )
        except Exception as e:
            return self.create_score(value=0.5, metadata={'error': str(e)})


class EmotionalIntensity(ScorableDimension):
    """Emotional intensity evaluation using VADER and punctuation."""

    def __init__(self):
        super().__init__(name="Emotional Intensity")
        try:
            self.vader = SentimentIntensityAnalyzer()
        except:
            self.vader = None

    def evaluate(self, text: str) -> DimensionScore:
        """Evaluate emotional intensity."""
        try:
            if self.vader is None:
                return self.create_score(value=0.0, metadata={'error': 'VADER not available'})

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
                metadata={'exclamations': exclamation_count, 'questions': question_count}
            )
        except Exception as e:
            return self.create_score(value=0.0, metadata={'error': str(e)})


class FormalityDimension(ScorableDimension):
    """Formality evaluation using formal/informal markers."""

    def __init__(self):
        super().__init__(name="Formality")
        self.formal_markers = {'dear', 'would', 'may i', 'respectfully', 'sincerely', 'regards'}
        self.informal_markers = {'hey', 'gonna', 'wanna', 'dude', 'mate', 'lol', 'bruh'}

    def evaluate(self, text: str) -> DimensionScore:
        """Evaluate formality based on markers."""
        try:
            text_lower = text.lower()
            formal_count = sum(1 for marker in self.formal_markers if marker in text_lower)
            informal_count = sum(1 for marker in self.informal_markers if marker in text_lower)

            # Score from 0 (informal) to 1 (formal)
            score = 0.5 + (formal_count * 0.15) - (informal_count * 0.15)
            score = max(0.0, min(1.0, score))

            return self.create_score(
                value=score,
                metadata={'formal_markers': formal_count, 'informal_markers': informal_count}
            )
        except Exception as e:
            return self.create_score(value=0.5, metadata={'error': str(e)})


class HedgingDetection(ScorableDimension):
    """Hedging detection using modal verbs and uncertainty cues."""

    def __init__(self):
        super().__init__(name="Hedging")
        self.modal_verbs = {'may', 'might', 'could', 'can', 'should', 'would'}
        self.uncertainty_cues = {'perhaps', 'maybe', 'possibly', 'seems', 'appears', 'allegedly'}

    def evaluate(self, text: str) -> DimensionScore:
        """Evaluate hedging (uncertainty) in the text."""
        try:
            text_lower = text.lower()
            modal_count = sum(1 for verb in self.modal_verbs if verb in text_lower)
            uncertainty_count = sum(1 for cue in self.uncertainty_cues if cue in text_lower)

            # Higher score = more hedging (more uncertainty)
            hedging_score = (modal_count * 0.05) + (uncertainty_count * 0.1)
            hedging_score = max(0.0, min(1.0, hedging_score))

            return self.create_score(
                value=hedging_score,
                metadata={'modal_verbs': modal_count, 'uncertainty_cues': uncertainty_count}
            )
        except Exception as e:
            return self.create_score(value=0.0, metadata={'error': str(e)})

