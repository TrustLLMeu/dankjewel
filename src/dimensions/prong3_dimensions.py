"""Prong 3: Extraction-Based Dimensions.

Five dimensions that use claim extraction + offline Wikidata verification:
  - Factual Accuracy: verify extracted triples against Wikidata
  - Factual Consistency: detect contradictions among triples (via Wikidata)
  - Temporal Accuracy: verify date claims against Wikidata time properties
  - Comparative Factuality: verify superlative/comparative claims
  - Modality Awareness: classify claims as hedged vs. asserted

Negation handling: when a Claim has negated=True, CONFIRMED and DENIED
verification results are inverted — a negated claim that the triple is
true (CONFIRMED) means the claim itself is false (DENIED), and vice versa.
UNKNOWN stays UNKNOWN (can't invert what we don't know).
"""

import time
from typing import List, Optional

from src.dimensions.base_dimension import ScorableDimension
from src.base import DimensionScore
from src.extraction.claim_extractor import Claim
from src.resources.wikidata_offline import (
    OfflineWikidata, VerificationResult
)


def _invert_result(result: VerificationResult) -> VerificationResult:
    """Invert a verification result for negated claims.

    CONFIRMED → DENIED, DENIED → CONFIRMED, UNKNOWN → UNKNOWN.
    """
    if result == VerificationResult.CONFIRMED:
        return VerificationResult.DENIED
    if result == VerificationResult.DENIED:
        return VerificationResult.CONFIRMED
    return VerificationResult.UNKNOWN


class FactualAccuracy(ScorableDimension):
    """Factual accuracy: verify extracted triples against offline Wikidata.

    Score = confirmed / (confirmed + denied).
    UNKNOWN triples are excluded from the ratio.
    Returns 0.5 when no triples are verifiable.
    Negated claims have their verification result inverted.
    """

    def __init__(self, wikidata: Optional[OfflineWikidata] = None):
        super().__init__(name="Factual Accuracy")
        self.wikidata = wikidata

    def evaluate(self, text: str, claims: List[Claim] = None) -> DimensionScore:
        start = time.perf_counter()
        if not claims or not self.wikidata:
            return self.create_score(
                value=0.5,
                metadata={'status': 'no_claims' if not claims else 'no_wikidata',
                          'num_claims': 0}
            )

        confirmed = 0
        denied = 0
        unknown = 0
        claim_details = []

        for claim in claims:
            # Skip claims with no object — unless existential, which
            # verify_triple handles by parsing the subject into (name, type).
            # Previously ALL 'exist' claims were skipped, dropping a large
            # fraction of FEVER 2.0 claims ("There is a cat called X").
            if not claim.object and claim.predicate != 'exist':
                unknown += 1
                continue

            detail = self.wikidata.verify_triple(
                claim.subject, claim.predicate, claim.object
            )

            # Invert result for negated claims
            effective_result = detail.result
            if claim.negated:
                effective_result = _invert_result(detail.result)

            claim_details.append({
                'claim': claim.to_dict(),
                'verification': detail.to_dict(),
                'negated': claim.negated,
                'effective_result': effective_result.value,
            })

            if effective_result == VerificationResult.CONFIRMED:
                confirmed += 1
            elif effective_result == VerificationResult.DENIED:
                denied += 1
            else:
                unknown += 1

        verifiable = confirmed + denied
        if verifiable == 0:
            score = 0.5  # No verifiable claims
        else:
            score = confirmed / verifiable

        elapsed = (time.perf_counter() - start) * 1000
        return self.create_score(
            value=score,
            raw_value={'confirmed': confirmed, 'denied': denied, 'unknown': unknown},
            metadata={
                'num_claims': len(claims),
                'verifiable': verifiable,
                'claim_details': claim_details,
                'verification_time_ms': elapsed,
            }
        )


