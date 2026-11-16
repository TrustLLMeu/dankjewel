"""Tests for the claim-admission gates (Slice 0 + Slice 1).

Slice 0: junk names never resolve in the KB lookup (the old prefix
matching turned "I" into Iceland and "it" into Italy), and the NLI
verifier never scores a non-referential subject.

Slice 1: deterministic admission — markdown cleaning, sentence gates
(heading/question/imperative/meta), triple gates (pronoun/malformed),
near-duplicate dropping, the admission metadata contract, and the
fixture from the exported teaching-prose run (76 claims → the quoted
false-claim examples, <= 15 admitted).

No network, no LLM: stubs for the verifier and the [CLAIMS] client.
"""

import json
import os

import pytest

from src.dimensions.prong3_dimensions import FactualAccuracy
from src.extraction.claim_admission import (
    PRONOUN_DETERMINERS, admit_triple, clean_markdown, filter_claims,
    is_admissible_sentence, is_commentary_label, is_junk_name,
    is_referential_subject, sentence_reject_reason, split_label,
)
from src.extraction.claim_extractor import Claim, ClaimExtractor
from src.extraction.llm_claim_extractor import LLMClaimExtractor
from src.prongs.prong3_extraction import Prong3Extraction
from src.resources.wikidata_offline import OfflineWikidata

FIXTURE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            'fixtures', 'teacher_false_claims.json')


# ── Test doubles ────────────────────────────────────────────────────────────

class StubVerifier:
    """NliVerifier double with a call log."""

    def __init__(self, score=0.9):
        self.score_value = score
        self.calls = []

    def score(self, claim: str, context: str) -> float:
        self.calls.append((claim, context))
        return self.score_value


class StubClaimsClient:
    """[CLAIMS] client double returning canned atomic sentences."""

    def __init__(self, atoms):
        self.atoms = atoms

    def claims(self, text):
        return list(self.atoms)


PARIS_CLAIM = Claim(
    subject="Paris", predicate="be", object="the capital of France",
    source_sentence="Paris is the capital of France.",
)
WHARVES_CLAIM = Claim(
    subject="Trondheim", predicate="be", object="famous for its wharves",
    source_sentence="Trondheim is famous for its wharves.",
)


# ── Slice 0: junk names never resolve ───────────────────────────────────────

class TestJunkLookup:

    @pytest.fixture
    def wikidata(self):
        return OfflineWikidata()

    def test_pronouns_and_punctuation_never_resolve(self, wikidata):
        for junk in ('I', 'it', '*', '#', 'they', 'who', 'what', 'the'):
            assert wikidata.lookup_entity(junk) is None, junk

    def test_exact_matches_still_resolve(self, wikidata):
        assert wikidata.lookup_entity('Oslo') == 'Q585'
        assert wikidata.lookup_entity('the Earth') == 'Q2'

    def test_prefix_match_needs_three_chars_and_word_boundary(self, wikidata):
        # Two-character queries never prefix-match ("Os" must not hit Oslo).
        assert wikidata.lookup_entity('Os') is None
        # Mid-word prefixes do not resolve: word boundary required, so
        # "Trondh" no longer leaks into "Trondheim" via LIKE '%'.
        assert wikidata.lookup_entity('Trondh') is None
        assert wikidata.lookup_entity('Icel') is None
        # A whole-word prefix of a stored label still resolves
        # ("South" → South Africa, Q258).
        assert wikidata.lookup_entity('South') == 'Q258'

    def test_is_junk_name(self):
        assert is_junk_name('I') and is_junk_name('it') and is_junk_name('*')
        assert is_junk_name('') and is_junk_name('the')
        assert not is_junk_name('Oslo') and not is_junk_name('the Earth')
        assert not is_junk_name('9 out of 10 dentists')


