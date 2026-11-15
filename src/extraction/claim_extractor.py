"""Rule-based claim extraction using spaCy dependency parsing.

Extracts (subject, predicate, object) triples from text by traversing
spaCy dependency trees. Each triple becomes a Claim with optional
temporal anchors, comparative tags, modality modifiers, and negation flag.

Efficiency is tracked via extraction_time_ms for future comparison
with vLLM-based claim extraction.
"""

import time
from dataclasses import dataclass, field
from typing import List, Optional
import spacy

from src.extraction.claim_admission import (
    clean_markdown, filter_claims, is_commentary_label, split_label,
)


@dataclass
class Claim:
    """A single extracted (subject, predicate, object) triple."""
    subject: str
    predicate: str
    object: str
    source_sentence: str
    modifiers: List[str] = field(default_factory=list)       # hedge words attached to verb
    temporal_anchor: Optional[str] = None                     # DATE entity if present
    comparative_tag: Optional[str] = None                     # JJR/JJS tag if present
    negated: bool = False                                     # True if verb has a 'neg' child
    source: str = "spacy"                                     # extraction track: "spacy" | "llm" | "both"
    atomic_text: Optional[str] = None                        # LLM track: the decontextualized atomic claim

    def to_dict(self) -> dict:
        return {
            'subject': self.subject,
            'predicate': self.predicate,
            'object': self.object,
            'source_sentence': self.source_sentence,
            'modifiers': self.modifiers,
            'temporal_anchor': self.temporal_anchor,
            'comparative_tag': self.comparative_tag,
            'negated': self.negated,
            'source': self.source,
            'atomic_text': self.atomic_text,
        }


@dataclass
class ExtractionResult:
    """Result of claim extraction with timing metadata.

    `metadata` carries dual-track info from the LLM extractor
    (llm_paragraphs / llm_claims / llm_errors) and the claim-admission
    gates (admitted_claims / discarded_candidates); rule-based
    extraction fills in the admission keys only.
    """
    claims: List[Claim]
    extraction_time_ms: float
    num_sentences: int
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            'claims': [c.to_dict() for c in self.claims],
            'extraction_time_ms': self.extraction_time_ms,
            'num_sentences': self.num_sentences,
            'metadata': self.metadata,
        }


def admission_metadata(admitted: int, discarded: dict) -> dict:
    """The admission half of ExtractionResult.metadata (shared by both
    extraction tracks so Prong 3 sees one uniform shape)."""
    return {
        'admitted_claims': admitted,
        'discarded_candidates': dict(discarded),
    }


# Modal verbs and uncertainty cues for modality detection
MODAL_VERBS = {'may', 'might', 'could', 'can', 'should', 'would'}
UNCERTAINTY_CUES = {'perhaps', 'maybe', 'possibly', 'seems', 'appears',
                    'allegedly', 'supposedly', 'reportedly', 'apparently'}


