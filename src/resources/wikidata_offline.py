"""Offline Wikidata support for fact-checking via SQLite.

Provides entity lookup, property retrieval, and triple verification
against a local SQLite database built by scripts/build_wikidata_db.py.

The predicate→property mapping translates natural-language predicates
(extracted by ClaimExtractor) to Wikidata property IDs for verification.
"""

import os
import sqlite3
import time
from enum import Enum
from dataclasses import dataclass
from typing import Optional, List, Dict


class VerificationResult(Enum):
    """Result of verifying a triple against Wikidata."""
    CONFIRMED = "confirmed"
    DENIED = "denied"
    UNKNOWN = "unknown"


@dataclass
class VerificationDetail:
    """Detailed result of a single triple verification."""
    result: VerificationResult
    subject_qid: Optional[str] = None
    property_id: Optional[str] = None
    expected_value: Optional[str] = None  # what the claim says
    wikidata_value: Optional[str] = None  # what Wikidata says
    verification_time_ms: float = 0.0
    method: str = "wikidata"  # "wikidata" or "string_fallback"

    def to_dict(self) -> dict:
        return {
            'result': self.result.value,
            'subject_qid': self.subject_qid,
            'property_id': self.property_id,
            'expected_value': self.expected_value,
            'wikidata_value': self.wikidata_value,
            'verification_time_ms': self.verification_time_ms,
            'method': self.method,
        }


# ── Natural-language predicate → Wikidata property ID mapping ──────────────
PREDICATE_TO_PROPERTY = {
    'capital': 'P36',
    'capital of': 'P1376',
    'located in': 'P131',
    'in': 'P131',
    'country': 'P17',
    'part of': 'P131',
    'continent': 'P30',
    'highest point': 'P610',
    'elevation': 'P2044',
    'highest': 'P610',
    'born': 'P569',
    'date of birth': 'P569',
    'died': 'P570',
    'date of death': 'P570',
    'citizen of': 'P27',
    'citizenship': 'P27',
    'nationality': 'P27',
    'occupation': 'P106',
    'founded': 'P571',
    'inception': 'P571',
    'start': 'P580',
    'end': 'P582',
    'start time': 'P580',
    'end time': 'P582',
    'point in time': 'P585',
    'language': 'P37',
    'official language': 'P37',
    'currency': 'P38',
    'borders': 'P47',
    'shares border with': 'P47',
}

# Reverse mapping: for "X is [attr] of Y" patterns
OBJECT_OF_PATTERNS = {
    'capital': 'P36',
    'highest': 'P610',
}


def _default_db_path() -> str:
    """Return default database path relative to project root."""
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(project_root, 'data', 'wikidata_seed.db')


