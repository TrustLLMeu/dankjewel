"""LLM-based atomic-claim extraction for Prong 3 (dual track).

MPropositionneur pattern (Pommeret et al., LLM-based Atomic Propositions
Help Weak Extractors, KG-LLM @ LREC 2026): a small local LLM decomposes
text into decontextualized atomic propositions, and the existing weak
extractor (spaCy triples) runs on those propositions instead of being
replaced by them. Here the [CLAIMS] task on the shared 1.5B server
produces the atomic claims; the existing ClaimExtractor triple logic
then parses each one into (subject, predicate, object) so downstream
Wikidata verification is unchanged.

Dual output: the spaCy track on the raw text is kept and merged with
the LLM track; identical (subject, predicate, object) triples collapse
to one claim with source="both" so a fact is never double-counted.

Opinion filtering is NOT implemented: the verified 1.5B keeps opinion
claims, and such claims verify UNKNOWN against the KB — the
FactualAccuracy dimension's honest denominator (confirmed/verifiable)
already excludes them. No generative selection/VeriScore stage.
"""

import logging
import re
import time
from typing import Dict, List, Optional, Tuple

from src.extraction.claim_admission import (
    filter_claims, sentence_reject_reason,
)
from src.extraction.claim_extractor import (
    Claim, ClaimExtractor, ExtractionResult, admission_metadata,
)
from src.llm_judge_client import JudgeError, LLMJudgeClient, get_shared_judge_client

logger = logging.getLogger(__name__)

# Blank-line separated paragraphs; cross-sentence pronouns inside a
# paragraph resolve because the whole paragraph goes to one [CLAIMS] call.
_PARAGRAPH_SPLIT = re.compile(r"\n\s*\n")

# Error strings kept short in metadata (full httpx exceptions are long).
_MAX_ERROR_LEN = 120


def _split_paragraphs(text: str) -> List[str]:
    """Split text into non-blank, blank-line separated paragraphs."""
    if not text or not text.strip():
        return []
    return [p.strip() for p in _PARAGRAPH_SPLIT.split(text) if p.strip()]


def _merge_claims(spacy_claims: List[Claim], llm_claims: List[Claim]) -> List[Claim]:
    """Merge the two tracks, collapsing identical triples.

    Key is the exact (subject, predicate, object) triple. A triple found
    by both tracks becomes one claim with source="both" (the llm
    atomic_text is preferred); duplicate triples within a track also
    collapse. Never double-counts a fact.
    """
    merged: List[Claim] = []
    index: Dict[Tuple[str, str, str], int] = {}
    for claim in spacy_claims:
        key = (claim.subject, claim.predicate, claim.object)
        if key in index:
            continue
        index[key] = len(merged)
        merged.append(claim)
    for claim in llm_claims:
        key = (claim.subject, claim.predicate, claim.object)
        pos = index.get(key)
        if pos is None:
            index[key] = len(merged)
            merged.append(claim)
        elif merged[pos].source == "spacy":
            merged[pos].source = "both"
            merged[pos].atomic_text = claim.atomic_text
    return merged


