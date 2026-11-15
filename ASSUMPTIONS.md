# Scientific Assumptions & Approximations

This document tracks all scientific assumptions, approximations, and design decisions
in the Instant Evaluator (IE) that may need revision as the system matures.

**Last updated:** 2026-07-11

---

## Prong 4: Intrinsic Evaluation

### A1. Top-k Entropy Approximation

**Assumption:** Token Entropy and Semantic Entropy can be meaningfully computed
from the top-k (default k=20) logprobs returned by vLLM's OpenAI-compatible
HTTP API, rather than requiring full vocabulary logit distributions.

**What we get:** Per-token log-probabilities for the top-k most probable tokens.
**What we don't get:** Full logits over the entire vocabulary (e.g., 151k tokens
for Qwen2.5).

**Impact:**
- **Uncertainty:** Exact — uses only the chosen token's log-probability.
- **Perplexity:** Exact — uses only per-token log-likelihoods.
- **Token Entropy:** Underestimate. True Shannon entropy sums over the full vocab;
  our top-k approximation captures only the dominant probability mass. Normalized
  against log2(k) instead of log2(vocab_size). Relative ranking between texts
  is preserved (high-entropy text still scores higher).
- **Semantic Entropy:** Good fit. The existing algorithm already clusters only the
  top-k tokens. Directly matches vLLM's HTTP API output.

**Mitigation:** Metadata on every score includes `method: 'top_k_approximation'`
and the actual `k` used, so downstream consumers know the precision level.

**To revisit when:** Switching to vLLM's native Python API (`vllm.LLM`) which
can return full logit tensors. This would give exact Token Entropy but at
significant computational cost (see A2).

### A2. Full Logits Computational Cost

**Context:** The vLLM HTTP API returns sparse top-k logprobs. Full logits require
the native Python API.

**Cost estimate for full logits (Qwen2.5-1.5B, vocab=151,936):**
- Per token: 151,936 × 4 bytes (float32) = **~592 KB**
- For 512 tokens: 512 × 592 KB = **~296 MB** per generation
- Network transfer (if remote): 296 MB / generation, ~3s at 100 MB/s
- Softmax computation: O(seq_len × vocab_size) = 512 × 151k = ~78M operations
- For larger models (Llama-3.1-70B, vocab=128,256): similar vocab cost but
  inference itself dominates

**Conclusion:** Full logits are feasible for offline batch evaluation but
impractical for real-time evaluation in an interactive UI.  Top-k approximation
is the correct choice for the proof-of-concept and likely for production.

### A3. Perplexity Normalization

**Assumption:** Raw perplexity values are reported without normalization.
Perplexity ranges from ~1.0 (perfectly predicted) to potentially thousands
(very surprising text). Other Prong 4 dimensions are normalized to [0, 1].

**Impact:** The aggregator averages Prong 4 scores. Raw perplexity can dominate
the aggregate if not scaled.

**Current mitigation:** The aggregator uses per-dimension scores and can apply
dimension-specific weighting. Perplexity's contribution is isolated.

**To revisit when:** Building the score visualization dashboard. A log-scale
normalization (e.g., `1 / (1 + log(ppl))`) may be needed for display.

---

## Prong 3: Extraction-Based Evaluation

### A4. Wikidata Seed Coverage

**Assumption:** A 122-entity seed database (a labelled seed, not Wikidata) is
sufficient for Phase 1 testing. Claims about entities not in the seed return
`unknown` rather than `confirmed` or `denied`.

**Impact:** Factual Accuracy scores are conservative — many true claims may
score 0.5 (unknown) rather than 1.0 (confirmed) simply because the entity
isn't seeded.

**To revisit when:** Expanding to 200k entities via SPARQL dump, or switching
to a live Wikidata API.

### A5. Rule-Based Claim Extraction

**Assumption:** spaCy dependency parsing can extract verifiable (S, P, O)
triples from English text. Known limitations:
- Complex sentences with multiple clauses may lose relationships
- Passive voice and relative clauses reduce extraction quality
- Event-level claims (e.g., "Queen played at Knebworth in 1986") don't map
  to Wikidata properties

**Impact:** Extraction recall is low for complex text. Precision is moderate.

**Admission gates (2026-11):** non-claims are now filtered before scoring —
markdown residue, headings, questions, imperatives, meta-discourse, pronouns
without a resolved referent, encyclopedic definitions (`X is a/an <abstract
noun>`), text-deictic subjects (`these claims`, `this article`) and
near-duplicates. The gates and their discard reasons are documented in
`src/extraction/claim_admission.py`; the fixture from an exported
teaching-prose run is `tests/fixtures/teacher_false_claims.json`.

