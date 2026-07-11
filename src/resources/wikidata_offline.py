"""Offline Wikidata support for fact-checking via SQLite.

Provides entity lookup, property retrieval, and triple verification
against a local SQLite database built by scripts/build_wikidata_db.py.

The predicate→property mapping translates natural-language predicates
(extracted by ClaimExtractor) to Wikidata property IDs for verification.
"""

import os
import re
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
# Keys are **lemma forms** as produced by spaCy's root.lemma_.lower() —
# e.g. "includes" parses to lemma "include", "directed" to "direct", etc.
# Both lemma and common surface forms are kept so that partial/compound
# predicates (e.g. "born in") still match when spaCy emits them verbatim.
PREDICATE_TO_PROPERTY = {
    # ── Geography ──
    'capital': 'P36',
    'capital of': 'P1376',
    'locate': 'P131',
    'located in': 'P131',
    'in': 'P131',
    'country': 'P17',
    'part of': 'P361',
    'continent': 'P30',
    'highest point': 'P610',
    'elevation': 'P2044',
    'highest': 'P610',
    'border': 'P47',
    'borders': 'P47',
    'share border with': 'P47',
    'shares border with': 'P47',
    'body of water': 'P206',
    'twin city': 'P190',
    'twin town': 'P190',
    'location': 'P276',
    'located at': 'P276',
    'situated in': 'P131',
    'seat of government': 'P159',
    # ── People: life events ──
    'bear': 'P569',       # "was born" → lemma "bear" (archaic) spaCy uses 'bear'
    'born': 'P569',
    'date of birth': 'P569',
    'born in': 'P19',
    'place of birth': 'P19',
    'die': 'P570',
    'died': 'P570',
    'date of death': 'P570',
    'died in': 'P20',
    'place of death': 'P20',
    'citizen of': 'P27',
    'citizenship': 'P27',
    'nationality': 'P27',
    'occupation': 'P106',
    'employer': 'P108',
    'work for': 'P108',
    'worked for': 'P108',
    'work at': 'P108',
    'worked at': 'P108',
    'position held': 'P39',
    'educate at': 'P69',
    'educated at': 'P69',
    'study at': 'P69',
    'studied at': 'P69',
    'spouse': 'P26',
    'marry': 'P26',
    'married to': 'P26',
    'father': 'P22',
    'mother': 'P25',
    'child': 'P40',
    'chairperson': 'P1037',
    'ceo': 'P169',
    'chief executive': 'P169',
    # ── Organizations / business ──
    'subsidiary': 'P355',
    'own by': 'P127',
    'owned by': 'P127',
    'manufacturer': 'P176',
    'make by': 'P176',
    'made by': 'P176',
    # ── Media: film / TV ──
    'instance of': 'P31',
    'subclass of': 'P279',
    'parent taxon': 'P171',
    'include': 'P527',
    'includes': 'P527',
    'has part': 'P527',
    'cast member': 'P161',
    'star in': 'P161',
    'starred in': 'P161',
    'direct': 'P57',
    'directed': 'P57',
    'director': 'P57',
    'direct by': 'P57',
    'directed by': 'P57',
    'produce': 'P162',
    'produced by': 'P162',
    'compose': 'P86',
    'composed by': 'P86',
    'perform': 'P175',
    'performed by': 'P175',
    'record label': 'P264',
    'sign to': 'P264',
    'signed to': 'P264',
    'genre': 'P136',
    'part of series': 'P179',
    'country of origin': 'P495',
    'base in': 'P495',
    'based in': 'P495',
    'broadcast by': 'P449',
    'air on': 'P449',
    'aired on': 'P449',
    'air': 'P449',
    'broadcast': 'P449',
    'production company': 'P465',
    'produced by company': 'P465',
    'author': 'P50',
    'write': 'P50',
    'written by': 'P50',
    'create': 'P170',
    'created by': 'P170',
    'notable work': 'P800',
    'known for': 'P800',
    'present in': 'P1441',
    'appear in': 'P1441',
    'appear': 'P1441',    # "appeared in Flash Comics" → P1441 (present in work)
    # ── Sports ──
    'member of': 'P54',
    'play for': 'P54',
    'plays for': 'P54',
    'sport': 'P118',
    'position played': 'P413',
    'plays position': 'P413',
    'participant in': 'P1344',
    # ── Language / culture ──
    'language': 'P37',
    'official language': 'P37',
    'currency': 'P38',
    'language of work': 'P407',
    'original language': 'P364',
    'speak': 'P1412',
    'speaks': 'P1412',
    'movement': 'P135',
    'award': 'P166',
    'award received': 'P166',
    'receive': 'P166',
    # ── Time ──
    'found': 'P571',     # "was founded" → root lemma "found"
    'founded': 'P571',
    'inception': 'P571',
    'start': 'P580',
    'end': 'P582',
    'start time': 'P580',
    'end time': 'P582',
    'point in time': 'P585',
    # ── Succession / follows ──
    'succeed': 'P155',   # "X succeeded by Y" — P155=follows, P156=followed by
    'succeed by': 'P156',
    'follow': 'P155',
    'follow by': 'P156',
    # ── Publication / release ──
    'publish': 'P577',
    'published': 'P577',
    'release': 'P577',
    'released': 'P577',
    'debut': 'P577',
    'debuted': 'P577',
    # ── Sports / competitions ──
    'host': 'P276',        # "Villa Park hosted FA Cup" → location
    'hosted': 'P276',
    'win': 'P166',         # "Chris Bosh won title" → award received
    'won': 'P166',
    'compete in': 'P1344',
    'competed in': 'P1344',
    # ── Location (broader) ──
    'headquarter': 'P159',
    'headquartered': 'P159',
    'headquartered in': 'P159',
    'base': 'P131',
    'seat': 'P159',
    # ── Naming / identity ──
    'is call': 'P1476',    # title (for works named after something)
    'go by': 'P1449',      # nickname — best-effort
    'know as': 'P1449',
    'known as': 'P1449',
    # ── Found / establish ──
    'establish': 'P571',
    'established': 'P571',
    'establish in': 'P571',
    'found in': 'P571',
    # ── Broader verb surface forms (spaCy lemma variants) ──
    'is headquarter': 'P159',   # "is headquartered in" spaCy → "is headquarter"
    'was broadcast': 'P449',
    'was include': 'P361',      # "was included in" → part of
    'include in': 'P361',
    'premier': 'P577',          # "premiered at number one" → publication date
    'premiered': 'P577',
    'was bear': 'P569',         # spaCy lemma for "was born" (alt form)
    'was draft': 'P569',        # "was drafted" (sports) — no clean mapping; use birth as fallback?
    'have': 'P39',              # vague; best-effort → position held
}

