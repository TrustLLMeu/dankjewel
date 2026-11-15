# Claim Admission (Prong 3)

Deterministic gates between claim extraction and claim verification. Extraction proposes candidates; only admitted claims are shown, counted and verified. All gates are lexicons and regexes — no models, no network. Code: `src/extraction/claim_admission.py`; tests: `tests/test_claim_admission.py` (41 passed).

## Why admission exists

The exported teaching-prose run (`dj_result_2026-11-15T19-56-34.json`, prompt "You are a teacher. Give some examples of false claims.") produced 76 "claims", ~39 of them fragments (bullet punctuation, contraction predicates, headings, pronoun subjects) and 0 verifiable (all 76 UNKNOWN). A verifier-enabled pre-fix run additionally produced 11 false denials from the lookup prefix bug (commit index `f49c1db`). After the gates: **8 admitted**, all **five expected lies retained** (flat Earth, 200 °C boiling, five eyes, 9/10 dentists, crime doubled), and **zero confident verdicts on pronoun/fragment claims** (the referential gate keeps them out of the verifier; in the default KB-exact run all eight relations are `unknown`). Admission is precision-first: a junk claim that reaches verification can earn a harmful verdict against the wrong entity; a dropped fragment costs nothing.

## The pipeline

`ClaimExtractor.extract` (spaCy track, always on) and `LLMClaimExtractor.extract` (dual track, `llm_extract` opt-in):

1. `clean_markdown` — curly quotes → ASCII; strip `#`/`>`/`-`/`1.` line markers and `**`/`*`/`_`/backtick markup.
2. Line-based parse units: bullets, headings and labels never merge into the neighbouring sentence; `split_label` splits "Label:" prefixes and commentary labels ("Why it's false:") gate their whole line as `meta`.
3. spaCy dependency parse → (subject, predicate, object) candidate triples (per ROOT verb, per subject × object pair). LLM track: one `[CLAIMS]` call per paragraph on the local 1.5B server; each atomic claim is re-parsed by the same triple logic (`source='llm'`); identical triples merge to `source='both'`.
4. `filter_claims` → `admit_triple` per candidate, in order: sentence gates (on `source_sentence`) → `malformed` → `definition` → `demonstrative` → `pronoun`/lexical head (skipped for `source='llm'`) → near-duplicate drop (lemma key, `duplicate`). LLM atoms also pass the sentence gates before triple parsing.
5. Verification: KB exact (`verify_triple`, always on), then the optional MiniCheck verifier (`_verifier_relation`, `llm_verify`) for claims the KB left UNKNOWN.

## Gate reference

| reason | rejects | example (rejected) | control (still passes) |
|---|---|---|---|
| markdown | bullet/heading prefixes, `**`, backtick residue | `*   **Claim:** "X."` | plain prose unchanged |
| heading | short labels: ends `:`, no period, Title-Case heavy | `Factual Errors (Simple Falsehoods)` | `The Earth is flat.` |
| question | interrogatives | `Are they credible?` | `The Earth is flat.` |
| imperative | verb-first openers | `Always question, verify, and seek evidence.` | `Critical thinking is your best defense against false claims!` |
| meta | teaching/organising meta-discourse | `Here are several examples of false claims:` | `Water boils at 200°C at sea level.` |
| pronoun | bare pronoun/determiner subject or object, or no lexical head (LLM track exempt) | `It is happy.` | `9 out of 10 dentists recommend Brand X toothpaste.` |
| malformed | empty/punct-only parts, contraction predicates, empty object (except `exist`), subject==object, deictic object | `The boiling point changes there.` | `There was an uprising.` (existential) |
| definition | `X is a/an <abstract noun>` | `A false claim is a statement.` | `Oslo is a city.` |
| demonstrative | text-deictic subjects | `These claims use real numbers.` | `Those two cities are in Norway.` |
| duplicate | near-duplicate of an admitted triple (lemmas, case/punct folded) | `THE EARTH is flat.` after `The Earth is flat.` | `Paris is the capital of France.` kept |

Sentence-level order in `sentence_reject_reason`: markdown → question → meta → imperative → heading. The `definition` and `demonstrative` gates are the slice 6d additions (`4028602`).

## The lookup guard

`OfflineWikidata.lookup_entity` (Slice 0, `f49c1db`) resolves by exact label, article-stripped label and exact alias first; prefix matching comes last and now requires a **3+ character** query and a **word boundary** (the stored label/alias equals the query or starts with the query plus a space). `is_junk_name` rejects punctuation-only strings, bare pronouns/determiners and bare stopwords before any match. Pre-fix, `LIKE 'i%'` resolved **I/it → Q38 Italy** (reproduced against `data/wikidata_seed.db`); post-fix `I`, `it`, `Trondh`, `Icel` → None while `South` → Q258 (South Africa) still prefix-matches. The verifier mirrors the guard: `_verifier_relation` returns UNKNOWN without scoring when `is_referential_subject(claim.subject)` fails, so a pronoun claim can no longer be judged against the wrong entity's facts.

