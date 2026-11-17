# Scouting brief — LLM-based Readability Assessment (Prong 2)

Date: 2026-11-17. Scout → Captain. Read-only; no product code touched.

**Target.** `TODO.md` §2 "LLM-Based Readability Assessment (Prong 2)" and
`docs/improvement-plan.md` Phases 2–4 (LLM dimensions via a shared vLLM
instance).

**Baseline to replace.** `src/dimensions/prong2_dimensions.py` →
`FluidityDimension`. Language-aware Flesch (Flesch 1948 / Amstad 1978 / Douma
1960 / Matricciani 2023 fallback), via `textstat+pyphen`, sub-millisecond.
Already flagged for replacement; see `ASSUMPTIONS.md` A10/A11.

**Shared runtime.** One vLLM, task prefixes `[JUDGE]` / `[CLAIMS]` /
`[READABILITY]` on the local OpenAI-compatible servers (`llm_judge_client.py`).
Do not propose a separate server, vendor SaaS, or a >1.7B judge.

**Filters applied.** Must fit D7.5 Prong 2 readability/fluency; must be online
(seconds); must not need a new prong; English first; method needs a
metric/repo/dataset we can point at.

---

## What was opened

| Source | URL | Year | Venue |
|--------|-----|------|-------|
| G-Eval | https://arxiv.org/abs/2303.16634 | 2023 | arXiv (Liu et al.) |
| FLASK | https://arxiv.org/abs/2307.10928 | 2023 (v4 Apr 2024) | ICLR 2024 Spotlight |
| Prometheus 2 | https://arxiv.org/abs/2405.01535 | 2024 | EMNLP 2024 |
| Prometheus-Vision | https://arxiv.org/abs/2401.06591 | 2024 | arXiv |
| FairEval | https://arxiv.org/abs/2305.17926 | 2023 | arXiv (Wang et al.) |
| MetaCritique | https://arxiv.org/abs/2401.04518 | 2024 | ACL 2024 Findings |
| ChatEval | https://arxiv.org/abs/2308.07201 | 2023 | arXiv (Chan et al.) |
| SemScore | https://arxiv.org/abs/2401.17072 | 2024 | arXiv (Aynetdinov & Akbik) |
| RAGAS general-purpose metrics | https://docs.ragas.io/en/latest/concepts/metrics/available_metrics/general_purpose/ | 2024+ | docs |
| DeepEval metrics | https://deepeval.com/docs/metrics-introduction | 2024+ | docs |
| FActScore | https://aclanthology.org/2023.emnlp-main.741/ | 2023 | EMNLP 2023 |
| MiniCheck | https://aclanthology.org/2024.emnlp-main.499/ | 2024 | EMNLP 2024 |
| VeriScore | https://aclanthology.org/2024.findings-emnlp.552/ | 2024 | EMNLP 2024 Findings |

**What was *not* found.** No open-source CEFR auto-leveler, TextEvaluator-style
LLM band, or Coh-Metrix-inspired rubric that (a) runs online, (b) fits a ≤1.7B
judge, and (c) ships English code + dataset. The 2025–2026 "LLM as readability
judge" papers cited in the brief request could not be located with the available
fetch tools. The ideas below therefore lean on the well-documented prompt-based
evaluation paradigms (G-Eval, FLASK, RAGAS/DeepEval rubrics) that are proven on
small local models.

---

## Idea 1 — G-Eval readability rubric (Liu 2023) · **adapt**

- **Source:** Liu et al., *G-Eval: NLG Evaluation using GPT-4 with Better
  Human Alignment*, https://arxiv.org/abs/2303.16634, 2023. GPT-4 backbone in
  the paper; the CoT + form-filling paradigm works on smaller models when the
  task is constrained.
- **Prong:** 2 (Fluidity / Fluency).
- **Why adapt:** The repo already uses the G-Eval pattern for `[JUDGE]`:
  few-shot JSON output `{"score": 0-1, "rationale": str}`. Extending the same
  pattern to readability is the shortest path. The paper shows that explicit
  evaluation steps (chain-of-thought) improve correlation with human judgment;
  our adaptation asks the judge to think about coherence, audience fit, flow,
  and vocabulary before emitting a single score.