class TestVerifierReferentialGate:

    def test_verifier_never_called_for_pronoun_subject(self):
        """A claim with subject 'I' must not reach the verifier."""
        stub = StubVerifier()
        dim = FactualAccuracy(wikidata=OfflineWikidata(), verifier=stub)
        claim = Claim(subject='I', predicate='be', object='happy',
                      source_sentence="I'm happy.")
        score = dim.evaluate("", claims=[claim], llm_verify=True)
        assert len(stub.calls) == 0
        assert score.metadata['relation_counts']['unknown'] == 1

    def test_verifier_scores_normal_claims(self, monkeypatch):
        """A referential subject with KB facts is scored by the verifier."""
        import src.dimensions.prong3_dimensions as p3
        monkeypatch.setattr(p3, "VERIFIER_MIN_KB_COVERAGE", 0.0)
        stub = StubVerifier(0.9)
        dim = FactualAccuracy(wikidata=OfflineWikidata(), verifier=stub)
        score = dim.evaluate("", claims=[WHARVES_CLAIM], llm_verify=True)
        assert len(stub.calls) == 1
        assert score.metadata['relation_counts']['confirmed'] == 1

    def test_kb_confirmed_claims_score_normally(self):
        """The gate never touches the exact-match path."""
        dim = FactualAccuracy(wikidata=OfflineWikidata())
        score = dim.evaluate("", claims=[PARIS_CLAIM])
        assert score.value == 1.0
        assert score.status == 'scored'

    def test_is_referential_subject(self):
        assert not is_referential_subject('I')
        assert not is_referential_subject('it')
        assert not is_referential_subject('*')
        assert not is_referential_subject('who')
        assert is_referential_subject('The Earth')
        assert is_referential_subject('9 out of 10 dentists')
        assert is_referential_subject('Brand X')


# ── Slice 1: markdown cleaning ──────────────────────────────────────────────

class TestCleanMarkdown:

    def test_curly_quotes_and_contractions(self):
        assert clean_markdown("it’s “fine”") == "it's \"fine\""

    def test_emphasis_and_code_markers_stripped(self):
        assert clean_markdown('**bold** text') == 'bold text'
        assert clean_markdown('an *italic* word') == 'an italic word'
        assert clean_markdown('a `code` span') == 'a code span'
        assert clean_markdown('_under_ score') == 'under score'
        assert '*' not in clean_markdown('**Claim:** "*Why*?"')

    def test_heading_blockquote_and_list_markers(self):
        assert clean_markdown('### 1. Factual Errors') == 'Factual Errors'
        assert clean_markdown('> quoted line') == 'quoted line'
        assert clean_markdown('*   bullet one') == 'bullet one'
        assert clean_markdown('2.  second item') == 'second item'

    def test_plain_prose_unchanged(self):
        text = 'Paris is the capital of France. It has two million people.'
        assert clean_markdown(text) == text


class TestLineLabels:

    def test_split_label(self):
        label, content = split_label('Claim: "The Earth is flat."')
        assert label == 'Claim'
        assert content == '"The Earth is flat."'
        assert split_label('Water boils at 100°C.') == (None, None)

    def test_commentary_labels(self):
        assert is_commentary_label("Why it's false")
        assert is_commentary_label('How it works')
        assert is_commentary_label("Why it's false (if unverified)")
        assert not is_commentary_label('Claim')
        assert not is_commentary_label('Source')


# ── Slice 1: sentence gates ────────────────────────────────────────────────

class TestSentenceGates:

    def test_markdown_residue_rejected(self):
        assert sentence_reject_reason('*   **Claim:** "X."') == 'markdown'
        assert not is_admissible_sentence('### A heading line')

    def test_headings_and_labels_rejected(self):
        assert sentence_reject_reason('Factual Errors (Simple Falsehoods)') == 'heading'
        assert sentence_reject_reason("Why it's false:") == 'heading'
        assert sentence_reject_reason('How to Identify False Claims') == 'heading'
        assert not is_admissible_sentence('Factual Errors (Simple Falsehoods)')

    def test_questions_rejected(self):
        assert sentence_reject_reason('Are they credible?') == 'question'
        assert not is_admissible_sentence('Who is making the claim?')

    def test_imperatives_rejected(self):
        assert sentence_reject_reason('Always question, verify, and seek evidence.') == 'imperative'
        assert not is_admissible_sentence('Consider the evidence carefully.')

    def test_meta_discourse_rejected(self):
        for sent in ('Here are several examples of false claims:',
                     'As your teacher, I encourage you to think.',
                     'Let me explain the concept.',
                     'For example, water boils at 100 degrees.',
                     'This means the claim is false.'):
            assert sentence_reject_reason(sent) == 'meta', sent

    def test_assertive_sentences_admitted(self):
        for sent in ('The Earth is flat.',
                     'Humans have two eyes.',
                     'Water boils at 200°C at sea level.',
                     'Critical thinking is your best defense against false claims!'):
            assert is_admissible_sentence(sent), sent


