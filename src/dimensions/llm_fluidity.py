"""LLM-based readability assessment for Prong 2 Fluency (dual output).

TODO.md §2: the second LLM dimension the improvement plan deferred.
The [READABILITY] task on the shared judge client (src/llm_judge_client,
defaults to the 1.5B server) rates a text's coherence, structural flow,
vocabulary complexity, and sentence structure for a general adult
audience and returns a 0-1 score, a CEFR-style level, and a short
rationale.

Dual output: the local Flesch baseline (FluidityDimension) ALWAYS runs
and stays the dimension's aggregated `value` — the LLM score never
replaces it, so a failed or slow judge call cannot regress the
dimension. The judge track's own state lives in `judge_status`
("scored" | "unknown" | "error") inside the metadata; the dimension's
top-level status stays whatever the baseline produced.

English first (TODO.md language scope): the [READABILITY] prompt is
verified for English only, so non-English evaluations abstain
(judge_status "unknown", judge_error explains why) and keep the
language-aware Flesch baseline untouched.
"""

import time
from typing import Any, Dict, Optional

from src.base import DimensionScore
from src.dimensions.base_dimension import ScorableDimension
from src.dimensions.prong2_dimensions import FluidityDimension
from src.evidence import source
from src.llm_judge_client import (
    JudgeUnavailableError, LLMJudgeClient, get_shared_judge_client,
    judge_route_for_lang,
)

# FluidityDimension emits this metadata note when the text has no words
# or sentences — the marker for "nothing readable to judge".
_DEGENERATE_NOTE = 'degenerate text (no words or sentences)'


class LLMFluidityDimension(ScorableDimension):
    """Dual-output Fluency: local Flesch baseline + [READABILITY] LLM track.

    Mirrors FluidityDimension's name ("Fluency") so Prong 2's registry
    key and every consumer that looks up the dimension are unchanged;
    only the metadata gains the dual-output contract:

        baseline_value              Flesch 0-1 normalized score (== value)
        baseline_raw_value          Flesch raw 0-100 before normalization
        baseline_processing_time_ms Flesch computation time
        llm_value / llm_level /
        llm_rationale              the [READABILITY] verdict, when scored
        llm_processing_time_ms     judge call time (None when no call)
        judge_status                scored | unknown | error
        judge_error                 why the judge track did not score
        judge_model                 which model the readability config
                                    points at

    plus the baseline's own interpretability keys (formula, lang, words,
    sentences, syllables) and the evidence contract: `rules` for the
    Flesch half, `llm_judge` for the LLM half.

    Failure semantics: the Flesch baseline always runs; an unreachable,
    timed-out, or unparseable judge only downgrades the judge track —
    `value` stays the baseline score and the dimension never goes blank.
    """

    def __init__(self, client: Optional[LLMJudgeClient] = None):
        """Create the dual-output Fluency dimension.

        Args:
            client: [READABILITY] client (test stubs can inject any
                object with `readability_model_name` and
                `readability(text) -> {"score", "level", "rationale"}`).
                None uses the process-wide shared judge client, lazily.
        """
        super().__init__(name="Fluency")
        self._client = client
        self._baseline = FluidityDimension()

    def _get_client(self) -> LLMJudgeClient:
        """Lazily resolve the shared [READABILITY] client."""
        if self._client is None:
            self._client = get_shared_judge_client()
        return self._client

    def evaluate(self, text: str, judge: Optional[LLMJudgeClient] = None,
                 **kwargs) -> DimensionScore:
        """Evaluate fluency on both tracks: Flesch baseline + LLM judge.

        The baseline half delegates to FluidityDimension, so its score,
        metadata, and status are byte-identical to the single-track
        behavior; this method only adds the dual-output keys and the
        `llm_judge` evidence entry.

        Args:
            text: the text to evaluate.
            judge: injected [READABILITY] client; overrides the
                constructor client for this call (tests). None uses
                the constructor/shared client.
            **kwargs: forwarded to the baseline (e.g. ``lang="en"``).

        Returns:
            DimensionScore whose `value` is the Flesch baseline score
            (identical to FluidityDimension) with the LLM track's dual
            output in the metadata.
        """
        lang = kwargs.get('lang', 'en')
        client = judge if judge is not None else self._get_client()

        baseline_start = time.perf_counter()
        score = self._baseline.evaluate(text, **kwargs)
        baseline_ms = (time.perf_counter() - baseline_start) * 1000.0

        track = self._readability_track(
            client, text, lang,
            baseline_degenerate=score.metadata.get('note') == _DEGENERATE_NOTE,
        )
        score.metadata['baseline_value'] = score.value
        score.metadata['baseline_raw_value'] = score.raw_value
        score.metadata['baseline_processing_time_ms'] = baseline_ms
        score.metadata['judge_model'] = client.readability_model_name
        score.metadata.update(track)
        score.metadata['evidence_sources'].update(self._judge_evidence(track))
        return score

    def _readability_track(self, client: LLMJudgeClient, text: str,
                           lang: str,
                           baseline_degenerate: bool) -> Dict[str, Any]:
        """Run the [READABILITY] judge and return its half of the dual
        output. Never raises.

        judge_status follows the judge call itself: "scored" with
        llm_value/llm_level/llm_rationale, "unknown" when the model
        could not be reached or has nothing readable to judge
        (non-English, degenerate text), "error" when it replied
        unusable JSON. The baseline half is never touched.
        """
        track: Dict[str, Any] = {
            'judge_status': 'unknown',
            'llm_value': None,
            'llm_level': None,
            'llm_rationale': None,
            'llm_processing_time_ms': None,
        }
        if judge_route_for_lang(lang) != 'en':
            # English first: the [READABILITY] prompt is verified for
            # English only, so non-English text abstains instead of
            # emitting an unvalidated score. The Flesch baseline for the
            # evaluation language is unchanged.
            track['judge_error'] = (
                f'readability judge is validated for English only (lang={lang!r})')
            return track
        if not text or not text.strip():
            # Nothing readable to judge (blank input; the pipeline
            # guards blank text, this covers direct calls).
            track['judge_error'] = 'empty text'
            return track
        if baseline_degenerate:
            # The Flesch baseline found no words or sentences; a judge
            # call on such text would rate noise. Abstain, no call.
            track['judge_error'] = _DEGENERATE_NOTE
            return track
        start = time.perf_counter()
        try:
            verdict = client.readability(text)
        except JudgeUnavailableError as e:
            # Timeout / connection / HTTP failure: surfaced as unknown so
            # a slow judge never blocks the evaluate path.
            track['judge_error'] = str(e)
        except Exception as e:  # ReadabilityParseError or a client bug
            track['judge_status'] = 'error'
            track['judge_error'] = str(e)
        else:
            track['judge_status'] = 'scored'
            track['llm_value'] = verdict['score']
            track['llm_level'] = verdict['level']
            track['llm_rationale'] = verdict['rationale']
        track['llm_processing_time_ms'] = (time.perf_counter() - start) * 1000.0
        return track

    @staticmethod
    def _judge_evidence(track: Dict[str, Any]) -> Dict[str, Any]:
        """Evidence-contract entry for the judge track half of the dual
        output (same shape as Relevance's)."""
        scored = track.get('judge_status') == 'scored'
        return {'llm_judge': source(track.get('llm_value'),
                                    track.get('judge_status', 'unknown'),
                                    1 if scored else None)}
