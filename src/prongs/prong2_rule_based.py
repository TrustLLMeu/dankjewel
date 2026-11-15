"""Prong 2: Rule-Based Evaluation."""

import time
from typing import List
from src.base import Evaluator, ProngResult, DimensionScore, Dimension
from src.dimensions.prong2_dimensions import (
    FluidityDimension,
    PolitenessDetection,
    EmotionalIntensity,
    FormalityDimension,
    HedgingDetection,
    LexicalDiversity
)


class Prong2RuleBased(Evaluator):
    """Rule-based evaluator using lexicons and readability metrics."""

    def __init__(self):
        super().__init__(prong_name="Rule-Based (Prong 2)")
        self._init_dimensions()

    def _init_dimensions(self) -> None:
        """Initialize all rule-based dimensions."""
        self.register_dimension(FluidityDimension())
        self.register_dimension(PolitenessDetection())
        self.register_dimension(EmotionalIntensity())
        self.register_dimension(FormalityDimension())
        self.register_dimension(HedgingDetection())
        self.register_dimension(LexicalDiversity())

    def evaluate(self, text: str, **kwargs) -> ProngResult:
        """
        Evaluate text using rule-based approaches.

        Args:
            text: The text to evaluate.
            **kwargs: Extra options forwarded to each dimension
                      (e.g. ``lang="nl"``).

        Evaluates:
        - Fluency (language-aware Flesch readability)
        - Politeness (lexical cues)
        - Emotional Intensity (VADER + punctuation)
        - Formality (formal/informal markers)
        - Hedging (modal verbs, uncertainty cues)
        """
        start_time = time.time()
        dimensions = []
        error = None

        try:
            for dimension in self.dimensions.values():
                score = dimension.evaluate(text, **kwargs)
                dimensions.append(score)
        except Exception as e:
            error = str(e)

        processing_time = time.time() - start_time

        return ProngResult(
            prong_name=self.prong_name,
            dimensions=dimensions,
            processing_time=processing_time,
            error=error
        )

