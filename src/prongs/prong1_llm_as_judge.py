"""Prong 1: LLM-as-Judge Evaluation (embeddings + toxicity detection)."""

import time
from typing import Optional, List
from src.base import Evaluator, ProngResult
from src.llm_judge_client import LLMJudgeClient, get_judge_for_lang
from src.prongs.prong1_dimensions import (
    Relevance,
    SemanticCoherence,
    Reliability,
    Toxicity
)


class Prong1LLMAsJudge(Evaluator):
    """LLM-as-Judge evaluator using embeddings for relevance/coherence and toxicity classifier."""

    def __init__(self, judge: Optional[LLMJudgeClient] = None):
        """
        Args:
            judge: tiny-judge client to use for the optional LLM track.
                None (the default) means "route by language when a
                request opts in" (get_judge_for_lang: 0.5B for English,
                1.5B otherwise); tests can inject a stub with the same
                judge()/model_name surface, which always overrides the
                routing.
        """
        super().__init__(prong_name="LLM-as-Judge (Prong 1)")
        self._judge = judge
        self._init_dimensions()

    def _init_dimensions(self) -> None:
        """Initialize all LLM-as-judge dimensions."""
        self.register_dimension(Relevance())
        self.register_dimension(SemanticCoherence())
        self.register_dimension(Reliability())
        self.register_dimension(Toxicity())

    def evaluate(self, text: str, prompt: Optional[str] = None, responses: Optional[List[str]] = None,
                 tiny_judge: bool = False, lang: str = "en") -> ProngResult:
        """
        Evaluate text using LLM-as-judge approach.

        Args:
            text: The response text to evaluate
            prompt: Optional prompt for relevance scoring
            responses: Optional list of responses for reliability scoring
            tiny_judge: Opt in to the tiny-LLM judge track on Relevance
                (dual output in that dimension's metadata). Default
                False: embeddings baseline only, no judge call.
            lang: The evaluation language. With tiny_judge, the judge
                client is selected by language (get_judge_for_lang):
                the 0.5B for English, the 1.5B for anything else. An
                explicitly injected judge client (constructor) always
                wins — tests and explicit configuration override the
                routing.

        Evaluates:
        - Relevance (semantic similarity to prompt)
        - Semantic Coherence (sentence-level coherence)
        - Reliability (topic stability across responses)
        - Toxicity (offensive language detection)
        """
        start_time = time.time()
        dimensions = []
        error = None

        # Judge selection for the opt-in track: an injected client wins
        # (test/override), otherwise the language router picks the
        # product judge — 0.5B for English, 1.5B for other languages.
        judge = None
        if tiny_judge:
            judge = self._judge if self._judge is not None else get_judge_for_lang(lang)

        try:
            # Evaluate Relevance
            rel_dim = self.dimensions['Relevance']
            rel_score = rel_dim.evaluate(prompt, text, judge=judge, lang=lang)
            dimensions.append(rel_score)

            # Evaluate Semantic Coherence
            coh_dim = self.dimensions['Semantic Coherence']
            coh_score = coh_dim.evaluate(text)
            dimensions.append(coh_score)

            # Evaluate Reliability (use responses if provided, otherwise use text)
            rel_dim = self.dimensions['Reliability']
            resp_list = responses or [text]
            rel_score = rel_dim.evaluate(resp_list)
            dimensions.append(rel_score)

            # Evaluate Toxicity
            tox_dim = self.dimensions['Toxicity']
            tox_score = tox_dim.evaluate(text)
            dimensions.append(tox_score)

        except Exception as e:
            error = str(e)

        processing_time = time.time() - start_time

        return ProngResult(
            prong_name=self.prong_name,
            dimensions=dimensions,
            processing_time=processing_time,
            error=error
        )