# ── Slice 1: triple gates ───────────────────────────────────────────────────

class TestAdmitTriple:

    def test_well_formed_claim_admitted(self):
        ok, reason = admit_triple(PARIS_CLAIM)
        assert ok and reason == 'admitted'

    def test_pronoun_subjects_rejected(self):
        for subj in ('I', 'It', 'she', 'they', 'who'):
            claim = Claim(subject=subj, predicate='be', object='happy',
                          source_sentence=f'{subj} is happy.')
            ok, reason = admit_triple(claim)
            assert not ok and reason == 'pronoun', subj

    def test_pronoun_claims_admitted_on_llm_track(self):
        """The LLM track resolves pronouns, so its claims pass."""
        claim = Claim(subject='It', predicate='be', object='a city',
                      source_sentence='It is a city.', source='llm',
                      atomic_text='Trondheim is a city.')
        ok, reason = admit_triple(claim)
        assert ok and reason == 'admitted'

    def test_malformed_rejections(self):
        cases = [
            (Claim(subject='', predicate='be', object='X',
                   source_sentence='X is Y.'), 'empty subject'),
            (Claim(subject='A', predicate='be', object='A',
                   source_sentence='A is A.'), 'subject == object'),
            (Claim(subject='X', predicate='be', object='',
                   source_sentence='X is.'), 'empty object'),
            (Claim(subject='*', predicate='be', object='X',
                   source_sentence='Something is X.'), 'punctuation subject'),
            (Claim(subject='X', predicate='’m', object='happy',
                   source_sentence="X's happy."), 'contraction predicate'),
            (Claim(subject='The boiling point', predicate='change',
                   object='there', source_sentence='The boiling point changes there.'),
             'discourse-marker object'),
        ]
        for claim, why in cases:
            ok, reason = admit_triple(claim)
            assert not ok and reason == 'malformed', why

    def test_existential_claims_admitted(self):
        claim = Claim(subject='an uprising', predicate='exist', object='',
                      source_sentence='There was an uprising.')
        ok, reason = admit_triple(claim)
        assert ok and reason == 'admitted'

    def test_sentence_reasons_attribute_from_source_sentence(self):
        cases = [
            (Claim(subject='X', predicate='be', object='Y',
                   source_sentence='*   **Claim:** "X."', ), 'markdown'),
            (Claim(subject='X', predicate='be', object='Y',
                   source_sentence="Why it's false:"), 'heading'),
            (Claim(subject='X', predicate='be', object='Y',
                   source_sentence='Are they credible?'), 'question'),
            (Claim(subject='X', predicate='be', object='Y',
                   source_sentence='Always question everything.'), 'imperative'),
            (Claim(subject='X', predicate='be', object='Y',
                   source_sentence='Here are some examples.'), 'meta'),
        ]
        for claim, expected in cases:
            ok, reason = admit_triple(claim)
            assert not ok and reason == expected

    def test_adverbial_object_fragments_rejected(self):
        for obj in ('by default', 'In most states', 'as slates',
                    'in general', 'for example'):
            claim = Claim(subject='The United States', predicate='have',
                          object=obj,
                          source_sentence=f'The United States has it {obj}.')
            ok, reason = admit_triple(claim)
            assert not ok and reason == 'adverbial', obj

    def test_placeholder_objects_rejected(self):
        for obj in ('unknown', 'unclear', 'not known', 'disputed'):
            claim = Claim(subject='The true cause', predicate='be',
                          object=obj,
                          source_sentence=f'The true cause is {obj}.')
            ok, reason = admit_triple(claim)
            assert not ok and reason == 'placeholder', obj

    def test_anaphoric_objects_rejected(self):
        for obj in ('the term', 'the phrase', 'the latter', 'the concept'):
            claim = Claim(subject='Nixon', predicate='popularize',
                          object=obj,
                          source_sentence=f'Nixon popularized {obj}.')
            ok, reason = admit_triple(claim)
            assert not ok and reason == 'anaphoric', obj

    def test_unbalanced_parenthetical_fragments_rejected(self):
        cases = [
            Claim(subject='Article I Section 8)', predicate='grant',
                  object='the power to declare',
                  source_sentence='Article I, Section 8 grants the power.'),
            Claim(subject='only Congress', predicate='have',
                  object='Under the U.S. Constitution Article I Section 8)',
                  source_sentence='Only Congress has the power.'),
        ]
        for claim in cases:
            ok, reason = admit_triple(claim)
            assert not ok and reason == 'malformed'

    def test_well_formed_political_claims_still_admitted(self):
        """The new object gates keep ordinary political facts."""
        cases = [
            Claim(subject='The UK', predicate='have',
                  object='an uncodified constitution',
                  source_sentence='The UK has an uncodified constitution.'),
            Claim(subject='The President', predicate='be',
                  object='the Commander in Chief of the armed forces',
                  source_sentence='The President is the Commander in Chief.'),
            Claim(subject='electors', predicate='cast',
                  object='separate votes',
                  source_sentence='Electors cast separate votes.'),
        ]
        for claim in cases:
            ok, reason = admit_triple(claim)
            assert ok and reason == 'admitted', claim.object