class FactualConsistency(ScorableDimension):
    """Factual consistency: detect contradictions among extracted triples.

    For triple pairs sharing a subject, use Wikidata to determine if their
    objects conflict. Score = 1.0 - (contradictory_pairs / total_pairs).
    Falls back to string mismatch when Wikidata returns UNKNOWN for both,
    tagged as method='string_fallback' in metadata.
    """

    def __init__(self, wikidata: Optional[OfflineWikidata] = None):
        super().__init__(name="Factual Consistency")
        self.wikidata = wikidata

    def evaluate(self, text: str, claims: List[Claim] = None) -> DimensionScore:
        start = time.perf_counter()
        if not claims or len(claims) < 2:
            return self.create_score(
                value=1.0,  # Single claim or no claims = no contradiction
                metadata={'status': 'insufficient_claims',
                          'num_claims': len(claims) if claims else 0}
            )

        # Group claims by normalized subject
        subject_groups = {}
        for claim in claims:
            key = claim.subject.lower().strip()
            if self.wikidata:
                qid = self.wikidata.lookup_entity(claim.subject)
                if qid:
                    key = qid  # Use QID as canonical key
            if key not in subject_groups:
                subject_groups[key] = []
            subject_groups[key].append(claim)

        contradictions = 0
        total_pairs = 0
        contradiction_details = []

        for key, group in subject_groups.items():
            if len(group) < 2:
                continue

            for i in range(len(group)):
                for j in range(i + 1, len(group)):
                    c1, c2 = group[i], group[j]
                    total_pairs += 1

                    is_contradiction, method = self._check_pair(c1, c2, key)
                    if is_contradiction:
                        contradictions += 1
                        contradiction_details.append({
                            'claim1': c1.to_dict(),
                            'claim2': c2.to_dict(),
                            'method': method,
                        })

        if total_pairs == 0:
            score = 1.0
        else:
            score = 1.0 - (contradictions / total_pairs)

        elapsed = (time.perf_counter() - start) * 1000
        return self.create_score(
            value=max(0.0, min(1.0, score)),
            raw_value={'contradictions': contradictions, 'total_pairs': total_pairs},
            metadata={
                'num_claims': len(claims),
                'contradiction_details': contradiction_details,
                'verification_time_ms': elapsed,
            }
        )

    def _check_pair(self, c1: Claim, c2: Claim, subject_key: str) -> tuple:
        """Check if two claims about the same subject contradict.

        Returns (is_contradiction: bool, method: str).
        """
        # If predicates are different, they describe different aspects — no contradiction
        if c1.predicate.lower() != c2.predicate.lower():
            if not (c1.predicate.lower() == 'be' and c2.predicate.lower() == 'be'):
                return False, 'predicate_mismatch'

        # If exactly one claim is negated, that's a potential contradiction
        # (one says X, the other says NOT X about the same subject+predicate)
        if c1.negated != c2.negated:
            obj1 = c1.object.strip().lower()
            obj2 = c2.object.strip().lower()
            if obj1 == obj2:
                return True, 'negation_polarity'
            # If objects overlap, it's a contradiction
            if obj1 in obj2 or obj2 in obj1:
                return True, 'negation_polarity'

        obj1 = c1.object.strip().lower()
        obj2 = c2.object.strip().lower()

        if obj1 == obj2:
            return False, 'identical'

        # Try Wikidata-based conflict detection
        if self.wikidata and isinstance(subject_key, str) and subject_key.startswith('Q'):
            for prop_id in ('P17', 'P131', 'P30', 'P36', 'P1376'):
                if self.wikidata.check_object_conflict(subject_key, prop_id, c1.object, c2.object):
                    return True, 'wikidata'

            all_claims = self.wikidata.get_claims(subject_key)
            if all_claims:
                obj1_found = any(
                    self.wikidata._values_match(c1.object, wc['value'], wc.get('value_qid'))
                    for wc in all_claims
                )
                obj2_found = any(
                    self.wikidata._values_match(c2.object, wc['value'], wc.get('value_qid'))
                    for wc in all_claims
                )
                if obj1_found != obj2_found:
                    return True, 'wikidata'
                if obj1_found and obj2_found:
                    return False, 'wikidata'

        if obj1 != obj2 and not (obj1 in obj2 or obj2 in obj1):
            return True, 'string_fallback'

        return False, 'no_conflict'