- **What to implement:**
  - `src/llm_judge_client.py`: add `readability()` method and
    `_READABILITY_SYSTEM_PROMPT` with `[READABILITY]` prefix, few-shot JSON
    examples, and explicit criteria (coherence, audience-appropriateness,
    structural flow, vocabulary complexity).
  - `src/dimensions/llm_fluidity.py`: new `LLMFluidityDimension` that calls
    `readability()`, maps score to `DimensionScore`, and preserves dual output
    (`baseline_value` = Flesch raw score, `llm_value` = judge score).
  - `src/dimensions/prong2_dimensions.py`: no edit if the dimension is
    registered elsewhere; otherwise add to pipeline alongside
    `FluidityDimension`.
- **Cost:** tiny vLLM ≤1.7B (1 call per text, ~100-150 output tokens,
  ~200 ms warm on the 0.5B/1.5B). English on 0.5B, non-English on 1.5B via
  existing `get_judge_for_lang()` routing.
- **Closes:** wXze surface (Prong 2 becomes LLM-based, like Prong 1's tiny
  judge); V55p (adds a validation target for Prong 2).
- **Risk:** The 0.5B model may collapse partial answers to 0, just as the
  `[JUDGE]` prompt note warns. The multi-aspect variant (Idea 2) mitigates
  this because a partial answer on one sub-dimension does not zero the whole
  score.

---

## Idea 2 — Multi-aspect readability prompt (4 sub-scores + overall) · **adapt**

- **Source:** D7.5 `TODO.md` §2 + `improvement-plan.md` Phase 2 (internal
  requirement); prompt scaffold inspired by DeepEval multi-metric evaluation and
  FLASK skill decomposition.
- **Prong:** 2 (Fluidity / Fluency).
- **Why adapt:** Flesch measures only syllables/sentence and cannot assess
  coherence, audience level, structural flow, or vocabulary complexity. D7.5
  explicitly lists these four. A single prompt returns all four sub-scores
  plus an overall, so one call replaces the single-score G-Eval approach with
  finer-grained evidence. If the model drops a field, the others survive;
  parse robustness is higher than Idea 1 because a partial response is still
  usable.
- **What to implement:**
  - `src/llm_judge_client.py`: `_READABILITY_SYSTEM_PROMPT_MULTI` with
    `[READABILITY]` prefix and schema:
    `{"coherence": 0-1, "audience_level": 0-1, "structural_flow": 0-1,
    "vocabulary_complexity": 0-1, "overall": 0-1, "rationale": str}`.
    Add `readability_multi()` method and a JSON parser that tolerates missing
    keys (missing → `unknown`, scored ones kept).
  - `src/dimensions/llm_fluidity.py`: `LLMFluidityDimension` computes overall
    from the judge or falls back to averaging the scored sub-dimensions.
    `metadata` carries all sub-scores for the UI evidence view.
  - `src/evidence.py`: add `readability` to evidence source tags so the
    Evidence panel can show sub-dimension breakdowns.
- **Cost:** tiny vLLM ≤1.7B (1 call per text, ~200-300 output tokens,
  ~300-400 ms warm). Still well within the online budget.
- **Closes:** wXze surface (Prong 2 uses an LLM); V55p (validates Prong 2);
  YE7H robustness (sub-dimensions make failure modes visible).

---

## Idea 3 — FLASK skill-level decomposition (Ye 2024) · **adapt**

- **Source:** Ye et al., *FLASK: Fine-grained Language Model Evaluation based
  on Alignment Skill Sets*, ICLR 2024 Spotlight,
  https://arxiv.org/abs/2307.10928. GitHub release includes evaluation data
  and prompt templates.
- **Prong:** 2 (Fluidity / Fluency), specifically structural flow and
  comprehension.
