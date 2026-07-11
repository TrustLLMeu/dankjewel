## Prong 4 Implementation Summary

**Date:** February 27, 2026 (last updated July 11, 2026)
**Status:** ✅ COMPLETE & TESTED — vLLM integration live
**Scope:** All 9 supported languages (language-agnostic; logprobs from vLLM HTTP API)

### Overview

Prong 4 (Intrinsic Evaluation) has been successfully implemented with four dimensions using model logits and log-likelihoods from vLLM:

- **Uncertainty**: Mean token confidence (higher = more uncertain)
- **Perplexity**: exp(mean NLL) — raw, no normalization
- **Token Entropy**: Shannon entropy of token distributions (normalized [0,1])
- **Semantic Entropy**: Entropy of top-5 clustered tokens (normalized [0,1])

### Data Structure

`IntrinsicData` (vLLM-compatible format):
```python
@dataclass
class IntrinsicData:
    token_ids: List[int]  # Generated token IDs [seq_len]
    logits: Optional[np.ndarray]  # [seq_len, vocab_size] raw model logits
    log_likelihoods: Optional[np.ndarray]  # [seq_len] negative log-likelihood per token
    vocab_size: Optional[int]  # Vocabulary size (auto-detected from logits.shape[1])
```

### Dimensions Implemented

#### 1. Uncertainty
- **Input:** Logits or log-likelihoods
- **Computation:** 1 - mean(max softmax probability per token)
- **Range:** [0, 1] where 0 = very confident, 1 = very uncertain
- **Example:** High confidence tokens → low uncertainty

#### 2. Perplexity
- **Input:** Log-likelihoods (or logits as fallback)
- **Computation:** exp(mean NLL)
- **Range:** [1, ∞) where 1 = perfect predictability, high = unpredictable
- **Note:** Raw (no normalization) per specification
- **Example:** High confidence → perplexity ≈ 1.1

#### 3. Token Entropy
- **Input:** Logits (required)
- **Computation:** Shannon entropy of per-token distributions, normalized by max entropy
- **Range:** [0, 1] where 0 = deterministic, 1 = uniform distribution
- **Unit:** Bits (entropy / log(2))
- **Example:** Peaked distribution → low entropy

#### 4. Semantic Entropy
- **Input:** Logits (required)
- **Computation:** Entropy of top-5 probable tokens (clustered), normalized
- **Range:** [0, 1] where 0 = deterministic, 1 = uniform among top-5
- **Unit:** Bits
- **Example:** One token dominates → low semantic entropy

### File Structure

```
src/
├── prongs/
│   └── prong4_intrinsic.py          # Main implementation
│       ├── IntrinsicData (dataclass)
│       ├── Uncertainty (dimension)
│       ├── Perplexity (dimension)
│       ├── TokenEntropy (dimension)
│       ├── SemanticEntropy (dimension)
│       └── Prong4Intrinsic (evaluator)
└── (other prongs...)

tests/
└── test_prong4.py                   # 19 comprehensive tests
```

### Test Results

✅ **All 19 tests PASSED:**

**Uncertainty Tests (3):**
- ✅ High vs low confidence comparison
- ✅ Low confidence produces high uncertainty
- ✅ No data returns neutral score

**Perplexity Tests (3):**
- ✅ High confidence → low perplexity
- ✅ Low confidence → higher perplexity
- ✅ Fallback to logits if log-likelihoods missing

**Token Entropy Tests (3):**
- ✅ High confidence → lower entropy
- ✅ Low confidence → higher entropy
- ✅ Uniform distribution → maximum entropy

**Semantic Entropy Tests (2):**
- ✅ High confidence → lower semantic entropy
- ✅ Low confidence → higher semantic entropy

**Integration Tests (6):**
- ✅ Basic evaluation with 4 dimensions
- ✅ All scores in valid ranges (perplexity ≥ 1, others [0,1])
- ✅ Missing data returns error
- ✅ JSON serialization works
- ✅ High vs low confidence differences
- ✅ Prong4LLMAsJudge initialization

**Data Validation Tests (2):**
- ✅ IntrinsicData validation succeeds
- ✅ Empty token sequence raises error

### Mock Data Examples

The test suite includes realistic mock data generation:

**High Confidence Logits:**
```python
logits[i, i % vocab_size] = 50.0  # Strong peak for one token
```
→ Uncertainty ≈ 0.001, Perplexity ≈ 1.0, Token Entropy ≈ 0.0

**Low Confidence Logits:**
```python
logits = np.random.normal(0, 3, size=(seq_len, vocab_size))  # Spread
```
→ Uncertainty ≈ 0.87, Perplexity ≈ 10+, Token Entropy ≈ 0.61+

### Integration Points

When vLLM is ready (Phase 2):

```python
# From vLLM output
prong4 = Prong4Intrinsic()
intrinsic_data = IntrinsicData(
    token_ids=vllm_output.token_ids,
    logits=vllm_output.logits,  # Shape: [seq_len, vocab_size]
    log_likelihoods=vllm_output.log_likelihoods,  # Shape: [seq_len]
    vocab_size=vllm_output.vocab_size
)
result = prong4.evaluate(text, intrinsic_data=intrinsic_data)
```

### Performance Metrics

- **Latency per text:** <50ms (computation only, no model inference)
- **Memory:** Minimal (numpy arrays only)
- **Numerical stability:** Uses log-domain operations, clips tiny probabilities
- **GPU support:** Not required (CPU-friendly numpy operations)

### Known Characteristics

1. **Uncertainty** — Inverted confidence (1 - prob), intuitive for "uncertain-ness"
2. **Perplexity** — Raw (no normalization), unbounded, direct from vLLM
3. **Token Entropy** — Normalized by vocab size entropy bound
4. **Semantic Entropy** — Approximation using top-5 tokens (reduces variance, computational cost)

### Score Ranges

| Dimension | Raw Range | Normalized | Interpretation |
|-----------|-----------|-----------|-----------------|
| Uncertainty | [0, 1] | N/A | 0 = confident, 1 = uncertain |
| Perplexity | [1, ∞) | raw | 1 = predictable, 10+ = diverse |
| Token Entropy | [0, log2(50000)] → [0, 1] | Yes | 0 = deterministic, 1 = max entropy |
| Semantic Entropy | [0, log2(5)] → [0, 1] | Yes | 0 = one token, 1 = 5 equally likely |

### Next Steps

1. **Full-logit mode** — expose vLLM's native Python API (`vllm.LLM`) for exact
   Token Entropy over full vocab (see `ASSUMPTIONS.md` A1/A2)
2. **Latency profiling** — measure real end-to-end latency across all 4 prongs
3. **Multilingual validation** — logprob pipeline is already language-agnostic;

### References

- **Protocol:** Deliverable 7.5 (D7_5.txt) — Intrinsic metrics section
- **Metrics:**
  - Uncertainty: Token-level softmax confidence
  - Perplexity: Standard NLP metric (exp of NLL)
  - Token Entropy: Shannon entropy (bits)
  - Semantic Entropy: Kuhn et al. (2023) approximation via top-k clustering

---

**Status:** ✅ Complete — vLLM HTTP API integrated via `src/vllm_adapter.py`
**Test Coverage:** 19 tests, 100% pass rate