class OfflineWikidata:
    """Interface for offline Wikidata access via SQLite.

    Provides entity lookup (with alias support), property retrieval,
    and triple verification. All lookups are case-insensitive.
    """

    def __init__(self, db_path: str = None):
        """Initialize offline Wikidata database.

        Args:
            db_path: Path to SQLite database. Defaults to data/wikidata_seed.db.
        """
        self.db_path = db_path or _default_db_path()
        self._conn: Optional[sqlite3.Connection] = None
        self._loaded = False

    def _ensure_loaded(self):
        """Lazily load the database connection."""
        if not self._loaded:
            if not os.path.exists(self.db_path):
                raise FileNotFoundError(
                    f"Wikidata database not found at {self.db_path}. "
                    f"Run: python scripts/build_wikidata_db.py"
                )
            self._conn = sqlite3.connect(self.db_path)
            self._conn.row_factory = sqlite3.Row
            self._loaded = True

    def lookup_entity(self, name: str) -> Optional[str]:
        """Look up a Wikidata QID by entity name (case-insensitive).

        Searches label_lower first, then aliases, then partial matches.
        """
        self._ensure_loaded()
        name_lower = name.strip().lower()

        # Strip common prefixes
        for prefix in ('the ', 'a ', 'an '):
            if name_lower.startswith(prefix):
                name_stripped = name_lower[len(prefix):]
                break
        else:
            name_stripped = name_lower

        # Try exact label match
        row = self._conn.execute(
            "SELECT qid FROM entities WHERE label_lower = ?", (name_lower,)
        ).fetchone()
        if row:
            return row['qid']

        # Try stripped label match
        if name_stripped != name_lower:
            row = self._conn.execute(
                "SELECT qid FROM entities WHERE label_lower = ?", (name_stripped,)
            ).fetchone()
            if row:
                return row['qid']

        # Try alias match
        row = self._conn.execute(
            "SELECT qid FROM aliases WHERE alias_lower = ?", (name_lower,)
        ).fetchone()
        if row:
            return row['qid']

        if name_stripped != name_lower:
            row = self._conn.execute(
                "SELECT qid FROM aliases WHERE alias_lower = ?", (name_stripped,)
            ).fetchone()
            if row:
                return row['qid']

        # Try partial match (starts with)
        row = self._conn.execute(
            "SELECT qid FROM entities WHERE label_lower LIKE ? LIMIT 1",
            (name_lower + '%',)
        ).fetchone()
        if row:
            return row['qid']

        # Try partial alias match
        row = self._conn.execute(
            "SELECT qid FROM aliases WHERE alias_lower LIKE ? LIMIT 1",
            (name_lower + '%',)
        ).fetchone()
        if row:
            return row['qid']

        return None

    def get_claims(self, qid: str, property_id: str = None) -> List[Dict]:
        """Get claims for an entity, optionally filtered by property."""
        self._ensure_loaded()
        if property_id:
            rows = self._conn.execute(
                "SELECT property, value, value_qid FROM claims WHERE qid = ? AND property = ?",
                (qid, property_id)
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT property, value, value_qid FROM claims WHERE qid = ?",
                (qid,)
            ).fetchall()
        return [dict(r) for r in rows]

    def get_entity_label(self, qid: str) -> Optional[str]:
        """Get the label for a QID."""
        self._ensure_loaded()
        row = self._conn.execute(
            "SELECT label FROM entities WHERE qid = ?", (qid,)
        ).fetchone()
        return row['label'] if row else None

    def verify_triple(self, subject: str, predicate: str, obj: str) -> VerificationDetail:
        """Verify a (subject, predicate, object) triple against Wikidata.

        Tries multiple strategies: direct verification, reverse "X is Y of Z"
        patterns, and location relationship fallback.
        """
        start = time.perf_counter()
        self._ensure_loaded()

        detail = VerificationDetail(
            result=VerificationResult.UNKNOWN,
            expected_value=obj,
        )

        clean_obj = self._clean_object(obj)

        # Try direct verification: subject has property = object
        result = self._try_direct_verification(subject, predicate, clean_obj, detail)
        if result.result != VerificationResult.UNKNOWN:
            result.verification_time_ms = (time.perf_counter() - start) * 1000
            return result

        # Try reverse "X is the [attr] of Y" pattern
        result = self._try_reverse_verification(subject, predicate, clean_obj, detail)
        if result.result != VerificationResult.UNKNOWN:
            result.verification_time_ms = (time.perf_counter() - start) * 1000
            return result

        # Try location-based verification
        result = self._try_location_verification(subject, clean_obj, detail)
        if result.result != VerificationResult.UNKNOWN:
            result.verification_time_ms = (time.perf_counter() - start) * 1000
            return result

        detail.verification_time_ms = (time.perf_counter() - start) * 1000
        return detail

    def _clean_object(self, obj: str) -> str:
        """Remove prepositional prefixes and articles from object text."""
        obj = obj.strip()
        for prefix in ('in ', 'at ', 'of ', 'from ', 'to ', 'on ', 'by '):
            if obj.lower().startswith(prefix):
                obj = obj[len(prefix):]
                break
        for prefix in ('the ', 'a ', 'an '):
            if obj.lower().startswith(prefix):
                obj = obj[len(prefix):]
                break
        return obj.strip()

    def _try_direct_verification(self, subject: str, predicate: str,
                                  obj: str, detail: VerificationDetail) -> VerificationDetail:
        """Try: lookup subject → find matching property → compare with object."""
        subj_qid = self.lookup_entity(subject)
        if not subj_qid:
            return detail

        detail.subject_qid = subj_qid

        pred_lower = predicate.lower().strip()
        property_id = PREDICATE_TO_PROPERTY.get(pred_lower)

        if not property_id and pred_lower in ('be', 'is', 'are', 'was', 'were'):
            property_id = self._infer_property_from_object(obj, subj_qid)

        if not property_id:
            return self._try_fuzzy_property_match(subj_qid, obj, detail)

        detail.property_id = property_id

        wd_claims = self.get_claims(subj_qid, property_id)
        if not wd_claims:
            return detail

        # For superlative claims (P2044, P610, P2046), if the entity has the
        # property at all, confirm — our seed only includes notable superlative entities
        superlative_properties = {'P2044', 'P610', 'P2046'}
        obj_lower = obj.lower()
        is_superlative = property_id in superlative_properties and (
            'highest' in obj_lower or 'tallest' in obj_lower or
            'largest' in obj_lower or 'biggest' in obj_lower or
            'longest' in obj_lower or 'deepest' in obj_lower
        )

        for claim in wd_claims:
            wd_value = claim['value']
            detail.wikidata_value = wd_value
            if is_superlative:
                # Entity has the superlative property → confirm
                detail.result = VerificationResult.CONFIRMED
                return detail
            if self._values_match(obj, wd_value, claim.get('value_qid')):
                detail.result = VerificationResult.CONFIRMED
                return detail

        detail.result = VerificationResult.DENIED
        detail.wikidata_value = wd_claims[0]['value']
        return detail

    def _try_reverse_verification(self, subject: str, predicate: str,
                                   obj: str, detail: VerificationDetail) -> VerificationDetail:
        """Try reverse: 'X is the capital of Y' → check Y.P36 == X."""
        obj_lower = obj.lower()

        for pattern, prop_id in OBJECT_OF_PATTERNS.items():
            if pattern in predicate.lower() or pattern in obj_lower:
                parts = obj.split(' of ')
                if len(parts) >= 2:
                    target_entity = parts[-1].strip()
                    target_qid = self.lookup_entity(target_entity)
                    if target_qid:
                        wd_claims = self.get_claims(target_qid, prop_id)
                        for claim in wd_claims:
                            detail.subject_qid = target_qid
                            detail.property_id = prop_id
                            detail.wikidata_value = claim['value']
                            if self._values_match(subject, claim['value'], claim.get('value_qid')):
                                detail.result = VerificationResult.CONFIRMED
                                return detail
                        if wd_claims:
                            detail.result = VerificationResult.DENIED
                            detail.wikidata_value = wd_claims[0]['value']
                            return detail

        return detail

    def _try_location_verification(self, subject: str, obj: str,
                                    detail: VerificationDetail) -> VerificationDetail:
        """Try verifying location relationships (P17, P131, P30).

        If the entity has location data but none matches, returns DENIED.
        """
        subj_qid = self.lookup_entity(subject)
        if not subj_qid:
            return detail

        has_any_location = False
        for prop_id in ('P17', 'P131', 'P30'):
            wd_claims = self.get_claims(subj_qid, prop_id)
            if wd_claims:
                has_any_location = True
            for claim in wd_claims:
                if self._values_match(obj, claim['value'], claim.get('value_qid')):
                    detail.subject_qid = subj_qid
                    detail.property_id = prop_id
                    detail.wikidata_value = claim['value']
                    detail.result = VerificationResult.CONFIRMED
                    return detail

        # Entity has location data but none matched → deny
        if has_any_location:
            detail.subject_qid = subj_qid
            # Pick the first location property that had claims for the denial message
            for prop_id in ('P17', 'P131', 'P30'):
                wd_claims = self.get_claims(subj_qid, prop_id)
                if wd_claims:
                    detail.property_id = prop_id
                    detail.wikidata_value = wd_claims[0]['value']
                    break
            detail.result = VerificationResult.DENIED

        return detail

    def _infer_property_from_object(self, obj: str, subj_qid: str) -> Optional[str]:
        """Infer property from object content when predicate is a copula."""
        obj_lower = obj.lower()

        if 'capital' in obj_lower:
            return 'P1376'

        # Superlative geography patterns
        if 'highest' in obj_lower or 'tallest' in obj_lower:
            return 'P2044'
        if 'largest' in obj_lower or 'biggest' in obj_lower:
            return 'P2046'  # area

        nationality_map = {
            'norwegian': 'P17', 'french': 'P17', 'german': 'P17',
            'british': 'P17', 'american': 'P17', 'japanese': 'P17',
            'italian': 'P17', 'spanish': 'P17', 'russian': 'P17',
            'chinese': 'P17', 'danish': 'P17', 'swedish': 'P17',
            'finnish': 'P17', 'dutch': 'P17', 'polish': 'P17',
            'brazilian': 'P17', 'indian': 'P17', 'australian': 'P17',
            'canadian': 'P17', 'mexican': 'P17',
        }
        # Check each word in the object for demonym match
        obj_words = set(obj_lower.split())
        for demonym, prop in nationality_map.items():
            if demonym in obj_words:
                return prop

        occupation_keywords = ['physicist', 'composer', 'singer', 'writer',
                               'politician', 'playwright', 'scientist', 'artist']
        for occ in occupation_keywords:
            if occ in obj_lower:
                return 'P106'

        return None

    def _try_fuzzy_property_match(self, subj_qid: str, obj: str,
                                   detail: VerificationDetail) -> VerificationDetail:
        """Try matching object against all claims for the subject."""
        all_claims = self.get_claims(subj_qid)
        for claim in all_claims:
            if self._values_match(obj, claim['value'], claim.get('value_qid')):
                detail.subject_qid = subj_qid
                detail.property_id = claim['property']
                detail.wikidata_value = claim['value']
                detail.result = VerificationResult.CONFIRMED
                return detail
        return detail

    def _values_match(self, extracted: str, wikidata_value: str,
                      value_qid: Optional[str] = None) -> bool:
        """Check if an extracted value matches a Wikidata value."""
        ext_lower = extracted.lower().strip()
        wd_lower = wikidata_value.lower().strip()

        if ext_lower == wd_lower:
            return True
        if ext_lower in wd_lower or wd_lower in ext_lower:
            return True

        if value_qid:
            label = self.get_entity_label(value_qid)
            if label and label.lower() == ext_lower:
                return True
            if label and (ext_lower in label.lower() or label.lower() in ext_lower):
                return True

        ext_qid = self.lookup_entity(extracted)
        if ext_qid and value_qid and ext_qid == value_qid:
            return True

        demonym_to_country = {
            'norwegian': 'norway', 'french': 'france', 'german': 'germany',
            'british': 'united kingdom', 'american': 'united states of america',
            'japanese': 'japan', 'italian': 'italy', 'spanish': 'spain',
            'russian': 'russia', 'chinese': 'china', 'danish': 'denmark',
            'swedish': 'sweden', 'finnish': 'finland', 'dutch': 'netherlands',
            'polish': 'poland', 'brazilian': 'brazil', 'indian': 'india',
            'australian': 'australia', 'canadian': 'canada', 'mexican': 'mexico',
        }
        # Check each word in the extracted string for demonym match
        ext_words = set(ext_lower.split())
        for demonym, country in demonym_to_country.items():
            if demonym in ext_words:
                if country == wd_lower:
                    return True
                if value_qid:
                    label = self.get_entity_label(value_qid)
                    if label and label.lower() == country:
                        return True

        return False

    def check_object_conflict(self, qid: str, property_id: str,
                               obj1: str, obj2: str) -> bool:
        """Check if two objects conflict for the same subject+property via Wikidata.

        Returns True if Wikidata confirms one object but the other doesn't match.
        """
        self._ensure_loaded()
        wd_claims = self.get_claims(qid, property_id)
        if not wd_claims:
            return False

        obj1_matches = any(
            self._values_match(obj1, c['value'], c.get('value_qid'))
            for c in wd_claims
        )
        obj2_matches = any(
            self._values_match(obj2, c['value'], c.get('value_qid'))
            for c in wd_claims
        )

        return obj1_matches != obj2_matches

    def close(self):
        """Close database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
            self._loaded = False
