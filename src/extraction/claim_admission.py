"""Deterministic claim-admission gates for Prong 3 (precision-first).

An exported run on markdown teaching prose produced 76 "claims", ~39 of
them fragments (bullet punctuation, contraction predicates, headings,
pronoun subjects) and zero verifiable ones. These gates keep
non-claims out of the claim pipeline: a triple is admitted only when
its sentence looks like an assertion and the triple looks like a
(subject, predicate, object) fact about entities.

Everything here is deterministic — lexicons and regexes, no models, no
network. spaCy contributes indirectly: the extractor's parsed
subject/predicate/object strings are what the triple-level checks
inspect. The same lexicons gate KB lookups (Slice 0): a pronoun or
punctuation fragment must never resolve to an entity.

Discard reasons (the histogram keys):
    markdown   raw markdown residue (bullet/heading markers, **, `)
    heading    headings and labels (short, no terminal period, ends
               with ':', Title-Case heavy)
    question   interrogative sentences
    imperative imperative sentences (verb-first openers)
    meta       teaching/organising meta-discourse ("here are",
               "as your teacher", "for example", ...)
    pronoun    bare pronoun/determiner subject or object, or a subject
               with no lexical (noun/proper-noun) head — LLM-track
               claims are exempt (the LLM resolves pronouns)
    malformed  empty/punctuation-only parts, contraction-fragment
               predicates, empty objects (except existentials),
               subject == object, discourse-marker objects
    definition encyclopedic definition: "X is a/an <abstract noun>"
               ("A false claim is a statement")
    demonstrative text-deictic subject: "these claims", "this article",
               "that statement" — refers to the document, not the world
    duplicate  near-duplicate of an already-admitted triple (same
               lemmas ignoring case/punctuation)
"""

import re
from typing import Dict, List, Optional, Tuple

# Closed-class words that never denote an entity. Pronouns/determiners
# per the slice brief; extended with the wh-words that parse as junk
# subjects ("Who is making the claim?").
PRONOUN_DETERMINERS = frozenset({
    'i', 'me', 'my', 'we', 'us', 'you', 'your', 'it', 'its', 'he', 'she',
    'they', 'them', 'this', 'that', 'these', 'those', 'there', 'here',
    'who', 'what', 'which',
})

# Function words: a name consisting solely of these (plus punctuation)
# is never an entity reference. Used both for KB-lookup rejection and
# for the lexical-head check on claim subjects.
STOPWORDS = frozenset({
    'a', 'an', 'the', 'and', 'or', 'but', 'nor', 'so', 'yet', 'of', 'in',
    'on', 'at', 'to', 'by', 'with', 'from', 'as', 'into', 'onto', 'over',
    'under', 'about', 'against', 'between', 'during', 'through', 'without',
    'within', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'am',
    'do', 'does', 'did', 'done', 'have', 'has', 'had', 'having', 'will',
    'would', 'shall', 'should', 'can', 'could', 'may', 'might', 'must',
    'not', 'no', 'yes', 'all', 'any', 'some', 'such', 'than', 'then',
    'too', 'very', 'just', 'also', 'more', 'most', 'other', 'own', 'same',
    's', 't', 'll', 've', 're', 'd', 'm', 'o',
})

# Object-side discourse markers: an "object" that is only a place/time
# deictic is not a nominal complement ("The boiling point changes there").
DISCOURSE_MARKER_OBJECTS = frozenset({
    'here', 'there', 'now', 'then', 'always', 'never', 'again', 'instead',
})

# Adverbial/prepositional fragments that the dependency parser hands back
# as objects although they assert nothing checkable. "The United States
# has a standing army in peacetime by default" produced an object
# "by default"; "In most states, electors cast ..." produced an object
# "In most states" from the sentence-initial adjunct.
ADVERBIAL_OBJECT_FRAGMENTS = frozenset({
    'by default', 'in general', 'in fact', 'in practice', 'in theory',
    'at least', 'at most', 'in particular', 'on average', 'of course',
    'in most states', 'in some states', 'in a few states', 'in many states',
    'as slates', 'as a result', 'for example', 'for instance',
    'in response', 'in turn', 'by contrast', 'on the other hand',
    'in addition', 'in reality', 'in principle', 'per se',
})