class TestFilterClaims:

    def test_near_duplicates_dropped(self):
        first = Claim(subject='The Earth', predicate='be', object='flat',
                      source_sentence='The Earth is flat.')
        second = Claim(subject='THE EARTH', predicate='be', object='flat.',
                       source_sentence='The earth is flat!')
        third = Claim(subject='Paris', predicate='be',
                      object='the capital of France',
                      source_sentence='Paris is the capital of France.')
        admitted, discarded = filter_claims([first, second, third])
        assert len(admitted) == 2
        assert discarded == {'duplicate': 1}

    def test_reason_histogram(self):
        claims = [
            Claim(subject='I', predicate='be', object='happy',
                  source_sentence="I'm happy."),
            Claim(subject='X', predicate='be', object='X',
                  source_sentence='X is X.'),
            PARIS_CLAIM,
        ]
        admitted, discarded = filter_claims(claims)
        assert len(admitted) == 1
        assert discarded == {'pronoun': 1, 'malformed': 1}


# ── Slice 1: extractor integration ─────────────────────────────────────────

class TestExtractorAdmission:

    def test_metadata_carries_admission_counts(self):
        result = ClaimExtractor().extract(
            "Paris is the capital of France. It is a city.")
        assert result.metadata['admitted_claims'] == len(result.claims)
        assert 'discarded_candidates' in result.metadata
        # The pronoun claim was gated away.
        assert result.metadata['discarded_candidates'].get('pronoun') == 1

    def test_markdown_prose_cleaned_before_parsing(self):
        text = "*   **Claim:** \"The Earth is flat.\"\n    *   **Why it's false:** It is round."
        result = ClaimExtractor().extract(text)
        subjects = {c.subject for c in result.claims}
        assert any('Earth' in s for s in subjects)
        # The commentary label line never contributes a claim.
        assert not any('false' in c.predicate or 'Why' in c.subject
                       for c in result.claims)
        assert result.metadata['discarded_candidates'].get('meta') == 1

    def test_llm_atoms_gated_by_sentence_rules(self):
        stub = StubClaimsClient([
            'Here are several examples of false claims.',
            'Water boils at 100 degrees Celsius.',
        ])
        extractor = LLMClaimExtractor(client=stub,
                                      spacy_extractor=ClaimExtractor(),
                                      include_spacy=False)
        result = extractor.extract("Some paragraph of text.")
        assert len(result.claims) == 1
        assert result.claims[0].subject == 'Water'
        assert result.metadata['discarded_candidates'].get('meta') == 1
        assert result.metadata['admitted_claims'] == 1

    def test_prong3_forwards_admission_into_fa_metadata(self):
        prong = Prong3Extraction()
        result = prong.evaluate("*   **Claim:** The Earth is flat.")
        fa = next(d for d in result.dimensions if d.name == 'Factual Accuracy')
        assert 'claim_admission' in fa.metadata
        assert fa.metadata['claim_admission']['admitted_claims'] == \
            len(fa.metadata['claim_details']) or fa.metadata['num_claims']

    def test_fa_admission_kwarg_forwarded_on_no_claims(self):
        dim = FactualAccuracy(wikidata=OfflineWikidata())
        admission = {'admitted_claims': 0, 'discarded_candidates': {'meta': 3}}
        score = dim.evaluate("", claims=[], admission=admission)
        assert score.metadata['claim_admission'] == admission
        assert score.status == 'unknown'


# ── Fixture: the exported teaching-prose run ────────────────────────────────