- **Why adapt:** FLASK decomposes coarse preference scores into 12 fine-grained
  skills (logical thinking, factuality, comprehension, etc.). For readability,
  the relevant skills are "comprehension" and "organization". The FLASK prompt
  template uses a rubric with 1-5 scoring per skill. We can map the 1-5 scale
  to 0-1, adapt the rubric text to the `[READABILITY]` prefix, and use the
  judge model in place of GPT-4. The paper reports high model-human
  correlation, so the rubric wording is validated.
- **What to implement:**
  - `src/dimensions/llm_fluidity.py`: add a `FLASKRubricDimension` or subclass
    that constructs the FLASK-style prompt (skill definition + 1-5 rubric
    descriptions). Since FLASK scores per text, no per-sentence decomposition
    is needed.
  - `data/benchmark_readability.json` (new): a small annotated English test
    set with readability labels, needed for dual-output benchmarking (Flesch
    vs. LLM) per `TODO.md` §3.
  - `scripts/run_benchmark.py`: extend to include a readability comparison
    table.
- **Cost:** tiny vLLM ≤1.7B (1 call per text, ~150-250 output tokens).
- **Closes:** V55p (adds a validated, peer-reviewed rubric decomposition to
  Prong 2); YE7H (benchmark data is a robustness asset).

---

## Idea 4 — RAGAS RubricsScore / DeepEval G-Eval prompt scaffolding · **adapt**

- **Source:** RAGAS `RubricsScore` docs,
  https://docs.ragas.io/en/latest/concepts/metrics/available_metrics/general_purpose/
  (2024+); DeepEval G-Eval docs,
  https://deepeval.com/docs/metrics-introduction (2024+).
- **Prong:** 2 (Fluidity / Fluency).
- **Why adapt:** Both frameworks publish the exact prompt format and have been
  tested against local models (DeepEval explicitly documents Ollama support for
  `deepseek-r1:1.5b`). RAGAS uses a 1-5 rubric with paragraph descriptions per
  level; DeepEval uses a natural-language criteria string. We do **not**
  pip-install either framework. We steal the rubric wording and prompt
  structure, then reimplement them inside our existing `LLMJudgeClient`
  (strict JSON, timeout, error-to-unknown).
- **What to implement:**
  - `src/llm_judge_client.py`: add a generic `rubric_score(name, rubrics,
    text)` helper that formats a RAGAS-style rubric prompt and calls the judge.
    Reuse `_parse_verdict` or extend it to extract integer scores from 1-5
    rubrics.
  - `src/dimensions/llm_fluidity.py`: instantiate the helper with a readability
    rubric borrowed from RAGAS "clarity" / "quality" examples, adapted to
  coherence and flow.
- **Cost:** tiny vLLM ≤1.7B (1 call per text).
- **Closes:** V55p (adds a second validated rubric track); wXze (uses an LLM).

---

## Idea 5 — FairEval calibration (Wang 2023) · **adapt**

- **Source:** Wang et al., *Large Language Models are not Fair Evaluators*,
  https://arxiv.org/abs/2305.17926, 2023. Proposes Multiple Evidence
  Calibration, Balanced Position Calibration, and Human-in-the-Loop
  Calibration.
- **Prong:** cross-cutting (all LLM-as-judge surfaces: Prong 1 `[JUDGE]`,
  Prong 2 `[READABILITY]`, Prong 3 `[CLAIMS]`).
