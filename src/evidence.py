"""Evidence-source contract for the dashboard (Stage A).

Every scored DimensionScore carries metadata["evidence_sources"]: a
machine-readable record of WHICH evidence sources informed that
dimension. Each entry maps a source key to

    {"value": float | None,    # the source's own [0,1] score where one is
                               # defined, else None
     "status": "scored" | "unknown" | "error",
     "n": int | None}          # items the source resolved where a count is
                               # meaningful (claims, tokens, sentences,
                               # responses), else None

Source keys (exactly these — the UI matches on them):

    embedding   MiniLM cosine similarity (Prong 1 Relevance / Semantic
                Coherence / Reliability)
    llm_judge   the tiny-LLM judge track (opt-in, Relevance dual output)
    classifier  toxic-bert toxicity probability (Toxicity)
    rules       lexicon / readability / counting heuristics (Prong 2 and
                Modality Awareness)
    spacy       spaCy dependency-parse claim extraction (Prong 3)
    llm_claims  the LLM atomic-claim extraction track (opt-in, Prong 3)
    kb_exact    offline Wikidata exact-triple verification
    minicheck   the MiniCheck NLI verifier track (opt-in, Prong 3)
    logprob     per-token log-probabilities of the generating model (Prong 4)

Contract rules:

  - A source is listed when it informed the dimension: it contributed at
    least one evidence item, scored a measurement, or its failure
    (status "error") / missing input (status "unknown") IS the
    dimension's outcome. Tracks that are off and code paths that were
    never reached are omitted entirely — an empty dict means "no source
    produced evidence for this dimension" (e.g. the short-text
    Semantic Coherence default, or a missing-prompt Relevance without
    a judge).
  - `value` keeps the source's natural direction where that is already
    [0,1]: Toxicity's probability and Uncertainty stay higher-is-worse,
    exactly like the parent dimension's `value`. Perplexity's defined
    [0,1] form is its agg_value 1/(1+ppl) (the raw ppl is unbounded).
  - `n` counts discrete evidence items; None when the source scores a
    single text with no itemization (rules, classifier).
"""

from typing import Dict, List, Optional

# The closed set of source keys. Entries with any other key are rejected.
SOURCE_KEYS = ('embedding', 'llm_judge', 'classifier', 'rules', 'spacy',
               'llm_claims', 'kb_exact', 'minicheck', 'logprob')

_STATUS_VALUES = ('scored', 'unknown', 'error')


def source(value: Optional[float] = None, status: str = 'scored',
           n: Optional[int] = None) -> Dict[str, Optional[float]]:
    """Build one normalized evidence-source entry."""
    if status not in _STATUS_VALUES:
        raise ValueError(
            f"Invalid evidence status {status!r}; must be one of {_STATUS_VALUES}"
        )
    return {
        'value': None if value is None else float(value),
        'status': status,
        'n': None if n is None else int(n),
    }


def normalize(evidence_sources: Optional[dict]) -> Dict[str, dict]:
    """Validate and normalize a whole evidence_sources dict.

    Every key must be in SOURCE_KEYS and every entry a
    {"value", "status", "n"} dict (extra/missing entry keys are an
    error — the UI depends on the exact shape).
    """
    if not evidence_sources:
        return {}
    unknown = set(evidence_sources) - set(SOURCE_KEYS)
    if unknown:
        raise ValueError(
            f"Unknown evidence source keys {sorted(unknown)}; "
            f"must be among {SOURCE_KEYS}"
        )
    normalized = {}
    for key, entry in evidence_sources.items():
        try:
            extra = set(entry) - {'value', 'status', 'n'}
            if extra or not set(entry) == {'value', 'status', 'n'}:
                raise ValueError(f"entry for {key!r} must have exactly "
                                 f"'value'/'status'/'n' keys, got {sorted(entry)}")
            normalized[key] = source(**entry)
        except TypeError as e:
            raise ValueError(f"entry for {key!r} is not a plain dict: {e}")
    return normalized


def compute_coverage(results: List, prong_scores: Dict[str, float],
                     prongs_total: int) -> Dict[str, object]:
    """Top-level coverage summary for the evaluation response.

    Claim counts come from Factual Accuracy's run over the merged claim
    list, using the always-on five-way relation track:
      - claims_verified:   claims with a confirmed or denied relation
                           (rule-based KB verdicts, or verifier verdicts
                           when llm_verify upgraded a KB-unknown claim)
      - claims_partial:    claims the verifier labelled partially_supported
      - claims_unverified: everything else (unknown, conflated, skipped)
    The three counts always sum to claims_total. judge_scored /
    rules_scored are true when at least one llm_judge / rules evidence
    entry scored; prongs_scored counts prongs with at least one
    aggregate=True scored dimension (the same membership rule as
    aggregated_scores.prong_scores).
    """
    claims_total = claims_verified = claims_partial = 0
    claims_confirmed = claims_denied = 0
    judge_scored = rules_scored = False
    fa_seen = False

    for result in results:
        if result.error:
            continue
        for dim in result.dimensions:
            evidence = dim.metadata.get('evidence_sources') or {}
            if dim.name == 'Factual Accuracy' and not fa_seen:
                fa_seen = True
                counts = dim.metadata.get('relation_counts') or {}
                claims_total = int(dim.metadata.get('num_claims', 0) or 0)
                claims_confirmed = counts.get('confirmed', 0)
                claims_denied = counts.get('denied', 0)
                claims_verified = claims_confirmed + claims_denied
                claims_partial = counts.get('partially_supported', 0)
            if evidence.get('llm_judge', {}).get('status') == 'scored':
                judge_scored = True
            if evidence.get('rules', {}).get('status') == 'scored':
                rules_scored = True

    claims_unverified = max(0, claims_total - claims_verified - claims_partial)
    return {
        'claims_total': claims_total,
        'claims_verified': claims_verified,
        'claims_confirmed': claims_confirmed,
        'claims_denied': claims_denied,
        'claims_partial': claims_partial,
        'claims_unverified': claims_unverified,
        'judge_scored': judge_scored,
        'rules_scored': rules_scored,
        'prongs_scored': len(prong_scores),
        'prongs_total': prongs_total,
    }