## Metadata contract

`ExtractionResult.metadata` carries `admission_metadata(...)`: `{admitted_claims: n, discarded_candidates: {reason: count}}`; the LLM track adds `llm_paragraphs`, `llm_claims`, `llm_errors`. `Prong3Extraction` forwards the summary to `FactualAccuracy.evaluate`, which stores it as `metadata.claim_admission` — diagnostics only, never part of the score. Each admitted claim's `source` is `spacy` | `llm` | `both`. The UI (`frontend/index.html`) reads `claim_details` from the Factual Accuracy metadata: dual-track counts, the claim evidence strip with per-claim source chips (locale `claim_source_spacy/llm/both`) and the KB ↔ MiniCheck agreement dumbbell (`verifier_score`). The `claim_admission` summary is in the API response but not rendered.

## Limits

- **Quoted/reported claims**: spaCy drops propositions embedded in reporting clauses ("The teacher said the Earth is flat" yields no triple); the optional LLM track handles some. Treat quoted claims as supported only when `llm_extract` is on (ASSUMPTIONS.md §A5).
- **Accepted leaks**: the fragment `smoking is that bad` and the advice sentence `Critical thinking is your best defense against false claims!` pass all gates; both evaluate `unknown` and do not affect scoring.
- **Unknown vs error**: no claims / no KB / `verifiable == 0` → `status='unknown'` (0.5 is display-only, never aggregated). Verifier down → relation stays UNKNOWN, the error string goes to `verifier_errors`, `minicheck` evidence status is `error`; a score is never fabricated.

## Adding or testing a gate

1. Add the check in `src/extraction/claim_admission.py` — `admit_triple` (triple level) or `sentence_reject_reason` (sentence level); lexicons live at the top of the module. The reason is a new lowercase histogram key.
2. Add a parametrised reject test plus an admitted control to `tests/test_claim_admission.py` — every gate keeps a "still passes" case.
3. If the fixture can produce it, add an example to `tests/fixtures/teacher_false_claims.json` (`text`, `expected_min`, `max_admitted` = 15) and extend `allowed_reasons` in `test_admission_on_exported_teaching_prose`.
4. Run `pytest tests/test_claim_admission.py -q` and check the fixture's discard histogram.

## Verification (this document)

- `pytest tests/test_claim_admission.py -q` at `bbb7d99`: **41 passed**, 1 warning (unrelated CUDA driver notice), ~10 s.
- Live fixture run (default, `llm_verify` off): 8 admitted; discarded `{meta 15, definition 1, pronoun 6, demonstrative 2, question 7}`; all five expected lies present; `relation_counts` all `unknown` (verifiable 0, status `unknown`).
- Pre-fix numbers (76 / ~39 / 0 verifiable / 11 false denials) are from the export file and commit index `f49c1db`; the pre-fix lookup mis-resolution was reproduced directly against the seed DB.

## Optional LLM admission (`llm_admit`)

An opt-in 1.5B classifier (`[ADMIT]` task, `LLMJudgeClient.admit`) can review the
admitted claims and drop those it classifies as non-claims (commentary, advice,
definitions). It is **not enabled by default and not recommended** for the current
model: on the teacher fixture it drops 4 of 9 claims — two intended (the "smoking
is that bad" fragment and the "Critical thinking..." advice) and two false
negatives ("Humans have five eyes", "This new supplement is 100% natural"). A
revised prompt that admits general-class claims still drops "five eyes" and starts
admitting the advice, so it trades recall for precision. The deterministic gates
remain the default; the classifier stays available for experiments, records
`llm_admit_dropped`/`llm_admit_unknown` in `metadata.claim_admission`, and keeps
claims when the model is unavailable.

## Ablation (teacher-prose fixture)

`scripts/eval_admission_ablation.py` adds one layer at a time and regenerates
`evaluation_results/admission_ablation.{json,md}`:

| Stage | Claims | Expected of 5 | Known non-claims |
|---|---|---|---|
| A raw | 76 | 5 | 46 |
| B +markdown | 28 | 5 | 15 |
| C +sentence | 17 | 5 | 8 |
| D +triple | 8 | 5 | 2 |
| E +dedupe | 8 | 5 | 2 |
| F +use-mention | 9 | 5 | 2 |

Reading: markdown cleaning removes most formatting fragments (76→28, junk 46→15);
the sentence gates remove headings, questions and meta-discourse (28→17, junk
15→8); the triple gates are the largest precision win (17→8, junk 8→2); the
use-mention pass adds the quoted claim with its provenance while keeping all five
intended lies. The two remaining non-claims are the documented leaks (the
"smoking is that bad" fragment and the advice sentence).