**Quoted/reported claims:** a deterministic use-mention pass extracts quoted
propositions and `Claim:`-labelled sentences, marks them `source="quote"`, and
gates the quoted sentence itself while treating the reporting line as
commentary. This covers the common `Claim: "..."` teaching format. Propositions
embedded mid-sentence in reported speech without quotes ("the teacher said that
the Earth is flat") still depend on the optional LLM extraction track.

**To revisit when:** adding a reported-speech parser for unquoted embedded
propositions, and a dedicated pass for quote patterns in other languages.

### A6. Inverted Copula Heuristic

**Assumption:** When a copula sentence has a descriptive NP as subject and a
proper noun as attribute (e.g., "The capital of France is Paris"), flipping
subject↔object produces a verifiable triple.

**Impact:** Works well for definitional statements. May misfire on sentences
like "The problem is John" where "John" is the attribute but flipping changes
meaning.

**To revisit when:** Broader claim extraction testing reveals misfire patterns.

### A7. Location Denial Heuristic

**Assumption:** If a Wikidata entity has location data (P17/P131/P30) and none
of it matches the claimed location, the claim is denied.

**Impact:** Correct for clear geographic claims. Could false-deny if the entity
has incomplete location data (e.g., entity has P17 but claimed location is a
more specific subdivision not in P131).

**To revisit when:** Expanding Wikidata seed to include deeper administrative
hierarchies.

---

## Prong 4 / Generation: Remote (Bring-Your-Own-Key) Backend

### A13. Chat-Completions Logprobs Availability Varies by Provider

**Assumption:** The remote `OpenAICompatibleClient` (`src/llm_backends/openai_compatible.py`)
talks to `/v1/chat/completions` — the endpoint nearly all hosted
OpenAI-compatible providers actually implement, unlike vLLM's legacy
`/v1/completions`. Its logprobs are requested via `logprobs: true,
top_logprobs: k` and parsed into the same flat `tokens`/`token_logprobs`/
`top_logprobs` fields the local vLLM backend produces, so Prong 4 and the
rest of the pipeline are backend-agnostic.

**Impact:** Not all providers return logprobs at all (many hosted APIs
omit or disable them), and those that do often cap `top_logprobs` far
below vLLM's configurable `VLLM_LOGPROBS_K` (typically ≤5, vs. 20 locally).
When a remote host returns no logprobs, `GenerationResult.tokens` /
`token_logprobs` / `top_logprobs` stay `None`, and Prong 4 falls back to
its existing neutral placeholder scores — identical to the pre-existing
"no vLLM data available" path used when running Prong 4 without a live
model at all. This means **Prong 4 fidelity is currently local-vLLM-only**;
remote-backend generations should be expected to show neutral Prong 4
scores for most third-party providers.

**To revisit when:** Auditing provider-by-provider logprobs support (e.g.
OpenAI itself supports `top_logprobs` up to 20 on chat completions; many
others do not), or if a provider-specific capability table becomes useful
in the UI.

### A14. API Key Handling — No Server-Side Persistence

**Assumption:** Remote backend credentials (`base_url`, `api_key`) are
supplied per-request by the frontend and never cached, logged, or
persisted server-side. A fresh `OpenAICompatibleClient` is constructed for
each request needing a remote backend and closed immediately afterward
(see `src/llm_backends/factory.py`).

**Impact:** No server-side secret storage to secure or leak, at the cost
of a small per-request connection-setup overhead (no connection pooling
across requests for remote backends, unlike the shared local vLLM client).
The frontend, by default, keeps the key only in page memory; a "remember
key" checkbox opts into `localStorage` persistence in the browser, with an
explicit on-page privacy note.

**To revisit when:** Scaling to concurrent multi-user deployments where
connection-pooling per remote host (keyed only by `base_url`, never by
key) would reduce latency.

---



### A8. Toxicity Model Choice

**Assumption:** `unitary/toxic-bert` is sufficient for toxicity detection.
It was trained on English civil-comments data and may underperform on:
- Non-English text
- Subtle/coded toxicity
- Domain-specific offensive language

**To revisit when:** Extending to non-English languages or domain-specific use cases.

### A9. Relevance via Cosine Similarity

**Assumption:** Cosine similarity between `all-MiniLM-L6-v2` embeddings of
prompt and response is a meaningful proxy for relevance.

**Impact:** Works well for factual Q&A. May mislead for creative writing
prompts where high similarity isn't the goal.

**To revisit when:** Evaluating creative/open-ended generation tasks.

---

## Prong 2: Rule-Based Evaluation

### A10. Language-Aware Flesch Readability as Fluency Baseline

**Assumption:** `FluidityDimension` uses language-specific Flesch readability
coefficients as a heuristic baseline for fluency scoring.  **LLMs are
state-of-the-art for readability assessment**; this rule-based approach will
be replaced by a fine-tuned LLM evaluator in a future iteration.

**Formula:** `score = base − ASL_coeff × (words/sentences) − ASW_coeff × (syllables/words)`

**Empirically validated coefficients:**
- **English:** Flesch, R. (1948). "A New Readability Yardstick". *Journal of
  Applied Psychology*, 32(3), 221–233. Coefficients: (206.835, 1.015, 84.6).
- **German (Flesch-Amstad):** Amstad, T. (1978). *Wie verständlich sind unsere
  Zeitungen?* Coefficients: (180.0, 1.0, 58.5).
- **Dutch (Flesch-Douma):** Douma, J. H. (1960). *De leesbaarheid van
  landbouwbladen.* Coefficients: (206.835, 0.93, 77.0).

**Pan-Germanic fallback** (used for da, fo, is, nb, nn, sv):
Matricciani, E. (2023). "Readability Indices Do Not Say It All on a Text
Readability". *Analytics*, 2(2), 296–314. MDPI.
Coefficients: (206.835, 1.0, 70.0). These were derived from a cross-linguistic
analysis of Germanic-family languages and provide a reasonable proxy when no
language-specific calibration study exists.

**Impact:** Measures readability, not fluency per se. Highly technical but
well-written text may score poorly. German and Dutch now use validated
formulas instead of the English coefficients. Other Germanic languages
use an approximation that is better calibrated than the English original
but not individually validated.

**To revisit when:** A fine-tuned LLM readability evaluator is integrated
(planned for a future Prong 1 dimension).

### A11. Syllable Counting Backend Mapping

**Assumption:** Syllable counting is performed by `textstat`, which delegates
to `pyphen` hyphenation dictionaries.  The `textstat.set_lang()` function
is called inside a `threading.Lock` to prevent interleaving in concurrent
requests (global mutable state).

**Backend mapping (project lang → pyphen dictionary):**
- `en` → `en` (native)
- `da` → `da` (pyphen da\_DK)
- `de` → `de` (pyphen de\_DE)
- `nb` → `nb` (pyphen nb\_NO — Bokmål)
- `nl` → `nl` (pyphen nl\_NL)
- `nn` → `nn` (pyphen nn\_NO — Nynorsk)
- `sv` → `sv` (pyphen sv\_SE)
- `fo` → `nn` (Faroese has no pyphen dictionary; Nynorsk is used as the
  nearest North-Germanic backend)
- `is` → `nn` (Icelandic has no pyphen dictionary; Nynorsk is used as the
  nearest North-Germanic backend)

**Why Nynorsk for fo/is:** Norwegian Nynorsk preserves more archaic
North-Germanic morphology (e.g., three grammatical genders, diphthongs,
strong-verb conjugations) than Bokmål or Danish, making it a closer
phonological proxy for Faroese and Icelandic syllable structure.

**Impact:** Syllable counts for Faroese and Icelandic are approximate.
Icelandic has vowel-length distinctions and diphthongs (e.g., "fjörður",
"þjóðvegur") that Nynorsk pyphen will miscount.  Acceptable for a
heuristic baseline; exact accuracy is not required since this entire
approach is a proxy pending an LLM-based evaluator.

**Lock overhead:** A `threading.Lock` acquire/release pair costs ~0.5 µs.
The critical section (set\_lang + three counting calls) takes ~0.5–1 ms.
Lock contention is negligible in the current single-worker uvicorn
architecture.

**To revisit when:** Switching to a multi-worker deployment or replacing
textstat with an LLM-based evaluator.

### A12. Politeness Lexicon Provenance

**Assumption:** The `politeness_cues` and `rudeness_cues` keyword lists are
derived from the politeness strategy definitions in:

Danescu-Niculescu-Mizil, C., Sudhof, M., Jurafsky, D., Leskovec, J., &
Potts, C. (2013). "A computational approach to politeness with application
to social factors." *Proceedings of the 51st Annual Meeting of the
Association for Computational Linguistics* (ACL 2013), P13-1025.

The paper defines politeness as a set of **strategies** (gratitude, greeting,
counterfactual modal, apologizing, bald-on-record urgency, etc.)
operationalised as syntactic and lexical patterns.  The English YAML
(`en.yaml`) contains a **keyword simplification** of those strategies — a
lossy extraction that maps each strategy to one or more flat string cues
suitable for substring matching.

**Non-English lexicons** (da, de, fo, is, nb, nl, nn, sv) are **best-effort
translations** of the English canonical markers.  They have not been
independently validated against a politeness corpus in those languages
and are flagged for refinement by annotators.

**Substring matching limitation:** The current `PolitenessDetection`
dimension uses `cue in text_lower` (substring matching).  This means:
- Multi-word cues like `"could you"` and `"vær så snill"` work correctly.
- Short cues like `"now"` may false-match inside longer words (e.g.,
  `"knowledge"`, `"unknown"`).
Word-boundary matching is deferred to a future iteration, as it affects
all lexicon-based dimensions, not just politeness.

**To revisit when:** Annotators complete validation of non-English lexicons,
or word-boundary matching is implemented across all Prong 2 dimensions.