# Placeholder objects mark a non-assertion, not a fact about the subject:
# "The true cause is unknown" asserts nothing that a KB can check.
PLACEHOLDER_OBJECTS = frozenset({
    'unknown', 'unclear', 'uncertain', 'not known', 'not clear',
    'undetermined', 'debatable', 'disputed', 'tbd', 'n/a', 'none',
})

# Anaphoric objects whose referent lies outside the triple: "Nixon later
# popularized the term" — which term is only recoverable from the previous
# sentence, so the triple is not verifiable on its own.
ANAPHORIC_OBJECTS = frozenset({
    'the term', 'the terms', 'the latter', 'the former', 'the same',
    'the opposite', 'the reverse', 'the concept', 'the idea', 'the phrase',
    'the word', 'the process', 'the practice',
})

# Encyclopedic-definition gate (slice 6d): "X is a/an <abstract noun>"
# asserts a category, not a checkable fact about a specific entity
# ("A false claim is a statement", "A country is a political entity").
ABSTRACT_NOUN_HEADS = frozenset({
    'statement', 'claim', 'idea', 'concept', 'reason', 'entity', 'defense',
    'example', 'question', 'topic', 'thing', 'term', 'definition',
    'phenomenon', 'process', 'matter', 'issue', 'notion', 'belief', 'opinion',
})

# Text-deictic subject gate (slice 6d): demonstratives over the text
# itself ("These claims use real numbers", "This article discusses ...")
# refer to the document, not to entities in the world.
GENERIC_TEXT_HEADS = frozenset({
    'claim', 'claims', 'statement', 'statements', 'example', 'examples',
    'article', 'section', 'text', 'passage', 'paragraph', 'list', 'essay',
    'sentence', 'sentences', 'document', 'chapter', 'table',
})
_DEMONSTRATIVE_RE = re.compile(r'^(these|those|this|that)\s+', re.I)
_DEFINITION_ARTICLE_RE = re.compile(r'^(a|an)\s+', re.I)

# Meta-discourse lexicon (slice brief): sentences that organise or teach
# rather than assert. Matched at sentence start, case-insensitive.
META_DISCOURSE_PHRASES = (
    'here are', 'here is', 'as your teacher', 'let me explain',
    'in this section', 'for example', 'for instance', 'this means',
    'that is',
)

# Verb-first sentence openers (imperatives).
IMPERATIVE_OPENERS = frozenset({
    'let', 'always', 'never', 'remember', 'consider', 'imagine',
    'suppose', 'note', 'look', 'listen', 'think', 'please', 'use',
    'verify', 'seek', 'question', 'check', 'avoid', 'beware', 'try',
    'keep', 'take', 'give', 'see', 'read', 'write', 'call', 'imagine',
})

_WORD_RE = re.compile(r"[\w'’-]+", re.UNICODE)
# Contraction fragments left in predicate position by the parser when
# the source had markdown-contorted text: "'m", "’", "s", ":*".
_CONTRACTION_PRED_RE = re.compile(r"^(?:['’`][a-z]{0,2}|[a-z]?['’][a-z]{1,2}|['’`])$")
_MARKDOWN_PREFIX_RE = re.compile(r'^\s*(?:[*#>+-]\s*|\d{1,3}[.)]\s)')


# ── Markdown cleaning ────────────────────────────────────────────────────────