class TemporalAccuracy(ScorableDimension):
    """Temporal accuracy: verify date claims against Wikidata time properties.

    Filters claims with temporal_anchor, verifies against Wikidata properties
    P585 (point in time), P580 (start time), P582 (end time), P569 (birth),
    P570 (death), P571 (inception).
    Score = fraction of date claims verified correctly.
    Negated claims have their verification result inverted.
    """

    DATE_PROPERTIES = {'P585', 'P580', 'P582', 'P569', 'P570', 'P571'}

    def __init__(self, wikidata: Optional[OfflineWikidata] = None):
        super().__init__(name="Temporal Accuracy")
        self.wikidata = wikidata

    def evaluate(self, text: str, claims: List[Claim] = None) -> DimensionScore:
        start = time.perf_counter()
        if not claims or not self.wikidata:
            return self.create_score(
                value=0.5,
                metadata={'status': 'no_claims' if not claims else 'no_wikidata'}
            )

        temporal_claims = [c for c in claims if c.temporal_anchor]
        if not temporal_claims:
            return self.create_score(
                value=0.5,
                metadata={'status': 'no_temporal_claims', 'num_claims': len(claims)}
            )

        confirmed = 0
        denied = 0
        unknown = 0
        details = []

        for claim in temporal_claims:
            result = self._verify_temporal(claim)
            details.append({
                'claim': claim.to_dict(),
                'result': result,
            })
            if result == 'confirmed':
                confirmed += 1
            elif result == 'denied':
                denied += 1
            else:
                unknown += 1

        verifiable = confirmed + denied
        if verifiable == 0:
            score = 0.5
        else:
            score = confirmed / verifiable

        elapsed = (time.perf_counter() - start) * 1000
        return self.create_score(
            value=score,
            raw_value={'confirmed': confirmed, 'denied': denied, 'unknown': unknown},
            metadata={
                'temporal_claims': len(temporal_claims),
                'details': details,
                'verification_time_ms': elapsed,
            }
        )

    def _verify_temporal(self, claim: Claim) -> str:
        """Verify a temporal claim's date against Wikidata.

        Inverts the result for negated claims.
        """
        subj_qid = self.wikidata.lookup_entity(claim.subject)
        if not subj_qid:
            return 'unknown'

        date_str = claim.temporal_anchor.strip()
        raw_result = None

        for prop in self.DATE_PROPERTIES:
            wd_claims = self.wikidata.get_claims(subj_qid, prop)
            for wc in wd_claims:
                wd_date = wc['value']
                if self._dates_match(date_str, wd_date):
                    raw_result = 'confirmed'
                    break
            if raw_result:
                break

        if raw_result is None:
            all_date_claims = []
            for prop in self.DATE_PROPERTIES:
                all_date_claims.extend(self.wikidata.get_claims(subj_qid, prop))
            if all_date_claims:
                raw_result = 'denied'
            else:
                raw_result = 'unknown'

        # Invert for negated claims
        if claim.negated:
            if raw_result == 'confirmed':
                return 'denied'
            elif raw_result == 'denied':
                return 'confirmed'

        return raw_result

    def _dates_match(self, extracted: str, wikidata: str) -> bool:
        """Check if extracted date matches Wikidata date (flexible matching)."""
        ext = extracted.strip().lower()
        wd = wikidata.strip().lower()

        if ext == wd:
            return True

        if ext in wd or wd in ext:
            return True

        import re
        ext_years = re.findall(r'\d{4}', ext)
        wd_years = re.findall(r'\d{4}', wd)
        if ext_years and wd_years and ext_years[0] == wd_years[0]:
            return True

        return False