class TestTeacherFixture:
    """The exported run produced 76 claims (~48 junk fragments, zero
    verifiable). The gates must admit the quoted false-claim examples
    and stay under the cap."""

    def test_admission_on_exported_teaching_prose(self):
        with open(FIXTURE_PATH, encoding='utf-8') as f:
            fixture = json.load(f)
        result = ClaimExtractor().extract(fixture['text'])
        admitted = result.claims

        assert len(admitted) <= fixture['max_admitted']

        def flat(claim):
            return ' '.join([claim.subject, claim.predicate, claim.object,
                             claim.source_sentence, claim.atomic_text or ''])

        for expected in fixture['expected_min']:
            hit = any(expected.lower() in flat(c).lower() for c in admitted)
            assert hit, f"expected {expected!r} among admitted claims"

        # Junk classes were actually gated (not admitted by accident).
        discards = result.metadata['discarded_candidates']
        assert discards, "nothing was gated"
        allowed_reasons = {'markdown', 'heading', 'question', 'imperative',
                           'meta', 'pronoun', 'malformed', 'duplicate',
                           'definition', 'demonstrative'}
        assert set(discards) <= allowed_reasons
        assert 'meta' in discards and 'pronoun' in discards
        # No admitted claim is a pronoun/fragment skeleton.
        for claim in admitted:
            assert claim.subject.lower() not in PRONOUN_DETERMINERS
            assert claim.predicate not in ("'m", "’", "'", ':*', '#')


# ── Slice 6d: definition and demonstrative gates ────────────────────────────

@pytest.mark.parametrize("subject,obj", [
    ("A false claim", "a statement"),
    ("A country", "a political entity"),
])
def test_definition_gate_rejects_encyclopedic_definitions(subject, obj):
    """Category definitions are not checkable facts about an entity."""
    claim = Claim(subject=subject, predicate='be', object=obj,
                  source='spacy', source_sentence=f"{subject} is {obj}.")
    admitted, reason = admit_triple(claim)
    assert not admitted
    assert reason == 'definition'


def test_definition_gate_keeps_specific_facts():
    """A copula with a concrete complement still passes."""
    claim = Claim(subject='Oslo', predicate='be', object='a city',
                  source='spacy', source_sentence='Oslo is a city.')
    admitted, reason = admit_triple(claim)
    assert admitted
    assert reason == 'admitted'


@pytest.mark.parametrize("subject", ["These claims", "This article",
                                     "That statement"])
def test_demonstrative_gate_rejects_text_deixis(subject):
    """Demonstratives over the document itself are not world claims."""
    claim = Claim(subject=subject, predicate='use', object='real numbers',
                  source='spacy', source_sentence=f"{subject} use real numbers.")
    admitted, reason = admit_triple(claim)
    assert not admitted
    assert reason == 'demonstrative'


def test_demonstrative_gate_keeps_world_reference():
    """A demonstrative over concrete entities of the world still passes."""
    claim = Claim(subject='Those two cities', predicate='be',
                  object='in Norway', source='spacy',
                  source_sentence='Those two cities are in Norway.')
    admitted, reason = admit_triple(claim)
    assert admitted
    assert reason == 'admitted'


# ── Use-mention pass: quoted / reported claims ──────────────────────────────

def test_quoted_claim_from_reporting_sentence():
    """A proposition in quotes is admitted as a claim the text mentions."""
    from src.extraction.claim_extractor import ClaimExtractor

    claims = ClaimExtractor().extract('The teacher said "The Earth is flat."').claims
    quotes = [c for c in claims if c.source == 'quote']
    assert len(quotes) == 1
    assert quotes[0].subject == 'The Earth'
    assert quotes[0].atomic_text == 'The Earth is flat.'


def test_claim_label_line_is_extracted_as_quote():
    """A 'Claim: \"...\"' label yields the quoted sentence as the claim."""
    from src.extraction.claim_extractor import ClaimExtractor

    claims = ClaimExtractor().extract('Claim: "Water boils at 200 °C."').claims
    assert len(claims) == 1
    assert claims[0].source == 'quote'
    assert claims[0].subject == 'Water'


def test_quote_provenance_wins_duplicate():
    """When the reporting line also yields the triple, quote provenance wins."""
    from src.extraction.claim_extractor import ClaimExtractor

    claims = ClaimExtractor().extract('Claim: "Water boils at 200 °C."').claims
    assert claims[0].source == 'quote'


