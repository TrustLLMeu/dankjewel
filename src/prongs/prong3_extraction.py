"""Prong 3: Extraction-Based Evaluation.

Extracts claims from text using spaCy dependency parsing, then verifies
them against offline Wikidata. Shares a single ClaimExtractor and
OfflineWikidata instance across all five dimensions. The optional
llm_extract flag routes extraction through LLMClaimExtractor (dual
track: spaCy triples + LLM atomic claims, MPropositionneur pattern).
The optional llm_verify flag runs the MiniCheck NLI verifier on
FactualAccuracy's five-way relation track for KB-unknown claims.
"""

import time
from typing import Optional

from src.base import Evaluator, ProngResult
from src.extraction.claim_extractor import ClaimExtractor
from src.extraction.llm_claim_extractor import LLMClaimExtractor
from src.llm_judge_client import get_shared_judge_client
from src.resources.nli_verifier import NliVerifier
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
                 llm_extractor: Optional[LLMClaimExtractor] = None,
                 verifier: Optional[NliVerifier] = None):
        """Initialize Prong 3.

        Args:
            wikidata_db_path: path to the offline Wikidata SQLite DB
                (None = the default seed DB).
            llm_extractor: injected LLMClaimExtractor for the
                llm_extract track (tests / eval scripts). None creates
                one lazily around the shared spaCy extractor.
            verifier: injected NliVerifier for the llm_verify track
                (tests / eval scripts). None means FactualAccuracy
                lazily creates the real MiniCheck verifier on first
                opt-in use.
        """
        super().__init__(prong_name="Extraction-Based (Prong 3)")
        self._extractor = ClaimExtractor()
        self._llm_extractor = llm_extractor
        try:
            self._wikidata = OfflineWikidata(db_path=wikidata_db_path)
            # Cache the row count at construction so /health and response
            # metadata never touch the shared SQLite connection while the
            # evaluation worker uses it.
            self._kb_entities = self._wikidata.entity_count()
        except Exception:
            self._wikidata = None
            self._kb_entities = None
        self._init_dimensions(verifier=verifier)

    def _init_dimensions(self, verifier: Optional[NliVerifier] = None) -> None:
        """Initialize all extraction-based dimensions with shared resources."""
        self.register_dimension(FactualAccuracy(
            wikidata=self._wikidata, verifier=verifier))
        self.register_dimension(FactualConsistency(wikidata=self._wikidata))
        self.register_dimension(TemporalAccuracy(wikidata=self._wikidata))
        self.register_dimension(ComparativeFactuality(wikidata=self._wikidata))
        self.register_dimension(ModalityAwareness())

    def evaluate(self, text: str, llm_extract: bool = False,
                 llm_verify: bool = False,
                 llm_admit: bool = False) -> ProngResult:
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
            llm_verify: opt in to the MiniCheck NLI verifier on
                FactualAccuracy's five-way relation track: KB-unknown
                claims with a resolvable subject are scored against the
                subject's formatted KB facts (confirmed / denied /
                partially_supported). Default False: rule-based five-way
                labels only, no model load, binary math unchanged.
            llm_admit: opt in to the 1.5B admission classifier: each
                admitted claim's sentence is classified as a checkable
                claim or not ([ADMIT] task) and non-claims are dropped.
                The classifier never invents claims; when it is
                unreachable the rule-filtered claims are kept and the
                metadata records how many verdicts were unknown. Default
                False: deterministic gates only.

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
            admission = {
                'admitted_claims': extraction_result.metadata.get('admitted_claims', len(claims)),
                'discarded_candidates': extraction_result.metadata.get('discarded_candidates', {}),
            }

            # Optional LLM admission: drop candidates the 1.5B classifies
            # as non-claims; keep them when the model is unavailable.
            if llm_admit and claims:
                kept = []
                dropped = 0
                unknown = 0
                for claim in claims:
                    sentence = claim.atomic_text or claim.source_sentence or ''
                    verdict = get_shared_judge_client().admit(sentence)
                    if verdict is None:
                        unknown += 1
                    elif not verdict:
                        dropped += 1
                        continue
                    kept.append(claim)
                claims = kept
                admission['llm_admit_dropped'] = dropped
                admission['llm_admit_unknown'] = unknown

            # Evaluate each dimension with pre-extracted claims
            verification_start = time.perf_counter()
            for dim_name, dimension in self.dimensions.items():
                if dim_name == "Factual Accuracy":
                    score = dimension.evaluate(text, claims=claims,
                                               llm_verify=llm_verify,
                                               admission=admission)
                else:
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
            result.metadata = {
                'extraction_time_ms': extraction_time_ms,
                'verification_time_ms': verification_time_ms,
                'num_claims': len(claims) if 'claims' in dir() else 0,
                'extraction': extraction_result.metadata,
            }

        return result

    def _get_llm_extractor(self) -> LLMClaimExtractor:
        """Lazily create the LLM claim extractor around the shared spaCy one."""
        if self._llm_extractor is None:
            self._llm_extractor = LLMClaimExtractor(
                spacy_extractor=self._extractor)
        return self._llm_extractor
