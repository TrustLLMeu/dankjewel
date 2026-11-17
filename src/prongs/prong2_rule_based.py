"""Prong 2: Rule-Based Evaluation."""

import time
from typing import Optional
from src.base import Evaluator, ProngResult, DimensionScore, Dimension
from src.dimensions.llm_fluidity import LLMFluidityDimension
from src.llm_judge_client import LLMJudgeClient
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

    def __init__(self, judge: Optional[LLMJudgeClient] = None):
        """Initialize Prong 2.

        Args:
            judge: [READABILITY] client for the optional LLM
                readability track on the Fluency dimension. None (the
                default) means the track lazily uses the process-wide
                shared judge client when a request opts in; tests can
                inject a stub with the same readability()/model surface.
        """
        super().__init__(prong_name="Rule-Based (Prong 2)")
        self._judge = judge
        self._llm_fluency: Optional[LLMFluidityDimension] = None
        self._init_dimensions()

    def _init_dimensions(self) -> None:
        """Initialize all rule-based dimensions."""
        self.register_dimension(FluidityDimension())
        self.register_dimension(PolitenessDetection())
        self.register_dimension(EmotionalIntensity())
        self.register_dimension(FormalityDimension())
        self.register_dimension(HedgingDetection())
        self.register_dimension(LexicalDiversity())

    def _get_llm_fluency(self) -> LLMFluidityDimension:
        """Lazily create the dual-output Fluency dimension around the
        injected (or shared) [READABILITY] client."""
        if self._llm_fluency is None:
            self._llm_fluency = LLMFluidityDimension(client=self._judge)
        return self._llm_fluency

    def evaluate(self, text: str, llm_readability: bool = False,
                 **kwargs) -> ProngResult:
        """
        Evaluate text using rule-based approaches.

        Args:
            text: The text to evaluate.
            llm_readability: Opt in to the [READABILITY] LLM track on
                the Fluency dimension (dual output in that dimension's
                metadata: the Flesch baseline stays `value`, plus
                llm_value/llm_level/llm_rationale/judge_status). The
                track is English-only — non-English languages keep the
                Flesch baseline. Default False: Flesch baseline only,
                no judge call, identical behavior and latency.
            **kwargs: Extra options forwarded to each dimension
                      (e.g. ``lang="nl"``).

        Evaluates:
        - Fluency (language-aware Flesch readability; optional
          [READABILITY] LLM dual track)
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
                if dimension.name == "Fluency" and llm_readability:
                    score = self._get_llm_fluency().evaluate(text, **kwargs)
                else:
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