def clean_markdown(text: str) -> str:
    """Normalise markdown prose into plain text. Deterministic, no models.

    - curly quotes/contractions → ASCII ('’' → "'", '“”' → '"')
    - heading markers at line starts ("### Title") stripped
    - blockquote markers stripped
    - leading list markers ("*", "-", "1.", "1)") stripped per line, so
      each bullet becomes its own plain line
    - emphasis/code markers removed anywhere ("**bold**", "*ital*",
      "_under_", "`code`"), plus any stray '*', '`' left over

    Emphasised line labels ("**Claim:** X") become plain "Label: X"
    lines; the extractor's split_label() then separates label from
    content so commentary labels can be gated and content labels
    parsed on their own.
    """
    if not text:
        return text
    # Curly quotes and ellipses → straight ASCII.
    text = (text.replace('’', "'").replace('‘', "'")
                .replace('“', '"').replace('”', '"').replace('…', '...'))
    # Heading markers at line starts.
    text = re.sub(r'^[ \t]{0,3}#{1,6}[ \t]*', '', text, flags=re.M)
    # Blockquote markers at line starts.
    text = re.sub(r'^[ \t]{0,3}>[ \t]?', '', text, flags=re.M)
    # Leading list markers: "- ", "* ", "+ ", "1. ", "1) ".
    text = re.sub(r'^([ \t]*)(?:[-*+•]|\d{1,3}[.)])[ \t]+', r'\1', text,
                  flags=re.M)
    # Emphasis / code markers, paired first then stray characters.
    text = re.sub(r'\*\*([^*\n]+)\*\*', r'\1', text)
    text = re.sub(r'\*([^*\n]+)\*', r'\1', text)
    text = re.sub(r'`([^`\n]+)`', r'\1', text)
    text = re.sub(r'\b_([^_\n]+)_\b', r'\1', text)
    text = text.replace('*', '').replace('`', '')
    return text


# ── Line labels ──────────────────────────────────────────────────────────────

# "Label:" prefixes that mark explanation/teaching commentary rather
# than content. A "Why it's false:" line is discourse ABOUT a claim.
_LABEL_RE = re.compile(r"^([A-Za-z][\w'’() ]{0,50}?):\s+(.+)$", re.S)


def split_label(line: str) -> Tuple[Optional[str], Optional[str]]:
    """Split a leading "Label:" prefix off a cleaned line.

    Returns (label, content) — both None when the line has no label.
    Only fires on short leading label phrases (≤ 8 words), never on
    mid-sentence colons.
    """
    m = _LABEL_RE.match(line.strip())
    if not m:
        return None, None
    label, content = m.group(1).strip(), m.group(2).strip()
    if len(label.split()) > 8 or not content:
        return None, None
    return label, content


def is_commentary_label(label: str) -> bool:
    """True for labels that mark explanation/teaching discourse.

    "Why it's false:" / "How it works:" style wh-labels are commentary
    about a claim, not the claim's content — their lines are gated as
    meta-discourse. Content labels ("Claim:", "Source:") pass and their
    content is parsed on its own.
    """
    low = (label or '').strip().lower()
    return low.startswith(('why', 'how', 'explanation', 'note'))


# ── Corrections (use-mention) ────────────────────────────────────────────────

# A correction line retracts or replaces the statement immediately before
# it. That makes the earlier statement a *mentioned* claim (source=quote)
# and the correction the speaker's assertion. The opener list is matched
# at line start only: "Actually, ..." as a whole-sentence discourse marker,
# never the same word inside a clause.
CORRECTION_LABELS = frozenset({
    'correction', 'corrections', 'correction to the claim', 'update',
    'clarification', 'erratum',
})
CORRECTION_OPENERS = (
    'actually,', 'in fact,', 'in reality,', 'to be precise,',
    'more precisely,', 'more accurately,', 'correction:', 'update:',
    'clarification:', 'i was wrong', "that's false", 'that is false',
    'this is false', 'this is incorrect', 'the correct statement is',
)


def is_correction_label(label: str) -> bool:
    """True when a line label announces a correction."""
    return (label or '').strip().lower() in CORRECTION_LABELS