# Reverse mapping: for "X is [attr] of Y" patterns
OBJECT_OF_PATTERNS = {
    'capital': 'P36',
    'highest': 'P610',
    'part': 'P361',
    'member': 'P54',
    'subclass': 'P279',
}


# ── Qualifier-gating: guard against over-confident weak matches ────────────
# FEVER 2.0's REFUTES claims are frequently produced by mutating a single
# precise detail in an otherwise-true sentence — an ordinal ("the THIRD
# James Bond film"), a role clause ("directed by X"), or a relative date
# ("before 1990") — while the generic type/category match still holds true.
# Our flat single-property verification has no way to see these embedded
# qualifiers, so weak/generic match paths (type-noun instance-of, fuzzy
# substring-against-all-claims, superlative auto-confirm, location
# containment) happily confirm the whole sentence. The functions below
# explicitly check embedded qualifiers and either deny (explicit
# contradiction) or abstain (unverifiable detail) rather than risk a false
# CONFIRMED.
_ROLE_QUALIFIER_PATTERNS = {
    'directed by': ('P57',),
    'written by': ('P50',),
    'composed by': ('P86',),
    'produced by': ('P162', 'P170'),
    'created by': ('P170',),
    'performed by': ('P175',),
}
_SERIES_TYPE_NOUNS = (
    'film', 'movie', 'single', 'album', 'book', 'novel', 'season',
    'episode', 'entry', 'installment', 'sequel', 'game',
)
_ORDINAL_SERIES_RE = re.compile(
    r'\b(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth)\b'
)
_TEMPORAL_QUALIFIER_RE = re.compile(
    r'\b(before|after|since|until)\s+\d{3,4}\b|\bbetween\s+\d{3,4}\s+and\s+\d{3,4}\b'
)


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

        # ── Multi-word name fallback ────────────────────────────────────
        # Handle names with middle names / extra words, e.g.
        # "Marie Sklodowska Curie" → try "Marie Curie", "Sklodowska Curie"
        # by dropping interior tokens one at a time.
        words = name_lower.split()
        if len(words) >= 3:
            # Drop each single interior word in sequence
            for i in range(1, len(words) - 1):
                candidate = ' '.join(words[:i] + words[i + 1:])
                row = self._conn.execute(
                    "SELECT qid FROM entities WHERE label_lower = ?", (candidate,)
                ).fetchone()
                if row:
                    return row['qid']
                row = self._conn.execute(
                    "SELECT qid FROM aliases WHERE alias_lower = ?", (candidate,)
                ).fetchone()
                if row:
                    return row['qid']

        # ── Compound-NP decomposition ────────────────────────────────────
        # Handles:
        #   "Sensitive Skin's first series"  → "Sensitive Skin"
        #   "The area of Muş Province"       → "Muş Province"
        #   "members of Congress"            → "Congress"
        #   "a movie called The Little Prince 2015 film" → "The Little Prince"
        #   "the governor of Novgorod Oblast" → "Novgorod Oblast"

        # Possessive: "X's Y..." → try "X"
        import re as _re
        m = _re.match(r"^(.+?)'s\b", name_lower)
        if m:
            qid = self.lookup_entity(m.group(1).strip())
            if qid:
                return qid

        # "X of Y" patterns — try the part after "of"
        m = _re.match(r'^(?:the\s+)?(?:\w+\s+){0,3}of\s+(.+)$', name_lower)
        if m:
            tail = m.group(1).strip()
            qid = self.lookup_entity(tail)
            if qid:
                return qid

        # "a/an [type] called/named/goes by [Name]"
        m = _re.match(
            r'^(?:a|an|the|no)\s+\S[\w\s,]+\s+(?:called|named|go by the name of)\s+(.+)$',
            name_lower
        )
        if m:
            name_part = m.group(1).strip().split(',')[0].strip()
            qid = self.lookup_entity(name_part)
            if qid:
                return qid

        # Last two words (e.g. "first series" stripped → just try last N words)
        if len(words) >= 2:
            for start in range(1, min(len(words), 4)):
                candidate = ' '.join(words[start:])
                if len(candidate) > 2:
                    row = self._conn.execute(
                        "SELECT qid FROM entities WHERE label_lower = ?", (candidate,)
                    ).fetchone()
                    if row:
                        return row['qid']
                    row = self._conn.execute(
                        "SELECT qid FROM aliases WHERE alias_lower = ?", (candidate,)
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

        # ── Existential claims: "There is a cat called Simon Pegg" ──
        # The extractor produces predicate='exist' with the type+name bundled
        # in the subject. Parse it into (name, type) and verify as
        # (name, be, type) — reusing the copula path + negation inversion.
        if predicate.lower().strip() == 'exist':
            parsed = self._parse_existential_subject(subject)
            if parsed:
                name, type_str = parsed
                return self.verify_triple(name, 'be', type_str)
            detail.verification_time_ms = (time.perf_counter() - start) * 1000
            return detail

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

    def _parse_existential_subject(self, subject: str):
        """Parse an existential subject like 'a cat called Simon Pegg'.

        Extracts the entity name and its asserted type.
        Returns (name, type_str) or None if the pattern is unrecognized.

        Handles common FEVER 2.0 existential patterns:
          'a cat called Simon Pegg'             → ('Simon Pegg', 'cat')
          'a squid that goes by the name of Pink' → ('Pink', 'squid')
          'no Brazilian called Freddie Highmore'  → ('Freddie Highmore', 'Brazilian')
          'a politician called Alan White'       → ('Alan White', 'politician')
          'a director, Sean Baker, who was...'   → ('Sean Baker', 'director')
        """
        s = subject.strip()

        # Strip leading articles / negation words
        for prefix in ('a ', 'an ', 'the ', 'no '):
            if s.lower().startswith(prefix):
                s = s[len(prefix):].strip()
                break

        # Try split keywords (longest first to avoid partial matches)
        for keyword in ('goes by the name of', 'called', 'named'):
            idx = s.lower().find(keyword)
            if idx != -1:
                type_part = s[:idx].strip()
                name_part = s[idx + len(keyword):].strip()

                # Clean type: strip relative clauses
                for sep in (' that ', ' which ', ' who '):
                    type_part = type_part.split(sep)[0].strip()

                # Clean name: strip trailing relative clauses and commas
                name_part = name_part.split(',')[0].strip()
                for sep in (' that ', ' who ', ' which '):
                    name_part = name_part.split(sep)[0].strip()

                # Strip leading articles from name
                for art in ('the ', 'a ', 'an '):
                    if name_part.lower().startswith(art):
                        name_part = name_part[len(art):].strip()
                        break

                if name_part and type_part:
                    return name_part, type_part
                break

        # Fallback: comma-separated "a director, Sean Baker, who..."
        if ',' in s:
            parts = [p.strip() for p in s.split(',') if p.strip()]
            if len(parts) >= 2:
                type_part = parts[0]
                for sep in (' that ', ' which ', ' who '):
                    type_part = type_part.split(sep)[0].strip()
                name_part = parts[1]
                for sep in (' that ', ' who ', ' which '):
                    name_part = name_part.split(sep)[0].strip()
                # Strip articles from type
                for art in ('a ', 'an ', 'the '):
                    if type_part.lower().startswith(art):
                        type_part = type_part[len(art):].strip()
                        break
                if name_part and type_part:
                    return name_part, type_part

        return None

    def _apply_qualifier_gate(self, subj_qid: str, obj: str) -> Optional['VerificationResult']:
        """Guard weak/generic CONFIRMED matches against embedded qualifiers.

        Returns:
            VerificationResult.DENIED  — an explicit role qualifier
                ("directed by X") contradicts Wikidata data we actually have.
            VerificationResult.UNKNOWN — an unverifiable qualifier is present
                (ordinal series position, relative/ranged date, or a role
                qualifier for which we have no data to check) — abstain
                rather than risk a false CONFIRMED.
            None — no gating needed; caller should keep its original result.
        """
        obj_lower = obj.lower()

        # ── Role qualifiers: "directed by X", "written by X", ... ──
        for phrase, props in _ROLE_QUALIFIER_PATTERNS.items():
            idx = obj_lower.find(phrase)
            if idx == -1:
                continue
            name_part = obj_lower[idx + len(phrase):].strip()
            name_part = re.split(r'\band\b|,|;|\.', name_part)[0].strip()
            if not name_part or len(name_part) < 2:
                continue

            has_data = False
            matched = False
            for prop in props:
                wd_claims = self.get_claims(subj_qid, prop)
                if wd_claims:
                    has_data = True
                for c in wd_claims:
                    if self._values_match(name_part, c['value'], c.get('value_qid')):
                        matched = True
                        break
                if matched:
                    break

            if has_data and not matched:
                return VerificationResult.DENIED
            if not has_data:
                return VerificationResult.UNKNOWN

        # ── Ordinal series position: "the third James Bond film" ──
        # No per-entity series-ordinal data exists in our flat claims
        # schema, so this cannot be verified — abstain instead of
        # confirming on the generic type match alone.
        if _ORDINAL_SERIES_RE.search(obj_lower) and any(
            noun in obj_lower for noun in _SERIES_TYPE_NOUNS
        ):
            return VerificationResult.UNKNOWN

        # ── Relative/ranged temporal qualifiers: "before 1990", "between X and Y" ──
        # FEVER fixers commonly shift a real date by a few years; we cannot
        # do arithmetic date reasoning here, so abstain rather than confirm.
        if _TEMPORAL_QUALIFIER_RE.search(obj_lower):
            return VerificationResult.UNKNOWN

        return None

    def _try_direct_verification(self, subject: str, predicate: str,
                                  obj: str, detail: VerificationDetail) -> VerificationDetail:
        """Try: lookup subject → find matching property → compare with object."""
        subj_qid = self.lookup_entity(subject)
        if not subj_qid:
            return detail

        detail.subject_qid = subj_qid

        pred_lower = predicate.lower().strip()
        property_id = PREDICATE_TO_PROPERTY.get(pred_lower)

        # Track whether the property was heuristically inferred — inferred
        # properties are guesses, so a non-match should return UNKNOWN, not
        # DENIED (we might have guessed the wrong property).
        inferred = False
        if not property_id and pred_lower in ('be', 'is', 'are', 'was', 'were'):
            property_id = self._infer_property_from_object(obj, subj_qid)
            inferred = True

        if not property_id:
            return self._try_fuzzy_property_match(subj_qid, obj, detail)

        detail.property_id = property_id

        wd_claims = self.get_claims(subj_qid, property_id)
        if not wd_claims:
            # ── Reverse-inclusion fallback ─────────────────────────────
            # "X includes/has-part Y" in biology maps to P527, but Wikidata
            # often stores the relation the other way: Y.P171 (parent taxon)
            # = X, or Y.P361 (part of) = X.  If the forward P527 is absent,
            # try the reverse.
            if property_id == 'P527':
                obj_qid = self.lookup_entity(obj)
                if obj_qid:
                    for rev_prop in ('P171', 'P361'):
                        rev_claims = self.get_claims(obj_qid, rev_prop)
                        for claim in rev_claims:
                            if self._values_match(subject, claim['value'], claim.get('value_qid')):
                                detail.subject_qid = obj_qid
                                detail.property_id = rev_prop
                                detail.wikidata_value = claim['value']
                                detail.result = VerificationResult.CONFIRMED
                                return detail
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
                # Entity has the superlative property → confirm, unless an
                # embedded qualifier we can't verify says otherwise.
                if inferred:
                    gate = self._apply_qualifier_gate(subj_qid, obj)
                    if gate is not None:
                        detail.result = gate
                        return detail
                detail.result = VerificationResult.CONFIRMED
                return detail
            if self._values_match(obj, wd_value, claim.get('value_qid')):
                # Weak/heuristic property matches (copula-inferred) are
                # gated: embedded role/ordinal/temporal qualifiers that
                # contradict or can't be checked override the confirmation.
                if inferred:
                    gate = self._apply_qualifier_gate(subj_qid, obj)
                    if gate is not None:
                        detail.result = gate
                        return detail
                detail.result = VerificationResult.CONFIRMED
                return detail

        # No claim matched. Only DENY if the property was explicitly mapped
        # (high confidence). If it was heuristically inferred, the non-match
        # might mean we guessed the wrong property — return UNKNOWN.
        if inferred:
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

        Only denies if the object itself resolves to a known entity (i.e.,
        looks like a place name). Non-place objects return UNKNOWN so we
        don't false-deny genre/occupation/type claims.

        Temporal objects (bare years like "1973", date strings) are skipped
        entirely — they are not location entities and would produce
        false denials via the DB's partial-match on year-prefixed entities.
        """
        # Guard: skip temporal / purely-numeric objects (years, date strings).
        # A bare year like "1973" is not a place; trying to look it up can
        # hit entities whose names start with that year and cause false denials.
        if re.match(r'^\d{1,4}s?$', obj.strip()):
            return detail

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
                    gate = self._apply_qualifier_gate(subj_qid, obj)
                    if gate is not None:
                        detail.subject_qid = subj_qid
                        detail.property_id = prop_id
                        detail.result = gate
                        return detail
                    detail.subject_qid = subj_qid
                    detail.property_id = prop_id
                    detail.wikidata_value = claim['value']
                    detail.result = VerificationResult.CONFIRMED
                    return detail

        # Only deny if the object looks like a genuine place — it must
        # resolve to a known entity AND that entity must itself carry a
        # geographic property (P17/P131/P30/P36) or be instance-of a
        # place-like type (P31 → country/city/etc). This blocks abstract
        # nouns that happen to resolve to a generic concept entity (e.g.
        # "protectorate" → Q164142, which has no location data of its own)
        # from being mistaken for a place and triggering a false denial.
        obj_qid = self.lookup_entity(obj)
        obj_is_place = False
        if obj_qid:
            if any(self.get_claims(obj_qid, p) for p in ('P17', 'P131', 'P30', 'P36')):
                obj_is_place = True
            else:
                place_type_words = {
                    'country', 'city', 'state', 'province', 'continent',
                    'island', 'republic', 'territory', 'region', 'county',
                    'municipality', 'district', 'town', 'village',
                }
                for c in self.get_claims(obj_qid, 'P31'):
                    if any(w in c['value'].lower() for w in place_type_words):
                        obj_is_place = True
                        break

        if has_any_location and obj_is_place:
            detail.subject_qid = subj_qid
            for prop_id in ('P17', 'P131', 'P30'):
                wd_claims = self.get_claims(subj_qid, prop_id)
                if wd_claims:
                    detail.property_id = prop_id
                    detail.wikidata_value = wd_claims[0]['value']
                    break
            detail.result = VerificationResult.DENIED

        return detail

    def _infer_property_from_object(self, obj: str, subj_qid: str) -> Optional[str]:
        """Infer property from object content when predicate is a copula.

        Handles:
          - Capital / superlative geography patterns
          - Demonyms (nationality → P17)
          - Occupations (physicist, composer → P106)
          - Taxonomy ("a marsupial", "a mammal" → P279 subclass-of, or P171 parent-taxon)
          - Instance-of ("a cat", "a country", "a film" → P31)
        """
        obj_lower = obj.lower()

        if 'capital' in obj_lower:
            return 'P1376'

        # Superlative geography patterns
        if 'highest' in obj_lower or 'tallest' in obj_lower:
            return 'P2044'
        if 'largest' in obj_lower or 'biggest' in obj_lower:
            return 'P2046'  # area

        # ── Taxonomy: "is a mammal", "is a marsupial" → P279 subclass-of ──
        # If the object is itself a known entity (a taxon QID), use P279.
        obj_qid = self.lookup_entity(obj)
        if obj_qid:
            # Check if the object entity has P105 (taxon rank) or P171 (parent taxon)
            # — if so, the subject "is a" that taxon → P279
            taxon_markers = self.get_claims(obj_qid, 'P105') + self.get_claims(obj_qid, 'P171')
            if taxon_markers:
                return 'P279'
            # If the object entity is itself an instance-of something (has P31),
            # then "subject is a object" → P31
            if self.get_claims(obj_qid, 'P31'):
                return 'P31'

        # ── Instance-of: "is a cat", "is a country", "is a film" → P31 ──
        # Common type nouns that map to P31 (instance of)
        type_nouns = {
            'cat', 'dog', 'bird', 'fish', 'animal', 'mammal', 'marsupial',
            'country', 'city', 'state', 'province', 'continent', 'island',
            'film', 'movie', 'series', 'show', 'album', 'song', 'book',
            'novel', 'play', 'game', 'sport', 'team', 'league', 'company',
            'corporation', 'organization', 'university', 'school', 'hospital',
            'river', 'lake', 'mountain', 'ocean', 'sea', 'desert', 'forest',
            'building', 'bridge', 'tower', 'airport', 'station',
            'politician', 'actor', 'actress', 'singer', 'musician', 'writer',
            'author', 'poet', 'artist', 'painter', 'sculptor', 'director',
            'producer', 'composer', 'athlete', 'player', 'coach', 'manager',
            'scientist', 'physicist', 'chemist', 'biologist', 'mathematician',
            'engineer', 'architect', 'doctor', 'lawyer', 'judge', 'teacher',
            'soldier', 'general', 'admiral', 'pilot', 'astronaut',
            'king', 'queen', 'prince', 'princess', 'emperor', 'empress',
            'president', 'prime minister', 'senator', 'governor', 'mayor',
        }
        # Check if any type noun appears as a standalone word in the object
        obj_words = set(obj_lower.replace('.', '').replace(',', '').split())
        if obj_words & type_nouns:
            return 'P31'

        # ── Demonyms: nationality → P17 ──
        nationality_map = {
            'norwegian': 'P17', 'french': 'P17', 'german': 'P17',
            'british': 'P17', 'american': 'P17', 'japanese': 'P17',
            'italian': 'P17', 'spanish': 'P17', 'russian': 'P17',
            'chinese': 'P17', 'danish': 'P17', 'swedish': 'P17',
            'finnish': 'P17', 'dutch': 'P17', 'polish': 'P17',
            'brazilian': 'P17', 'indian': 'P17', 'australian': 'P17',
            'canadian': 'P17', 'mexican': 'P17', 'greek': 'P17',
            'turkish': 'P17', 'korean': 'P17', 'portuguese': 'P17',
            'irish': 'P17', 'scottish': 'P17', 'welsh': 'P17',
            'austrian': 'P17', 'swiss': 'P17', 'belgian': 'P17',
            'argentine': 'P17', 'egyptian': 'P17', 'iranian': 'P17',
            'iraqi': 'P17', 'pakistani': 'P17', 'bangladeshi': 'P17',
            'thai': 'P17', 'vietnamese': 'P17', 'indonesian': 'P17',
            'malaysian': 'P17', 'filipino': 'P17', 'nigerian': 'P17',
            'south african': 'P17', 'kenyan': 'P17', 'ethiopian': 'P17',
        }
        obj_words = set(obj_lower.split())
        for demonym, prop in nationality_map.items():
            if demonym in obj_words:
                return prop

        # ── Occupations (broader list) ──
        occupation_keywords = [
            'physicist', 'composer', 'singer', 'writer', 'author', 'poet',
            'politician', 'playwright', 'scientist', 'artist', 'painter',
            'actor', 'actress', 'musician', 'director', 'producer',
            'athlete', 'footballer', 'basketball', 'baseball', 'soccer',
            'engineer', 'architect', 'mathematician', 'philosopher',
            'historian', 'journalist', 'novelist', 'screenwriter',
        ]
        for occ in occupation_keywords:
            if occ in obj_lower:
                return 'P106'

        # ── Record label / music industry ──
        if 'record label' in obj_lower or 'label' in obj_lower:
            return 'P264'

        # ── Genre ──
        if 'genre' in obj_lower:
            return 'P136'

        return None

    def _try_fuzzy_property_match(self, subj_qid: str, obj: str,
                                   detail: VerificationDetail) -> VerificationDetail:
        """Try matching object against all claims for the subject.

        This is the weakest verification path — it ignores the predicate
        entirely and just checks for ANY claim value overlapping the object
        text. Always gated: a match here is far more likely to be a
        coincidental partial overlap than the direct/explicit paths.
        """
        all_claims = self.get_claims(subj_qid)
        for claim in all_claims:
            if self._values_match(obj, claim['value'], claim.get('value_qid')):
                gate = self._apply_qualifier_gate(subj_qid, obj)
                if gate is not None:
                    detail.subject_qid = subj_qid
                    detail.result = gate
                    return detail
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

        # Word-boundary-aware substring matching. The old `ext_lower in
        # wd_lower` check matched "cat" in "category", "us" in "house" —
        # false positives that inflated REFUTES scores. Word boundaries
        # allow "united states" in "united states of america" while
        # blocking "cat" in "category".
        if len(ext_lower) >= 3 and len(wd_lower) >= 3:
            if re.search(r'\b' + re.escape(ext_lower) + r'\b', wd_lower) or \
               re.search(r'\b' + re.escape(wd_lower) + r'\b', ext_lower):
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