class LLMClaimExtractor:
    """Dual-track claim extractor: spaCy triples + LLM atomic claims.

    Same public contract as ClaimExtractor: extract(text) ->
    ExtractionResult. The LLM track makes ONE [CLAIMS] call per
    paragraph; each returned atomic claim is re-run through the
    existing spaCy triple logic to get subject/predicate/object
    (LLM-track claims get source="llm" and atomic_text=the atomic
    sentence).

    Failure semantics: an unreachable, timed-out, or unparseable claims
    model contributes zero claims for that paragraph — recorded as a
    short string in ExtractionResult.metadata['llm_errors'] — and
    extract() never raises into Prong 3 because of the LLM track.
    """

    def __init__(self, client: Optional[LLMJudgeClient] = None,
                 spacy_extractor: Optional[ClaimExtractor] = None,
                 include_spacy: bool = True):
        """Create the dual-track extractor.

        Args:
            client: [CLAIMS] client (test stubs can inject any object
                with a claims(text) -> list[str] method). None uses the
                process-wide shared judge client, lazily.
            spacy_extractor: shared ClaimExtractor for the spaCy track
                and the per-atomic-claim triple logic. None creates one
                lazily.
            include_spacy: also run the spaCy track on the raw text and
                merge (dual output, the default). False = LLM track only.
        """
        self._client = client
        self._spacy = spacy_extractor
        self._include_spacy = include_spacy

    def _get_client(self) -> LLMJudgeClient:
        """Lazily resolve the shared [CLAIMS] client."""
        if self._client is None:
            self._client = get_shared_judge_client()
        return self._client

    def _get_spacy(self) -> ClaimExtractor:
        """Lazily create the shared spaCy extractor."""
        if self._spacy is None:
            self._spacy = ClaimExtractor()
        return self._spacy

    def extract(self, text: str) -> ExtractionResult:
        """Extract claims from text on both tracks and merge.

        Applies the same deterministic admission gates as the spaCy
        track (Slice 1): the raw-text spaCy track cleans markdown and
        filters its triples, every LLM atomic sentence is checked with
        the sentence-level gate before triple parsing, and the merged
        list goes through filter_claims. metadata carries the shared
        admission keys plus the LLM track's own counters.

        Args:
            text: the text to extract claims from.

        Returns:
            ExtractionResult with merged, admitted claims (source
            "spacy" / "llm" / "both") and metadata {'admitted_claims':
            n, 'discarded_candidates': {reason: count}, 'llm_paragraphs':
            n, 'llm_claims': n, 'llm_errors': [...]}.
        """
        start = time.perf_counter()
        spacy_claims: List[Claim] = []
        num_sentences = 0
        discarded: Dict[str, int] = {}

        if self._include_spacy:
            spacy_result = self._get_spacy().extract(text)
            spacy_claims = spacy_result.claims
            num_sentences = spacy_result.num_sentences
            for reason, count in (spacy_result.metadata
                                  .get('discarded_candidates', {})).items():
                discarded[reason] = discarded.get(reason, 0) + count
        else:
            num_sentences = self._get_spacy().count_sentences(text)

        paragraphs = _split_paragraphs(text)
        errors: List[str] = []
        llm_claims = self._llm_claims(paragraphs, errors, discarded)

        merged = _merge_claims(spacy_claims, llm_claims)
        admitted, merge_discarded = filter_claims(merged)
        for reason, count in merge_discarded.items():
            discarded[reason] = discarded.get(reason, 0) + count

        elapsed_ms = (time.perf_counter() - start) * 1000.0
        llm_count = sum(1 for c in admitted if c.source in ("llm", "both"))
        metadata = admission_metadata(len(admitted), discarded)
        metadata.update({
            'llm_paragraphs': len(paragraphs),
            'llm_claims': llm_count,
            'llm_errors': errors,
        })
        return ExtractionResult(
            claims=admitted,
            extraction_time_ms=elapsed_ms,
            num_sentences=num_sentences,
            metadata=metadata,
        )

    def _llm_claims(self, paragraphs: List[str], errors: List[str],
                    discarded: Dict[str, int]) -> List[Claim]:
        """Run the [CLAIMS] task per paragraph and triple-parse the atoms.

        A failed paragraph (unreachable / timeout / unparseable reply)
        contributes zero claims and appends one short error string.
        Each atomic sentence passes the deterministic sentence-level
        admission gate before triple parsing; rejected atoms are
        counted into `discarded` by reason.
        """
        claims: List[Claim] = []
        client = self._get_client()
        spacy = self._get_spacy()
        for paragraph in paragraphs:
            try:
                atomic = client.claims(paragraph)
            except JudgeError as e:
                errors.append(str(e)[:_MAX_ERROR_LEN])
                continue
            for atom in atomic:
                reason = sentence_reject_reason(atom)
                if reason:
                    discarded[reason] = discarded.get(reason, 0) + 1
                    continue
                for claim in spacy.extract_from_sentence_text(atom):
                    claim.source = "llm"
                    claim.atomic_text = atom
                    claims.append(claim)
        return claims
