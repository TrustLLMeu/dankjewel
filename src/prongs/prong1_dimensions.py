"""Prong 1 dimensions: Relevance, SemanticCoherence, Reliability, Toxicity."""
import time
from typing import Any, Dict, List, Optional
import numpy as np
from src.dimensions.base_dimension import ScorableDimension
from src.base import DimensionScore
from src.evidence import source
from src.llm_judge_client import LLMJudgeClient, JudgeUnavailableError
from src.models.embeddings import Embeddings
from src.models.toxicity_model import ToxicityModel


def cos_to_01(cos_val: float) -> float:
    return max(0.0, min(1.0, (cos_val + 1.0) / 2.0))


class Relevance(ScorableDimension):
    def __init__(self, embeddings: Optional[Embeddings] = None):
        super().__init__(name="Relevance")
        self.emb = embeddings or Embeddings()

    def evaluate(self, prompt: Optional[str], response: str,
                 judge: Optional[LLMJudgeClient] = None) -> DimensionScore:
        """Score response relevance, optionally with a tiny-LLM second opinion.

        The embedding baseline stays the default: `value` (and anything
        aggregated from it) is always the baseline score. When `judge` is
        given, the metadata additionally carries the dual output
        (baseline_value / llm_value, both processing times, judge model,
        judge_status "scored"|"unknown"|"error", rationale). A failed or
        slow judge call only downgrades the judge track — the baseline
        score and the dimension's status are untouched.

        Args:
            prompt: the original prompt; None/blank → unmeasurable (unknown).
            response: the text to score.
            judge: tiny-judge client (or any object with `model_name` and
                `judge(prompt, response)` — tests inject a stub). None
                (the default) keeps the existing single-track behavior.
        """
        start = time.time()
        if prompt is None or not prompt.strip():
            # No prompt → relevance to the prompt cannot be measured.
            # (The old fallback scored the response against a fake
            # first-sentence pseudo-prompt, which measures cohesion,
            # not relevance.) Report unknown; the placeholder value is
            # display-only and never aggregated. The embedding source
            # is never invoked; a judge, if requested, has nothing to
            # rate relevance against (its track runs and abstains).
            score = self.create_score(
                value=0.5,
                metadata={'reason': 'no prompt provided'},
                status='unknown',
                evidence_sources={} if judge is None else
                {'llm_judge': source(None, 'unknown', None)},
            )
            if judge is not None:
                score.metadata.update(self._judge_track(judge, None, response,
                                                       score.value, time.time() - start))
            return score
        try:
            p_emb = self.emb.embed_texts([prompt])[0]
            # split response into sentences
            from spacy.lang.en import English
            nlp = English()
            nlp.add_pipe('sentencizer')
            doc = nlp(response)
            sents = [s.text.strip() for s in doc.sents if s.text.strip()]
            if not sents:
                # fallback to whole response
                sents = [response]
            sent_embs = self.emb.embed_texts(sents)
            sims = [self.emb.cosine_sim(p_emb, se) for se in sent_embs]
            raw = float(np.mean(sims))
            score = cos_to_01(raw)
            metadata = {'model': self.emb.model_name, 'sentences': len(sents)}
        except Exception as e:
            err = self.create_score(value=0.5, metadata={'error': str(e)}, status='error',
                                    evidence_sources={'embedding': source(None, 'error', None)})
            if judge is not None:
                track = self._judge_track(judge, prompt, response,
                                          err.value, time.time() - start)
                err.metadata.update(track)
                err.metadata['evidence_sources'].update(self._judge_evidence(track))
            return err
        result = self.create_score(value=score, raw_value=raw,
                                   metadata={**metadata, 'time': time.time()-start},
                                   evidence_sources={'embedding': source(score, 'scored', len(sents))})
        if judge is not None:
            track = self._judge_track(judge, prompt, response,
                                      result.value, time.time() - start)
            result.metadata.update(track)
            result.metadata['evidence_sources'].update(self._judge_evidence(track))
        return result

    @staticmethod
    def _judge_evidence(track: Dict[str, Any]) -> Dict[str, Any]:
        """Evidence-contract entry for the judge track half of the dual output."""
        scored = track.get('judge_status') == 'scored'
        return {'llm_judge': source(track.get('llm_value'),
                                    track.get('judge_status', 'unknown'),
                                    1 if scored else None)}

    def _judge_track(self, judge: LLMJudgeClient, prompt: Optional[str], response: str,
                     baseline_value: float, baseline_elapsed_s: float) -> Dict[str, Any]:
        """Run the tiny judge and return its half of the dual output. Never raises.

        judge_status follows the judge call itself: "scored" with an
        llm_value, "unknown" when the judge could not be reached or has
        nothing to judge (no prompt), "error" when it replied unusable
        JSON. The baseline half of the metadata mirrors what the
        embedding path already produced.
        """
        track: Dict[str, Any] = {
            'baseline_value': baseline_value,
            'baseline_processing_time_ms': baseline_elapsed_s * 1000.0,
            'judge_model': judge.model_name,
            'judge_status': 'unknown',
            'llm_value': None,
            'llm_processing_time_ms': None,
            'rationale': None,
        }
        if prompt is None or not prompt.strip():
            # Consistent with the embedding baseline: without a prompt
            # there is nothing for the judge to rate relevance against.
            track['judge_error'] = 'no prompt provided'
            return track
        start = time.perf_counter()
        try:
            verdict = judge.judge(prompt, response)
            llm_value, rationale = verdict['score'], verdict['rationale']
        except JudgeUnavailableError as e:
            # Timeout / connection / HTTP failure: surfaced as unknown so
            # a slow judge never blocks the evaluate path.
            track['judge_error'] = str(e)
        except Exception as e:  # JudgeParseError or an unexpected client bug
            track['judge_status'] = 'error'
            track['judge_error'] = str(e)
        else:
            track['judge_status'] = 'scored'
            track['llm_value'] = llm_value
            track['rationale'] = rationale
        track['llm_processing_time_ms'] = (time.perf_counter() - start) * 1000.0
        return track