class ComparativeFactuality(ScorableDimension):
    """Comparative factuality: verify superlative/comparative claims.

    Filters claims with comparative_tag (JJR/JJS), verifies via Wikidata.
    Score = fraction of verified comparative/superlative claims.
    Negated claims have their verification result inverted.
    """

    def __init__(self, wikidata: Optional[OfflineWikidata] = None):
        super().__init__(name="Comparative Factuality")
        self.wikidata = wikidata

    def evaluate(self, text: str, claims: List[Claim] = None) -> DimensionScore:
        start = time.perf_counter()
        if not claims or not self.wikidata:
            return self.create_score(
                value=0.5,
                metadata={'status': 'no_claims' if not claims else 'no_wikidata'}
            )

        comp_claims = [c for c in claims if c.comparative_tag]
        if not comp_claims:
            return self.create_score(
                value=0.5,
                metadata={'status': 'no_comparative_claims', 'num_claims': len(claims)}
            )

        confirmed = 0
        denied = 0
        unknown = 0
        details = []

        for claim in comp_claims:
            detail = self.wikidata.verify_triple(
                claim.subject, claim.predicate, claim.object
            )

            # Invert result for negated claims
            effective_result = detail.result
            if claim.negated:
                effective_result = _invert_result(detail.result)

            details.append({
                'claim': claim.to_dict(),
                'verification': detail.to_dict(),
                'comparative_type': claim.comparative_tag,
                'negated': claim.negated,
                'effective_result': effective_result.value,
            })

            if effective_result == VerificationResult.CONFIRMED:
                confirmed += 1
            elif effective_result == VerificationResult.DENIED:
                denied += 1
            else:
                unknown += 1

        verifiable = confirmed + denied
        if verifiable == 0:
            score = 0.5
        else:
            score = confirmed / verifiable

        elapsed = (time.perf_counter() - start) * 1000
        return self.create_score(
            value=score,
            raw_value={'confirmed': confirmed, 'denied': denied, 'unknown': unknown},
            metadata={
                'comparative_claims': len(comp_claims),
                'details': details,
                'verification_time_ms': elapsed,
            }
        )


class ModalityAwareness(ScorableDimension):
    """Modality awareness: classify claims as hedged vs. asserted.

    Uses the modifiers list on each claim (modal verbs, uncertainty cues)
    detected at the dependency-tree level by ClaimExtractor.
    Score = hedged_claims / total_claims (higher = more hedged text).
    Returns 0.0 (fully asserted) when no hedging is detected.

    Descriptive/style axis — appropriate hedging is good for genuinely
    uncertain claims and bad for well-established facts, so there is no
    universal "better" direction. Excluded from aggregation
    (aggregate=False) and reported for information only.
    """

    def __init__(self):
        super().__init__(name="Modality Awareness")

    def evaluate(self, text: str, claims: List[Claim] = None) -> DimensionScore:
        start = time.perf_counter()
        if not claims:
            return self.create_score(
                value=0.5,
                metadata={'status': 'no_claims'},
                aggregate=False,
            )

        hedged = 0
        asserted = 0
        details = []

        for claim in claims:
            is_hedged = len(claim.modifiers) > 0
            if is_hedged:
                hedged += 1
            else:
                asserted += 1
            details.append({
                'sentence': claim.source_sentence,
                'hedged': is_hedged,
                'modifiers': claim.modifiers,
            })

        total = hedged + asserted
        if total == 0:
            score = 0.5
        else:
            score = hedged / total

        elapsed = (time.perf_counter() - start) * 1000
        return self.create_score(
            value=score,
            raw_value={'hedged': hedged, 'asserted': asserted},
            metadata={
                'num_claims': total,
                'details': details,
                'evaluation_time_ms': elapsed,
            },
            aggregate=False,
        )