# TODO — LLM-Based Dimension Upgrades

**Created:** 2026-03-12
**Status:** Planning
**Language scope:** English first; multilingual deferred until LLM dimensions are functional.

---

## Overview

Two evaluation dimensions currently use rule-based or small-model heuristics.
Each will gain an LLM-based alternative served by a single shared vLLM instance.
(Toxicity detection already uses vLLM — no action needed.)
The existing rule-based implementations are computationally cheap and will be
**retained as default baselines** for benchmarking quality and latency against
the LLM alternatives. Every evaluation will produce **dual output**: both the
baseline score and the LLM score, at the **dimension level**.

---

## 1. LLM-Based Claim Extraction (Prong 3)

### Current baseline
- `src/extraction/claim_extractor.py` — spaCy dependency parsing (`en_core_web_sm`)
- Extracts (subject, predicate, object) triples by walking dependency trees
- Annotates temporal anchors, comparative tags, and modality modifiers
- Timing already tracked via `extraction_time_ms` and `verification_time_ms`
  in `src/prongs/prong3_extraction.py` (designed for this comparison)

### Limitations of baseline
- No coreference resolution ("He won in 2020" — who is "He"?)
- Misses implicit and multi-sentence claims
- Hardcoded to English (`en_core_web_sm`)
- Syntactic triples miss paraphrased or embedded facts

### LLM replacement
- [ ] Create `src/extraction/llm_claim_extractor.py`
- [ ] Prompt-based atomic-fact decomposition (à la SAFE / FActScore)
- [ ] Input: raw text → Output: list of `Claim` objects (same dataclass)
- [ ] Use `VLLMClient.generate()` with a claim-extraction task prefix
- [ ] Return `ExtractionResult` with `extraction_time_ms` for benchmarking

### Dual output
- Both spaCy-extracted claims and LLM-extracted claims included in result
- `DimensionScore.metadata` carries `baseline_claims` and `llm_claims`

---

## 2. LLM-Based Readability Assessment (Prong 2)

### Current baseline
- `src/dimensions/prong2_dimensions.py` → `FluidityDimension`
- Language-aware Flesch readability (Flesch 1948, Amstad 1978, Douma 1960,
  Pan-Germanic fallback from Matricciani 2023)
- Syllable counting via `textstat` + `pyphen`
- Sub-millisecond execution

### Limitations of baseline
- Measures surface features only (syllables per word, words per sentence)
- Cannot assess coherence, audience-appropriateness, or structural flow
- Flesch scores are poorly calibrated for non-English Germanic languages
- Already marked for replacement in docstring and `src/config.py`

### LLM replacement
- [ ] Create `src/dimensions/llm_fluidity.py`
- [ ] Prompt-based readability assessment via `VLLMClient.generate()`
- [ ] Evaluates: coherence, audience level, structural flow, vocabulary complexity
- [ ] Structured output: score (0–1), reading level, explanation
- [ ] Use task prefix `[READABILITY]` for multi-task model routing

### Dual output
- `DimensionScore.metadata` carries `baseline_value` (Flesch raw score) and
  `llm_value`
- Flesch raw score and formula name always included for interpretability

---

## 3. Benchmarking

All comparisons are at the **dimension level** — each LLM dimension is benchmarked
against its rule-based baseline individually.

### Timing
- Every LLM dimension must log `processing_time_ms` using the same pattern as
  `extraction_time_ms` in `src/prongs/prong3_extraction.py`
- Baseline times are logged alongside for direct comparison:
  - Claim extraction: spaCy `extraction_time_ms` vs. vLLM `extraction_time_ms`
  - Readability: Flesch computation ms (sub-millisecond) vs. vLLM generation ms

### Quality
- [ ] Extend `scripts/run_benchmark.py` to output side-by-side quality and
      latency tables per dimension
- [ ] Use `data/benchmark_claims.json` for claim extraction comparison
- [ ] Create English-language annotated test set for readability

### Output format
```
Dimension               Baseline (ms)   LLM (ms)   Baseline score   LLM score
─────────────────────   ─────────────   ────────   ──────────────   ─────────
Claim Extraction              12.3        340.5          0.72          0.91
Readability Assessment         0.4        310.8          0.65          0.78
```

---

## 4. Single-Model Strategy

All LLM dimensions will be served by a **single vLLM instance** running
one base model (e.g., Mistral-7B-Instruct), keeping VRAM at ~14–16 GB.
(Toxicity detection already runs on this instance.)

### Approach options
1. **Multi-task prompting** — One model, task prefixes
   (`[CLAIMS]`, `[READABILITY]`). Simplest; no fine-tuning needed
   for initial experiments.
2. **Multi-task fine-tuning** — One model fine-tuned on mixed training data from
   both tasks. Better quality, requires ~1k–5k labelled English examples
   per task.
3. **Multi-LoRA serving** — One base model with two LoRA adapters, swapped
   per request. vLLM supports this natively. Best quality-per-VRAM ratio.

### Training data (English first)
- Claim extraction: `data/benchmark_claims.json` (existing, likely insufficient alone)
- Readability: needs annotated English dataset with reading-level labels
- Target: ~1,000–5,000 labelled examples per task for LoRA fine-tuning

---

## 5. Pipeline Integration (Deferred)

> Deferred until individual LLM dimensions are working in English.

### Current state
- `src/pipeline.py` → `EvaluationPipeline.__init__()` instantiates each prong
  independently with no shared resources
- No `VLLMClient` is passed between prongs
- Prong 4 already receives `intrinsic_data` from an external vLLM generation

### Required changes (when ready)
- [ ] `EvaluationPipeline.__init__()` accepts an optional `VLLMClient` instance
- [ ] Shared client is passed to Prongs 1, 2, and 3 for their LLM dimensions
- [ ] Each prong's `evaluate()` returns dual scores (baseline + LLM) in
      `DimensionScore.metadata`
- [ ] Fallback: if vLLM is unreachable, dimensions return baseline scores only
      (matching existing error-handling pattern)

### Multilingual (deferred further)
- English first until all three LLM dimensions are functional and benchmarked
- Multilingual follows: the nine languages in `src/config.py`
  (da, de, en, fo, is, nb, nn, nl, sv)
- LLM-based approach natively supports multilingual — eliminates per-language
  spaCy models and Flesch coefficient gaps
- Rule-based baselines already cover multilingual via lexicons and Flesch
  coefficients












