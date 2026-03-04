"""Prong 3: Extraction-Based Evaluation.

Extracts claims from text using spaCy dependency parsing, then verifies
them against offline Wikidata. Shares a single ClaimExtractor and
OfflineWikidata instance across all five dimensions.
"""

import time
from src.base import Evaluator, ProngResult
from src.extraction.claim_extractor import ClaimExtractor
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

    def __init__(self, wikidata_db_path: str = None):
        super().__init__(prong_name="Extraction-Based (Prong 3)")
        self._extractor = ClaimExtractor()
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

    def evaluate(self, text: str) -> ProngResult:
        """
        Evaluate text using extraction-based approaches.

        1. Extract claims from text (once, shared across dimensions)
        2. Pass claims to each dimension for evaluation
        3. Log timing metadata for efficiency tracking

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

        return result
