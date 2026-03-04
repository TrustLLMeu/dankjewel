# Scientific Assumptions & Approximations

This document tracks all scientific assumptions, approximations, and design decisions
in the Instant Evaluator (IE) that may need revision as the system matures.

**Last updated:** 2026-02-27

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

**Assumption:** A ~75-entity seed database is sufficient for Phase 1 testing.
Claims about entities not in the seed return `unknown` rather than `confirmed`
or `denied`.

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

**To revisit when:** Integrating vLLM-based claim extraction (Phase 2), which
can handle arbitrary sentence structures via prompted decomposition.

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

## Prong 1: LLM-as-Judge

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

### A10. Flesch Reading Ease as Fluency Proxy

**Assumption:** Flesch Reading Ease score correlates with text fluency.

**Impact:** Measures readability, not fluency per se. Highly technical but
well-written text may score poorly.

**To revisit when:** Adding LLM-based fluency evaluation in Prong 1.