def test_fixture_reported_claims_keep_quote_provenance():
    """The teacher fixture's quoted lies are admitted as mentioned claims."""
    import json
    from pathlib import Path
    from src.extraction.claim_extractor import ClaimExtractor

    fixture = json.loads(Path('tests/fixtures/teacher_false_claims.json').read_text())
    claims = ClaimExtractor().extract(fixture['text']).claims
    quotes = [c for c in claims if c.source == 'quote']
    assert len(quotes) >= 5
    joined = ' '.join(f"{c.subject} {c.predicate} {c.object}" for c in quotes).lower()
    for expected in ('earth', 'five eyes', 'dentists', 'crime', 'boil'):
        assert expected in joined


# ── Corrections: the corrected statement is the assertion ───────────────────

def test_correction_marks_previous_statement_as_quote():
    """A Correction line retracts the preceding line's claim."""
    from src.extraction.claim_extractor import ClaimExtractor

    text = ("The United Kingdom has a written, codified constitution.\n"
            "Correction: The UK has an uncodified constitution.")
    result = ClaimExtractor().extract(text)
    assert result.metadata['correction_pairs'] == 1
    by_text = {c.object: c.source for c in result.claims}
    assert by_text['a written codified constitution'] == 'quote'
    assert by_text['an uncodified constitution'] == 'spacy'


def test_actually_opener_marks_previous_statement_as_quote():
    """A line-initial 'Actually,' also retracts the preceding line."""
    from src.extraction.claim_extractor import ClaimExtractor

    text = ("The United States has a standing army in peacetime.\n"
            "Actually, the United States has no standing army in peacetime.")
    result = ClaimExtractor().extract(text)
    assert result.metadata['correction_pairs'] == 1
    quotes = [c for c in result.claims if c.source == 'quote']
    assert any('standing army' in c.object for c in quotes)


def test_correction_without_a_previous_line_is_not_a_pair():
    """A standalone correction line adds no pair and stays asserted."""
    from src.extraction.claim_extractor import ClaimExtractor

    result = ClaimExtractor().extract(
        'Correction: The UK has an uncodified constitution.')
    assert result.metadata['correction_pairs'] == 0
    assert [c.source for c in result.claims] == ['spacy']


# ── llm_admit: optional 1.5B admission classifier ───────────────────────────

def test_llm_admit_drops_classified_nonclaims(monkeypatch):
    """Claims the classifier rejects are removed and counted."""
    import src.prongs.prong3_extraction as p3mod

    class StubClient:
        def admit(self, sentence):
            return 'smoking' not in sentence.lower()

    monkeypatch.setattr(p3mod, 'get_shared_judge_client', lambda: StubClient())
    prong = p3mod.Prong3Extraction()
    result = prong.evaluate('Smoking is that bad. Oslo is the capital of Norway.',
                            llm_admit=True)
    fa = [d for d in result.dimensions if d.name == 'Factual Accuracy'][0]
    meta = fa.metadata['claim_admission']
    assert meta['llm_admit_dropped'] == 1
    assert meta['llm_admit_unknown'] == 0
    subjects = [c['claim']['subject'] for c in fa.metadata['claim_details']]
    assert 'Smoking' not in subjects and 'Oslo' in subjects


def test_llm_admit_keeps_claims_when_classifier_is_unavailable(monkeypatch):
    """Unknown verdicts never remove claims."""
    import src.prongs.prong3_extraction as p3mod

    class StubClient:
        def admit(self, sentence):
            return None

    monkeypatch.setattr(p3mod, 'get_shared_judge_client', lambda: StubClient())
    prong = p3mod.Prong3Extraction()
    result = prong.evaluate('Oslo is the capital of Norway.', llm_admit=True)
    fa = [d for d in result.dimensions if d.name == 'Factual Accuracy'][0]
    meta = fa.metadata['claim_admission']
    assert meta['llm_admit_unknown'] == 1
    assert meta['llm_admit_dropped'] == 0


def test_llm_admit_off_makes_no_model_calls(monkeypatch):
    """Flag off: the classifier is never consulted."""
    import src.prongs.prong3_extraction as p3mod

    class ExplodingClient:
        def admit(self, sentence):
            raise AssertionError('classifier must not be called')

    monkeypatch.setattr(p3mod, 'get_shared_judge_client', lambda: ExplodingClient())
    prong = p3mod.Prong3Extraction()
    result = prong.evaluate('Oslo is the capital of Norway.', llm_admit=False)
    assert result.error is None
