"""Prong 3: Extraction-Based Evaluation.

Extracts claims from text using spaCy dependency parsing, then verifies
them against offline Wikidata. Shares a single ClaimExtractor and
OfflineWikidata instance across all five dimensions. The optional
llm_extract flag routes extraction through LLMClaimExtractor (dual
track: spaCy triples + LLM atomic claims, MPropositionneur pattern).
"""

import time
from typing import Optional

from src.base import Evaluator, ProngResult
from src.extraction.claim_extractor import ClaimExtractor
from src.extraction.llm_claim_extractor import LLMClaimExtractor
from src.resources.wikidata_offline import OfflineWikidata
from src.dimensions.prong3_dimensions import (
    FactualAccuracy,
    FactualConsistency,
    TemporalAccuracy,
    ComparativeFactuality,
    ModalityAwareness
)


class Prong3Extraction(Evaluator):
    """Extraction-based evaluator using claim extraction and fact-checking.

    Initializes shared ClaimExtractor (spaCy) and OfflineWikidata (SQLite)
    once, extracts claims from text once, then passes pre-extracted claims
    to all five dimensions. Logs extraction and verification times for
    efficiency tracking (future comparison with vLLM-based extraction).
    """

    def __init__(self, wikidata_db_path: str = None,
                 llm_extractor: Optional[LLMClaimExtractor] = None):
        """Initialize Prong 3.

        Args:
            wikidata_db_path: path to the offline Wikidata SQLite DB
                (None = the default seed DB).
            llm_extractor: injected LLMClaimExtractor for the
                llm_extract track (tests / eval scripts). None creates
                one lazily around the shared spaCy extractor.
        """
        super().__init__(prong_name="Extraction-Based (Prong 3)")
        self._extractor = ClaimExtractor()
        self._llm_extractor = llm_extractor
        try:
            self._wikidata = OfflineWikidata(db_path=wikidata_db_path)
        except Exception:
            self._wikidata = None
        self._init_dimensions()

    def _init_dimensions(self) -> None:
        """Initialize all extraction-based dimensions with shared resources."""
        self.register_dimension(FactualAccuracy(wikidata=self._wikidata))
        self.register_dimension(FactualConsistency(wikidata=self._wikidata))
        self.register_dimension(TemporalAccuracy(wikidata=self._wikidata))
        self.register_dimension(ComparativeFactuality(wikidata=self._wikidata))
        self.register_dimension(ModalityAwareness())

    def evaluate(self, text: str, llm_extract: bool = False) -> ProngResult:
        """
        Evaluate text using extraction-based approaches.

        1. Extract claims from text (once, shared across dimensions)
        2. Pass claims to each dimension for evaluation
        3. Log timing metadata for efficiency tracking

        Args:
            text: the text to evaluate.
            llm_extract: opt in to the LLM claim-extraction track (dual
                output). True routes extraction through LLMClaimExtractor:
                spaCy claims (source "spacy") + LLM atomic claims
                (source "llm"/"both") merged and deduped, passed to the
                dimensions as today. False (the default) is identical to
                the previous spaCy-only behavior.

        Evaluates:
        - Factual Accuracy (claim extraction + Wikidata verification)
        - Factual Consistency (internal contradiction detection via Wikidata)
        - Temporal Accuracy (time anchor extraction + Wikidata verification)
        - Comparative Factuality (superlatives/comparatives + Wikidata)
        - Modality Awareness (hedged vs. strong claims)
        """
        start_time = time.time()
        dimensions = []
        error = None

        try:
            # Extract claims once — shared across all dimensions
            if llm_extract:
                extraction_result = self._get_llm_extractor().extract(text)
            else:
                extraction_result = self._extractor.extract(text)
            claims = extraction_result.claims
            extraction_time_ms = extraction_result.extraction_time_ms

            # Evaluate each dimension with pre-extracted claims
            verification_start = time.perf_counter()
            for dimension in self.dimensions.values():
                score = dimension.evaluate(text, claims=claims)
                dimensions.append(score)
            verification_time_ms = (time.perf_counter() - verification_start) * 1000

        except Exception as e:
            error = str(e)
            extraction_time_ms = 0.0
            verification_time_ms = 0.0

        processing_time = time.time() - start_time

        result = ProngResult(
            prong_name=self.prong_name,
            dimensions=dimensions,
            processing_time=processing_time,
            error=error
        )

        # Attach timing metadata to the result for efficiency tracking
        # (accessible via result.to_dict() in the JSON output)
        if not error:
            # Store timing in the last dimension's metadata as a workaround
            # (ProngResult doesn't have a metadata field — this is tracked in JSON output)
            result._extraction_time_ms = extraction_time_ms
            result._verification_time_ms = verification_time_ms
            result._num_claims = len(claims) if 'claims' in dir() else 0
            result._extraction_metadata = extraction_result.metadata

        return result

    def _get_llm_extractor(self) -> LLMClaimExtractor:
        """Lazily create the LLM claim extractor around the shared spaCy one."""
        if self._llm_extractor is None:
            self._llm_extractor = LLMClaimExtractor(
                spacy_extractor=self._extractor)
        return self._llm_extractor