class SemanticCoherence(ScorableDimension):
    def __init__(self, embeddings: Optional[Embeddings] = None):
        super().__init__(name="Semantic Coherence")
        self.emb = embeddings or Embeddings()

    def evaluate(self, response: str) -> DimensionScore:
        start = time.time()
        try:
            from spacy.lang.en import English
            nlp = English()
            nlp.add_pipe('sentencizer')
            doc = nlp(response)
            sents = [s.text.strip() for s in doc.sents if s.text.strip()]
            if len(sents) <= 1:
                # short texts are considered coherent by default — a
                # documented assumption, not an embedding measurement,
                # so the evidence contract lists no source here.
                return self.create_score(value=1.0, raw_value=1.0, metadata={'time': time.time()-start})
            sent_embs = self.emb.embed_texts(sents)
            sims = []
            for i in range(len(sent_embs)-1):
                sims.append(self.emb.cosine_sim(sent_embs[i], sent_embs[i+1]))
            raw = float(np.mean(sims))
            score = cos_to_01(raw)
            return self.create_score(value=score, raw_value=raw, metadata={'sentences': len(sents), 'time': time.time()-start},
                                     evidence_sources={'embedding': source(score, 'scored', len(sents))})
        except Exception as e:
            return self.create_score(value=0.5, metadata={'error': str(e)}, status='error',
                                     evidence_sources={'embedding': source(None, 'error', None)})


class Reliability(ScorableDimension):
    def __init__(self, embeddings: Optional[Embeddings] = None):
        super().__init__(name="Reliability")
        self.emb = embeddings or Embeddings()

    def evaluate(self, responses: List[str]) -> DimensionScore:
        start = time.time()
        try:
            if not responses:
                return self.create_score(value=0.5, metadata={'reason': 'no responses provided'}, status='unknown')
            if len(responses) == 1:
                # single response: measure internal consistency
                resp = responses[0]
                from spacy.lang.en import English
                nlp = English()
                nlp.add_pipe('sentencizer')
                doc = nlp(resp)
                sents = [s.text.strip() for s in doc.sents if s.text.strip()]
                if len(sents) <= 1:
                    # short-text default (0.8) — an assumption, not an
                    # embedding measurement; no evidence source listed.
                    return self.create_score(value=0.8, metadata={'note': 'short text'})
                sent_embs = self.emb.embed_texts(sents)
                sims = []
                for i in range(len(sent_embs)-1):
                    sims.append(self.emb.cosine_sim(sent_embs[i], sent_embs[i+1]))
                mean_sim = float(np.mean(sims))
                var_sim = float(np.var(sims))
                # combine mean and variance into score
                score = cos_to_01(mean_sim) * (1.0 - min(1.0, var_sim*2.0))
                return self.create_score(value=score, raw_value={'mean_sim': mean_sim, 'var_sim': var_sim, 'time': time.time()-start},
                                         evidence_sources={'embedding': source(score, 'scored', len(sents))})
            else:
                # multiple responses: compare full-response embeddings
                emb = self.emb.embed_texts(responses)
                sims = []
                for i in range(len(emb)):
                    for j in range(i+1, len(emb)):
                        sims.append(self.emb.cosine_sim(emb[i], emb[j]))
                if not sims:
                    return self.create_score(value=0.5, metadata={'reason': 'no pairwise similarities computable'}, status='unknown',
                                             evidence_sources={'embedding': source(None, 'unknown', None)})
                mean_sim = float(np.mean(sims))
                var_sim = float(np.var(sims))
                score = cos_to_01(mean_sim) * (1.0 - min(1.0, var_sim*2.0))
                return self.create_score(value=score, raw_value={'mean_sim': mean_sim, 'var_sim': var_sim, 'time': time.time()-start},
                                         evidence_sources={'embedding': source(score, 'scored', len(responses))})
        except Exception as e:
            return self.create_score(value=0.5, metadata={'error': str(e)}, status='error',
                                     evidence_sources={'embedding': source(None, 'error', None)})


class Toxicity(ScorableDimension):
    def __init__(self, model: Optional[ToxicityModel] = None):
        super().__init__(name="Toxicity")
        self.model = model or ToxicityModel()

    def evaluate(self, response: str) -> DimensionScore:
        start = time.time()
        try:
            res = self.model.score(response)
            prob = float(res.get('probability', 0.0))
            # `value` stays as the toxicity probability (higher = more
            # toxic — its natural, documented meaning). For aggregation,
            # higher-is-better is required, so `agg_value` supplies the
            # inverted (1 - prob) contribution: a toxic response should
            # PULL DOWN the prong/total score, not inflate it via a naive
            # average of an unrelated-direction number.
            return self.create_score(
                value=prob, raw_value=res,
                metadata={'model': self.model.model_name, 'time': time.time()-start},
                agg_value=1.0 - prob,
                evidence_sources={'classifier': source(prob, 'scored', None)},
            )
        except Exception as e:
            # A failed toxicity check must not contribute a perfect
            # agg_value=1.0 to the average — status="error" excludes it.
            return self.create_score(value=0.0, metadata={'error': str(e)}, agg_value=1.0, status='error',
                                     evidence_sources={'classifier': source(None, 'error', None)})