- **Why adapt:** The paper shows that LLM evaluators suffer from position bias
  (order effects), verbosity bias, and self-enhancement bias. For the
  readability task this matters when we later benchmark baseline vs. LLM score
  or compare two model outputs. The simplest applicable strategy is Balanced
  Position Calibration: when comparing two texts, swap their order in two
  separate calls and average the scores. For absolute single-text scoring,
  the insight is: do **not** ask the judge to implicitly compare against an
  exemplar inside the prompt, because the exemplar's position biases the
  result. The repo's existing `_JUDGE_SYSTEM_PROMPT` note already warns about
  this ("user message that repeats an exemplar verbatim echoes that exemplar's
  score").
- **What to implement:**
  - `src/llm_judge_client.py`: add a `calibrated_compare(a, b, task)` helper
    that runs the judge twice with swapped order and averages, plus a
    divergence check (if the two scores differ by >0.3, flag as "unreliable"
    in metadata). This is for offline benchmarking only; the online evaluate
    path stays one-call.
  - `docs/` or `ASSUMPTIONS.md`: document the bias risk and the calibration
    strategy.
- **Cost:** tiny vLLM ≤1.7B (2 calls for comparative benchmarking; 1 call for
  online absolute scoring).
- **Closes:** YE7H ("robustness testing and analysis of failure cases are
  limited"); partially V55p (adds validation rigor).

---

## Idea 6 — SemScore semantic-similarity fallback (Aynetdinov 2024) · **skip**

- **Source:** Aynetdinov & Akbik, *SemScore: Automated Evaluation of
  Instruction-Tuned LLMs based on Semantic Textual Similarity*,
  https://arxiv.org/abs/2401.17072, 2024.
- **Prong:** 2 (Fluidity / Fluency — coherence proxy).
- **Why skip:** SemScore compares model output to gold target responses using
  STS (sentence-transformer embeddings), not an LLM. It is a
  reference-based metric, and Dankjewel's online evaluator must be
  referenceless. The paper's finding (STS outperforms complex metrics for
  instruction tuning) is relevant for later benchmark design, but the method
  does not replace an LLM readability judge.
- **Cost:** CPU-only if used, but wrong frame for this prong.
- **Closes:** none.

---

## Idea 7 — ChatEval multi-agent debate (Chan 2023) · **skip**

- **Source:** Chan et al., *ChatEval: Towards Better LLM-based Evaluators
  through Multi-Agent Debate*, https://arxiv.org/abs/2308.07201, 2023.
- **Prong:** cross-cutting.
- **Why skip:** ChatEval runs 3+ LLM calls per evaluation (verdict collection
  from multiple agent perspectives + aggregation). The paper shows the
  approach improves reliability, but the call budget (3+ × ~200 ms each =
  600+ ms) plus coordination overhead exceeds the online evaluator's latency
  budget. The repo's improvement-plan explicitly budgets a single judge call
  per dimension with fallback to baseline if the judge times out.
- **Cost:** too-heavy for online (3+ calls per dimension; latency
  unpredictable on 0.5B/1.5B).
- **Closes:** none at online cost.

---

## Idea 8 — Prometheus 2 / Prometheus-Vision evaluator models (Kim 2024 / Lee
2024) · **skip**

- **Source:** Kim et al., *Prometheus 2: An Open Source Language Model
  Specialized in Evaluating Other Language Models*,
  https://arxiv.org/abs/2405.01535, EMNLP 2024; Lee et al.,
  *Prometheus-Vision*, https://arxiv.org/abs/2401.06591, 2024.
