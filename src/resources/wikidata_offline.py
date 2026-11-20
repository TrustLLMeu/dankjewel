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

from src.extraction.claim_admission import is_junk_name


class VerificationResult(Enum):
    """Result of verifying a triple against Wikidata.

    Five-way relation labels (OmniProv scheme, descriptive track):
    CONFIRMED (entailment), DENIED (contradiction), UNKNOWN (neutral /
    no evidence), PARTIALLY_SUPPORTED (partial), CONFLATED (the claim
    attributes to the subject a property value that belongs to a
    different entity). PARTIALLY_SUPPORTED and CONFLATED never change
    the binary confirmed/(confirmed+denied) math — see the conflation
    rule on verify_triple and the FactualAccuracy five-way track.
    """
    CONFIRMED = "confirmed"
    DENIED = "denied"
    UNKNOWN = "unknown"
    PARTIALLY_SUPPORTED = "partially_supported"
    CONFLATED = "conflated"


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
    'population': 'P1082',
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


# Reverse of PREDICATE_TO_PROPERTY: Wikidata property ID → a natural-
# language predicate phrase, for formatting a subject's KB facts as the
# MiniCheck verifier's grounding document (one
# "<label> <predicate phrase> <value>." line per claim row). The first
# phrase in PREDICATE_TO_PROPERTY order wins — deterministic and
# testable; properties with no mapped phrase fall back to the raw PID.
PROPERTY_TO_PHRASE = {}
for _phrase, _pid in PREDICATE_TO_PROPERTY.items():
    PROPERTY_TO_PHRASE.setdefault(_pid, _phrase)
del _phrase, _pid


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

# ── Claim-type router: possessives, superlatives, quantities ───────────────
# A claim's surface form carries the property it is about: "the USA's
# currency", "the currency of the USA", "population exceeds 330 million".
# Decomposing those forms before the generic predicate map prevents the
# owner entity from being verified against the wrong property (the
# extended KB exposed this: "The USA's currency is the US dollar" was
# denied via P17 because the compound subject resolved to Q30).
ATTRIBUTE_TO_PROPERTY = {
    'currency': 'P38',
    'capital': 'P36',
    'population': 'P1082',
    'anthem': 'P85',
    'national anthem': 'P85',
    'national language': 'P37',
    'official language': 'P37',
    'language': 'P37',
    'continent': 'P30',
    'inception': 'P571',
    'founded': 'P571',
    'head of government': 'P6',
    'head of state': 'P35',
    'legislative body': 'P194',
    # Count claims (C0b): restricted activation in _try_direct_verification
    # — trigger only when object head noun in {states, members, seats} and
    # owner in {USA, Senate, House of Representatives, Congress}. The map
    # enables possessive decomposition; the guard enforces the scope.
    'number of seats': 'P1342',
    'seats': 'P1342',
    'members': 'P1342',
    'member of': 'P463',
    'senate': 'P1342',
    'house of representatives': 'P1342',
    # Symbols (flag entity-valued; national symbols not yet in DB — abstain-safe)
    'flag': 'P163',
    'national flag': 'P163',
    'national bird': 'P2464',
    'national flower': 'P2464',
    'national mammal': 'P2464',
    'national animal': 'P2464',
    'national sport': 'P2464',
}
# P2046 (area) deliberately absent: numeric, descriptive claims abstain.

# ── C0b: count-claim vocabulary and QIDs ─────────────────────────────────
_COUNT_HEAD_NOUNS = frozenset({'states', 'state', 'members', 'member', 'seats', 'seat'})
_COUNT_OWNERS = frozenset({'usa', 'united states', 'united states of america', 'congress',
                            'senate', 'house of representatives'})
# USA states: Q30 P150 with territory filter. Chambers: QIDs for direct P1342.
_COUNT_QIDS = {'usa': 'Q30', 'united states': 'Q30', 'united states of america': 'Q30',
               'congress': 'Q11268', 'senate': 'Q66096', 'house of representatives': 'Q11701'}