def split_correction_opener(line: str) -> Tuple[str, bool]:
    """Strip a line-initial correction opener.

    Returns ``(content, is_correction)``. "Actually, the UK has ..." →
    ("the UK has ...", True); an ordinary line is returned unchanged
    with ``False``. A colon opener ("Correction: X") is normally already
    split off by ``split_label``; this helper covers the label-less forms
    and the case where the label regex declined (long content).
    """
    stripped = (line or '').lstrip()
    low = stripped.lower()
    for opener in CORRECTION_OPENERS:
        if low.startswith(opener):
            rest = stripped[len(opener):].lstrip(' ,;:-—')
            if rest:
                return rest, True
    return line, False


# ── Sentence-level gates ─────────────────────────────────────────────────────

def _is_heading_or_label(sent: str) -> bool:
    """Headings/labels: short, no terminal period, ends with ':', or
    Title-Case heavy."""
    s = sent.strip()
    if s.endswith(':'):
        return True
    if s.endswith(('.', '!', '?', '"')):
        return False
    words = _WORD_RE.findall(s)
    if not words or len(words) > 10:
        return False
    capitalized = [w for w in words if w[0].isupper()]
    return len(capitalized) >= max(2, (len(words) + 1) // 2)


_QUOTE_SPAN_RE = re.compile(r'["“”]([^"“”]{10,300}?)["“”]')
_REPORTED_LABEL_RE = re.compile(
    r'^(?:claim|statement|example|false claim)\s*:\s*(.+)$', re.I)


def extract_reported_claims(text: str) -> List[Tuple[str, str]]:
    """Find quoted or labelled propositions that the text *mentions*.

    The spaCy track treats every sentence as the speaker's assertion, but
    teaching and reporting prose embeds claims in quotes or after a
    ``Claim:`` label (the use-mention distinction). This pass returns
    ``(quoted_sentence, outer_line)`` pairs for those embedded
    propositions; the extractor runs its triple logic on the quoted
    sentence and marks the claim ``source="quote"``. Admission then
    applies the sentence gates to the quoted sentence (via
    ``atomic_text``) rather than to the commentary line.

    Deduplicated, order-preserving. Quoted spans shorter than three words
    or without terminal punctuation are ignored.
    """
    found: List[Tuple[str, str]] = []
    seen = set()

    def add(quoted: str, outer: str) -> None:
        quoted = quoted.strip().strip('"“”\'')
        if not quoted or len(quoted.split()) < 3:
            return
        if not quoted.rstrip().endswith(('.', '!', '?')):
            return
        if quoted in seen:
            return
        seen.add(quoted)
        found.append((quoted, outer))

    for raw_line in text.split('\n'):
        line = raw_line.strip()
        if not line:
            continue
        for match in _QUOTE_SPAN_RE.finditer(line):
            add(match.group(1), line)
        label_match = _REPORTED_LABEL_RE.match(line)
        if label_match:
            add(label_match.group(1), line)
    return found


def sentence_reject_reason(sent: str) -> Optional[str]:
    """Why a sentence is not admissible, or None if it is.

    Reason order: markdown, question, meta, imperative, heading —
    "Let me explain ..." is meta-discourse (the brief's lexicon) rather
    than an imperative, a "Here are ... :" line is meta before the
    label-shaped heading rule fires, and an ordinary label like "Why
    it's false:" falls through to heading.
    """
    s = sent.strip()
    if not s:
        return 'markdown'
    # Raw markdown residue: bullet/quote/heading prefixes or bold marks.
    if _MARKDOWN_PREFIX_RE.match(s) or '**' in s or '`' in s:
        return 'markdown'
    if s.endswith('?') or s.endswith('?"'):
        return 'question'
    low = s.lower()
    for phrase in META_DISCOURSE_PHRASES:
        if low.startswith(phrase):
            return 'meta'
    first = _WORD_RE.search(low)
    if first and first.group(0) in IMPERATIVE_OPENERS:
        return 'imperative'
    if _is_heading_or_label(s):
        return 'heading'
    return None


def is_admissible_sentence(sent: str) -> bool:
    """True when the sentence can carry an assertive claim.

    False for headings/labels, questions, imperatives and
    meta-discourse (see sentence_reject_reason for the exact rules).
    """
    return sentence_reject_reason(sent) is None


# ── Name / subject gates (shared with the KB lookup, Slice 0) ───────────────

def _tokens(phrase: str) -> List[str]:
    return [t.lower() for t in _WORD_RE.findall(phrase or '')]


def _has_lexical_head(phrase: str) -> bool:
    """True when the phrase contains a lexical (noun/proper-noun-ish)
    token: a word that is not a pronoun, determiner, stopword or bare
    digit."""
    for token in _tokens(phrase):
        if token in PRONOUN_DETERMINERS or token in STOPWORDS:
            continue
        if re.search(r'[a-z]', token):
            return True
    return False


def is_junk_name(name: str) -> bool:
    """True for names that must never resolve to a KB entity.

    Punctuation/symbol-only strings, bare pronouns/determiners ("it",
    "these", "who") and bare stopwords ("the", "of") — the strings the
    old prefix matching happily resolved ("I" → Iceland, "it" → Italy).
    """
    s = (name or '').strip().lower()
    if not s or not re.search(r'\w', s, re.UNICODE):
        return True
    if s in PRONOUN_DETERMINERS or s in STOPWORDS:
        return True
    return False


def is_referential_subject(subject: str) -> bool:
    """True when a claim subject can denote an entity.

    Pronouns, punctuation fragments and all-function-word phrases are
    never referential; anything with a lexical head ("The Earth",
    "9 out of 10 dentists", "Brand X") is.
    """
    s = (subject or '').strip()
    if not s or not re.search(r'\w', s, re.UNICODE):
        return False
    low = s.lower()
    if low in PRONOUN_DETERMINERS or low in STOPWORDS:
        return False
    return _has_lexical_head(s)


# ── Triple-level gates ───────────────────────────────────────────────────────

def _is_punct_only(s: str) -> bool:
    return not re.search(r'\w', s.strip(), re.UNICODE)


def _has_unbalanced_delimiter(s: str) -> bool:
    """True when parentheses/brackets do not pair up.

    The spaCy track can hand back a parenthetical fragment as a subject
    or object ("Article I Section 8)", "Under the U.S. Constitution
    Article I Section 8)") when the source had an inline citation. A
    dangling delimiter marks a parser artifact, never a checkable name.
    """
    text = s or ''
    for opener, closer in (('(', ')'), ('[', ']')):
        if text.count(opener) != text.count(closer):
            return True
    return False


def admit_triple(claim) -> Tuple[bool, str]:
    """Decide whether an extracted Claim is an admissible factual claim.

    Returns (admitted, reason); reason is 'admitted' or one of the
    discard reasons (markdown / heading / question / imperative / meta /
    pronoun / malformed / definition / demonstrative / adverbial /
    placeholder / anaphoric). 'duplicate' is assigned by filter_claims.

    Sentence-level reasons come from claim.source_sentence; the
    triple-level gates inspect the extracted strings. Claims produced by
    the LLM track (source 'llm') are exempt from the pronoun and
    lexical-head checks — that track decontextualizes and resolves
    pronouns — but not from malformed. A 'both' claim is not exempt: its
    subject string also appears in the spaCy track, so a pronoun there is
    still junk.
    """
    # ── Sentence-level reasons (from the source sentence) ─────────────
    # Quoted/reported claims are gated on the quoted sentence itself;
    # the outer line ("Claim: ...", "The teacher said ...") is
    # commentary by construction.
    if getattr(claim, 'source', '') == 'quote' and claim.atomic_text:
        sentence_text = claim.atomic_text
    else:
        sentence_text = claim.source_sentence or ''
    reason = sentence_reject_reason(sentence_text)
    if reason:
        return False, reason

    subj = claim.subject.strip()
    pred = claim.predicate.strip()
    obj = claim.object.strip()

    # ── Malformed: structure that can never be a fact triple ──────────
    if not subj or not pred:
        return False, 'malformed'
    # Empty objects are only valid for existential claims.
    if not obj and claim.predicate.strip() != 'exist':
        return False, 'malformed'
    if _is_punct_only(subj) or _is_punct_only(pred) or (obj and _is_punct_only(obj)):
        return False, 'malformed'
    if _CONTRACTION_PRED_RE.match(pred):
        return False, 'malformed'
    if subj.lower() == obj.lower():
        return False, 'malformed'
    if _has_unbalanced_delimiter(subj) or _has_unbalanced_delimiter(obj):
        return False, 'malformed'
    if obj.lower() in DISCOURSE_MARKER_OBJECTS:
        return False, 'malformed'

    # ── Adverbial / placeholder / anaphoric objects ───────────────────
    # "The United States has ... by default"; "The true cause is
    # unknown"; "Nixon popularized the term". None of these objects
    # denote a checkable value.
    obj_low = obj.lower().strip().rstrip('.').strip()
    if obj_low in ADVERBIAL_OBJECT_FRAGMENTS:
        return False, 'adverbial'
    if obj_low in PLACEHOLDER_OBJECTS:
        return False, 'placeholder'
    if obj_low in ANAPHORIC_OBJECTS:
        return False, 'anaphoric'

    # ── Encyclopedic definitions: "X is a/an <abstract noun>" ─────────
    if pred.lower() == 'be' and _DEFINITION_ARTICLE_RE.match(obj):
        tokens = _tokens(obj)
        if tokens and tokens[-1] in ABSTRACT_NOUN_HEADS:
            return False, 'definition'

    # ── Text-deictic subjects: "these claims", "this article" ─────────
    if _DEMONSTRATIVE_RE.match(subj):
        tokens = _tokens(subj)
        if tokens and tokens[-1] in GENERIC_TEXT_HEADS:
            return False, 'demonstrative'

    # ── Pronoun / lexical-head gates (LLM track exempt) ───────────────
    if claim.source != 'llm':
        if subj.lower() in PRONOUN_DETERMINERS or obj.lower() in PRONOUN_DETERMINERS:
            return False, 'pronoun'
        if not is_referential_subject(subj):
            return False, 'pronoun'

    return True, 'admitted'


def _dedup_key(claim) -> tuple:
    """Near-duplicate key: the triple with case/punctuation folded away
    ("The Earth is flat" ≈ "the earth is flat")."""
    def norm(part: str) -> Tuple[str, ...]:
        return tuple(_tokens(part))
    return (norm(claim.subject), norm(claim.predicate), norm(claim.object))


def filter_claims(claims: List) -> Tuple[List, Dict[str, int]]:
    """Apply the admission gates and drop near-duplicates.

    Returns (admitted_claims, discard_counts) where discard_counts maps
    each reason to how many candidates it rejected (including
    'duplicate').
    """
    discard_counts: Dict[str, int] = {}
    admitted: List = []
    seen = set()
    for claim in claims:
        ok, reason = admit_triple(claim)
        if not ok:
            discard_counts[reason] = discard_counts.get(reason, 0) + 1
            continue
        key = _dedup_key(claim)
        if key in seen:
            discard_counts['duplicate'] = discard_counts.get('duplicate', 0) + 1
            # Prefer the quoted provenance when the same triple also came
            # from the reporting line: the use-mention pass is the better
            # description of where this claim came from.
            if getattr(claim, 'source', '') == 'quote':
                for index, kept in enumerate(admitted):
                    if _dedup_key(kept) == key:
                        admitted[index] = claim
                        break
            continue
        seen.add(key)
        admitted.append(claim)
    return admitted, discard_counts
