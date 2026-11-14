"""Prong 1 dimensions: Relevance, SemanticCoherence, Reliability, Toxicity."""
import time
from typing import List, Optional
import numpy as np
from src.dimensions.base_dimension import ScorableDimension
from src.base import DimensionScore
from src.models.embeddings import Embeddings
from src.models.toxicity_model import ToxicityModel


def cos_to_01(cos_val: float) -> float:
    return max(0.0, min(1.0, (cos_val + 1.0) / 2.0))


class Relevance(ScorableDimension):
    def __init__(self, embeddings: Optional[Embeddings] = None):
        super().__init__(name="Relevance")
        self.emb = embeddings or Embeddings()

    def evaluate(self, prompt: Optional[str], response: str) -> DimensionScore:
        start = time.time()
        if prompt is None or not prompt.strip():
            # No prompt → relevance to the prompt cannot be measured.
            # (The old fallback scored the response against a fake
            # first-sentence pseudo-prompt, which measures cohesion,
            # not relevance.) Report unknown; the placeholder value is
            # display-only and never aggregated.
            return self.create_score(
                value=0.5,
                metadata={'reason': 'no prompt provided'},
                status='unknown',
            )
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
            return self.create_score(value=0.5, metadata={'error': str(e)}, status='error')
        return self.create_score(value=score, raw_value=raw, metadata={**metadata, 'time': time.time()-start})


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
                # short texts are considered coherent by default
                return self.create_score(value=1.0, raw_value=1.0, metadata={'time': time.time()-start})
            sent_embs = self.emb.embed_texts(sents)
            sims = []
            for i in range(len(sent_embs)-1):
                sims.append(self.emb.cosine_sim(sent_embs[i], sent_embs[i+1]))
            raw = float(np.mean(sims))
            score = cos_to_01(raw)
            return self.create_score(value=score, raw_value=raw, metadata={'sentences': len(sents), 'time': time.time()-start})
        except Exception as e:
            return self.create_score(value=0.5, metadata={'error': str(e)}, status='error')


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
                    return self.create_score(value=0.8, metadata={'note': 'short text'})
                sent_embs = self.emb.embed_texts(sents)
                sims = []
                for i in range(len(sent_embs)-1):
                    sims.append(self.emb.cosine_sim(sent_embs[i], sent_embs[i+1]))
                mean_sim = float(np.mean(sims))
                var_sim = float(np.var(sims))
                # combine mean and variance into score
                score = cos_to_01(mean_sim) * (1.0 - min(1.0, var_sim*2.0))
                return self.create_score(value=score, raw_value={'mean_sim': mean_sim, 'var_sim': var_sim, 'time': time.time()-start})
            else:
                # multiple responses: compare full-response embeddings
                emb = self.emb.embed_texts(responses)
                sims = []
                for i in range(len(emb)):
                    for j in range(i+1, len(emb)):
                        sims.append(self.emb.cosine_sim(emb[i], emb[j]))
                if not sims:
                    return self.create_score(value=0.5, metadata={'reason': 'no pairwise similarities computable'}, status='unknown')
                mean_sim = float(np.mean(sims))
                var_sim = float(np.var(sims))
                score = cos_to_01(mean_sim) * (1.0 - min(1.0, var_sim*2.0))
                return self.create_score(value=score, raw_value={'mean_sim': mean_sim, 'var_sim': var_sim, 'time': time.time()-start})
        except Exception as e:
            return self.create_score(value=0.5, metadata={'error': str(e)}, status='error')


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
            )
        except Exception as e:
            # A failed toxicity check must not contribute a perfect
            # agg_value=1.0 to the average — status="error" excludes it.
            return self.create_score(value=0.0, metadata={'error': str(e)}, agg_value=1.0, status='error')