class ClaimExtractor:
    """Extract structured claims from text using spaCy dependency parsing.

    Loads en_core_web_sm once and reuses it. Extracts triples by walking
    the dependency tree for each sentence:
      - subject: nsubj / nsubjpass of the root verb
      - predicate: root verb (+ aux children, negation tracked separately)
      - object: dobj / attr / prep+pobj / acomp of the root verb

    Also annotates:
      - temporal_anchor: DATE entities from spaCy NER overlapping the sentence
      - comparative_tag: JJR/JJS POS tags in the object span
      - modifiers: modal/uncertainty words governing the verb
      - negated: True if the root verb has a 'neg' dependency child
    """

    def __init__(self):
        try:
            self._nlp = spacy.load('en_core_web_sm')
        except OSError:
            raise RuntimeError(
                "spaCy model 'en_core_web_sm' not found. "
                "Install with: python -m spacy download en_core_web_sm"
            )

    def extract(self, text: str) -> ExtractionResult:
        """Extract claims from text.

        Applies the deterministic admission gates (Slice 1): the text is
        markdown-cleaned before parsing, and the candidate triples are
        filtered by claim_admission.filter_claims (pronoun/fragment/
        heading/meta candidates are discarded, near-duplicates dropped).
        ExtractionResult.metadata carries the admission histogram.

        Returns:
            ExtractionResult with list of Claim objects and timing info.
        """
        start = time.perf_counter()
        cleaned = clean_markdown(text)
        candidates = []
        num_sentences = 0
        discarded: dict = {}

        # Split bullet lines: after cleaning, each markdown line is its
        # own parse unit — bullets/headings/labels never merge into the
        # neighbouring sentence's dependency tree (that merging is what
        # produced heading-text subjects and quoted-claim fragments in
        # the exported run). A "Label:" prefix is split off; commentary
        # labels ("Why it's false:") gate the whole line as meta.
        for raw_line in cleaned.split('\n'):
            line = raw_line.strip()
            if not line:
                continue
            label, content = split_label(line)
            if label is not None and is_commentary_label(label):
                discarded['meta'] = discarded.get('meta', 0) + 1
                continue
            parse_text = content if label is not None else line
            doc = self._nlp(parse_text)
            sents = list(doc.sents)
            num_sentences += len(sents)
            for sent in sents:
                candidates.extend(self._extract_from_sentence(sent))

        claims, gate_discarded = filter_claims(candidates)
        for reason, count in gate_discarded.items():
            discarded[reason] = discarded.get(reason, 0) + count

        elapsed_ms = (time.perf_counter() - start) * 1000.0
        return ExtractionResult(
            claims=claims,
            extraction_time_ms=elapsed_ms,
            num_sentences=num_sentences,
            metadata=admission_metadata(len(claims), discarded),
        )

    def extract_from_sentence_text(self, text: str) -> List[Claim]:
        """Run the per-sentence triple logic on a standalone text fragment.

        Same dependency-parse logic as extract(), but on caller-provided
        text — e.g. a decontextualized atomic claim from the LLM track —
        instead of the original document. No behavior change for extract().

        Args:
            text: the fragment to parse (usually one atomic claim sentence).

        Returns:
            List of Claim objects extracted from the fragment.
        """
        doc = self._nlp(text)
        claims = []
        for sent in doc.sents:
            claims.extend(self._extract_from_sentence(sent))
        return claims

    def count_sentences(self, text: str) -> int:
        """Count sentences in text with the shared spaCy pipeline."""
        return len(list(self._nlp(text).sents))

    def _extract_from_sentence(self, sent) -> List[Claim]:
        """Extract claims from a single spaCy Span (sentence)."""
        claims = []
        sent_text = sent.text.strip()

        # Collect DATE entities in this sentence
        date_entities = [ent.text for ent in sent.ents if ent.label_ == 'DATE']
        temporal_anchor = date_entities[0] if date_entities else None

        # Find root verb(s) in the sentence
        for token in sent:
            if token.dep_ == 'ROOT':
                root_claims = self._extract_from_root(token, sent_text, temporal_anchor)
                claims.extend(root_claims)

        return claims

    def _extract_from_root(self, root, sent_text: str,
                           temporal_anchor: Optional[str]) -> List[Claim]:
        """Extract claims from a ROOT token and its dependents."""
        claims = []

        # --- Detect modifiers (modality) and negation early ---
        modifiers = self._get_modifiers(root)
        negated = self._detect_negation(root)

        # --- Handle existential constructions: "There could be an uprising" ---
        has_expl = any(c.dep_ == 'expl' for c in root.children)
        if has_expl:
            # In existential constructions, the attr/dobj IS the claim subject
            for child in root.children:
                if child.dep_ in ('attr', 'dobj'):
                    subj_text = self._expand_noun(child)
                    comp_tag = self._detect_comparative(child)
                    # "no" as a determiner inside the existential NP acts as
                    # sentential negation ("There exists NO city called X")
                    # but spaCy attaches it as a 'det' of the noun, not a
                    # 'neg' child of the root verb — _detect_negation() alone
                    # misses this very common FEVER 2.0 pattern.
                    existential_negated = negated or any(
                        t.dep_ == 'det' and t.text.lower() == 'no'
                        for t in child.subtree
                    )
                    claim = Claim(
                        subject=subj_text,
                        predicate='exist',
                        object='',
                        source_sentence=sent_text,
                        modifiers=modifiers,
                        temporal_anchor=temporal_anchor,
                        comparative_tag=comp_tag,
                        negated=existential_negated,
                    )
                    claims.append(claim)
            return claims

        # --- Find subject(s) ---
        subjects = self._get_subjects(root)
        if not subjects:
            return claims

        # --- Build predicate (negation tracked separately, not in predicate) ---
        predicate = self._build_predicate(root)

        # --- Find object(s) ---
        objects = self._get_objects(root)
        if not objects:
            return claims

        # --- Build claims for each subject × object pair ---
        for subj in subjects:
            for obj_text, comp_tag in objects:
                final_subj = subj
                final_obj = obj_text

                # --- Inverted copula detection ---
                # "The capital of France is Paris" → subject is a description,
                # object is the named entity. Flip so Wikidata can verify.
                if root.lemma_ == 'be':
                    final_subj, final_obj = self._maybe_flip_copula(
                        root, final_subj, final_obj
                    )

                claim = Claim(
                    subject=final_subj,
                    predicate=predicate,
                    object=final_obj,
                    source_sentence=sent_text,
                    modifiers=modifiers,
                    temporal_anchor=temporal_anchor,
                    comparative_tag=comp_tag,
                    negated=negated,
                )
                claims.append(claim)

        return claims

    def _detect_negation(self, root) -> bool:
        """Detect whether the root verb is negated (has a 'neg' child)."""
        for child in root.children:
            if child.dep_ == 'neg':
                return True
        return False

    def _get_subjects(self, root) -> List[str]:
        """Get subject noun phrases from root's dependents."""
        subjects = []
        for child in root.children:
            if child.dep_ in ('nsubj', 'nsubjpass'):
                subj_text = self._expand_noun(child)
                subjects.append(subj_text)
                # Also grab conjuncts ("France and Germany are ...")
                for conj in child.conjuncts:
                    subjects.append(self._expand_noun(conj))
        return subjects

    def _maybe_flip_copula(self, root, subj: str, obj: str) -> tuple:
        """Detect inverted copula and flip subject/object if needed.

        Pattern: "The capital of France is Paris" has:
          - nsubj = "capital" (common noun, no NER)
          - attr  = "Paris" (proper noun, GPE entity)
        We flip to produce (Paris, be, the capital of France) which is
        verifiable against Wikidata.

        Returns (subject, object), possibly swapped.
        """
        subj_token = None
        attr_token = None
        for child in root.children:
            if child.dep_ in ('nsubj', 'nsubjpass'):
                subj_token = child
            if child.dep_ == 'attr':
                attr_token = child

        if not subj_token or not attr_token:
            return subj, obj

        subj_is_description = subj_token.pos_ in ('NOUN', 'DET') and subj_token.ent_type_ == ''
        attr_is_entity = attr_token.pos_ == 'PROPN' or attr_token.ent_type_ != ''

        if subj_is_description and attr_is_entity:
            new_subj = attr_token.text
            new_obj = subj
            return new_subj, new_obj

        return subj, obj

    def _build_predicate(self, root) -> str:
        """Build predicate string from root verb + auxiliaries + particles.

        Negation is NOT included here — it is tracked separately via the
        `negated` flag on Claim so the predicate stays clean for property
        matching (e.g., "be" matches PREDICATE_TO_PROPERTY, "be not" does not).
        """
        parts = []
        for child in root.children:
            if child.dep_ in ('aux', 'auxpass'):
                parts.append((child.i, child.text.lower()))
            if child.dep_ == 'prt':  # verb particle: "carried out"
                parts.append((child.i, child.text.lower()))
        parts.append((root.i, root.lemma_.lower()))
        parts.sort(key=lambda x: x[0])
        return ' '.join(p[1] for p in parts)

    def _get_objects(self, root) -> List[tuple]:
        """Get object phrases from root's dependents.

        Returns list of (object_text, comparative_tag_or_None).
        Each prepositional phrase becomes its own separate triple candidate
        rather than being merged into one combined string — "in Flash Comics"
        and "in 1973" are independent facts and should be verified separately.
        """
        objects = []
        # Direct objects, attributes, complements
        for child in root.children:
            if child.dep_ in ('dobj', 'attr', 'acomp', 'oprd'):
                obj_text = self._expand_noun(child)
                comp_tag = self._detect_comparative(child)
                objects.append((obj_text, comp_tag))
                # Conjuncts: "Paris and London"
                for conj in child.conjuncts:
                    obj_text2 = self._expand_noun(conj)
                    comp_tag2 = self._detect_comparative(conj)
                    objects.append((obj_text2, comp_tag2))

        # Prepositional objects: each prep → pobj becomes a separate object
        # candidate so each can be individually verified against Wikidata.
        # (Previously they were merged into one string, which prevented any
        # of them from matching cleanly.)
        for child in root.children:
            if child.dep_ == 'prep':
                for pobj in child.children:
                    if pobj.dep_ == 'pobj':
                        # Skip temporal/numeric prep objects ("in 1973",
                        # "in the 1970s") — they are not Wikidata-verifiable
                        # entity facts and trigger false location denials.
                        if pobj.ent_type_ == 'DATE' or pobj.like_num:
                            continue
                        if any(t.ent_type_ == 'DATE' for t in pobj.subtree
                               if t != pobj):
                            continue
                        obj_text = self._expand_noun(pobj)
                        comp_tag = self._detect_comparative(pobj)
                        objects.append((f"{child.text} {obj_text}", comp_tag))

            if child.dep_ == 'advmod':
                for prep_child in child.children:
                    if prep_child.dep_ == 'prep':
                        for pobj in prep_child.children:
                            if pobj.dep_ == 'pobj':
                                if pobj.ent_type_ == 'DATE' or pobj.like_num:
                                    continue
                                obj_text = self._expand_noun(pobj)
                                comp_tag = self._detect_comparative(pobj)
                                objects.append(
                                    (f"{child.text} {prep_child.text} {obj_text}", comp_tag)
                                )

        return objects

    def _expand_noun(self, token) -> str:
        """Expand a token to its full subtree noun phrase.

        Three classes of tokens are excluded from the expansion:
        1. Tokens that belong to embedded relative/adverbial clauses
           (relcl, advcl, ccomp, xcomp).  The entire subtree of such a
           clause head is collected upfront, so that aux/auxpass tokens
           that precede the clause head in linear order are also excluded
           (old 'break' approach missed those).
        2. Subjects/objects of embedded verbs — but NEVER the seed token
           itself.  The old condition lacked the ``t != token`` guard,
           which caused the head token (e.g. nsubj "Canary", dobj
           "constitution", dobj "tiger") to be filtered out, leaving only
           its modifiers ("Black", "a novel", "Tasmanian").
        3. Punctuation tokens at the boundary of the phrase.
        """
        subtree_tokens = sorted(token.subtree, key=lambda t: t.i)

        # ── Step 1: collect indices belonging to embedded clauses ──────
        # This is more robust than the old 'break on relcl' approach:
        # it also catches aux/auxpass that appear *before* the clause head
        # in linear order (e.g. "a network is headquartered" — 'is' leaks
        # through with break-on-relcl because it comes before 'headquartered').
        embedded: set = set()
        for t in subtree_tokens:
            if t.dep_ in ('relcl', 'advcl', 'ccomp', 'xcomp') and t != token:
                for t2 in t.subtree:
                    embedded.add(t2.i)

        # ── Step 2: build phrase, applying exclusion rules ─────────────
        phrase_tokens = []
        for t in subtree_tokens:
            if t.i in embedded:
                continue
            # Skip punctuation at the edges (periods, commas etc.)
            if t.is_punct:
                continue
            # Skip subjects/objects of embedded verbs — but NEVER the
            # seed token itself (old bug: lacked ``t != token`` guard).
            if (t != token
                    and t.dep_ in ('nsubj', 'nsubjpass', 'dobj')
                    and t.head != token
                    and t.head.pos_ == 'VERB'):
                continue
            phrase_tokens.append(t)

        if phrase_tokens:
            return ' '.join(t.text for t in phrase_tokens).strip()
        return token.text

    def _detect_comparative(self, token) -> Optional[str]:
        """Detect comparative/superlative adjectives in token's subtree."""
        for t in token.subtree:
            if t.tag_ == 'JJS':
                return 'superlative'
            if t.tag_ == 'JJR':
                return 'comparative'
        return None

    def _get_modifiers(self, root) -> List[str]:
        """Detect modal verbs and uncertainty cues modifying the root verb."""
        modifiers = []
        for child in root.children:
            if child.dep_ in ('aux', 'advmod') and child.text.lower() in MODAL_VERBS:
                modifiers.append(child.text.lower())
            if child.dep_ == 'advmod' and child.text.lower() in UNCERTAINTY_CUES:
                modifiers.append(child.text.lower())
        sent = root.sent
        for token in sent:
            if token.i >= root.i:
                break
            if token.text.lower() in UNCERTAINTY_CUES:
                if token.text.lower() not in modifiers:
                    modifiers.append(token.text.lower())
        return modifiers