# Territories / historical units on Q30 P150 that must not count as states.
_TERRITORY_SUBSTRINGS = ('territory', 'district of columbia', 'american samoa',
                         'virgin islands', 'guam', 'mariana', 'puerto rico',
                         'philippine', 'philippines', 'commonwealth of the philippines')

# Superlative claims need a ranking/quantity comparison. The flat schema
# cannot supply one, so only the two properties whose established path
# already handles superlatives (elevation, highest point) keep the
# auto-confirm; P31/P17/P2046 matches abstain instead of confirming a
# "largest/smallest/most" claim on a generic type word.
_SUPERLATIVE_RE = re.compile(
    r"\b(largest|smallest|highest|lowest|tallest|shortest|longest|deepest|"
    r"biggest|greatest|fastest|slowest|oldest|youngest|most|least)\b",
    re.IGNORECASE,
)
_SUPERLATIVE_PROPERTIES = {'P2044', 'P610'}

# Location containment is only meaningful for location claims. Running it
# for every UNKNOWN made "Chicago is the USA's capital" confirm via
# P17=United States and made "has a Department of the Treasury" deny.
_LOCATION_PREDICATE_CUES = ('locat', 'situat', 'border', 'part of', 'in ')
_LOCATION_OBJECT_BLOCKERS = (
    "'s", 'capital', 'currency', 'population', 'department', 'member',
    'language', 'anthem', 'flag', 'bird', 'animal', 'flower', 'sport',
    'mammal', 'tree', 'gemstone', 'dance', 'most', 'least', 'largest',
    'smallest', 'highest', 'lowest', 'president', 'senate', 'house',
)

# Demonyms ground a nationality claim in the country relation (P17), so
# "Tromsø is a Norwegian city" confirms through Norway. Shared by the
# value matcher and the location-claim guard.
_DEMONYM_TO_COUNTRY = {
    'norwegian': 'norway', 'french': 'france', 'german': 'germany',
    'british': 'united kingdom', 'american': 'united states of america',
    'japanese': 'japan', 'italian': 'italy', 'spanish': 'spain',
    'russian': 'russia', 'chinese': 'china', 'danish': 'denmark',
    'swedish': 'sweden', 'finnish': 'finland', 'dutch': 'netherlands',
    'polish': 'poland', 'brazilian': 'brazil', 'indian': 'india',
    'australian': 'australia', 'canadian': 'canada', 'mexican': 'mexico',
}


def _parse_quantity(text: str):
    """Parse a quantity expression into (number, comparator).

    Comparators: 'gt' (exceed/more than/over), 'lt' (less than/under),
    'approx' (approximately/about), or None for exact equality.
    Returns None when no number is present.
    """
    low = (text or '').lower()
    comparator = None
    if re.search(r'\b(exceed|exceeds|exceeded|more than|greater than|over|above)\b', low):
        comparator = 'gt'
    elif re.search(r'\b(less than|fewer than|under|below)\b', low):
        comparator = 'lt'
    elif re.search(r'\b(approximately|approx\.?|about|around|roughly|nearly)\b', low):
        comparator = 'approx'
    m = re.search(
        r'(-?\d[\d,]*(?:\.\d+)?)\s*(thousand|million|billion|trillion)?',
        low,
    )
    if not m:
        return None
    number = float(m.group(1).replace(',', ''))
    multiplier = {
        'thousand': 1e3, 'million': 1e6,
        'billion': 1e9, 'trillion': 1e12,
    }.get(m.group(2), 1.0)
    return number * multiplier, comparator