- **Prong:** cross-cutting.
- **Why skip:** Prometheus 2 is a 7B parameter model fine-tuned for evaluation.
  The paper explicitly compares against smaller models and finds 7B necessary
  for strong human/GPT-4 correlation. Prometheus-Vision is multimodal and even
  larger. Both violate the improvement-plan non-goal ("Judges larger than
  1.5B"). The rubric-based evaluation *method* is already captured by Ideas 1,
  2, and 4; the model itself is out of scope.
- **Cost:** too-heavy (7B+, not deployable on the product's shared vLLM).
- **Closes:** none (would close wXze's "Prong 1 does not use an LLM" at
  higher quality, but the cap prevents it).

---

## Closing table

| # | Idea | Prong / surface | Verdict | PoC-sized? |
|---|------|-----------------|---------|-----------|
| 1 | G-Eval single-score readability rubric | Prong 2 | adapt | Yes — 1 call, ≤1.5B |
| 2 | Multi-aspect readability (4 sub-scores + overall) | Prong 2 | adapt | Yes — 1 call, ≤1.5B |
| 3 | FLASK skill-level decomposition for comprehension / organization | Prong 2 | adapt | Yes — 1 call, ≤1.5B |
| 4 | RAGAS RubricsScore / DeepEval G-Eval prompt scaffolding | Prong 2 | adapt | Yes — 1 call, steal wording only |
| 5 | FairEval calibration (position-bias swap + divergence check) | All judge surfaces | adapt | Yes — 2 calls for benchmarking only |
| 6 | SemScore STS fallback | — | skip | Reference-based, not referenceless |
| 7 | ChatEval multi-agent debate | All prongs | skip | 3+ calls, too slow for online |
| 8 | Prometheus 2 / Prometheus-Vision models | All prongs | skip | 7B+, violates cap |

**Recommendation.** Ideas 1 + 2 are the highest-leverage pair. Idea 1 gives a
single-score drop-in replacement for Flesch with the same JSON pattern already
verified for `[JUDGE]`. Idea 2 upgrades that to the four sub-dimensions D7.5
asks for, improves parse robustness (missing keys are survivable), and produces
richer metadata for the UI evidence view. Implement Idea 1 first for a quick
win, then Idea 2 as the polished version. Ideas 3 and 4 are prompt-engineering
alternatives to compare during benchmarking. Idea 5 is deferred to the
benchmarking script (offline calibration), not the online path.

---

## Protocol Steward filter

| # | Verdict | D7.5 / test |
|---|---------|-------------|
| 1 G-Eval rubric | **IN PROTOCOL** | Prong 2 evaluates fluency. Test: `LLMFluidityDimension` emits 0-1 score + rationale JSON. |
| 2 Multi-aspect readability | **IN PROTOCOL** | Same, with sub-dimensions. Test: metadata carries coherence/audience/flow/vocabulary scores. |
| 3 FLASK skill rubric | **IN PROTOCOL** | Same, validated rubric wording. Test: rubric scores map to 0-1 and correlate with Flesch on a small benchmark. |
| 4 RAGAS/DeepEval scaffold | **IN PROTOCOL** | Prompt borrowing is allowed; no framework dependency. Test: prompt produces parseable JSON on 0.5B. |
| 5 FairEval calibration | **IN PROTOCOL** | Robustness testing per YE7H. Test: swap-order comparison script exists in `scripts/`. |
| 6 SemScore | **SKIP confirmed** | Reference-based, wrong frame for referenceless online eval. |
| 7 ChatEval | **SKIP confirmed** | Multi-agent debate exceeds online latency budget. |
| 8 Prometheus 2 | **SKIP confirmed** | 7B+ violates ≤1.5B cap. |

**Honesty:** None of the ADAPT items re-opens nine-language claims, LLM-as-judge
naming, or 0.5-as-quality overclaims. Idea 2's sub-dimensions are English-first;
multilingual follows the same rollout pattern as the existing `[JUDGE]` task
(English on 0.5B, non-English on 1.5B after validation).

---

## Prompt-scaffold comparison (for the Implementer)

The repo's `_JUDGE_SYSTEM_PROMPT` uses a strict JSON few-shot with exactly two
exemplars and `temperature=0`. The `[READABILITY]` prompt should follow the same
shape. Three scaffold options were compared:

1. **Single-score** (Idea 1): simplest, one key to parse, but fragile — a
   dropped score or malformed rationale invalidates the whole response.
2. **Multi-aspect** (Idea 2): four sub-scores + overall + rationale. If the
   model drops one sub-score, the others are still parseable and the overall
   can be computed from the partial set. This matches the repo's existing
   `JudgeParseError` recovery (partial answers collapse to 0 for the missing
   field, not the whole score).
3. **Rubric 1-5** (Idea 4): human-readable score descriptions, but requires
   mapping 1-5 → 0-1 and the 0.5B model may not reliably distinguish adjacent
   levels. The Few-shot JSON pattern with explicit numeric keys is safer on
   small models.

**Verdict for the 0.5B judge:** Start with Scaffold 2 (multi-aspect) because it
survives partial output best. If the 0.5B fails to emit four scores reliably,
fall back to Scaffold 1 (single-score) on the 0.5B, or route to the 1.5B for
Scaffold 2.