def _normalize_entity_text(text: str) -> str:
    """Lowercase, normalise hyphens and US/UK country abbreviations."""
    s = (text or '').lower().replace('-', ' ')
    s = re.sub(r'\b(u\.s\.a\.|u\.s\.|usa|us)\b', 'united states', s)
    s = re.sub(r'\b(u\.k\.|uk)\b', 'united kingdom', s)
    return re.sub(r'\s+', ' ', s).strip()


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
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._loaded = True

    def lookup_entity(self, name: str) -> Optional[str]:
        """Look up a Wikidata QID by entity name (case-insensitive).

        Searches label_lower first, then aliases, then partial matches.
        Slice 0 hardening: junk names (punctuation-only strings, bare
        pronouns/determiners, bare stopwords) never resolve — the old
        prefix matching turned "I" into Iceland and "it" into Italy,
        producing harmful verdicts against the wrong entity's facts.
        Prefix matches now require a 3+ character query and a word
        boundary (the stored label/alias equals the query or starts
        with the query followed by a space).
        """
        self._ensure_loaded()
        name_lower = name.strip().lower()
        if is_junk_name(name_lower):
            return None

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

        # Try partial match (starts with). Slice 0 hardening: the query
        # must match on a word boundary — the stored label/alias equals
        # the query or starts with the query followed by a space ("Oslo
        # C" may match "Oslo City", but "it" may no longer match "Italy").
        # Single-token queries need 4+ characters: a 3-letter common word
        # ("God") otherwise resolves to a longer title ("God Save the
        # King") and grounds unrelated claims. Multi-word partials stay
        # allowed.
        for candidate in dict.fromkeys((name_lower, name_stripped)):
            if is_junk_name(candidate):
                continue
            if len(candidate) < 3 or (' ' not in candidate and len(candidate) < 4):
                continue
            row = self._conn.execute(
                "SELECT qid FROM entities WHERE label_lower LIKE ? LIMIT 1",
                (candidate + ' %',)
            ).fetchone()
            if row:
                return row['qid']
            row = self._conn.execute(
                "SELECT qid FROM aliases WHERE alias_lower LIKE ? LIMIT 1",
                (candidate + ' %',)
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

        Conflation rule (deterministic, always-on): when a triple ends
        up UNKNOWN after every strategy, but the direct attempt had
        resolved the subject AND a property for which the subject has
        its own value, and the object resolves to a KB entity that is a
        value of that SAME property for a DIFFERENT subject, the result
        is CONFLATED instead of UNKNOWN — e.g. "X is the capital of Y"
        where Y is another capital's country: X's own capital-of value
        differs, so the claim conflates X with that other capital. The
        rule only upgrades UNKNOWN results; exact-match CONFIRMED and
        DENIED (including the reverse "X is the capital of Y" denial
        when Y's capital is known and differs) are unchanged.
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

        # Try location-based verification (only for location relations)
        result = self._try_location_verification(
            subject, predicate, clean_obj, detail, raw_obj=obj)
        if result.result != VerificationResult.UNKNOWN:
            result.verification_time_ms = (time.perf_counter() - start) * 1000
            return result

        # ── Conflation rule (deterministic, always-on) ─────────────────
        # Only fires on a final UNKNOWN, so no previous CONFIRMED/DENIED
        # ever changes (binary math is untouched). By this point the
        # direct attempt resolved the subject (detail.subject_qid) and a
        # property for it (detail.property_id), and no later path
        # matched the object — so the subject has its own value(s) for
        # the property, the object missed them, and if the object also
        # resolves to a KB entity that is a value of that SAME property
        # for a DIFFERENT subject, the claim conflates two entities'
        # attributes (e.g. "X is the capital of Y" where Y is another
        # capital's country).
        if detail.result == VerificationResult.UNKNOWN and detail.subject_qid \
                and detail.property_id:
            wd_claims = self.get_claims(detail.subject_qid, detail.property_id)
            obj_missed = not any(
                self._values_match(clean_obj, c['value'], c.get('value_qid'))
                for c in wd_claims
            )
            if wd_claims and obj_missed and self._is_conflated(
                    detail.subject_qid, detail.property_id, clean_obj):
                detail.result = VerificationResult.CONFLATED
                detail.wikidata_value = wd_claims[0]['value']

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

    def _is_superlative(self, obj: str) -> bool:
        """True for a ranking phrase the flat schema cannot check."""
        return bool(_SUPERLATIVE_RE.search(obj or ''))

    def _decompose_possessive(self, text: str):
        """Parse 'The USA's currency' / 'the currency of the USA'.

        Returns (owner_name, property_id) or None when the attribute is
        not one the KB models as a property. The property map is
        deliberately small: only attributes with a direct Wikidata
        property and a clear head noun.
        """
        s = (text or '').strip()
        m = re.match(r"^(.+?)\s+'s\s+(.+)$", s, re.IGNORECASE)
        if not m:
            m = re.match(r"^(.+?)'s\s+(.+)$", s, re.IGNORECASE)
        if m:
            owner, attr = m.group(1), m.group(2)
        else:
            m = re.match(
                r"^(?:the\s+)?(.+?)\s+of\s+(?:the\s+)?(.+)$",
                s, re.IGNORECASE,
            )
            if not m:
                return None
            attr, owner = m.group(1), m.group(2)
        owner = re.sub(r'^(the|a|an)\s+', '', owner.strip(), flags=re.IGNORECASE)
        attr = re.sub(r'^(the|a|an)\s+', '', attr.strip(), flags=re.IGNORECASE).lower()
        if not owner or not attr:
            return None
        prop = ATTRIBUTE_TO_PROPERTY.get(attr)
        if not prop:
            for key in sorted(ATTRIBUTE_TO_PROPERTY, key=len, reverse=True):
                if attr == key or attr.endswith(' ' + key):
                    prop = ATTRIBUTE_TO_PROPERTY[key]
                    break
        return (owner, prop) if prop else None

    def _is_count_object(self, obj: str) -> bool:
        """True when the object head noun denotes a countable membership (C0b)."""
        low = (obj or '').lower()
        return any(re.search(r'\b' + re.escape(w) + r'\b', low) for w in _COUNT_HEAD_NOUNS)

    def _count_claim_kb_count(self, subject: str, obj: str) -> Optional[int]:
        """Deterministic state/seat count for a subject (C0b).

        - USA states: count filtered Q30 P150 entries (territories excluded).
        - Chambers/Congress: direct Q66096/Q11701/Q11268 P1342 value.
        - Returns None when the subject is not a recognised owner or the
          KB carries no relevant property; the caller must abstain.
        """
        subj_norm = _normalize_entity_text(subject or '')
        # Strip leading articles already handled by _normalize; direct lookup:
        for key in sorted(_COUNT_OWNERS, key=len, reverse=True):
            if subj_norm == key or subj_norm.endswith(' ' + key):
                owner_key = key
                break
        else:
            return None
        qid = _COUNT_QIDS.get(owner_key)
        if not qid:
            return None
        obj_low = (obj or '').lower()
        wants_states = bool(re.search(r'\bstates?\b', obj_low))
        wants_members = bool(re.search(r'\b(members?|seats?)\b', obj_low))
        if not (wants_states or wants_members):
            return None
        if qid == 'Q30' and wants_states:
            rows = self.get_claims(qid, 'P150')
            if not rows:
                return None
            filtered = [r for r in rows if not any(t in r['value'].lower() for t in _TERRITORY_SUBSTRINGS)]
            if not filtered:
                return None
            # Q816 (Arizona) retains its P150 row despite its alias shadowing Q30;
            # the substring filter keeps it (value 'Q816'), so 49 named + 1 = 50.
            return len(filtered)
        # Chambers/Congress: seats; USA members total only for total-seats phrasing
        if wants_members:
            claims = self.get_claims(qid, 'P1342')
            if not claims:
                return None
            try:
                return int(float(str(claims[0]['value']).replace(',', '').strip()))
            except (TypeError, ValueError):
                return None
        if wants_states:
            claims = self.get_claims(qid, 'P150')
            if not claims:
                return None
            filtered = [r for r in claims if not any(t in r['value'].lower() for t in _TERRITORY_SUBSTRINGS)]
            return len(filtered) if filtered else None
        return None

    def _verify_count_claim(self, subject: str, obj: str) -> Optional['VerificationDetail']:
        """Attempt a count-based verification (C0b).

        Extracts the claimed integer, looks up the KB count for the
        subject, and returns CONFIRMED (exact match, tolerance 0) or
        DENIED. Never uses the 0.10 approximation band: count claims are
        exact. Returns None when the subject/object is not a count
        claim or the KB lacks the property — caller must abstain, never
        deny.
        """
        if not self._is_count_object(obj):
            return None
        parsed = _parse_quantity(obj)
        if not parsed:
            return None
        claimed, _comparator = parsed
        # Count claims are always exact, ignore comparator
        kb_count = self._count_claim_kb_count(subject, obj)
        if kb_count is None:
            return None
        matched = abs(claimed - kb_count) < 1e-9
        qid, pid = None, None
        subj_norm = _normalize_entity_text(subject)
        for k in sorted(_COUNT_OWNERS, key=len, reverse=True):
            if subj_norm == k or subj_norm.endswith(' ' + k):
                qid = _COUNT_QIDS[k]
                pid = 'P150' if (qid == 'Q30' and bool(re.search(r'\bstates?\b', (obj or '').lower()))) else 'P1342'
                break
        detail = VerificationDetail(
            result=VerificationResult.CONFIRMED if matched else VerificationResult.DENIED,
            expected_value=obj,
            subject_qid=qid,
            property_id=pid,
            wikidata_value=str(kb_count),
        )
        return detail

    def _compare_quantity(self, obj: str, claims: List[Dict],
                          predicate: str = '') -> Optional[VerificationResult]:
        """Compare a numeric claim with the owner's KB quantity values.

        The comparator often lives in the predicate ("exceeds 330
        million"), so parse predicate + object together.
        """
        parsed = _parse_quantity(f"{predicate} {obj}")
        if not parsed:
            return None
        number, comparator = parsed
        values = []
        for claim in claims:
            try:
                values.append(float(str(claim['value']).replace(',', '').strip()))
            except (TypeError, ValueError):
                continue
        if not values:
            return None
        value = max(values)
        if comparator == 'gt':
            return (VerificationResult.CONFIRMED if value > number
                    else VerificationResult.DENIED)
        if comparator == 'lt':
            return (VerificationResult.CONFIRMED if value < number
                    else VerificationResult.DENIED)
        tolerance = 0.10 if comparator == 'approx' else 0.01
        return (VerificationResult.CONFIRMED
                if abs(value - number) / max(value, 1.0) <= tolerance
                else VerificationResult.DENIED)

    def _verify_possessive_attribute(self, owner: str, prop: str, obj: str,
                                     predicate: str = '') -> Optional['VerificationDetail']:
        """Verify an object against owner.prop, bypassing the predicate map."""
        owner_qid = self.lookup_entity(owner)
        if not owner_qid:
            return None
        claims = self.get_claims(owner_qid, prop)
        if not claims:
            return None
        detail = VerificationDetail(
            result=VerificationResult.UNKNOWN,
            expected_value=obj,
            subject_qid=owner_qid,
            property_id=prop,
        )
        for claim in claims:
            if self._values_match(obj, claim['value'], claim.get('value_qid')):
                detail.result = VerificationResult.CONFIRMED
                detail.wikidata_value = claim['value']
                return detail
        if prop == 'P1082':
            compared = self._compare_quantity(obj, claims, predicate)
            if compared is not None:
                detail.result = compared
                detail.wikidata_value = claims[0]['value']
                return detail
        # Entity-valued attributes (flag P163, symbols P2464 etc.) carry an entity,
        # not a description. A numeric/descriptive object ("50 stars") does not deny
        # the entity — it abstains. Only an entity that resolves differently denies.
        if prop in ('P163', 'P2464'):
            # "50 stars and 12 stripes" is not "flag of the United States" — abstain, not deny
            if any(w in obj.lower() for w in ('star', 'stripe', 'color', 'colour')):
                detail.result = VerificationResult.UNKNOWN
                detail.wikidata_value = claims[0]['value']
                return detail
            detail.result = VerificationResult.UNKNOWN
            detail.wikidata_value = claims[0]['value']
            return detail
        detail.result = VerificationResult.DENIED
        detail.wikidata_value = claims[0]['value']
        return detail

    def _is_location_claim(self, predicate: str, obj: str) -> bool:
        """True when the relation is about place containment.

        The location fallback used to run for every UNKNOWN, so a
        possessive or type claim could confirm/deny against the subject's
        country. Restrict it to location predicates and copulas with a
        prepositional place phrase that carries no attribute marker.
        """
        pred = (predicate or '').lower()
        obj_low = (obj or '').lower()
        if any(cue in pred for cue in _LOCATION_PREDICATE_CUES):
            return True
        if pred in ('be', 'is', 'are', 'was', 'were'):
            if any(re.search(r'\b' + re.escape(d) + r'\b', obj_low)
                   for d in _DEMONYM_TO_COUNTRY):
                return True
            if re.search(r'\b(in|of)\s+', obj_low):
                return not any(
                    blocker in obj_low for blocker in _LOCATION_OBJECT_BLOCKERS
                )
        return False

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
        # ── C0b: count claims ("52 states", "100 members") bypass both
        # the possessive decomposition and the predicate map — "The
        # USA's Senate" would decompose to Q30 P1342 (empty), masking the
        # chamber seat count. Trigger only when the object head noun is
        # in {states, members, seats} and the subject is a recognised
        # owner; otherwise fall through.
        count_detail = self._verify_count_claim(subject, obj)
        if count_detail is not None and count_detail.subject_qid is not None:
            detail.result = count_detail.result
            detail.subject_qid = count_detail.subject_qid
            detail.property_id = count_detail.property_id
            detail.wikidata_value = count_detail.wikidata_value
            return detail

        # Compound subjects carry their own property: "The USA's
        # currency" must check P38, not whatever the copula infers.
        decomposed = self._decompose_possessive(subject)
        if decomposed:
            owner, prop = decomposed
            possessive = self._verify_possessive_attribute(owner, prop, obj, predicate)
            if possessive is not None:
                detail.result = possessive.result
                detail.subject_qid = possessive.subject_qid
                detail.property_id = possessive.property_id
                detail.wikidata_value = possessive.wikidata_value
                return detail

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

        # A superlative needs the ranking, which the flat schema does not
        # carry. Only the established elevation/highest-point path keeps
        # its auto-confirm; a P31/P17/P2046 type match must abstain
        # ("largest country", "most populous country", "smallest country").
        if self._is_superlative(obj) and property_id not in _SUPERLATIVE_PROPERTIES:
            detail.result = VerificationResult.UNKNOWN
            return detail

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

    def _is_conflated(self, subj_qid: str, property_id: str, obj: str) -> bool:
        """Deterministic conflation check for a subject+property miss.

        True when `obj` resolves to a KB entity that is a value of the
        SAME `property_id` on a DIFFERENT subject, while the subject's
        own value for that property differs (established by the caller:
        this only runs after the object missed every value match).

        Args:
            subj_qid: QID of the claim's subject (has claims for the property).
            property_id: the resolved Wikidata property ID.
            obj: the claim's object text.
        """
        obj_qid = self.lookup_entity(obj)
        if not obj_qid:
            return False
        self._ensure_loaded()
        row = self._conn.execute(
            "SELECT 1 FROM claims WHERE property = ? AND value_qid = ? "
            "AND qid != ? LIMIT 1",
            (property_id, obj_qid, subj_qid)
        ).fetchone()
        return row is not None

    def format_entity_facts(self, qid: str) -> Optional[str]:
        """Format an entity's KB claims as a grounding document.

        One "<label> <predicate phrase> <value>." line per claim row,
        with the phrase from PROPERTY_TO_PHRASE (the reverse of
        PREDICATE_TO_PROPERTY); properties with no mapped phrase fall
        back to the raw PID. This is the document the MiniCheck verifier
        scores claims against on the five-way track.

        Args:
            qid: QID of the subject entity.

        Returns:
            The formatted facts, or None when the entity is unknown or
            has no claims (the caller keeps relation "unknown").
        """
        self._ensure_loaded()
        label = self.get_entity_label(qid)
        if not label:
            return None
        claims = self.get_claims(qid)
        if not claims:
            return None
        lines = []
        for claim in claims:
            phrase = PROPERTY_TO_PHRASE.get(claim['property'], claim['property'])
            value = claim.get('value') or ''
            lines.append(f"{label} {phrase} {value}.")
        return "\n".join(lines)

    def _try_reverse_verification(self, subject: str, predicate: str,
                                   obj: str, detail: VerificationDetail) -> VerificationDetail:
        """Try reverse: 'X is the capital of Y' → check Y.P36 == X."""
        # Possessive object: "Chicago is the USA's capital" must check
        # USA.P36, not Chicago's country. If the owner has no property
        # claims, fall through so the conflation rule can still label a
        # cross-entity slot ("Trondheim is the capital of Hordaland").
        decomposed = self._decompose_possessive(obj)
        if decomposed:
            owner, prop = decomposed
            reverse = self._verify_possessive_attribute(owner, prop, subject, predicate)
            if reverse is not None:
                detail.result = reverse.result
                detail.subject_qid = reverse.subject_qid
                detail.property_id = reverse.property_id
                detail.wikidata_value = reverse.wikidata_value
                return detail

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

    def _try_location_verification(self, subject: str, predicate: str, obj: str,
                                    detail: VerificationDetail,
                                    raw_obj: str = None) -> VerificationDetail:
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

        # Only location relations reach the containment check. Without
        # this, a possessive or type claim confirms/denies against the
        # subject's country ("Chicago is the USA's capital"). Use the
        # raw object: _clean_object strips the leading "in ", which the
        # guard needs to recognise the relation.
        if not self._is_location_claim(predicate, raw_obj if raw_obj is not None else obj):
            return detail
        if self._is_superlative(obj):
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

        # "The President is the Commander-in-Chief of the armed forces":
        # Wikidata models the office as a subclass (P279) of
        # commander-in-chief. Hyphen/space variants both occur in parsed
        # text.
        if 'commander in chief' in obj_lower.replace('-', ' '):
            return 'P279'

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
        # A ranking phrase ("most populous", "largest") cannot be checked
        # by value overlap; the type/category word would produce a false
        # confirmation.
        if self._is_superlative(obj):
            return detail
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
        ext_lower = _normalize_entity_text(extracted)
        wd_lower = _normalize_entity_text(wikidata_value)

        if ext_lower == wd_lower:
            return True

        # Word-boundary-aware substring matching. The old unbounded
        # `in` check matched "cat" in "category", "state" in "united
        # states" and "Africa" in "African Development Bank" — false
        # positives that inflated REFUTES scores. Word boundaries allow
        # "united states" in "united states of america" while blocking
        # the short-word cases. Hyphens and US/UK abbreviations are
        # normalised first so "US dollar" matches "United States
        # dollar" and "commander-in-chief" matches "Commander in Chief".
        if len(ext_lower) >= 3 and len(wd_lower) >= 3:
            if re.search(r'\b' + re.escape(ext_lower) + r'\b', wd_lower) or \
               re.search(r'\b' + re.escape(wd_lower) + r'\b', ext_lower):
                return True

        if value_qid:
            label = self.get_entity_label(value_qid)
            if label:
                label_lower = _normalize_entity_text(label)
                if label_lower == ext_lower:
                    return True
                if len(label_lower) >= 3 and len(ext_lower) >= 3:
                    if re.search(r'\b' + re.escape(ext_lower) + r'\b', label_lower) or \
                       re.search(r'\b' + re.escape(label_lower) + r'\b', ext_lower):
                        return True

        ext_qid = self.lookup_entity(extracted)
        if ext_qid and value_qid and ext_qid == value_qid:
            return True

        # Check each word in the extracted string for demonym match
        ext_words = set(ext_lower.split())
        for demonym, country in _DEMONYM_TO_COUNTRY.items():
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

    def entity_count(self) -> int:
        """Number of entity rows in the loaded KB."""
        self._ensure_loaded()
        return int(self._conn.execute(
            "SELECT COUNT(*) FROM entities").fetchone()[0])

    def close(self):
        """Close database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
            self._loaded = False